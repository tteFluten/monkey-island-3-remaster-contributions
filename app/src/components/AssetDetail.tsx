import { useState, useRef, useEffect } from 'react';
import type { Asset, Variant, SceneManifest } from '@shared/types';
import { assetFileUrl, importVariant, startGeneration, subscribeJobEvents, approveVariant, getCostumeFrames, upscaleCostume } from '../lib/api';
import { PngEditor } from './PngEditor';

interface Props {
  asset: Asset;
  scene: SceneManifest;
  onClose: () => void;
  onNavigate: (dir: 'prev' | 'next') => void;
  hasPrev: boolean;
  hasNext: boolean;
  onRefresh: () => void;
  mcpConnected: boolean;
}

const DEFAULT_PROMPT = `Remaster the original game background in @1 at high resolution. Preserve its exact composition, camera, perspective, object positions, silhouettes, painted cartoon style, palette and lighting. Clean compression and pixelation while faithfully reconstructing existing contours and painted detail. Do not add, remove, move or redesign elements. No photorealism, new text, crop or camera change.`;

export function AssetDetail({
  asset, scene, onClose, onNavigate, hasPrev, hasNext, onRefresh, mcpConnected,
}: Props) {
  const [tab, setTab] = useState<'view' | 'generate'>('view');
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [showVariantIdx, setShowVariantIdx] = useState<number | null>(null);
  const [sliderPos, setSliderPos] = useState(50);
  const [compareMode, setCompareMode] = useState(false);
  const [editing, setEditing] = useState<{ src: string; filename: string } | null>(null);
  const [imageRevision, setImageRevision] = useState(0);

  // Generate state
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [model, setModel] = useState('gemini-2.5-flash-image');
  const [generating, setGenerating] = useState(false);
  const [genStatus, setGenStatus] = useState('');
  const [uploading, setUploading] = useState(false);

  // Costume frames
  const [frames, setFrames] = useState<{ file: string; frame: number; url: string; upscaledUrl: string | null }[]>([]);
  const [activeFrame, setActiveFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showUpscaled, setShowUpscaled] = useState(true);
  const [hasUpscaled, setHasUpscaled] = useState(false);
  const [upscaling, setUpscaling] = useState(false);

  const frameStripRef = useRef<HTMLDivElement>(null);

  const uploadRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0, px: 0, py: 0 });

  const variants = asset.variants
    .map(vid => scene.variants[vid])
    .filter(Boolean);

  const activeVariant = showVariantIdx !== null ? variants[showVariantIdx] : null;

  // Reset on asset change
  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setShowVariantIdx(variants.length > 0 ? 0 : null);
    setCompareMode(false);
    setTab('view');
    setGenerating(false);
    setGenStatus('');
  }, [asset.id]);

  // Keyboard
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (editing) return;
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowLeft') hasPrev && onNavigate('prev');
      else if (e.key === 'ArrowRight') hasNext && onNavigate('next');
      else if (e.key === '+' || e.key === '=') setZoom(z => Math.min(10, z * 1.3));
      else if (e.key === '-') setZoom(z => Math.max(0.1, z / 1.3));
      else if (e.key === '0') { setZoom(1); setPan({ x: 0, y: 0 }); }
      else if (e.key === 'c') setCompareMode(m => !m);
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [hasPrev, hasNext, editing]);

  // Load costume frames
  useEffect(() => {
    if (asset.type !== 'character' || !asset.metadata?.akosId) return;
    setFrames([]);
    setActiveFrame(0);
    setPlaying(false);
    getCostumeFrames(asset.metadata.akosId as string)
      .then(data => {
        setFrames(data.frames);
        setHasUpscaled(data.hasUpscaled);
        setShowUpscaled(data.hasUpscaled);
      })
      .catch(() => {});
  }, [asset.id]);

  // Playback timer
  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const interval = setInterval(() => {
      setActiveFrame(f => (f + 1) % frames.length);
    }, 100);
    return () => clearInterval(interval);
  }, [playing, frames.length]);

  // Auto-scroll frame strip
  useEffect(() => {
    if (!frameStripRef.current) return;
    const child = frameStripRef.current.children[activeFrame] as HTMLElement | undefined;
    child?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }, [activeFrame]);

  function handleWheel(e: React.WheelEvent) {
    e.stopPropagation();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(z => Math.max(0.1, Math.min(10, z * delta)));
  }

  function handleMouseDown(e: React.MouseEvent) {
    if (e.button === 2) return;
    dragging.current = true;
    dragStart.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      setPan({
        x: dragStart.current.px + (ev.clientX - dragStart.current.x),
        y: dragStart.current.py + (ev.clientY - dragStart.current.y),
      });
    };
    const onUp = () => {
      dragging.current = false;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  function handleSliderDrag(e: React.MouseEvent) {
    e.stopPropagation();
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const update = (cx: number) => setSliderPos(Math.max(0, Math.min(100, ((cx - rect.left) / rect.width) * 100)));
    update(e.clientX);
    const onMove = (ev: MouseEvent) => update(ev.clientX);
    const onUp = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  async function handleUpload(files: FileList) {
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await importVariant(scene.scene.id, asset.id, file);
      }
      onRefresh();
    } catch (err) {
      alert('Upload failed: ' + String(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleGenerate() {
    if (!mcpConnected) { alert('ImageLab not connected'); return; }
    setGenerating(true);
    setGenStatus('Starting...');
    try {
      const aspectW = asset.width;
      const aspectH = asset.height;
      const gcd = (a: number, b: number): number => b ? gcd(b, a % b) : a;
      const d = gcd(aspectW, aspectH);
      const ratioW = aspectW / d;
      const ratioH = aspectH / d;
      // Pick closest standard ratio
      let aspectRatio = '4:3';
      const r = ratioW / ratioH;
      if (r > 1.5) aspectRatio = '16:9';
      else if (r > 1.2) aspectRatio = '4:3';
      else if (r > 0.9) aspectRatio = '1:1';
      else aspectRatio = '3:4';

      const job = await startGeneration({
        sceneId: scene.scene.id,
        assetId: asset.id,
        prompt,
        model,
        aspectRatio,
        imageSize: model.startsWith('gemini') ? '4K' : '1K',
        references: [{ position: 1, assetId: asset.id, label: 'background' }],
      });

      // Subscribe to SSE
      const unsub = subscribeJobEvents(job.id, (data: any) => {
        if (data.status) setGenStatus(data.status);
        if (data.status === 'completed' || data.status === 'failed') {
          setGenerating(false);
          if (data.status === 'completed') {
            setGenStatus('Done!');
            setTab('view');
            onRefresh();
          } else {
            setGenStatus('Failed: ' + (data.error || 'unknown error'));
          }
          unsub();
        }
      });
    } catch (err) {
      setGenerating(false);
      setGenStatus('Error: ' + String(err));
    }
  }

  async function handleApprove() {
    if (!activeVariant) return;
    try {
      await approveVariant(scene.scene.id, asset.id, activeVariant.id);
      onRefresh();
    } catch (err) {
      alert('Approve failed: ' + String(err));
    }
  }

  const isCharacter = asset.type === 'character' && frames.length > 0;
  const currentFrame = isCharacter ? frames[activeFrame] : null;
  const refreshed = (url: string) => imageRevision ? `${url}${url.includes('?') ? '&' : '?'}edit=${imageRevision}` : url;
  const originalUrl = refreshed(currentFrame
    ? (showUpscaled && currentFrame.upscaledUrl ? currentFrame.upscaledUrl : currentFrame.url)
    : assetFileUrl(asset.originalPath));
  const variantUrl = activeVariant ? refreshed(assetFileUrl(activeVariant.filePath)) : '';

  async function handleCopyImage() {
    const url = activeVariant ? variantUrl : originalUrl;
    try {
      const res = await fetch(url);
      const blob = await res.blob();
      const pngBlob = blob.type === 'image/png' ? blob : await new Promise<Blob>((resolve) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement('canvas');
          canvas.width = img.naturalWidth;
          canvas.height = img.naturalHeight;
          canvas.getContext('2d')!.drawImage(img, 0, 0);
          canvas.toBlob(b => resolve(b!), 'image/png');
        };
        img.src = URL.createObjectURL(blob);
      });
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': pngBlob })]);
    } catch (err) {
      alert('Copy failed: ' + String(err));
    }
  }

  const imgTransform: React.CSSProperties = {
    transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
    transformOrigin: 'center center',
    imageRendering: zoom >= 2 ? 'pixelated' : 'auto',
    userSelect: 'none',
    pointerEvents: 'none',
  };

  return (
    <div className="detail-overlay">
      {/* Top bar */}
      <div className="detail-topbar">
        <button className="detail-close" onClick={onClose}>&times;</button>

        <div className="detail-info">
          <strong>{asset.name}</strong>
          <span className="detail-dims">
            {asset.width}&times;{asset.height} &middot; {asset.type}
            {isCharacter && <> &middot; {frames.length} frames</>}
          </span>
        </div>

        <div className="detail-tabs">
          <button className={`detail-tab ${tab === 'view' ? 'active' : ''}`} onClick={() => setTab('view')}>
            View
          </button>
          <button className={`detail-tab ${tab === 'generate' ? 'active' : ''}`} onClick={() => setTab('generate')}>
            Generate HD
          </button>
        </div>

        <div style={{ flex: 1 }} />

        {tab === 'view' && (
          <div className="detail-actions">
            {variants.length > 0 && (
              <>
                <select
                  className="filter-select"
                  value={showVariantIdx ?? ''}
                  onChange={e => {
                    const v = e.target.value;
                    setShowVariantIdx(v === '' ? null : Number(v));
                    setCompareMode(false);
                  }}
                  style={{ width: 'auto' }}
                >
                  <option value="">Original only</option>
                  {variants.map((v, i) => (
                    <option key={v.id} value={i}>
                      HD {i + 1} — {v.width}x{v.height} ({v.model})
                    </option>
                  ))}
                </select>

                {activeVariant && (
                  <>
                    <button
                      className={`detail-btn ${compareMode ? 'active' : ''}`}
                      onClick={() => setCompareMode(m => !m)}
                      title="Compare (C)"
                    >
                      Compare
                    </button>
                    <button
                      className={`detail-btn ${asset.approvedVariantId === activeVariant.id ? 'approved' : ''}`}
                      onClick={handleApprove}
                    >
                      {asset.approvedVariantId === activeVariant.id ? 'Approved' : 'Approve'}
                    </button>
                  </>
                )}
              </>
            )}

            <button className="detail-btn" onClick={handleCopyImage} title="Copy image to clipboard">
              Copy
            </button>

            <button className="detail-btn" onClick={() => {
              setPlaying(false);
              setEditing({ src: activeVariant ? variantUrl : originalUrl,
                filename: currentFrame && !activeVariant ? currentFrame.file : `${asset.name}.png` });
            }}>Edit / erase</button>

            <button
              className="detail-btn"
              onClick={() => uploadRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? 'Uploading...' : 'Upload HD'}
            </button>
            <input
              ref={uploadRef}
              type="file"
              accept="image/*"
              multiple
              style={{ display: 'none' }}
              onChange={e => e.target.files && handleUpload(e.target.files)}
            />

            <span className="detail-zoom">{Math.round(zoom * 100)}%</span>
            <button className="detail-btn-sm" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} title="Reset (0)">1:1</button>
          </div>
        )}
      </div>

      {/* Content */}
      {tab === 'view' ? (
        <div
          ref={containerRef}
          className="detail-canvas"
          onWheel={handleWheel}
          onMouseDown={compareMode ? undefined : handleMouseDown}
        >
          {!compareMode ? (
            // Single image view (original or variant)
            <img
              src={activeVariant ? variantUrl : originalUrl}
              alt={asset.name}
              style={imgTransform}
              draggable={false}
            />
          ) : activeVariant ? (
            // Compare slider
            <>
              <div
                style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                onMouseDown={handleMouseDown}
              >
                <img src={variantUrl} alt="HD" style={imgTransform} draggable={false} />
                <div style={{
                  position: 'absolute', inset: 0, overflow: 'hidden',
                  clipPath: `inset(0 ${100 - sliderPos}% 0 0)`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <img src={originalUrl} alt="Original" style={imgTransform} draggable={false} />
                </div>
              </div>
              {/* Slider line */}
              <div className="compare-line" style={{ left: `${sliderPos}%` }} onMouseDown={handleSliderDrag}>
                <div className="compare-handle">&harr;</div>
              </div>
              <div className="compare-label left">Original</div>
              <div className="compare-label right">HD</div>
            </>
          ) : null}
        </div>
      ) : (
        // Generate tab
        <div className="generate-panel">
          <div className="gen-form">
            <div className="gen-preview">
              <img src={originalUrl} alt={asset.name} />
              <span>Original reference ({asset.width}&times;{asset.height})</span>
            </div>

            <div className="gen-fields">
              <label className="gen-label">
                Prompt
                <textarea
                  className="gen-textarea"
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  rows={5}
                />
              </label>

              <label className="gen-label">
                Model
                <select className="filter-select" value={model} onChange={e => setModel(e.target.value)}>
                  <option value="gemini-2.5-flash-image">Gemini 2.5 Flash (fast, reliable)</option>
                  <option value="gemini-3.1-pro-image-preview">Gemini 3.1 Pro (best quality)</option>
                  <option value="gpt-image-2">GPT Image 2</option>
                  <option value="gpt-image-1">GPT Image 1</option>
                </select>
              </label>

              <button
                className="gen-submit"
                onClick={handleGenerate}
                disabled={generating || !mcpConnected}
              >
                {generating ? genStatus : mcpConnected ? 'Generate with ImageLab' : 'ImageLab not connected'}
              </button>

              {!generating && genStatus && (
                <div className={`gen-status ${genStatus.startsWith('Error') || genStatus.startsWith('Failed') ? 'error' : 'ok'}`}>
                  {genStatus}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Navigation arrows */}
      {hasPrev && (
        <button className="nav-arrow left" onClick={() => onNavigate('prev')}>&lsaquo;</button>
      )}
      {hasNext && (
        <button className="nav-arrow right" onClick={() => onNavigate('next')}>&rsaquo;</button>
      )}

      {/* Bottom variant info */}
      {tab === 'view' && activeVariant && (
        <div className="detail-bottom">
          <span>{activeVariant.model}</span>
          <span>{activeVariant.width}&times;{activeVariant.height}</span>
          <span>{(activeVariant.fileSize / 1024).toFixed(0)} KB</span>
          {activeVariant.prompt && (
            <span className="detail-prompt">{activeVariant.prompt.slice(0, 120)}</span>
          )}
        </div>
      )}

      {/* Costume frame browser */}
      {tab === 'view' && isCharacter && (
        <div className="frame-browser">
          <div className="frame-controls">
            <button className="detail-btn-sm" onClick={() => setActiveFrame(f => Math.max(0, f - 1))} disabled={activeFrame === 0}>&lsaquo;</button>
            <button className="detail-btn-sm" onClick={() => setPlaying(p => !p)}>
              {playing ? 'Pause' : 'Play'}
            </button>
            <button className="detail-btn-sm" onClick={() => setActiveFrame(f => Math.min(frames.length - 1, f + 1))} disabled={activeFrame === frames.length - 1}>&rsaquo;</button>
            <span className="frame-counter">Frame {activeFrame + 1} / {frames.length}</span>

            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
              {hasUpscaled && (
                <button
                  className={`detail-btn-sm ${showUpscaled ? 'active' : ''}`}
                  onClick={() => setShowUpscaled(v => !v)}
                >
                  {showUpscaled ? 'HD 3x' : 'Original'}
                </button>
              )}
              <button
                className="detail-btn-sm"
                onClick={async () => {
                  if (!asset.metadata?.akosId) return;
                  setUpscaling(true);
                  try {
                    await upscaleCostume(asset.metadata.akosId as string);
                    const data = await getCostumeFrames(asset.metadata.akosId as string);
                    setFrames(data.frames);
                    setHasUpscaled(data.hasUpscaled);
                    setShowUpscaled(true);
                  } catch (err) {
                    alert('Upscale failed: ' + String(err));
                  } finally {
                    setUpscaling(false);
                  }
                }}
                disabled={upscaling}
              >
                {upscaling ? 'Upscaling...' : hasUpscaled ? 'Re-upscale' : 'Upscale 3x'}
              </button>
            </div>
          </div>
          <div className="frame-strip" ref={frameStripRef}>
            {frames.map((f, i) => (
              <div
                key={f.frame}
                className={`frame-thumb ${i === activeFrame ? 'active' : ''}`}
                onClick={() => { setActiveFrame(i); setPlaying(false); }}
              >
                <img src={f.url} alt={`Frame ${f.frame}`} loading="lazy" />
              </div>
            ))}
          </div>
        </div>
      )}
      {editing && <PngEditor src={editing.src} filename={editing.filename}
        onSaved={() => { setImageRevision(Date.now()); onRefresh(); }} onClose={() => setEditing(null)} />}
    </div>
  );
}
