import { useState, useEffect, useCallback } from 'react';
import { getScenes, getProject, syncExtracted, getExtractStats } from './lib/api';
import type { SceneManifest, Asset } from '@shared/types';
import { AssetGrid } from './components/AssetGrid';
import { AssetDetail } from './components/AssetDetail';
import { BatchQueue } from './components/BatchQueue';
import { Playtest } from './components/Playtest';
import { TopazOutputs } from './components/TopazOutputs';

const DEFAULT_PROMPT = `Remaster the original game background in @1 at high resolution. Preserve its exact composition, camera, perspective, object positions, silhouettes, painted cartoon style, palette and lighting. Clean compression and pixelation while faithfully reconstructing existing contours and painted detail. Do not add, remove, move or redesign elements. No photorealism, new text, crop or camera change.`;

function App() {
  type Workspace = 'playtest' | 'library' | 'outputs';
  const readWorkspace = (): Workspace => window.location.hash.split('?')[0] === '#outputs' ? 'outputs' : window.location.hash.split('?')[0] === '#library' ? 'library' : 'playtest';
  const [workspace, updateWorkspace] = useState<Workspace>(readWorkspace);
  function setWorkspace(view: Workspace) { window.location.hash = view; updateWorkspace(view); }
  useEffect(() => {
    const changed = () => updateWorkspace(readWorkspace());
    window.addEventListener('hashchange', changed);
    return () => window.removeEventListener('hashchange', changed);
  }, []);
  const [scenes, setScenes] = useState<SceneManifest[]>([]);
  const [mcpConnected, setMcpConnected] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState<{ asset: Asset; scene: SceneManifest } | null>(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [extractStats, setExtractStats] = useState<{ backgrounds: number; objects: number } | null>(null);

  // Batch queue state
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showBatch, setShowBatch] = useState(false);
  const [batchModel, setBatchModel] = useState('gemini-2.5-flash-image');

  const loadData = useCallback(async () => {
    try {
      const [scenesData, projectData] = await Promise.all([getScenes(), getProject()]);
      setScenes(scenesData);
      setMcpConnected(projectData.mcpConnected);
    } catch (err) {
      console.error('Failed to load:', err);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    getExtractStats().then(s => setExtractStats(s.extracted)).catch(() => {});
  }, []);

  async function handleSync() {
    setSyncing(true);
    try {
      const result = await syncExtracted();
      alert(`Imported ${result.backgrounds} backgrounds + ${result.objects} objects (${result.skipped} already existed, ${result.scenes} new scenes)`);
      await loadData();
    } catch (err) {
      alert('Sync failed: ' + String(err));
    } finally {
      setSyncing(false);
    }
  }

  // Flatten all assets from all scenes
  const allAssets: { asset: Asset; scene: SceneManifest }[] = [];
  for (const scene of scenes) {
    for (const asset of Object.values(scene.assets)) {
      allAssets.push({ asset, scene });
    }
  }

  // Filter and search
  const filtered = allAssets.filter(({ asset }) => {
    if (filter !== 'all' && asset.type !== filter) return false;
    if (search && !asset.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  // Sort: backgrounds first, then objects, then by name
  const typeOrder: Record<string, number> = { background: 0, object: 1, character: 2, interface: 3, animation: 4, cinematic: 5 };
  filtered.sort((a, b) => (typeOrder[a.asset.type] ?? 9) - (typeOrder[b.asset.type] ?? 9) || a.asset.name.localeCompare(b.asset.name));

  // Navigation within filtered list
  const selectedIdx = selectedAsset ? filtered.findIndex(f => f.asset.id === selectedAsset.asset.id) : -1;

  function navigateAsset(dir: 'prev' | 'next') {
    const newIdx = dir === 'prev' ? selectedIdx - 1 : selectedIdx + 1;
    if (newIdx >= 0 && newIdx < filtered.length) {
      setSelectedAsset(filtered[newIdx]);
    }
  }

  function toggleSelect(assetId: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(assetId)) next.delete(assetId);
      else next.add(assetId);
      return next;
    });
  }

  function selectAll() {
    // Select all currently filtered that don't have HD yet
    const ids = filtered.filter(f => f.asset.variants.length === 0).map(f => f.asset.id);
    setSelected(new Set(ids));
  }

  function startBatch() {
    if (selected.size === 0) return;
    setShowBatch(true);
  }

  // Get unique types for filter
  const types = [...new Set(allAssets.map(a => a.asset.type))].sort();

  // Count how many have at least one variant
  const withHD = allAssets.filter(a => a.asset.variants.length > 0).length;

  // Items for batch queue
  const batchItems = filtered.filter(f => selected.has(f.asset.id));

  if (workspace === 'outputs') return <TopazOutputs onLibrary={() => setWorkspace('library')} onPlaytest={() => setWorkspace('playtest')} />;
  if (workspace === 'playtest') return <Playtest onLibrary={() => setWorkspace('library')} onOutputs={() => setWorkspace('outputs')} />;

  return (
    <div className="app-shell">
      {/* Header */}
      <header className="app-topbar">
        <div className="topbar-title">
          <strong>MI3 Remaster</strong>
          <button className="detail-btn" onClick={() => setWorkspace('playtest')}>Playtest</button>
          <button className="detail-btn" onClick={() => setWorkspace('outputs')}>Batch outputs</button>
          <span className="topbar-stats">
            {allAssets.length} assets
            {withHD > 0 && <> &middot; {withHD} with HD</>}
          </span>
        </div>

        <div className="topbar-controls">
          <input
            className="search-input"
            placeholder="Search..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />

          <select
            className="filter-select"
            value={filter}
            onChange={e => setFilter(e.target.value)}
          >
            <option value="all">All types ({allAssets.length})</option>
            {types.map(t => (
              <option key={t} value={t}>
                {t} ({allAssets.filter(a => a.asset.type === t).length})
              </option>
            ))}
          </select>

          <div className="topbar-sep" />

          {/* Select mode toggle */}
          <button
            className={`detail-btn-sm ${selectMode ? 'active' : ''}`}
            onClick={() => { setSelectMode(!selectMode); if (selectMode) setSelected(new Set()); }}
            style={{ fontSize: 11, padding: '4px 10px' }}
          >
            {selectMode ? `${selected.size} selected` : 'Select'}
          </button>

          {selectMode && (
            <>
              <button
                className="detail-btn-sm"
                onClick={selectAll}
                style={{ fontSize: 11, padding: '4px 10px' }}
              >
                All without HD
              </button>

              <select
                className="filter-select"
                value={batchModel}
                onChange={e => setBatchModel(e.target.value)}
                style={{ width: 'auto', fontSize: 11 }}
              >
                <option value="gemini-2.5-flash-image">Gemini 2.5 Flash</option>
                <option value="gemini-3.1-pro-image-preview">Gemini 3.1 Pro</option>
                <option value="gpt-image-2">GPT Image 2</option>
              </select>

              <button
                className="gen-submit"
                onClick={startBatch}
                disabled={selected.size === 0 || !mcpConnected}
                style={{ padding: '4px 14px', fontSize: 11 }}
              >
                Generate {selected.size} assets
              </button>
            </>
          )}

          <div className="topbar-sep" />

          <button
            className="detail-btn-sm"
            onClick={handleSync}
            disabled={syncing}
            style={{ fontSize: 11, padding: '4px 10px' }}
          >
            {syncing ? 'Syncing...' : 'Sync'}
          </button>

          <div className="mcp-status">
            <span className={`mcp-dot ${mcpConnected ? 'connected' : ''}`} />
            <span>ImageLab {mcpConnected ? 'OK' : 'Off'}</span>
          </div>
        </div>
      </header>

      {/* Asset grid */}
      <main className="app-body">
        {filtered.length === 0 ? (
          <div className="empty-msg">
            {allAssets.length === 0 ? (
              <div style={{ textAlign: 'center' }}>
                <p>No assets imported yet.</p>
                {extractStats && (extractStats.backgrounds + extractStats.objects) > 0 ? (
                  <button
                    className="gen-submit"
                    style={{ marginTop: 12 }}
                    onClick={handleSync}
                    disabled={syncing}
                  >
                    {syncing ? 'Importing...' : `Import ${extractStats.backgrounds} backgrounds + ${extractStats.objects} objects`}
                  </button>
                ) : (
                  <p style={{ fontSize: 12, marginTop: 8 }}>Run nutcracker to extract game resources first.</p>
                )}
              </div>
            ) : 'No assets match your search.'}
          </div>
        ) : (
          <AssetGrid
            items={filtered}
            onSelect={setSelectedAsset}
            selected={selected}
            onToggleSelect={toggleSelect}
            selectMode={selectMode}
          />
        )}
      </main>

      {/* Detail modal */}
      {selectedAsset && !showBatch && (
        <AssetDetail
          asset={selectedAsset.asset}
          scene={selectedAsset.scene}
          onClose={() => setSelectedAsset(null)}
          onNavigate={navigateAsset}
          hasPrev={selectedIdx > 0}
          hasNext={selectedIdx < filtered.length - 1}
          onRefresh={loadData}
          mcpConnected={mcpConnected}
        />
      )}

      {/* Batch queue modal */}
      {showBatch && (
        <BatchQueue
          items={batchItems}
          prompt={DEFAULT_PROMPT}
          model={batchModel}
          onClose={() => { setShowBatch(false); setSelectMode(false); setSelected(new Set()); }}
          onRefresh={loadData}
        />
      )}
    </div>
  );
}

export default App;
