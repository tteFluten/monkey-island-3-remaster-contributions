import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { assetsRouter } from './routes/assets.js';
import { jobsRouter } from './routes/jobs.js';
import { exportRouter } from './routes/export.js';
import { scenesRouter } from './routes/scenes.js';
import { projectRouter } from './routes/project.js';
import { extractRouter } from './routes/extract.js';
import { ensureDirectories } from './services/files.js';
import { setProjectRoot } from './services/manifest.js';
import { PlaytestService } from './services/playtest.js';
import { createPlaytestRouter } from './routes/playtest.js';
import { TopazOutputs } from './services/topaz.js';
import { AssetEdits } from './services/asset_edits.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = process.env.MI3_PROJECT_ROOT || path.resolve(__dirname, __dirname.includes('/dist/') ? '../../../..' : '../..');

setProjectRoot(PROJECT_ROOT);

const app = express();
const PORT = Number(process.env.PORT || 5201);
const assetEdits = new AssetEdits(PROJECT_ROOT);
const playtest = new PlaytestService(PROJECT_ROOT, () => assetEdits.installPending());
const topaz = new TopazOutputs(PROJECT_ROOT);

app.use(express.json({ limit: '50mb' }));

// Serve extracted/upscaled images statically
app.use('/files/extracted', express.static(path.join(PROJECT_ROOT, 'extracted')));
app.use('/files/upscaled', express.static(path.join(PROJECT_ROOT, 'upscaled')));
app.use('/files/previews', express.static(path.join(PROJECT_ROOT, 'previews')));
app.use('/files/output', express.static(path.join(PROJECT_ROOT, 'output')));

// API routes
app.use('/api/playtest', createPlaytestRouter(playtest));
app.post('/api/asset-edits', async (req, res) => {
  const local = ['127.0.0.1', 'localhost', '[::1]'];
  try {
    if (!local.includes(req.hostname) || (req.get('origin') && !local.includes(new URL(req.get('origin')!).hostname))) {
      res.status(403).json({ error: 'Local access only' }); return;
    }
    if (!req.is('application/json')) { res.status(415).json({ error: 'JSON request required' }); return; }
    res.json(await assetEdits.replace(req.body ?? {}));
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Could not replace the asset';
    res.status(message.includes('changed since') ? 409 : 400).json({ error: message });
  }
});
app.get('/api/topaz', async (req, res) => {
  try {
    res.setHeader('Cache-Control', 'no-store');
    res.json(await topaz.snapshot(String(req.query.group ?? ''), String(req.query.q ?? ''), Number(req.query.page ?? 1), Number(req.query.room ?? 0)));
  } catch { res.status(500).json({ error: 'Could not read batch outputs. Try again in a moment.' }); }
});
app.use('/api/project', projectRouter);
app.use('/api/scenes', scenesRouter);
app.use('/api/assets', assetsRouter);
app.use('/api/jobs', jobsRouter);
app.use('/api/export', exportRouter);
app.use('/api/extract', extractRouter);

// Health check
app.get('/api/health', (_req, res) => {
  res.json({ ok: true, projectRoot: PROJECT_ROOT });
});

async function start() {
  await ensureDirectories(PROJECT_ROOT);
  await playtest.init();
  const server = app.listen(PORT, '127.0.0.1', () => {
    console.log(`MI3 Remaster server running at http://localhost:${PORT}`);
    console.log(`Project root: ${PROJECT_ROOT}`);
  });
  let stopping = false;
  const shutdown = async () => {
    if (stopping) return;
    stopping = true;
    await playtest.dispose();
    server.close();
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

start().catch(console.error);
