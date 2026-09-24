import { Router } from 'express';
import path from 'path';
import fs from 'fs/promises';
import { fileURLToPath } from 'url';
import { getSceneManifest, getAllScenes } from '../services/manifest.js';
import { writeJsonAtomic } from '../services/files.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../..');

export const exportRouter = Router();

// Export approved variants for a scene
exportRouter.post('/scene/:sceneId', async (req, res) => {
  try {
    const manifest = await getSceneManifest(req.params.sceneId);
    const exported: { assetId: string; assetName: string; variantId: string; filePath: string }[] = [];

    const exportDir = path.join(PROJECT_ROOT, 'output', manifest.scene.name.replace(/[^a-zA-Z0-9_-]/g, '_'));
    await fs.mkdir(exportDir, { recursive: true });

    for (const [assetId, asset] of Object.entries(manifest.assets)) {
      if (!asset.approvedVariantId) continue;
      const variant = manifest.variants[asset.approvedVariantId];
      if (!variant) continue;

      const srcPath = path.join(PROJECT_ROOT, variant.filePath);
      const ext = variant.filePath.split('.').pop() || 'png';
      const destName = `${asset.name.replace(/[^a-zA-Z0-9_-]/g, '_')}.${ext}`;
      const destPath = path.join(exportDir, destName);

      await fs.copyFile(srcPath, destPath);
      exported.push({ assetId, assetName: asset.name, variantId: variant.id, filePath: destName });
    }

    // Write export manifest
    const exportManifest = {
      scene: manifest.scene.name,
      sceneId: req.params.sceneId,
      exportedAt: new Date().toISOString(),
      assets: exported,
    };
    await writeJsonAtomic(path.join(exportDir, 'manifest.json'), exportManifest);

    res.json({ exportDir: path.relative(PROJECT_ROOT, exportDir), assets: exported });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});
