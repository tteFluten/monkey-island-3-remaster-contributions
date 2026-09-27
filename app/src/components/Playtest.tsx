import { useEffect, useRef, useState } from 'react';
import type { PlaytestSnapshot, PlaytestSettings, PlaytestStatus, ImportCandidate } from '../../shared/playtest';
import { PLAYTEST_SCALE } from '../../shared/playtest';
import { assetFileUrl } from '../lib/api';
import './playtest.css';

async function api<T>(route = '', method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/playtest${route}`, { method, headers: method === 'GET' ? undefined : { 'Content-Type': 'application/json' }, body: method === 'GET' ? undefined : JSON.stringify(body ?? {}) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}

export function Playtest({ onLibrary, onOutputs }: { onLibrary: () => void; onOutputs: () => void }) {
  const [snapshot, setSnapshot] = useState<PlaytestSnapshot | null>(null);
  const [settings, setSettings] = useState<PlaytestSettings | null>(null);
  const [status, setStatus] = useState<PlaytestStatus | null>(null);
  const [roomId, setRoomId] = useState(9);
  const [search, setSearch] = useState('');
  const [split, setSplit] = useState(50);
  const [mode, setMode] = useState<'compare' | 'remaster' | 'original'>('compare');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState(false);
  const [setup, setSetup] = useState(false);
  const [candidates, setCandidates] = useState<ImportCandidate[] | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const importButtonRef = useRef<HTMLButtonElement>(null);
  const pendingRef = useRef(false);
  pendingRef.current = pending;
  const [chosen, setChosen] = useState<Record<string, number | null>>({});

  useEffect(() => {
    if (!candidates) return;
    const dialog = dialogRef.current;
    dialog?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !pendingRef.current) setCandidates(null);
      if (event.key !== 'Tab' || !dialog) return;
      const targets = Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled), select:not(:disabled), [tabindex="0"]'));
      const first = targets[0], last = targets[targets.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) { event.preventDefault(); first.focus(); }
    }
    dialog?.addEventListener('keydown', keydown);
    return () => { dialog?.removeEventListener('keydown', keydown); importButtonRef.current?.focus(); };
  }, [candidates]);

  async function refresh() {
    const data = await api<PlaytestSnapshot>();
    setSnapshot(data); setStatus(data.status);
    setSettings(previous => previous ?? data.settings);
  }
  useEffect(() => {
    void refresh().catch(e => setError(e.message));
    const events = new EventSource('/api/playtest/events');
    events.onmessage = event => { setStatus(JSON.parse(event.data)); };
    events.onerror = () => setError('Connection interrupted. The editor will reconnect automatically.');
    events.onopen = () => setError('');
    return () => events.close();
  }, []);

  async function act(action: () => Promise<unknown>, message = '') {
    setPending(true); setError(''); setNotice('');
    try { await action(); await refresh(); if (message) setNotice(message); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setPending(false); }
  }
  const room = snapshot?.rooms.find(r => r.room === roomId) ?? snapshot?.rooms[0];
  const variant = room?.variants.find(v => v.id === room.selectedVariantId);
  const rooms = snapshot?.rooms.filter(r => `${r.room} ${r.name}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  const busy = pending || Boolean(status?.busy);
  const ready = status?.running && status.engine?.ready && !busy;
  const selected = Object.entries(chosen).filter(([, number]) => number !== null);
  const duplicateRooms = selected.map(([, number]) => number).filter((number, index, all) => all.indexOf(number) !== index);
  const withRemaster = snapshot?.rooms.filter(r => r.selectedVariantId).length ?? 0;

  async function scan() {
    await api('/settings', 'PUT', settings);
    const result = await api<ImportCandidate[]>('/scan');
    setCandidates(result);
    const counts = new Map<number, number>();
    result.forEach(c => { if (c.room !== null) counts.set(c.room, (counts.get(c.room) ?? 0) + 1); });
    setChosen(Object.fromEntries(result.map(c => [c.file, !c.error && c.room !== null && counts.get(c.room) === 1 ? c.room : null])));
  }

  return <div className="pt-shell">
    <header className="pt-header">
      <div className="pt-brand"><span className="pt-mark" aria-hidden="true">Ⅲ</span><div><strong>Monkey Island</strong><span>REMASTER WORKSHOP</span></div></div>
      <nav aria-label="Workspace"><button className="pt-nav active" aria-current="page">Playtest</button><button className="pt-nav" onClick={onLibrary}>Asset library</button><button className="pt-nav" onClick={onOutputs}>Batch outputs</button></nav>
      <div className="pt-header-end"><span className={`pt-dot ${status?.running ? 'live' : ''}`} />{status?.running ? 'Game running' : 'Game offline'}<button onClick={() => setSetup(!setup)} aria-expanded={setup}>Setup</button></div>
    </header>
    <div className="pt-messages" aria-live="polite">
      {(error || status?.error) && <div className="pt-error" role="alert">{error || status?.error}</div>}
      {notice && <div className="pt-notice">{notice}</div>}
      {status?.busy && <div className="pt-progress"><span className="pt-dot live" />{status.busy}…</div>}
    </div>
    {setup && settings && <section className="pt-setup" aria-label="Local setup">
      <div><h2>Local game setup</h2><p>Your discs and master artwork remain untouched.</p></div>
      <div className="pt-setup-fields">{(['disc1', 'disc2', 'backgroundFolder'] as const).map((key, i) => <label key={key}>{['Disc 1 ISO', 'Disc 2 ISO', 'Background folder'][i]}<input value={settings[key]} onChange={e => setSettings({ ...settings, [key]: e.target.value })} disabled={busy || status?.running} /></label>)}</div>
      <div className="pt-setup-actions">
        <button disabled={busy || status?.running} onClick={() => void act(() => api('/settings', 'PUT', settings), 'Setup saved')}>Save paths</button>
        <button disabled={busy || status?.running} onClick={() => void act(async () => { await api('/settings', 'PUT', settings); await api('/discs', 'POST'); }, 'Both discs imported')}>{status?.gameReady ? 'Reimport discs' : 'Import discs'}</button>
        <button disabled={busy || status?.running} onClick={() => void act(() => api('/build', 'POST'), 'Mac engine ready')}>{status?.engineReady ? 'Rebuild engine' : 'Build Mac engine'}</button>
      </div>
    </section>}
    <div className="pt-workspace">
      <aside className="pt-rooms">
        <div className="pt-section-heading"><h2>Rooms</h2><span>{snapshot?.rooms.length ?? '—'}</span></div>
        <label className="pt-search"><span className="sr-only">Find a room</span><input placeholder="Find a room or number…" value={search} onChange={e => setSearch(e.target.value)} /></label>
        <div className="pt-room-list">{rooms.map(r => <button key={r.room} className={`pt-room ${room?.room === r.room ? 'selected' : ''}`} onClick={() => { setRoomId(r.room); setNotice(''); }} aria-pressed={room?.room === r.room}>
          <img loading="lazy" src={assetFileUrl(r.originalPath)} alt="" />
          <div><span className="pt-room-number">ROOM {String(r.room).padStart(4, '0')}</span><strong>{r.name}</strong><span>{r.selectedVariantId ? 'Remaster selected' : 'Original artwork'}</span></div>
          {status?.engine?.room === r.room && <span className="pt-dot live" title="Active in game" />}
        </button>)}{!rooms.length && <p className="pt-empty">{snapshot ? 'No rooms match your search.' : 'Loading rooms…'}</p>}</div>
        <div className="pt-room-footer"><strong>{withRemaster} / {snapshot?.rooms.length ?? 0}</strong> backgrounds selected</div>
      </aside>
      <main className="pt-stage">
        <div className="pt-stage-heading"><div><span className="pt-eyebrow">ROOM {String(room?.room ?? 0).padStart(4, '0')}</span><h1>{room?.name ?? 'Loading workshop'}</h1></div><button ref={importButtonRef} disabled={busy || status?.running} onClick={() => void act(scan)}>Import folder</button></div>
        <div className="pt-view-tools" aria-label="Preview mode">{(['compare', 'remaster', 'original'] as const).map(m => <button key={m} className={mode === m ? 'active' : ''} aria-pressed={mode === m} disabled={m !== 'original' && !variant} onClick={() => setMode(m)}>{m === 'compare' ? 'Compare' : m === 'remaster' ? 'Remaster' : 'Original'}</button>)}<span>Full room · proportions preserved</span></div>
        <div className="pt-canvas">
          {room && <div className="pt-artwork" style={{ aspectRatio: `${room.width}/${room.height}` }}>
            <img src={assetFileUrl(mode === 'remaster' && variant ? variant.filePath : room.originalPath)} alt={`${room.name}, ${mode === 'remaster' && variant ? 'remastered' : 'original'} background`} />
            {mode === 'compare' && variant && <><img className="pt-overlay" style={{ clipPath: `inset(0 0 0 ${split}%)` }} src={assetFileUrl(variant.filePath)} alt="Remaster comparison" /><div className="pt-divider" style={{ left: `${split}%` }} /><span className="pt-image-label original">Original</span><span className="pt-image-label remaster">Remaster</span></>}
          </div>}
        </div>
        {mode === 'compare' && variant && <label className="pt-comparison">Original<input aria-label="Comparison divider" type="range" min="0" max="100" value={split} onChange={e => setSplit(Number(e.target.value))} />Remaster</label>}
        {!variant && <p className="pt-preview-hint">Import your background folder to compare and test remasters.</p>}
        <footer className="pt-dimensions"><div><span>ORIGINAL</span><strong>{room?.width} × {room?.height}</strong></div><div><span>MASTER</span><strong>{variant ? `${variant.width} × ${variant.height}` : 'Not selected'}</strong></div><div><span>GAME TEXTURE · {PLAYTEST_SCALE}×</span><strong>{room ? `${room.width * PLAYTEST_SCALE} × ${room.height * PLAYTEST_SCALE}` : '—'}</strong></div></footer>
      </main>
      <aside className="pt-controls">
        <div className="pt-section-heading"><h2>In-game test</h2><span className="pt-dot" /></div>
        <p className="pt-subtle">Play in a native game window. Keep this workshop open to switch rooms and artwork.</p>
        <div className="pt-checks"><div><span>Game data</span><strong>{status?.gameReady ? 'Ready' : 'Import discs'}</strong></div><div><span>Mac engine</span><strong>{status?.engineReady ? 'Ready' : 'Build needed'}</strong></div><div><span>Display</span><strong>4:3 · {PLAYTEST_SCALE}× renderer</strong></div></div>
        {(!status?.gameReady || !status?.engineReady) && <button onClick={() => setSetup(true)}>Open setup</button>}
        {snapshot && <label className="pt-character-pack">Cannon-room characters
          <select value={snapshot.settings.characterPack} disabled={busy || status?.running} onChange={e => {
            const characterPack = e.target.value as PlaytestSettings['characterPack'];
            void act(async () => {
              await api('/settings', 'PUT', { ...snapshot.settings, characterPack });
              setSettings(previous => previous ? { ...previous, characterPack } : null);
            }, 'Character version selected. Launch to compare.');
          }}>
            <option value="topaz" disabled={!snapshot.characterPacks.topaz}>Topaz{snapshot.characterPacks.topaz ? ` · ${snapshot.characterPacks.topaz} frames` : ' · not staged'}</option>
            <option value="topaz-crisp" disabled={!snapshot.characterPacks['topaz-crisp']}>Topaz crisp borders{snapshot.characterPacks['topaz-crisp'] ? ` · ${snapshot.characterPacks['topaz-crisp']} frames` : ' · not staged'}</option>
            <option value="quiver" disabled={!snapshot.characterPacks.quiver}>Quiver{snapshot.characterPacks.quiver ? ` · ${snapshot.characterPacks.quiver} frames` : ' · not staged'}</option>
            <option value="original">Original</option>
          </select>
          <small>Stop the game to switch versions. Both packs are preserved.</small>
        </label>}
        <button className="pt-primary" disabled={busy || status?.running || !status?.gameReady || !status?.engineReady} onClick={() => void act(() => api('/launch', 'POST'), 'Game launched. Finish the opening, then jump to a room.')}>▶ Launch game</button>
        <div className="pt-running" aria-live="polite"><span className={`pt-dot ${ready ? 'live' : ''}`} /><div><strong>{status?.engine ? (status.engine.ready ? `Room ${status.engine.room} · ready` : `Room ${status.engine.room} · waiting`) : status?.running ? 'Starting engine…' : 'Ready when you are'}</strong><span>{status?.engine?.backgroundLoaded ? `Loaded ${status.engine.width} × ${status.engine.height}` : status?.running ? 'Finish opening / close menus to use controls' : 'Launch to begin a playable test'}</span></div></div>
        <button disabled={!ready || !room} onClick={() => void act(() => api('/jump', 'POST', { room: room!.room }))}>Jump to room {room?.room}</button>
        <p className="pt-small">Room jumps preserve current game state. Puzzle progress may differ from normal play.</p>
        <div className="pt-rule" />
        <label className="pt-variant-label">Test background<select value={room?.selectedVariantId ?? ''} disabled={busy || !room || room.finalBackground} onChange={e => void act(() => api('/selection', 'PUT', { room: room!.room, variantId: e.target.value || null }))}>{!room?.finalBackground && <option value="">Original artwork</option>}{room?.variants.map((v, i) => <option key={v.id} value={v.id}>{room?.finalBackground ? 'Final background' : `Variant ${i + 1}`} · {v.width} × {v.height}</option>)}</select></label>
        <button className="pt-brass" disabled={busy || !room || Boolean(status?.running && !ready)} onClick={() => void act(() => api('/apply', 'POST', { room: room!.room }), status?.running ? 'Background applied' : 'Background prepared for the next launch')}>Apply and reload</button>
        <button disabled={busy || !room || room.finalBackground || !variant || Boolean(status?.running && !ready)} onClick={() => void act(async () => { await api('/selection', 'PUT', { room: room!.room, variantId: null }); await api('/apply', 'POST', { room: room!.room }); }, 'Original background restored')}>Use original</button>
        <button className="pt-stop" disabled={!status?.running} onClick={() => void act(() => api('/stop', 'POST'))}>Stop game</button>
        <details className="pt-log"><summary>Activity log <span>{status?.logs.length ?? 0}</span></summary><pre>{status?.logs.join('\n') || 'No activity yet.'}</pre></details>
      </aside>
    </div>
    {candidates && <div className="pt-modal-shade"><section ref={dialogRef} tabIndex={-1} className="pt-import" role="dialog" aria-modal="true" aria-label="Map background imports">
      <div className="pt-import-heading"><div><span className="pt-eyebrow">FOLDER IMPORT</span><h2>Match artwork to rooms</h2><p>{candidates.length} images found. Choose one image per room; leave others skipped.</p></div><button disabled={busy} onClick={() => setCandidates(null)} aria-label="Close import">✕</button></div>
      <div className="pt-import-list"><table><thead><tr><th>Image</th><th>Dimensions</th><th>Room</th></tr></thead><tbody>{candidates.map(c => <tr key={c.file}><td>{c.file}{c.error && <span className="pt-error">{c.error}</span>}</td><td>{c.width} × {c.height}</td><td><select aria-label={`Room for ${c.file}`} disabled={busy || Boolean(c.error)} value={chosen[c.file] ?? ''} onChange={e => setChosen({ ...chosen, [c.file]: e.target.value === '' ? null : Number(e.target.value) })}><option value="">Skip image</option>{snapshot?.rooms.map(r => <option key={r.room} value={r.room}>{r.room} · {r.name}</option>)}</select></td></tr>)}</tbody></table></div>
      <footer>{duplicateRooms.length > 0 ? <span className="pt-error">Multiple images selected for room {duplicateRooms.join(', ')}.</span> : <span>{selected.length} backgrounds selected · masters preserved</span>}<button className="pt-primary" disabled={busy || !selected.length || duplicateRooms.length > 0} onClick={() => void act(async () => { const result = await api<{ imported: number; skipped: number }>('/import', 'POST', { items: selected.map(([file, room]) => ({ file, room })) }); setCandidates(null); setNotice(`${result.imported} imported, ${result.skipped} already available`); })}>{busy ? 'Importing…' : 'Import backgrounds'}</button></footer>
    </section></div>}
  </div>;
}
