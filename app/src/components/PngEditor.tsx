import { useEffect, useRef, useState } from 'react';
import type { PointerEvent } from 'react';
import './png-editor.css';

type Point = { x: number; y: number };
type Stroke = { size: number; points: Point[] };

function erase(context: CanvasRenderingContext2D, from: Point, to: Point, size: number) {
  context.save();
  context.globalCompositeOperation = 'destination-out';
  context.lineWidth = size;
  context.lineCap = 'round';
  context.lineJoin = 'round';
  context.beginPath();
  if (from.x === to.x && from.y === to.y) {
    context.arc(to.x, to.y, size / 2, 0, Math.PI * 2);
    context.fill();
  } else {
    context.moveTo(from.x, from.y);
    context.lineTo(to.x, to.y);
    context.stroke();
  }
  context.restore();
}

/** A frozen preview with revision-checked replacement and optional PNG export. */
export function PngEditor({ src, filename, onClose, onSaved, canReplace = true }: {
  src: string; filename: string; onClose: () => void; onSaved?: (url: string) => void; canReplace?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const original = useRef<HTMLImageElement | null>(null);
  const strokes = useRef<Stroke[]>([]);
  const undone = useRef<Stroke[]>([]);
  const current = useRef<{ pointerId: number; stroke: Stroke } | null>(null);
  const revision = useRef(0);
  const expectedHash = useRef('');
  const currentUrl = useRef(src);
  const [version, setVersion] = useState(0);
  const [savedVersion, setSavedVersion] = useState(0);
  const [size, setSize] = useState(24);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [space, setSpace] = useState({ width: 1, height: 1 });
  const [zoom, setZoom] = useState(1);
  const [matte, setMatte] = useState('checker');
  const [cursor, setCursor] = useState<Point | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [confirmClose, setConfirmClose] = useState(false);
  const ready = dimensions.width > 0;
  const dirty = version !== savedVersion;
  const fit = ready ? Math.min((space.width - 48) / dimensions.width, (space.height - 48) / dimensions.height, 1) : 1;
  const scale = Math.max(0.01, fit) * zoom;

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const element = dialog.current!;
    element.showModal();
    return () => { element.close(); previousFocus?.focus(); };
  }, []);

  useEffect(() => {
    const element = viewport.current!;
    const observer = new ResizeObserver(([entry]) => setSpace({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    const abort = new AbortController();
    let objectUrl = '';
    const image = new Image();
    image.onload = () => {
      if (cancelled || !canvas.current) return;
      const surface = canvas.current;
      surface.width = image.naturalWidth;
      surface.height = image.naturalHeight;
      const context = surface.getContext('2d');
      if (!context) { setError('This browser could not open the image editor.'); return; }
      context.drawImage(image, 0, 0);
      original.current = image;
      setDimensions({ width: surface.width, height: surface.height });
    };
    image.onerror = () => { if (!cancelled) setError('Could not load this image. Close the editor and try again.'); };
    void (async () => {
      try {
        const response = await fetch(src, { signal: abort.signal, cache: 'no-store' });
        if (!response.ok) throw new Error('Could not load this image. Close the editor and try again.');
        const bytes = await response.arrayBuffer();
        const hash = await crypto.subtle.digest('SHA-256', bytes);
        if (cancelled) return;
        expectedHash.current = Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
        objectUrl = URL.createObjectURL(new Blob([bytes]));
        image.src = objectUrl;
      } catch (error) { if (!cancelled) setError(error instanceof Error ? error.message : 'Could not load this image.'); }
    })();
    return () => { cancelled = true; abort.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [src]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  // A history button can become disabled after use and move focus to <body>.
  // Listen at window level while this modal is mounted so shortcuts still work.
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement;
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key.toLowerCase() === 's') {
        event.preventDefault(); event.stopImmediatePropagation(); void save();
      } else if (!typing && event.key.toLowerCase() === 'z') {
        event.preventDefault(); event.stopImmediatePropagation();
        if (event.shiftKey) redo(); else undo();
      }
    };
    window.addEventListener('keydown', handleKey, true);
    return () => window.removeEventListener('keydown', handleKey, true);
  });

  function changed() {
    revision.current++;
    setVersion(revision.current);
    setMessage('');
    setConfirmClose(false);
  }

  function redraw() {
    const surface = canvas.current!;
    const context = surface.getContext('2d')!;
    context.clearRect(0, 0, surface.width, surface.height);
    context.drawImage(original.current!, 0, 0);
    for (const stroke of strokes.current) {
      stroke.points.forEach((point, i) => erase(context, stroke.points[Math.max(0, i - 1)], point, stroke.size));
    }
    changed();
  }

  function undo() {
    if (saving || current.current || !strokes.current.length) return;
    undone.current.push(strokes.current.pop()!);
    redraw();
  }

  function redo() {
    if (saving || current.current || !undone.current.length) return;
    strokes.current.push(undone.current.pop()!);
    redraw();
  }

  function point(event: PointerEvent<HTMLCanvasElement>): Point {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: (event.clientX - bounds.left) * event.currentTarget.width / bounds.width,
      y: (event.clientY - bounds.top) * event.currentTarget.height / bounds.height };
  }

  function start(event: PointerEvent<HTMLCanvasElement>) {
    if (!ready || saving || event.button !== 0 || current.current) return;
    event.preventDefault();
    event.currentTarget.focus({ preventScroll: true });
    const position = point(event);
    const stroke = { size, points: [position] };
    event.currentTarget.setPointerCapture(event.pointerId);
    current.current = { pointerId: event.pointerId, stroke };
    strokes.current.push(stroke);
    undone.current = [];
    erase(event.currentTarget.getContext('2d')!, position, position, size);
    setCursor(position);
    setDrawing(true);
    changed();
  }

  function move(event: PointerEvent<HTMLCanvasElement>) {
    const position = point(event);
    setCursor(position);
    const active = current.current;
    if (!active || active.pointerId !== event.pointerId) return;
    erase(event.currentTarget.getContext('2d')!, active.stroke.points.at(-1)!, position, active.stroke.size);
    active.stroke.points.push(position);
  }

  function finish(event: PointerEvent<HTMLCanvasElement>) {
    if (current.current?.pointerId !== event.pointerId) return;
    current.current = null;
    setDrawing(false);
    setCursor(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function close() {
    if (saving) return;
    if (dirty) setConfirmClose(true);
    else onClose();
  }

  async function save(download = !canReplace) {
    if (!ready || drawing || saving) return;
    setSaving(true);
    setError('');
    const exportedVersion = revision.current;
    try {
      const blob = await new Promise<Blob>((resolve, reject) => canvas.current!.toBlob(
        value => value ? resolve(value) : reject(new Error('Could not create the PNG. Please try again.')), 'image/png'));
      if (!download) {
        const png = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(',')[1]);
          reader.onerror = () => reject(new Error('Could not read the edited PNG.'));
          reader.readAsDataURL(blob);
        });
        const response = await fetch('/api/asset-edits', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: currentUrl.current, expected: expectedHash.current, png }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not replace the asset. Your edits are still here.');
        expectedHash.current = result.sha256;
        currentUrl.current = result.url;
        setMessage(result.message);
        onSaved?.(result.url);
      } else {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename.replace(/\.png$/i, '') + '-edited.png';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
        setMessage('PNG download started.');
      }
      setSavedVersion(exportedVersion);
      setConfirmClose(false);
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not save the PNG.'); }
    finally { setSaving(false); }
  }

  return <dialog ref={dialog} className="png-editor" aria-labelledby="png-editor-title"
    onCancel={event => { event.preventDefault(); close(); }}
    onKeyDown={event => event.stopPropagation()}>
    <header className="png-editor-header">
      <div><h2 id="png-editor-title">Erase pixels</h2><p>{filename}</p></div>
      <button onClick={close} disabled={saving} aria-label="Close image editor">Close</button>
    </header>
    <div className="png-editor-tools">
      <label>Eraser size <input aria-label="Eraser size" type="range" min="1" max="256" value={size}
        onChange={event => setSize(Number(event.target.value))} disabled={drawing} /><span>{size} px</span></label>
      <button onClick={undo} disabled={!strokes.current.length || drawing || saving}>Undo</button>
      <button onClick={redo} disabled={!undone.current.length || drawing || saving}>Redo</button>
      <label>Zoom <select aria-label="Editor zoom" value={zoom} onChange={event => { setZoom(Number(event.target.value)); setCursor(null); }} disabled={drawing}>
        <option value={1}>Fit</option><option value={2}>2× fit</option><option value={4}>4× fit</option><option value={8}>8× fit</option>
      </select></label>
      <label>Canvas <select value={matte} onChange={event => setMatte(event.target.value)}>
        <option value="checker">Transparency</option><option value="dark">Dark</option><option value="light">Light</option>
      </select></label>
    </div>
    <p className="png-editor-help">Drag to erase. Zoom in and scroll for detail. Undo: ⌘/Ctrl Z · Redo: ⇧ ⌘/Ctrl Z</p>
    <div ref={viewport} className={`png-editor-viewport ${matte}`}>
      <div className="png-editor-stage">
        <div className="png-editor-image" style={{ width: ready ? dimensions.width * scale : 1, height: ready ? dimensions.height * scale : 1 }}>
          <canvas ref={canvas} tabIndex={0} aria-label="Editable asset. Drag to erase pixels." onPointerDown={start} onPointerMove={move}
            onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish}
            onPointerLeave={() => { if (!current.current) setCursor(null); }} />
          {cursor && <span className="png-editor-brush" aria-hidden="true" style={{
            left: cursor.x * scale, top: cursor.y * scale, width: size * scale, height: size * scale,
          }} />}
        </div>
      </div>
    </div>
    {error && <p className="png-editor-error" role="alert">{error}</p>}
    <footer className="png-editor-footer">
      <div><span>{ready ? `${dimensions.width} × ${dimensions.height} · PNG · ${dirty ? 'Unsaved edits' : 'Ready'}` : 'Loading image…'}</span>
        <p>{canReplace ? 'Replace asset saves here and keeps a backup. Game textures update when the game is closed.' : 'Archived versions can be downloaded. Select the current 4× output to replace it.'}</p><span role="status">{message}</span></div>
      {confirmClose && <div className="png-editor-discard" role="alert"><span>Close without saving these edits?</span>
        <button onClick={() => setConfirmClose(false)}>Keep editing</button><button onClick={onClose}>Discard edits</button></div>}
      <button onClick={() => void save(true)} disabled={!ready || drawing || saving}>Download PNG</button>
      {canReplace && <button className="png-editor-save" onClick={() => void save(false)} disabled={!ready || drawing || saving}>{saving ? 'Saving…' : 'Replace asset'}</button>}
    </footer>
  </dialog>;
}
