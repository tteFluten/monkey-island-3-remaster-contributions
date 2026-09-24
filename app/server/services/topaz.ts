import fs from 'node:fs/promises';
import path from 'node:path';
import type { TopazSnapshot, TopazOutput } from '../../shared/topaz.js';

interface RecordEntry { source: string; size: [number, number] }
interface ScenePlan { total_sources: number; previous_crisp_sources?: string[]; scenes: { id: string; room: number; name: string; minimum_new_credits: number; sources: { source: string; operation: string }[] }[] }
const folders = ['costumes', 'objects', 'objects_layers'];
const sourcePattern = /^(costumes|objects|objects_layers)\/[a-zA-Z0-9_-]+\.png$/;
function sourceRoom(source: string) { return Number(source.match(/\/(?:LFLF_)?(\d+)_/)?.[1] ?? 0); }

export class TopazOutputs {
  private manifestStamp = -1;
  private records = new Map<string, RecordEntry>();
  private root: string;
  private sceneStamp = -1;
  private scenePlan: ScenePlan | null = null;
  constructor(projectRoot: string) { this.root = path.join(projectRoot, 'output/topaz-batch'); }

  async snapshot(group = '', query = '', requestedPage = 1, room = 0): Promise<TopazSnapshot> {
    const manifest = path.join(this.root, 'manifest.json');
    const stat = await fs.stat(manifest).catch((error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') return null;
      throw error;
    });
    if (stat && stat.mtimeMs !== this.manifestStamp) {
      const data = JSON.parse(await fs.readFile(manifest, 'utf8')) as { records: RecordEntry[] };
      this.records = new Map(data.records.filter(r => sourcePattern.test(r.source)).map(r => [r.source, r]));
      this.manifestStamp = stat.mtimeMs;
    } else if (!stat) { this.records.clear(); this.manifestStamp = -1; }
    const files = await Promise.all(([4, 6] as const).flatMap(scale => folders.map(async folder => {
      const entries = await fs.readdir(path.join(this.root, `${scale}x`, folder), { withFileTypes: true }).catch((error: NodeJS.ErrnoException) => {
        if (error.code === 'ENOENT') return [];
        throw error;
      });
      return entries.filter(e => e.isFile() && e.name.endsWith('.png')).map(e => ({ source: `${folder}/${e.name}`, scale }));
    })));
    const cutouts = new Map<string, { url: string; previousUrl?: string; previousScale?: 4 | 6; processing: 'matting' | 'opaque' | 'derived' | 'manual' }>();
    let characterProgress: Record<string, number | string> | null = null;
    const sceneRoot = path.join(path.dirname(this.root), 'topaz-scenes');
    const sceneStat = await fs.stat(path.join(sceneRoot, 'plan.json')).catch(() => null);
    if (sceneStat && sceneStat.mtimeMs !== this.sceneStamp) {
      this.scenePlan = JSON.parse(await fs.readFile(path.join(sceneRoot, 'plan.json'), 'utf8'));
      this.sceneStamp = sceneStat.mtimeMs;
    } else if (!sceneStat) { this.scenePlan = null; this.sceneStamp = -1; }
    const sceneDirs = (await fs.readdir(sceneRoot, { withFileTypes: true }).catch(() => []))
      .filter(e => e.isDirectory() && /^(room-\d{4}|derived)$/.test(e.name)).map(e => `topaz-scenes/${e.name}`);
    for (const directory of ['topaz-cannon-objectmatting', 'topaz-character-objectmatting', 'topaz-difficulty-knife', ...sceneDirs]) {
      const base = path.join(path.dirname(this.root), directory);
      const jobs = await fs.readFile(path.join(base, 'jobs.json'), 'utf8').then(JSON.parse).catch((error: NodeJS.ErrnoException) => {
        if (error.code === 'ENOENT') return {}; throw error;
      });
      const audits = await fs.readFile(path.join(base, 'audits.json'), 'utf8').then(JSON.parse).catch((error: NodeJS.ErrnoException) => {
        if (error.code === 'ENOENT') return {}; throw error;
      });
      for (const [source, audit] of Object.entries(audits)) {
        if (Object.hasOwn(jobs, source)) jobs[source] = { ...jobs[source], ...(audit as object) };
      }
      for (const [source, value] of Object.entries(jobs)) {
        const job = value as { state: string; validation?: { passed: boolean; sha256: string; cleanup?: { type?: string } } };
        if (!sourcePattern.test(source) || !this.records.has(source) || !['validated', 'accepted'].includes(job.state)
            || !job.validation?.passed || !/^[a-f0-9]{64}$/.test(job.validation.sha256)) continue;
        if (!await fs.stat(path.join(base, '4x', source)).then(s => s.isFile()).catch(() => false)) continue;
        const previous = await fs.stat(path.join(base, 'previous/asset-tool', source)).then(s => s.isFile()).catch(() => false);
        const oldSix = await fs.stat(path.join(this.root, '6x', source)).then(s => s.isFile()).catch(() => false);
        const oldCrisp = await fs.stat(path.join(this.root, '6x-crisp', source)).then(s => s.isFile()).catch(() => false);
        cutouts.set(source, { url: `/files/output/${directory}/4x/${source}?v=${job.validation.sha256}`,
          processing: job.validation.cleanup?.type === 'opaque-artwork' ? 'opaque'
            : ['alias', 'derive-layer', 'empty'].includes(job.validation.cleanup?.type ?? '') ? 'derived' : 'matting',
          previousUrl: oldCrisp ? `/files/output/topaz-batch/6x-crisp/${source}`
            : previous ? `/files/output/${directory}/previous/asset-tool/${source}`
            : oldSix ? `/files/output/topaz-batch/6x/${source}` : undefined,
          previousScale: oldCrisp ? 6 : previous ? 4 : oldSix ? 6 : undefined });
      }
      if (directory === 'topaz-character-objectmatting') {
        characterProgress = await fs.readFile(path.join(base, 'progress.json'), 'utf8').then(JSON.parse).catch((error: NodeJS.ErrnoException) => {
          if (error.code === 'ENOENT') return null; throw error;
        });
      }
    }
    const edits = await fs.readFile(path.join(path.dirname(this.root), 'asset-edits/manifest.json'), 'utf8').then(JSON.parse).catch((error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') return {}; throw error;
    });
    for (const [source, value] of Object.entries(edits.overrides ?? {})) {
      const sha = (value as { sha256?: string }).sha256;
      if (!sourcePattern.test(source) || !this.records.has(source) || !sha || !/^[a-f0-9]{64}$/.test(sha)) continue;
      if (!await fs.stat(path.join(path.dirname(this.root), 'asset-edits/versions', sha, source)).then(s => s.isFile()).catch(() => false)) continue;
      const previous = cutouts.get(source);
      cutouts.set(source, { url: `/files/output/asset-edits/versions/${sha}/${source}`, processing: 'manual',
        previousUrl: previous?.url, previousScale: previous ? 4 : undefined });
    }
    const completedFiles = files.flat();
    for (const source of cutouts.keys()) {
      if (!completedFiles.some(f => f.source === source && f.scale === 4)) completedFiles.push({ source, scale: 4 });
    }
    const outputs: TopazOutput[] = [];
    const crispFiles = new Set((await fs.readdir(path.join(this.root, '6x-crisp/costumes'), { withFileTypes: true }).catch((error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') return [];
      throw error;
    })).filter(e => e.isFile() && e.name.endsWith('.png')).map(e => `costumes/${e.name}`));
    const groups = new Map<string, number>();
    const readySources = new Set<string>();
    const rooms = new Map<number, { room: number; ready: number; prepared: number }>();
    for (const source of this.records.keys()) {
      const number = sourceRoom(source);
      const entry = rooms.get(number) ?? { room: number, ready: 0, prepared: 0 };
      entry.prepared++;
      rooms.set(number, entry);
    }
    for (const { source, scale } of completedFiles) {
      if (scale === 6 && cutouts.has(source)) continue; // Replaced versions live only in the comparison selector.
      const record = this.records.get(source);
      if (!record) continue; // Ignore partial writes and outputs unrelated to the prepared batch.
      const groupId = source.startsWith('costumes/') ? source.split('_frame_')[0] : source.split('/')[0];
      const number = sourceRoom(source);
      if (!readySources.has(source)) rooms.get(number)!.ready++;
      readySources.add(source);
      if (!room || room === number) groups.set(groupId, (groups.get(groupId) ?? 0) + 1);
      outputs.push({ source, group: groupId, room: number, label: source.split('/')[1].replace('.png', ''),
        originalUrl: `/files/output/topaz-batch/cleaned/${source}`,
        outputUrl: scale === 4 && cutouts.has(source) ? cutouts.get(source)!.url : `/files/output/topaz-batch/${scale}x/${source}`, scale,
        cutoutUrl: scale === 4 ? cutouts.get(source)?.url : undefined,
        previousUrl: scale === 4 ? cutouts.get(source)?.previousUrl : undefined,
        processing: scale === 4 ? cutouts.get(source)?.processing : undefined,
        previousScale: scale === 4 ? cutouts.get(source)?.previousScale : undefined,
        crispUrl: scale === 6 && crispFiles.has(source) ? `/files/output/topaz-batch/6x-crisp/${source}` : undefined,
        width: record.size[0] * scale, height: record.size[1] * scale });
    }
    outputs.sort((a, b) => a.source.localeCompare(b.source, undefined, { numeric: true }));
    const filtered = outputs.filter(o => (!room || o.room === room) && (!group || o.group === group) && o.source.toLowerCase().includes(query.toLowerCase()));
    const pages = Math.max(1, Math.ceil(filtered.length / 48));
    const page = Math.min(pages, Math.max(1, Number.isFinite(requestedPage) ? Math.floor(requestedPage) : 1));
    let progress = await fs.readFile(path.join(this.root, 'progress.json'), 'utf8').then(text => {
      const p = JSON.parse(text);
      // Expose only display information, never local credentials, paths or process controls.
      return { state: p.state, current_source: p.current_source, updated_at: p.updated_at,
        run_completed: p.run_completed, run_estimated_credits: p.run_estimated_credits, run_credit_cap: p.run_credit_cap,
        downloads_pending: p.job_counts?.download_pending ?? 0 };
    }).catch((error: NodeJS.ErrnoException) => { if (error.code === 'ENOENT') return null; throw error; });
    if (characterProgress) progress = {
      state: String(characterProgress.state), current_source: undefined, updated_at: Number(characterProgress.updated_at),
      run_completed: Number(characterProgress.validated), run_estimated_credits: Number(characterProgress.submitted_credits),
      run_credit_cap: Number(characterProgress.credit_cap), downloads_pending: 0,
    };
    const queue = await fs.readFile(path.join(sceneRoot, 'progress.json'), 'utf8').then(JSON.parse).catch(() => null);
    let submitted = Number(queue?.submitted_credits ?? 0);
    let queueUpdated = Number(queue?.updated_at ?? 0);
    if (queue?.state === 'running' && /^(room-\d{4}|difficulty-knife|characters)$/.test(queue.current_scene)) {
      const activeRoot = queue.current_scene === 'characters' ? path.join(path.dirname(this.root), 'topaz-character-objectmatting')
        : queue.current_scene === 'difficulty-knife' ? path.join(path.dirname(this.root), 'topaz-difficulty-knife')
        : path.join(sceneRoot, queue.current_scene);
      const active = await fs.readFile(path.join(activeRoot, 'progress.json'), 'utf8').then(JSON.parse).catch(() => null);
      if (active?.state === 'running') {
        submitted += Number(active.submitted_credits ?? 0);
        queueUpdated = Number(active.updated_at ?? queueUpdated);
      }
    }
    if (queue && queue.state !== 'waiting_for_characters') progress = {
      state: String(queue.state), current_source: undefined, updated_at: queueUpdated, run_completed: cutouts.size,
      run_estimated_credits: submitted, run_credit_cap: Number(queue.credit_cap), downloads_pending: 0,
    };
    const sceneBatch = this.scenePlan ? {
      state: String(queue?.state ?? 'prepared'), current: typeof queue?.current_scene === 'string' ? queue.current_scene : null,
      creditCap: Number(queue?.credit_cap ?? 0), submitted,
      previousCrisp: { total: this.scenePlan.previous_crisp_sources?.length ?? 0,
        ready: this.scenePlan.previous_crisp_sources?.filter(s => cutouts.has(s)).length ?? 0 },
      scenes: this.scenePlan.scenes.map(scene => ({ id: scene.id, room: scene.room, name: scene.name,
        total: scene.sources.length, ready: scene.sources.filter(e => cutouts.has(e.source)).length,
        preserved: scene.sources.filter(e => e.operation === 'preserve').length,
        smallPilots: scene.sources.filter(e => e.operation === 'review-small').length,
        minimumCredits: scene.minimum_new_credits })),
    } : undefined;
    return { prepared: this.records.size, ready: outputs.length, matched: filtered.length, page, pages,
      groups: [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([id, count]) => ({ id, count })),
      rooms: [...rooms.values()].sort((a, b) => a.room - b.room),
      outputs: filtered.slice((page - 1) * 48, page * 48), progress, sceneBatch,
      cutouts: { ready: cutouts.size, total: characterProgress ? Number(characterProgress.total) + 14 : 14,
        guybrush: [...cutouts.keys()].filter(s => s.includes('AKOS_0002_')).length,
        wally: [...cutouts.keys()].filter(s => s.includes('AKOS_0025_')).length,
        cannon: [...cutouts.keys()].filter(s => s.includes('AKOS_0026_')).length,
        state: characterProgress ? String(characterProgress.state) : 'awaiting_review' } };
  }
}
