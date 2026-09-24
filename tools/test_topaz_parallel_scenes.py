import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import threading
import json
from topaz_parallel_scenes import allocate, validate_membership, execute
from quiver_cannon import atomic

class ParallelBudgetTests(unittest.TestCase):
    def test_two_workers_cannot_reserve_the_same_balance(self):
        limits=allocate(150,[(14,97),(15,760)])
        self.assertEqual(limits,{14:97,15:53})
        self.assertEqual(sum(limits.values()),150)

    def test_room_ceiling_cannot_expand_with_a_large_balance(self):
        self.assertEqual(allocate(10000,[(14,97),(15,760)]),{14:97,15:760})

    def test_empty_balance_and_invalid_reservations(self):
        self.assertEqual(allocate(0,[(14,97),(15,760)]),{14:0,15:0})
        for balance,requests in [(10,[(14,1),(14,2)]),(-1,[]),(float('nan'),[]),(10,[(14,-1)])]:
            with self.assertRaises(ValueError):allocate(balance,requests)

    def test_duplicate_sources_rejected_across_rooms_and_groups(self):
        with self.assertRaises(ValueError):
            validate_membership({14:[{'sources':['a']}],15:[{'sources':['a']}]})
        with self.assertRaises(ValueError):
            validate_membership({14:[{'sources':['a']},{'sources':['a']}]})
        validate_membership({14:[{'sources':['a']}],15:[{'sources':['b']}]})

    def test_both_rooms_run_together_with_frozen_reservations_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); output=root/'output'; batch=root/'batch'; local=root/'local'
            atomic(batch/'manifest.json',{})
            atomic(output/'plan.json',dict(source_batch=str(batch),source_manifest_sha256='hash',
                scenes=[dict(id=f'room-{r:04}',room=r) for r in (14,15)]))
            atomic(output/'batches/plan.json',dict(scene_plan_sha256='hash',batches=[
                dict(id=f'room-{r:04}-b001',scene=f'room-{r:04}',room=r,name='test',phase='process',
                     sources=[f'source-{r}'] + (['uncertain-14'] if r == 14 else []),planning_minimum_credits=8) for r in (14,15)]))
            atomic(output/'batches/room-0014-production/budget.json',
                dict(ceiling=10,initial_cost=0,sources=['source-14','uncertain-14']))
            atomic(output/'room-0014/jobs.json',{'source-14':dict(state='upscaled',
                history=[dict(estimate=dict(credits=6))]),
                'uncertain-14':dict(state='unknown',estimate=dict(credits=1),history=[])})
            barrier=threading.Barrier(2); calls=[]
            def fake_run(base,api,remaining,**kwargs):
                calls.append((base.name,remaining,kwargs['concurrency']))
                barrier.wait(timeout=5)  # Fails if workers run serially.
                jobs=json.loads((base/'jobs.json').read_text()) if (base/'jobs.json').exists() else {}
                source=kwargs['sources'][0]
                job=jobs.setdefault(source,dict(history=[]))
                job['history'].append(dict(estimate=dict(credits=remaining)))
                job['state']='validated'
                atomic(base/'jobs.json',jobs)
                atomic(base/'progress.json',dict(state='awaiting_review'))
            with patch('topaz_parallel_scenes.API') as api, \
                 patch('topaz_parallel_scenes.digest',return_value='hash'), \
                 patch('topaz_parallel_scenes.prepare_scene'), \
                 patch('topaz_parallel_scenes.run',side_effect=fake_run), \
                 patch('topaz_parallel_scenes.materialize'), \
                 patch('topaz_parallel_scenes.report'), \
                 patch('topaz_parallel_scenes.install',return_value={'new_or_changed':0}), \
                 patch('topaz_parallel_scenes.subprocess.run'):
                api.return_value.balance.return_value=100
                execute([14,15],output,local,max_credits=10)
                self.assertCountEqual(calls,[('room-0014',3,16),('room-0015',7,16)])
                progress=json.loads((output/'batches/room-0014-production/progress.json').read_text())
                self.assertEqual(progress['recovery_sources'],['uncertain-14'])
                self.assertEqual(progress['state'],'scene_production_checkpoint')
                saved=(output/'batches/parallel-0014-0015/budget.json').read_bytes()
                api.return_value.balance.return_value=10000
                execute([14,15],output,local)
                self.assertEqual(len(calls),2)
                self.assertEqual(saved,(output/'batches/parallel-0014-0015/budget.json').read_bytes())

if __name__=='__main__':unittest.main()
