import { Router } from 'express';
import path from 'path';
import fs from 'fs/promises';
import { fileURLToPath } from 'url';
import sharp from 'sharp';
import {
  createJob,
  updateJob,
  addVariant,
  getSceneManifest,
} from '../services/manifest.js';
import { callImageLabGenerate, getMcpClient } from '../services/mcp.js';
import type { GenerateRequest } from '../../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../..');

export const jobsRouter = Router();

// SSE endpoint for job status updates
const jobListeners = new Map<string, Set<(data: string) => void>>();

function notifyJobUpdate(jobId: string, data: unknown) {
  const listeners = jobListeners.get(jobId);
  if (listeners) {
    const msg = JSON.stringify(data);
    for (const listener of listeners) {
      listener(msg);
    }
  }
}

// Watch a job via SSE
jobsRouter.get('/:jobId/events', (req, res) => {
  const { jobId } = req.params;
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  });

  const send = (data: string) => {
    res.write(`data: ${data}\n\n`);
  };

  if (!jobListeners.has(jobId)) {
    jobListeners.set(jobId, new Set());
  }
  jobListeners.get(jobId)!.add(send);

  req.on('close', () => {
    jobListeners.get(jobId)?.delete(send);
    if (jobListeners.get(jobId)?.size === 0) {
      jobListeners.delete(jobId);
    }
  });
});

// Start a generation job
jobsRouter.post('/generate', async (req, res) => {
  try {
    const body = req.body as GenerateRequest;
    const { assetId, sceneId, prompt, model, aspectRatio, imageSize, references, sourceVariantId } = body;

    if (!assetId || !sceneId || !prompt) {
      return res.status(400).json({ error: 'assetId, sceneId, prompt required' });
    }

    // Create job record
    const job = await createJob(sceneId, {
      assetId,
      tool: 'imagelab-generate',
      model: model || 'gemini-3.1-flash-image-preview',
      prompt,
      params: { aspect_ratio: aspectRatio || '4:3', image_size: imageSize || '4K' },
      references: references || [],
      sourceVariantId,
    });

    // Return immediately, process in background
    res.json(job);

    // Execute generation asynchronously
    executeJob(job.id, sceneId, body).catch(err => {
      console.error(`Job ${job.id} failed:`, err);
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

async function executeJob(jobId: string, sceneId: string, req: GenerateRequest) {
  try {
    // Update status: sending
    await updateJob(sceneId, jobId, { status: 'sending', startedAt: new Date().toISOString() });
    notifyJobUpdate(jobId, { status: 'sending' });

    // Build reference images
    const images: { base64: string; label?: string }[] = [];
    const manifest = await getSceneManifest(sceneId);

    for (const ref of (req.references || [])) {
      const asset = manifest.assets[ref.assetId];
      if (!asset) continue;

      // Read from source variant or original
      let filePath: string;
      if (req.sourceVariantId && manifest.variants[req.sourceVariantId]) {
        filePath = path.join(PROJECT_ROOT, manifest.variants[req.sourceVariantId].filePath);
      } else {
        filePath = path.join(PROJECT_ROOT, asset.originalPath);
      }

      const buffer = await fs.readFile(filePath);
      images.push({
        base64: buffer.toString('base64'),
        label: ref.label,
      });
    }

    // Update status: generating
    await updateJob(sceneId, jobId, { status: 'generating' });
    notifyJobUpdate(jobId, { status: 'generating' });

    // Call ImageLab (image_size only for Gemini models)
    const isGemini = req.model?.startsWith('gemini');
    const result = await callImageLabGenerate({
      prompt: req.prompt,
      images: images.length > 0 ? images : undefined,
      model: req.model,
      aspect_ratio: req.aspectRatio,
      image_size: isGemini ? (req.imageSize || '4K') : undefined,
    });

    // Update status: saving
    await updateJob(sceneId, jobId, { status: 'saving' });
    notifyJobUpdate(jobId, { status: 'saving' });

    // Determine file extension from MIME
    const extMap: Record<string, string> = {
      'image/png': 'png',
      'image/jpeg': 'jpg',
      'image/webp': 'webp',
    };
    const ext = extMap[result.mimeType] || 'png';
    const filename = `${req.assetId}_${jobId}.${ext}`;
    const relPath = path.join('upscaled', filename);
    await fs.writeFile(path.join(PROJECT_ROOT, relPath), result.imageData);

    // Get actual dimensions
    const meta = await sharp(result.imageData).metadata();

    // Create variant record
    const variant = await addVariant(sceneId, {
      assetId: req.assetId,
      filePath: relPath,
      width: meta.width || 0,
      height: meta.height || 0,
      mimeType: result.mimeType,
      fileSize: result.imageData.length,
      jobId,
      sourceVariantId: req.sourceVariantId,
      tool: 'imagelab-generate',
      model: req.model || 'gemini-3.1-flash-image-preview',
      prompt: req.prompt,
      params: { aspect_ratio: req.aspectRatio, image_size: req.imageSize },
      references: req.references || [],
    });

    // Update job: completed
    await updateJob(sceneId, jobId, {
      status: 'completed',
      resultVariantId: variant.id,
      completedAt: new Date().toISOString(),
    });
    notifyJobUpdate(jobId, { status: 'completed', variantId: variant.id });

  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    await updateJob(sceneId, jobId, {
      status: 'failed',
      error: errorMsg,
      completedAt: new Date().toISOString(),
    });
    notifyJobUpdate(jobId, { status: 'failed', error: errorMsg });
  }
}

// Check MCP connection
jobsRouter.get('/mcp/status', async (_req, res) => {
  try {
    await getMcpClient();
    res.json({ connected: true });
  } catch (err) {
    res.json({ connected: false, error: String(err) });
  }
});

// Get all jobs for a scene
jobsRouter.get('/scene/:sceneId', async (req, res) => {
  try {
    const manifest = await getSceneManifest(req.params.sceneId);
    res.json(Object.values(manifest.jobs));
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});
