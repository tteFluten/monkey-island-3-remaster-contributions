import { Router } from 'express';
import multer from 'multer';
import path from 'path';
import fs from 'fs/promises';
import { fileURLToPath } from 'url';
import sharp from 'sharp';
import {
  addAsset,
  addVariant,
  updateVariantReview,
  approveVariant,
  getSceneManifest,
} from '../services/manifest.js';
import { hashBuffer } from '../services/files.js';
import type { AssetType } from '../../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../..');

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 100 * 1024 * 1024 } });

export const assetsRouter = Router();

// Import an original asset
assetsRouter.post('/import', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: 'No file uploaded' });

    const { sceneId, name, type, metadata } = req.body;
    if (!sceneId || !name || !type) {
      return res.status(400).json({ error: 'sceneId, name, type required' });
    }

    const buffer = req.file.buffer;
    const hash = await hashBuffer(buffer);

    // Get image dimensions
    const meta = await sharp(buffer).metadata();
    const width = meta.width || 0;
    const height = meta.height || 0;

    // Save to extracted/
    const ext = req.file.originalname.split('.').pop() || 'png';
    const filename = `${sceneId}_${name.replace(/[^a-zA-Z0-9_-]/g, '_')}.${ext}`;
    const relPath = path.join('extracted', filename);
    await fs.writeFile(path.join(PROJECT_ROOT, relPath), buffer);

    const asset = await addAsset(sceneId, {
      name,
      type: type as AssetType,
      originalPath: relPath,
      originalHash: hash,
      width,
      height,
      metadata: metadata ? JSON.parse(metadata) : undefined,
    });

    res.json(asset);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Import a variant (manual upload, not from ImageLab)
assetsRouter.post('/variant/import', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: 'No file uploaded' });

    const { sceneId, assetId, prompt, model, tool } = req.body;
    if (!sceneId || !assetId) {
      return res.status(400).json({ error: 'sceneId, assetId required' });
    }

    const buffer = req.file.buffer;
    const meta = await sharp(buffer).metadata();

    const ext = req.file.originalname.split('.').pop() || 'png';
    const filename = `${assetId}_v${Date.now()}.${ext}`;
    const relPath = path.join('upscaled', filename);
    await fs.writeFile(path.join(PROJECT_ROOT, relPath), buffer);

    const variant = await addVariant(sceneId, {
      assetId,
      filePath: relPath,
      width: meta.width || 0,
      height: meta.height || 0,
      mimeType: req.file.mimetype,
      fileSize: buffer.length,
      tool: tool || 'manual-import',
      model: model || 'manual',
      prompt: prompt || '',
      params: {},
      references: [],
    });

    res.json(variant);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Update variant review status
assetsRouter.patch('/:sceneId/variants/:variantId/review', async (req, res) => {
  try {
    const { reviewStatus, reviewNotes } = req.body;
    const variant = await updateVariantReview(
      req.params.sceneId,
      req.params.variantId,
      reviewStatus,
      reviewNotes
    );
    res.json(variant);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Approve a variant for an asset
assetsRouter.post('/:sceneId/assets/:assetId/approve/:variantId', async (req, res) => {
  try {
    const result = await approveVariant(
      req.params.sceneId,
      req.params.assetId,
      req.params.variantId
    );
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Get asset image file
assetsRouter.get<{ 0: string }>('/file/*', async (req, res) => {
  try {
    const relativePath = req.params[0];
    const filePath = path.join(PROJECT_ROOT, relativePath);
    // Security: ensure path is within project
    if (!filePath.startsWith(PROJECT_ROOT + path.sep)) {
      return res.status(403).json({ error: 'Access denied' });
    }
    res.sendFile(filePath);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});
