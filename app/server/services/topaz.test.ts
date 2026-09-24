import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { TopazOutputs } from './topaz.js';

test('validated character cutouts appear before installation; audited failures are hidden', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mi3-cutout-'));
  try {
    const batch = path.join(root, 'output/topaz-batch');
    const cutouts = path.join(root, 'output/topaz-character-objectmatting');
    const source = 'costumes/LFLF_0009_AKOS_0025_frame_5.png';
    await fs.mkdir(batch, { recursive: true });
    await fs.mkdir(path.join(cutouts, '4x/costumes'), { recursive: true });
    await fs.writeFile(path.join(batch, 'manifest.json'), JSON.stringify({ records: [{ source, size: [88, 161] }] }));
    const job = { state: 'validated', validation: { passed: true, sha256: 'a'.repeat(64) } };
    await fs.writeFile(path.join(cutouts, 'jobs.json'), JSON.stringify({ [source]: job, '../private.png': job }));
    const service = new TopazOutputs(root);
    assert.equal((await service.snapshot()).ready, 0);
    await fs.writeFile(path.join(cutouts, '4x', source), 'provider bytes');
    await fs.writeFile(path.join(cutouts, 'progress.json'), JSON.stringify({ state: 'running', total: 316,
      validated: 1, submitted_credits: 1, credit_cap: 360, updated_at: 2, pid: 9, secret: 'private' }));
    const ready = await service.snapshot();
    assert.equal(ready.ready, 1);
    assert.equal(ready.outputs[0].scale, 4);
    assert.equal(ready.outputs[0].width, 352);
    assert.match(ready.outputs[0].cutoutUrl!, /topaz-character-objectmatting\/4x\//);
    assert.equal(ready.outputs[0].previousUrl, undefined);
    assert.equal(ready.cutouts?.total, 330);
    assert(!JSON.stringify(ready).includes('private'));
    await fs.writeFile(path.join(cutouts, 'audits.json'), JSON.stringify({ [source]: { state: 'rejected', validation: { passed: false } } }));
    assert.equal((await service.snapshot()).ready, 0);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('outputs reflect finished files, numeric frames, filtering and live additions without exposing private metadata', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mi3-topaz-'));
  try {
    const service = new TopazOutputs(root);
    assert.equal((await service.snapshot()).ready, 0);
    const batch = path.join(root, 'output/topaz-batch');
    await fs.mkdir(path.join(batch, '6x/costumes'), { recursive: true });
    const records = [2, 10, 1].map(frame => ({ source: `costumes/LFLF_0016_AKOS_0094_frame_${frame}.png`, size: [82, 273] }));
    await fs.writeFile(path.join(batch, 'manifest.json'), JSON.stringify({ records }));
    await fs.writeFile(path.join(batch, 'progress.json'), JSON.stringify({ state: 'processing', pid: 10, secret: 'private', updated_at: 1, run_completed: 2, run_estimated_credits: 3, run_credit_cap: 192 }));
    for (const record of records.slice(0, 2)) await fs.writeFile(path.join(batch, '6x', record.source), 'finished');
    await fs.writeFile(path.join(batch, '6x/costumes/unknown.png'), 'unrelated');
    await fs.writeFile(path.join(batch, '6x', records[2].source + '.tmp'), 'incomplete');
    const first = await service.snapshot();
    assert.equal(first.ready, 2);
    assert.deepEqual(first.outputs.map(o => o.source), records.slice(0, 2).map(r => r.source));
    assert.equal(first.outputs[0].width, 492);
    assert.equal(first.outputs[0].height, 1638);
    assert.equal(first.outputs[0].room, 16);
    assert.deepEqual(first.rooms, [{ room: 16, ready: 2, prepared: 3 }]);
    assert(!JSON.stringify(first).includes('private'));
    assert(!JSON.stringify(first.progress).includes('pid'));
    await fs.rename(path.join(batch, '6x', records[2].source + '.tmp'), path.join(batch, '6x', records[2].source));
    const next = await service.snapshot('', 'frame_1');
    assert.equal(next.ready, 3);
    assert.equal(next.matched, 2);
    assert.equal(next.outputs[0].source, records[2].source);
    assert.equal((await service.snapshot('objects')).matched, 0);
    assert.equal((await service.snapshot('', '', 1, 9)).matched, 0);
    assert.equal((await service.snapshot('', '', 1, 16)).matched, 3);
    assert.equal((await service.snapshot('', '', NaN)).page, 1);
    await fs.mkdir(path.join(batch, '6x-crisp/costumes'), { recursive: true });
    await fs.writeFile(path.join(batch, '6x-crisp', records[0].source), 'refined');
    const refined = await service.snapshot();
    assert.equal(refined.outputs.find(o => o.source === records[0].source)?.crispUrl, `/files/output/topaz-batch/6x-crisp/${records[0].source}`);
    assert.equal(refined.outputs.find(o => o.source === records[1].source)?.crispUrl, undefined);
    await fs.mkdir(path.join(batch, '4x/costumes'), { recursive: true });
    await fs.writeFile(path.join(batch, '4x', records[0].source), 'direct 4x');
    const mixed = await service.snapshot();
    const four = mixed.outputs.find(o => o.source === records[0].source && o.scale === 4)!;
    assert.equal(four.width, 328); assert.equal(four.height, 1092);
    assert.equal(four.outputUrl, `/files/output/topaz-batch/4x/${records[0].source}`);
    assert.equal(four.crispUrl, undefined);
    assert.equal(mixed.outputs.filter(o => o.source === records[0].source).length, 2);
    assert.deepEqual(mixed.rooms, [{ room: 16, ready: 3, prepared: 3 }]);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('scene queue exposes safe progress and finished scene files without altering room ownership', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mi3-scene-'));
  try {
    const batch = path.join(root, 'output/topaz-batch');
    const scenes = path.join(root, 'output/topaz-scenes');
    const source = 'costumes/LFLF_0001_AKOS_0002_frame_4.png';
    await fs.mkdir(batch, { recursive: true });
    await fs.mkdir(path.join(scenes, 'room-0009/4x/costumes'), { recursive: true });
    await fs.writeFile(path.join(batch, 'manifest.json'), JSON.stringify({ records: [{ source, size: [12, 15] }] }));
    await fs.writeFile(path.join(scenes, 'plan.json'), JSON.stringify({ total_sources: 1, previous_crisp_sources: [source], secret: 'private', scenes: [
      { id: 'room-0009', room: 9, name: 'cannon', minimum_new_credits: 1, sources: [{ source, operation: 'upscale-matting' }] },
    ] }));
    await fs.writeFile(path.join(scenes, 'progress.json'), JSON.stringify({ state: 'running', current_scene: 'room-0009',
      credit_cap: 20, submitted_credits: 4, updated_at: 2, pid: 22, secret: 'private' }));
    await fs.writeFile(path.join(scenes, 'room-0009/progress.json'), JSON.stringify({ state: 'running', submitted_credits: 2 }));
    await fs.writeFile(path.join(scenes, 'room-0009/jobs.json'), JSON.stringify({ [source]: { state: 'validated', validation: { passed: true, sha256: 'a'.repeat(64) } } }));
    await fs.writeFile(path.join(scenes, 'room-0009/4x', source), 'provider pixels');
    await fs.mkdir(path.join(batch, '6x/costumes'), { recursive: true });
    await fs.mkdir(path.join(batch, '6x-crisp/costumes'), { recursive: true });
    await fs.writeFile(path.join(batch, '6x', source), 'old master');
    await fs.writeFile(path.join(batch, '6x-crisp', source), 'old crisp');
    const result = await new TopazOutputs(root).snapshot();
    assert.equal(result.outputs.length, 1);
    assert.equal(result.outputs[0].scale, 4);
    assert.equal(result.outputs[0].previousScale, 6);
    assert.match(result.outputs[0].previousUrl!, /6x-crisp/);
    assert.deepEqual(result.sceneBatch?.previousCrisp, { total: 1, ready: 1 });
    assert.equal(result.outputs[0].room, 1);
    assert.match(result.outputs[0].cutoutUrl!, /topaz-scenes\/room-0009/);
    assert.equal(result.sceneBatch?.scenes[0].ready, 1);
    assert.equal(result.sceneBatch?.submitted, 6);
    assert.equal(result.progress?.run_estimated_credits, 6);
    assert(!JSON.stringify(result).includes('private'));
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('manual replacements become the current 4x preview while provider and 6x versions stay archived', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mi3-manual-'));
  try {
    const source = 'costumes/LFLF_0001_AKOS_0002_frame_22.png';
    const sha = 'b'.repeat(64);
    const batch = path.join(root, 'output/topaz-batch');
    const edit = path.join(root, 'output/asset-edits');
    await fs.mkdir(path.join(batch, '6x/costumes'), { recursive: true });
    await fs.mkdir(path.join(batch, '4x/costumes'), { recursive: true });
    await fs.mkdir(path.join(edit, 'versions', sha, 'costumes'), { recursive: true });
    await fs.writeFile(path.join(batch, 'manifest.json'), JSON.stringify({ records: [{ source, size: [83, 214] }] }));
    await fs.writeFile(path.join(batch, '6x', source), 'six');
    await fs.writeFile(path.join(batch, '4x', source), 'provider');
    await fs.writeFile(path.join(edit, 'manifest.json'), JSON.stringify({ overrides: { [source]: { sha256: sha } } }));
    await fs.writeFile(path.join(edit, 'versions', sha, source), 'manual');
    const result = await new TopazOutputs(root).snapshot('', source, 1, 1);
    assert.equal(result.outputs.length, 1);
    const output = result.outputs[0];
    assert.equal(output.processing, 'manual');
    assert.equal(output.scale, 4);
    assert.equal(output.width, 332);
    assert.equal(output.height, 856);
    assert.equal(output.outputUrl, `/files/output/asset-edits/versions/${sha}/${source}`);
    assert.equal(output.cutoutUrl, output.outputUrl);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});
