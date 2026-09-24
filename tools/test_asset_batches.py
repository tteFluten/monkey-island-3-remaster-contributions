import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from asset_batches import build_plan, execute, prepare, report
from quiver_cannon import atomic
from topaz_character_cutouts import digest


class BatchTests(unittest.TestCase):
    def fixture(self, root):
        source_batch = root/'original'; source_batch.mkdir()
        atomic(source_batch/'manifest.json', {'records': []})
        sources = [f'costumes/LFLF_0009_AKOS_0025_frame_{n}.png' for n in range(35)]
        entries = [dict(source=s, operation='existing', owner='topaz-character-objectmatting') for s in sources]
        entries += [dict(source='objects/0009_alias.png', operation='alias', parent=sources[0]),
                    dict(source='objects_layers/0009_alias.png', operation='derive-layer', parent='objects/0009_alias.png')]
        other = dict(source='objects/0010_prop.png', operation='upscale-matting')
        plan = dict(source_batch=str(source_batch), source_manifest_sha256=digest(source_batch/'manifest.json'),
                    total_sources=len(entries)+1, scenes=[dict(id='room-0009', room=9, name='cannon', sources=entries),
                    dict(id='room-0010', room=10, name='next', sources=[other])])
        out=root/'scenes'; atomic(out/'plan.json', plan); prepare(out)
        return out, plan, sources

    def test_every_source_once_bounded_and_dependency_linked(self):
        with tempfile.TemporaryDirectory() as temp:
            _, plan, sources = self.fixture(Path(temp))
            result = build_plan(plan)
            batches = result['batches']
            flattened = [s for b in batches for s in b['sources']]
            self.assertEqual(len(set(flattened)), plan['total_sources'])
            self.assertEqual(len(flattened), plan['total_sources'])
            self.assertTrue(all(0 < len(b['sources']) <= 32 for b in batches))
            first = batches[0]
            self.assertEqual(first['sources'], sources[:32])
            alias = next(b for b in batches if 'objects/0009_alias.png' in b['sources'])
            self.assertEqual(alias['dependencies'], [first['id']])

    def test_only_selected_sources_and_frozen_budget_on_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); out, plan, sources=self.fixture(root)
            batch=read_json(out/'batches/plan.json')['batches'][0]
            api=type('API', (), {'balance': lambda self: 100})()
            calls=[]; base=root/'topaz-character-objectmatting'
            def worker(directory, api, credits, **kwargs):
                calls.append((directory, credits, kwargs['sources']))
                jobs=read_json(directory/'jobs.json') if (directory/'jobs.json').exists() else {}
                if sources[0] not in jobs:
                    jobs[sources[0]]=dict(state='failed', history=[dict(estimate=dict(credits=2))])
                    atomic(directory/'jobs.json',jobs)
            with patch('asset_batches.run',side_effect=worker), patch('asset_batches.materialize') as materialize, patch('asset_batches.report',return_value={'batches':[{**batch,'counts':{'needs_provider_review':1,'pending':31}}]}):
                result=execute(out,batch['id'],api,5,root/'local')
                self.assertEqual(len(calls),1)
                self.assertEqual(calls[0][2],sources[:32])
                self.assertEqual(result['credits'],2)
                jobs=read_json(base/'jobs.json')
                jobs[sources[34]]=dict(history=[dict(estimate=dict(credits=99))])
                atomic(base/'jobs.json', jobs)
                execute(out,batch['id'],api,5,root/'local')
                self.assertEqual(calls[-1][1],3)  # Other batches do not consume this batch's budget.
                with self.assertRaises(ValueError): execute(out,batch['id'],api,10,root/'local')
                self.assertEqual(len(calls),2)
                self.assertTrue(result['stopped_at_checkpoint'])
                self.assertEqual([s['room'] for s in materialize.call_args.args[1]['scenes']],[9,10])
                self.assertEqual(materialize.call_args.args[1]['scenes'][1]['sources'],[])

    def test_completed_requires_review_and_installed_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); out, plan, sources=self.fixture(root)
            master=root/'result.png'; master.write_bytes(b'validated-result'); sha=digest(master)
            files={sources[0]:dict(master=master,sha256=sha,reviewed=False)}
            with patch('asset_batches.completed',return_value=files):
                self.assertEqual(report(out,root/'local')['batches'][0]['counts']['needs_review'],1)
                atomic(out/'reviews'/(sources[0]+'.json'),dict(sha256=sha))
                self.assertEqual(report(out,root/'local')['batches'][0]['counts']['ready_to_install'],1)
                for pack in ('topaz-cannon','topaz-crisp'):
                    target=root/'local/hd'/pack/sources[0].replace('_frame_','_aframe_')
                    target.parent.mkdir(parents=True); target.write_bytes(master.read_bytes())
                self.assertEqual(report(out,root/'local')['batches'][0]['counts']['installed'],1)
                target.write_bytes(b'stale')
                self.assertNotIn('installed',report(out,root/'local')['batches'][0]['counts'])
                master.write_bytes(b'changed-after-validation')
                self.assertEqual(report(out,root/'local')['batches'][0]['counts']['changed_output'],1)

    def test_draft_install_does_not_claim_review_or_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); out,plan,sources=self.fixture(root)
            master=root/'draft.png'; master.write_bytes(b'draft'); sha=digest(master)
            for pack in ('topaz-cannon','topaz-crisp'):
                target=root/'local/hd'/pack/sources[0].replace('_frame_','_aframe_')
                target.parent.mkdir(parents=True); target.write_bytes(master.read_bytes())
            atomic(root/'local/draft-install/receipt.json',dict(assets={sources[0]:dict(sha256=sha)}))
            with patch('asset_batches.completed',return_value={}):
                batch=report(out,root/'local')['batches'][0]
                self.assertEqual(batch['counts']['installed_draft'],1)
                self.assertFalse(batch['complete'])

    def test_stable_ids_reject_changed_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            out,plan,_=self.fixture(Path(temp)); plan['scenes'][0]['name']='changed'
            atomic(out/'plan.json',plan)
            with self.assertRaises(ValueError): prepare(out)


def read_json(path):
    return json.loads(path.read_text())


if __name__ == '__main__': unittest.main()
