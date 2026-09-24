import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quiver_cannon import atomic
from topaz_scenes import read
from topaz_continue_scenes import select_rooms, continue_scenes


class ContinuationTests(unittest.TestCase):
    def test_frozen_order_skips_rooms_without_regular_sources(self):
        plan={'scenes':[{'room':n} for n in (9,19,20,21,1)]}
        units=[{'room':19,'phase':'process','sources':['a']},
               {'room':20,'phase':'pilot','sources':['b']},
               {'room':21,'phase':'process','sources':['c']},
               {'room':1,'phase':'process','sources':['d']}]
        self.assertEqual(select_rooms(plan,units,19)[0],[19,21,1])

    def test_automatic_pairs_hold_slow_job_and_cannot_spend_later_topup(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'output'
            rooms=[19,20,21,22,23,24,25]
            atomic(out/'plan.json',{'scenes':[{'room':r} for r in rooms]})
            atomic(out/'batches/plan.json',dict(scene_plan_sha256='frozen',batches=[
                dict(room=r,phase='process',sources=[str(r)]) for r in rooms]))
            atomic(out/'room-0020/jobs.json',{'20':dict(state='validated',history=[])})
            calls=[]
            def fake_execute(pair,max_credits):
                calls.append((pair,max_credits))
                charge=3 if len(calls)==1 else 2
                for r in pair:
                    slow=r==19
                    atomic(out/f'room-{r:04}/jobs.json',{str(r):dict(state='submitted' if slow else 'validated',
                        stage='matting',process_id='saved',history=[dict(estimate=dict(credits=charge))])})
                    atomic(out/'batches'/f'room-{r:04}-production/progress.json',
                        dict(state='awaiting_provider' if slow else 'scene_production_checkpoint'))
            with patch('topaz_continue_scenes.OUTPUT',out),patch('topaz_continue_scenes.API') as api, \
                 patch('topaz_continue_scenes.execute',side_effect=fake_execute):
                api.return_value.balance.return_value=10
                continue_scenes(19)
                self.assertEqual(calls,[([19,21],10),([22,23],4)])
                folder=out/'batches/continuation-from-0019'
                self.assertEqual(read(folder/'progress.json')['state'],'credit_cap')
                frozen=(folder/'budget.json').read_bytes()
                api.return_value.balance.return_value=1000
                continue_scenes(19)
                self.assertEqual(len(calls),2)
                self.assertEqual((folder/'budget.json').read_bytes(),frozen)
                self.assertEqual(read(out/'room-0019/jobs.json')['19']['process_id'],'saved')

if __name__=='__main__':unittest.main()
