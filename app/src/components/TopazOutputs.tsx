import { useEffect, useState } from 'react';
import type { TopazSnapshot } from '../../shared/topaz';
import { PngEditor } from './PngEditor';
import './topaz.css';

function groupName(group: string) {
  const match = group.match(/LFLF_(\d+)_AKOS_(\d+)/);
  if (match) return `Room ${Number(match[1])} · Costume ${Number(match[2])}`;
  return group === 'objects_layers' ? 'Object layers' : 'Objects';
}

export function TopazOutputs({ onLibrary, onPlaytest }: { onLibrary: () => void; onPlaytest: () => void }) {
  const [snapshot, setSnapshot] = useState<TopazSnapshot | null>(null);
  const [error, setError] = useState('');
  const [group, setGroup] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('group') ?? '');
  const [room, setRoom] = useState(() => Number(new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('room')) || 0);
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('q') ?? '');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState('');
  const [mode, setMode] = useState<'compare' | 'original' | 'output'>(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('view') === 'output' ? 'output' : 'compare');
  const [split, setSplit] = useState(50);
  const [matte, setMatte] = useState('checker');
  const [borderVersion, setBorderVersion] = useState('cutout');
  const [editing, setEditing] = useState<{ src: string; filename: string; canReplace: boolean } | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);

  useEffect(() => {
    const navigate = () => {
      const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
      setRoom(Number(params.get('room')) || 0); setGroup(params.get('group') ?? ''); setQuery(params.get('q') ?? '');
      setMode(params.get('view') === 'output' ? 'output' : 'compare'); setPage(1); setSelected(''); setBorderVersion('cutout');
    };
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const params = new URLSearchParams({ group, q: query, page: String(page), room: String(room) });
        const response = await fetch(`/api/topaz?${params}`, { signal: abort.signal });
        if (!response.ok) throw new Error('Cannot load batch outputs. Retrying automatically.');
        const data: TopazSnapshot = await response.json();
        if (!abort.signal.aborted) { setSnapshot(data); setError(''); }

      } catch (e) {
        if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'Could not load outputs.');
      } finally {
        if (!abort.signal.aborted) timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [group, query, page, room, refreshVersion]);

  const outputs = snapshot?.outputs ?? [];
  const outputKey = (o: TopazSnapshot['outputs'][number]) => `${o.source}:${o.scale}`;
  const active = outputs.find(o => outputKey(o) === selected) ?? outputs[0];
  const index = active ? outputs.indexOf(active) : -1;
  const cutoutUrl = active?.cutoutUrl;
  const useCutout = borderVersion === 'cutout' && Boolean(cutoutUrl);
  const useCrisp = !useCutout && borderVersion !== 'original' && Boolean(active?.crispUrl);
  const previousUrl = active?.previousUrl ?? active?.outputUrl;
  const outputUrl = useCutout ? cutoutUrl : useCrisp ? active?.crispUrl : previousUrl;
  const shownScale = cutoutUrl && !useCutout ? active?.previousScale ?? active?.scale : active?.scale;
  const progress = snapshot?.progress;
  const stale = progress && Date.now() / 1000 - progress.updated_at > 180;
  const state = !progress ? 'No batch running' : progress.state === 'stopped' ? 'Batch stopped'
    : progress.state === 'awaiting_provider' ? 'Waiting for saved Topaz jobs'
    : progress.state === 'downloads_pending' ? 'Downloads pending'
    : progress.state === 'interrupted' ? 'Batch interrupted' : progress.state === 'credit_cap' ? 'Credit limit reached' : progress.state === 'awaiting_review' ? 'Ready for review' : stale ? 'Waiting for batch progress' : 'Batch processing';
  const roomProgress = snapshot?.rooms?.find(r => r.room === room);

  return <div className="to-shell">
    <header className="to-header">
      <strong>MI3 Remaster</strong>
      <nav aria-label="Workspace">
        <button onClick={onPlaytest}>Playtest</button>
        <button onClick={onLibrary}>Asset library</button>
        <button aria-current="page">Batch outputs</button>
      </nav>
      <span className="to-model">Wonder 3.5 · High · {shownScale ?? 4}×</span>
    </header>
    <div className="to-summary">
      <div><h1>{room === 9 ? 'The cannon room.' : room ? `Room ${room}.` : 'The next frame.'}</h1><p>Review the remaster as each image finishes.</p></div>
      <div className="to-progress" role="status"><strong>{roomProgress ? `${roomProgress.ready} / ${roomProgress.prepared}` : snapshot?.ready.toLocaleString() ?? '…'} outputs ready</strong>
        <span>{state} · refreshes every 5 seconds</span>
        {progress && <span>{progress.run_estimated_credits} / {progress.run_credit_cap} credits submitted this run</span>}
        {!!snapshot?.cutouts?.ready && <span>New 4× outputs: {snapshot.cutouts.ready}</span>}
        {!!snapshot?.cutouts?.ready && <span>Guybrush {snapshot.cutouts.guybrush} · Wally {snapshot.cutouts.wally}/220 · Cannon {snapshot.cutouts.cannon}/14</span>}
        {!!snapshot?.sceneBatch?.previousCrisp.total && <span>Previous crisp assets → 4× cutouts: {snapshot.sceneBatch.previousCrisp.ready} / {snapshot.sceneBatch.previousCrisp.total}</span>}
        {!!progress?.downloads_pending && <span>{progress.downloads_pending} paid result(s) awaiting download recovery</span>}
      </div>
    </div>
    {error && <p className="to-error" role="alert">{error}</p>}
    {snapshot?.sceneBatch && <details className="to-scene-batches">
      <summary>Scene batches · {snapshot.sceneBatch.current === 'characters' ? 'Finishing Guybrush and Wally'
        : snapshot.sceneBatch.current ?? 'Cannon room first'} · {snapshot.sceneBatch.state.replaceAll('_', ' ')}</summary>
      <p>4× Wonder 3.5 High. Transparent artwork gets Topaz background removal; solid scenery stays intact.
        Shared frames and positioned layers reuse existing results. Backgrounds are preserved.
        Previously generated 6× crisp assets take priority before new scenes.</p>
      <p>Spending pauses at the available balance or the queue’s {snapshot.sceneBatch.creditCap.toLocaleString()}-credit limit.
        Finished outputs still need visual review before installation. Small effects have a separate pilot queue.</p>
      <div className="to-scene-table"><table><thead><tr><th>Scene / resource</th><th>New outputs</th><th>Small pilots</th><th>Minimum new credits*</th><th>Review</th></tr></thead>
        <tbody>{snapshot.sceneBatch.scenes.map(s => <tr key={s.id} aria-current={snapshot.sceneBatch?.current === s.id ? 'step' : undefined}>
          <td>{s.room} · {s.name}{s.preserved ? ` · ${s.preserved} preserved` : ''}</td>
          <td>{s.ready} / {s.total - s.preserved}</td><td>{s.smallPilots || '—'}</td><td>{s.minimumCredits}</td>
          <td><button onClick={() => { setRoom(s.room); setGroup(''); setPage(1); }}>View assets</button></td>
        </tr>)}</tbody></table></div>
      <p>*Planning estimate excluding reserved work and small pilots. API prices are checked before each submission.
        After the cannon room and knife, batches follow resource numbers; shared characters remain reusable across scenes.</p>
    </details>}
    <div className="to-workspace">
      <aside className="to-browser" aria-label="Finished images">
        <label>Room<select value={room} onChange={e => {
          const number = Number(e.target.value);
          setRoom(number); setGroup(''); setPage(1);
          window.history.replaceState(null, '', number ? `#outputs?room=${number}` : '#outputs');
        }}>
          <option value={0}>All rooms</option>
          {snapshot?.rooms?.map(r => <option key={r.room} value={r.room}>{r.room === 9 ? '9 · Cannon room' : `Room ${r.room}`} ({r.ready}/{r.prepared})</option>)}
        </select></label>
        <label>Sequence<select value={group} onChange={e => { setGroup(e.target.value); setPage(1); }}>
          <option value="">All finished images</option>
          {snapshot?.groups.map(g => <option key={g.id} value={g.id}>{groupName(g.id)} ({g.count})</option>)}
        </select></label>
        <label className="to-search">Find a frame<input type="search" placeholder="Room, costume, frame…" value={query}
          onChange={e => { setQuery(e.target.value); setPage(1); }} /></label>
        <div className="to-thumbnails">
          {outputs.map(o => <button key={outputKey(o)} className={o === active ? 'selected' : ''}
            aria-pressed={o === active} aria-label={`${groupName(o.group)} · ${o.label} · ${o.scale}×`} onClick={() => setSelected(outputKey(o))}>
            <img src={o.cutoutUrl ?? o.outputUrl} alt="" loading="lazy" />
            <span>{o.label.match(/_frame_(\d+)$/) ? `Frame ${o.label.match(/_frame_(\d+)$/)![1]} · ${o.scale}×` : o.label}</span>
          </button>)}
        </div>
        {snapshot && <div className="to-pages">
          <button disabled={snapshot.page <= 1} onClick={() => setPage(snapshot.page - 1)} aria-label="Previous page">←</button>
          <span>{snapshot.page} / {snapshot.pages} · {snapshot.matched} images</span>
          <button disabled={snapshot.page >= snapshot.pages} onClick={() => setPage(snapshot.page + 1)} aria-label="Next page">→</button>
        </div>}
      </aside>
      <main className="to-review">
        {active ? <>
          <div className="to-title"><div><span>{groupName(active.group)}</span><h2>{active.label}</h2></div>
            <div className="to-prev-next">
              <button disabled={index <= 0} onClick={() => setSelected(outputKey(outputs[index - 1]))} aria-label="Previous image">←</button>
              <button disabled={index >= outputs.length - 1} onClick={() => setSelected(outputKey(outputs[index + 1]))} aria-label="Next image">→</button>
            </div>
          </div>
          <div className="to-tools">
            <div role="group" aria-label="Comparison view">
              {(['compare', 'original', 'output'] as const).map(m => <button key={m} aria-pressed={mode === m}
                onClick={() => setMode(m)}>{m === 'compare' ? 'Compare' : m === 'original' ? 'Cleaned original' : `${shownScale}× output`}</button>)}
            </div>
            <label>Canvas <select value={matte} onChange={e => setMatte(e.target.value)}>
              <option value="checker">Transparency</option><option value="dark">Dark</option><option value="light">Light</option>
            </select></label>
            <label>Border version <select value={useCutout ? 'cutout' : useCrisp ? 'crisp' : 'original'} onChange={e => setBorderVersion(e.target.value)}>
              <option value="cutout" disabled={!cutoutUrl}>{active.processing === 'manual' ? 'Manual edit (current)' : active.processing === 'opaque' ? 'Enhanced solid artwork' : active.processing === 'derived' ? 'Reused enhanced artwork' : 'Topaz background removal'}</option>
              <option value="original" disabled={Boolean(cutoutUrl && !active.previousUrl)}>{cutoutUrl ? `Archived ${active.previousScale ?? 4}× version` : 'Current Topaz'}</option>
              <option value="crisp" disabled={!active.crispUrl}>Crisp borders</option>
            </select></label>
          </div>
          <div className={`to-canvas ${matte}`}>
            <img src={mode === 'original' ? active.originalUrl : outputUrl}
              style={mode === 'compare' ? { clipPath: `inset(0 0 0 ${split}%)` } : undefined}
              alt={mode === 'original' ? 'Cleaned original asset' : `Topaz ${shownScale}× output`} />
            {mode === 'compare' && <>
              <div className="to-original-overlay" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
                <img src={active.originalUrl} alt="Cleaned original comparison" />
              </div>
              <div className="to-divider" style={{ left: `${split}%` }} />
              <span className="to-side original">Cleaned original</span><span className="to-side output">{shownScale}× {useCutout ? 'Topaz cutout' : useCrisp ? 'crisp borders' : 'output'}</span>
            </>}
          </div>
          {mode === 'compare' && <label className="to-slider">Comparison split
            <input type="range" min="0" max="100" value={split} onChange={e => setSplit(Number(e.target.value))} />
          </label>}
          <footer className="to-details"><span>{active.width / active.scale * (shownScale ?? active.scale)} × {active.height / active.scale * (shownScale ?? active.scale)} · PNG</span>
            <button onClick={() => outputUrl && setEditing({ src: outputUrl, filename: `${active.label}-${shownScale}x.png`, canReplace: shownScale === 4 && outputUrl === active.outputUrl })}>Edit / erase</button>
            <a href={outputUrl} target="_blank" rel="noreferrer">Open full resolution ↗</a>
            <a href={outputUrl} download={active.label + (useCutout ? '-topaz-cutout' : useCrisp ? '-crisp' : '') + `-${shownScale}x.png`}>Download PNG ↓</a></footer>
          <p className="to-note">{useCutout && active.processing === 'manual' ? 'Your saved replacement. Future batch installations preserve this edit.' : useCutout ? active.processing === 'opaque' ? 'Solid artwork is preserved; no background removal is applied.' : active.processing === 'derived' ? 'Reuses enhanced pixels without another paid request or original edge restoration.' : 'Topaz Object Matting. Enhanced colors are preserved; no original edge pixels or original transparency mask are restored.' : useCrisp ? 'Contours are smoothed with a narrow ink border; canvas dimensions and masters are preserved.' : 'Original silhouettes and transparency are preserved.'}</p>
        </> : <div className="to-empty"><h2>{!snapshot ? 'Loading outputs…' : 'No finished images here yet.'}</h2>
          <p>{query || group ? 'Try another sequence or clear the search.' : 'Finished images will appear here automatically as the batch runs.'}</p></div>}
      </main>
    </div>
    {editing && <PngEditor src={editing.src} filename={editing.filename} canReplace={editing.canReplace}
      onSaved={() => { setBorderVersion('cutout'); setRefreshVersion(v => v + 1); }} onClose={() => setEditing(null)} />}
  </div>;
}
