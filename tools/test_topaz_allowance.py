import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quiver_cannon import atomic
from topaz_allowance import Allowance, charge, regular_batches
from topaz_character_cutouts import digest
from topaz_scenes import read


def fixture(root):
    output=root/'output';batch=root/'batch'
    atomic(batch/'manifest.json',{})
    sources={19:'costumes/LFLF_0019_AKOS_0094_frame_0.png',
             21:'costumes/LFLF_0021_AKOS_0200_frame_0.png'}
    atomic(output/'plan.json',dict(source_batch=str(batch),
        source_manifest_sha256=digest(batch/'manifest.json'),scenes=[
        dict(id=f'room-{r:04}',room=r,sources=[dict(source=s,operation='upscale-matting')])
        for r,s in sources.items()]))
    atomic(output/'batches/plan.json',dict(scene_plan_sha256=digest(output/'plan.json'),batches=[
        dict(id=f'room-{r:04}-b001',scene=f'room-{r:04}',room=r,name='test',phase='process',
             sources=[s],planning_minimum_credits=2) for r,s in sources.items()]))
    return output,sources


class AllowanceTests(unittest.TestCase):
    def test_scene_queue_excludes_external_results_and_native_effects(self):
        effect='costumes/LFLF_0020_AKOS_0192_frame_0.png'
        plan=dict(scenes=[dict(sources=[dict(source='ordinary',operation='upscale-matting'),
            dict(source='cached',operation='existing'),dict(source=effect,operation='upscale-matting')])])
        units=[dict(phase='process',sources=['ordinary','cached',effect])]
        self.assertEqual(regular_batches(plan,units)[0]['sources'],['ordinary'])

    def test_shared_source_once_baseline_and_restart_do_not_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            output,sources=fixture(Path(temp));s=sources[19]
            atomic(output/'room-0019/jobs.json',{s:dict(state='upscaled',history=[dict(estimate=dict(credits=1))])})
            allowance=Allowance(output,'run-1').create(3)
            original=allowance.path.read_bytes()
            scope=allowance.data['membership']['sources']
            self.assertEqual(sum(rows.count(s) for rows in scope.values()),1)
            atomic(output/'room-0019/jobs.json',{s:dict(state='validated',history=[dict(estimate=dict(credits=2))])})
            self.assertEqual(allowance.remaining(),2)
            resumed=Allowance(output,'run-1').create(3).validate()
            self.assertEqual(resumed.remaining(),2)
            self.assertEqual(original,resumed.path.read_bytes())
            with self.assertRaises(ValueError):resumed.create(3002)
            self.assertEqual(original,resumed.path.read_bytes())

    def test_unknown_charge_reserved_and_changed_scope_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            output,sources=fixture(Path(temp))
            allowance=Allowance(output,'run').create(3)
            atomic(output/'room-0019/jobs.json',{sources[19]:dict(state='unknown',estimate=dict(credits=1),
                history=[dict(estimate=dict(credits=1))])})
            self.assertEqual(allowance.remaining(),1)
            plan=read(output/'plan.json');plan['scenes'].reverse();atomic(output/'plan.json',plan)
            with self.assertRaises(ValueError):allowance.validate()

    def test_invalid_authorization_never_created(self):
        with tempfile.TemporaryDirectory() as temp:
            output,_=fixture(Path(temp))
            for value in (0,-1,True,1.5,float('nan')):
                with self.assertRaises(ValueError):Allowance(output,'bad').create(value)
            for name in ('../escape','','a/b'):
                with self.assertRaises(ValueError):Allowance(output,name)
            for value in (float('nan'),float('inf'),-1,True):
                with self.assertRaises(ValueError):charge(dict(history=[dict(estimate=dict(credits=value))]))

    def test_new_room_reservations_preserve_old_budgets_and_share_cap(self):
        from topaz_parallel_scenes import execute
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output,sources=fixture(root)
            old=output/'batches/room-0019-production/budget.json'
            atomic(old,dict(ceiling=1,initial_cost=0,sources=[sources[19]]))
            old_bytes=old.read_bytes()
            allowance=Allowance(output,'run').create(3)
            calls=[]
            def fake_run(base,api,remaining,**kwargs):
                calls.append((base.name,remaining))
                source=kwargs['sources'][0]
                if remaining>=2:
                    atomic(base/'jobs.json',{source:dict(state='validated',history=[dict(estimate=dict(credits=2))])})
                else:atomic(base/'jobs.json',{})
                atomic(base/'progress.json',dict(state='credit_cap' if remaining<2 else 'awaiting_review'))
            with patch('topaz_parallel_scenes.API') as api, \
                 patch('topaz_parallel_scenes.prepare_scene'), \
                 patch('topaz_parallel_scenes.run',side_effect=fake_run), \
                 patch('topaz_parallel_scenes.materialize'), \
                 patch('topaz_parallel_scenes.install',return_value={'new_or_changed':0}), \
                 patch('topaz_parallel_scenes.report'),patch('topaz_parallel_scenes.subprocess.run'):
                api.return_value.balance.return_value=10000
                execute([19,21],output,root/'local',allowance_id='run')
                self.assertCountEqual(calls,[('room-0019',2),('room-0021',1)])
                self.assertEqual(allowance.remaining(),1)
                saved=(allowance.folder/'parallel-0019-0021/budget.json').read_bytes()
                calls.clear()
                execute([19,21],output,root/'local',allowance_id='run')
                self.assertEqual(calls,[('room-0021',1)])
                self.assertEqual(saved,(allowance.folder/'parallel-0019-0021/budget.json').read_bytes())
                self.assertEqual(old_bytes,old.read_bytes())

    def test_guybrush_uses_new_allowance_without_rewriting_old_budget(self):
        from topaz_guybrush import execute
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output,sources=fixture(root)
            allowance=Allowance(output,'run').create(3)
            folder=output/'batches/guybrush-all'
            membership=dict(owners={sources[19]:'room-0019'})
            atomic(folder/'plan.json',membership)
            atomic(folder/'budget.json',dict(ceiling=1,initial_cost=0,
                membership_sha256=digest(folder/'plan.json')))
            before=(folder/'budget.json').read_bytes()
            def fake_run(base,api,remaining,**kwargs):
                self.assertEqual(remaining,3)
                self.assertEqual(kwargs['concurrency'],16)
                atomic(base/'jobs.json',{sources[19]:dict(state='validated',history=[dict(estimate=dict(credits=2))])})
                atomic(base/'progress.json',dict(state='awaiting_review'))
            with patch('topaz_guybrush.prepare',return_value=membership),patch('topaz_guybrush.prepare_scene'), \
                 patch('topaz_guybrush.API'),patch('topaz_guybrush.run',side_effect=fake_run), \
                 patch('topaz_guybrush.materialize'),patch('topaz_guybrush.status',return_value={'states':{}}), \
                 patch('topaz_guybrush.install',return_value={'new_or_changed':1}):
                self.assertEqual(execute(0,output,root/'local',allowance_id='run'),'production_checkpoint')
            self.assertEqual(before,(folder/'budget.json').read_bytes())
            self.assertEqual(allowance.remaining(),1)

    def test_handoff_only_after_guybrush_checkpoint(self):
        from topaz_resume import execute
        for state in ('production_checkpoint','credit_cap','awaiting_provider','stopped'):
            with self.subTest(state=state),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);output,_=fixture(root);calls=[]
                def first(*args,**kwargs):calls.append('guybrush');return state
                def second(*args,**kwargs):calls.append('rooms');return 'credit_cap'
                with patch('topaz_resume.OUTPUT',output),patch('topaz_resume.ROOT',root), \
                     patch('topaz_resume.guybrush',side_effect=first), \
                     patch('topaz_resume.continue_scenes',side_effect=second), \
                     patch('topaz_resume.install',return_value={'new_or_changed':0}), \
                     patch('topaz_resume.package',return_value={}),patch('asset_pack.verify',return_value={}):
                    result=execute('run',3)
                self.assertEqual(calls,['guybrush','rooms'] if state=='production_checkpoint' else ['guybrush'])
                self.assertEqual(result['phase'],'rooms' if state=='production_checkpoint' else 'guybrush')


if __name__=='__main__':unittest.main()
