import { Router } from 'express';
import path from 'path';
import fs from 'fs/promises';
import { fileURLToPath } from 'url';
import sharp from 'sharp';
import { addAsset, createScene, getAllScenes, getSceneManifest } from '../services/manifest.js';
import { hashBuffer } from '../services/files.js';
import type { AssetType } from '../../shared/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../..');

export const extractRouter = Router();

// Sync all extracted images into the manifest (idempotent)
extractRouter.post('/sync', async (_req, res) => {
  try {
    const extractedDir = path.join(PROJECT_ROOT, 'extracted');
    const results = { backgrounds: 0, objects: 0, costumes: 0, skipped: 0, scenes: 0 };

    // Scan backgrounds
    const bgDir = path.join(extractedDir, 'backgrounds');
    let bgFiles: string[] = [];
    try {
      bgFiles = (await fs.readdir(bgDir)).filter(f => f.endsWith('.png')).sort();
    } catch { /* no backgrounds dir */ }

    // Scan objects
    const objDir = path.join(extractedDir, 'objects');
    let objFiles: string[] = [];
    try {
      objFiles = (await fs.readdir(objDir)).filter(f => f.endsWith('.png')).sort();
    } catch { /* no objects dir */ }

    // Scan costumes (character sprites) - group by AKOS resource, import first frame as representative
    const costumeDir = path.join(extractedDir, 'costumes');
    let costumeFiles: string[] = [];
    try {
      costumeFiles = (await fs.readdir(costumeDir)).filter(f => f.endsWith('.png')).sort();
    } catch { /* no costumes dir */ }

    // Group costume frames by AKOS resource and pick frame_0 as representative
    const costumeGroups = new Map<string, { file: string; room: string; frameCount: number }>();
    for (const f of costumeFiles) {
      const match = f.match(/^(LFLF_(\d+)_AKOS_\d+)_frame_(\d+)\.png$/);
      if (!match) continue;
      const [, akosId, roomStr, frameStr] = match;
      if (!costumeGroups.has(akosId)) {
        costumeGroups.set(akosId, { file: f, room: roomStr, frameCount: 0 });
      }
      costumeGroups.get(akosId)!.frameCount++;
      // Keep frame_0 as representative
      if (frameStr === '0') {
        costumeGroups.get(akosId)!.file = f;
      }
    }

    // Group by room number (prefix before first _)
    const rooms = new Map<string, { bgs: string[]; objs: string[]; costumes: { akosId: string; file: string; room: string; frameCount: number }[] }>();
    for (const f of bgFiles) {
      const room = f.split('_')[0];
      if (!rooms.has(room)) rooms.set(room, { bgs: [], objs: [], costumes: [] });
      rooms.get(room)!.bgs.push(f);
    }
    for (const f of objFiles) {
      const room = f.split('_')[0];
      if (!rooms.has(room)) rooms.set(room, { bgs: [], objs: [], costumes: [] });
      rooms.get(room)!.objs.push(f);
    }
    for (const [akosId, info] of costumeGroups) {
      const room = info.room;
      if (!rooms.has(room)) rooms.set(room, { bgs: [], objs: [], costumes: [] });
      rooms.get(room)!.costumes.push({ akosId, ...info });
    }

    // Load existing scenes by room number
    const existingScenes = await getAllScenes();
    const roomToScene = new Map<number, string>();
    for (const s of existingScenes) {
      if (s.scene.roomNumber) roomToScene.set(s.scene.roomNumber, s.scene.id);
    }

    for (const [roomStr, files] of rooms) {
      const roomNum = parseInt(roomStr, 10);
      if (isNaN(roomNum)) continue;

      // Get or create scene
      let sceneId = roomToScene.get(roomNum);
      if (!sceneId) {
        // Name from first background filename
        const firstName = files.bgs[0] || files.objs[0] || `room_${roomStr}`;
        const sceneName = firstName.replace('.png', '').replace(/^\d+_/, '');
        const scene = await createScene(sceneName, roomNum);
        sceneId = scene.id;
        roomToScene.set(roomNum, sceneId);
        results.scenes++;
      }

      // Get existing hashes to skip duplicates
      const manifest = await getSceneManifest(sceneId);
      const existingHashes = new Set(Object.values(manifest.assets).map(a => a.originalHash));

      // Import backgrounds
      for (const file of files.bgs) {
        const filePath = path.join(bgDir, file);
        const buffer = await fs.readFile(filePath);
        const hash = await hashBuffer(buffer);
        if (existingHashes.has(hash)) { results.skipped++; continue; }
        existingHashes.add(hash);

        const meta = await sharp(buffer).metadata();
        const relPath = path.join('extracted', 'backgrounds', file);

        await addAsset(sceneId, {
          name: file.replace('.png', ''),
          type: 'background' as AssetType,
          originalPath: relPath,
          originalHash: hash,
          width: meta.width || 0,
          height: meta.height || 0,
          metadata: { roomNumber: roomNum, originalFile: file },
        });
        results.backgrounds++;
      }

      // Import objects
      for (const file of files.objs) {
        const filePath = path.join(objDir, file);
        const buffer = await fs.readFile(filePath);
        const hash = await hashBuffer(buffer);
        if (existingHashes.has(hash)) { results.skipped++; continue; }
        existingHashes.add(hash);

        const meta = await sharp(buffer).metadata();
        const relPath = path.join('extracted', 'objects', file);

        await addAsset(sceneId, {
          name: file.replace('.png', ''),
          type: 'object' as AssetType,
          originalPath: relPath,
          originalHash: hash,
          width: meta.width || 0,
          height: meta.height || 0,
          metadata: { roomNumber: roomNum, originalFile: file },
        });
        results.objects++;
      }

      // Import costumes (first frame as representative)
      for (const costume of files.costumes) {
        const filePath = path.join(costumeDir, costume.file);
        let buffer: Buffer;
        try { buffer = await fs.readFile(filePath); } catch { continue; }
        const hash = await hashBuffer(buffer);
        if (existingHashes.has(hash)) { results.skipped++; continue; }
        existingHashes.add(hash);

        const meta = await sharp(buffer).metadata();
        const relPath = path.join('extracted', 'costumes', costume.file);

        await addAsset(sceneId, {
          name: costume.akosId,
          type: 'character' as AssetType,
          originalPath: relPath,
          originalHash: hash,
          width: meta.width || 0,
          height: meta.height || 0,
          frameCount: costume.frameCount,
          metadata: { roomNumber: roomNum, akosId: costume.akosId, frameCount: costume.frameCount },
        });
        results.costumes++;
      }
    }

    res.json(results);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// List costume frames for an AKOS resource
extractRouter.get('/costume-frames/:akosId', async (req, res) => {
  try {
    const { akosId } = req.params;
    const costumeDir = path.join(PROJECT_ROOT, 'extracted', 'costumes');
    const upscaledDir = path.join(PROJECT_ROOT, 'upscaled', 'costumes');
    const files = (await fs.readdir(costumeDir))
      .filter(f => f.startsWith(akosId + '_frame_') && f.endsWith('.png'))
      .sort((a, b) => {
        const na = parseInt(a.match(/_frame_(\d+)\.png$/)?.[1] || '0', 10);
        const nb = parseInt(b.match(/_frame_(\d+)\.png$/)?.[1] || '0', 10);
        return na - nb;
      });

    // Check which frames have upscaled versions
    let upscaledFiles: Set<string> = new Set();
    try {
      const uFiles = await fs.readdir(upscaledDir);
      upscaledFiles = new Set(uFiles.filter(f => f.startsWith(akosId + '_frame_')));
    } catch { /* no upscaled dir yet */ }

    const frames = files.map(f => ({
      file: f,
      frame: parseInt(f.match(/_frame_(\d+)\.png$/)?.[1] || '0', 10),
      url: `/api/assets/file/extracted/costumes/${f}`,
      upscaledUrl: upscaledFiles.has(f) ? `/api/assets/file/upscaled/costumes/${f}` : null,
    }));
    res.json({ akosId, frames, hasUpscaled: upscaledFiles.size > 0 });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Upscale a costume (runs Python script)
extractRouter.post('/upscale-costume/:akosId', async (req, res) => {
  try {
    const { akosId } = req.params;
    const scale = req.body?.scale || 3;
    const { execSync } = await import('child_process');
    const scriptPath = path.join(PROJECT_ROOT, 'tools', 'upscale_costumes.py');
    const result = execSync(
      `python3 "${scriptPath}" "${akosId}" --scale ${scale}`,
      { cwd: PROJECT_ROOT, timeout: 60000 }
    ).toString();
    res.json({ ok: true, output: result.trim() });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Upscale ALL costumes (runs in background)
extractRouter.post('/upscale-all', async (req, res) => {
  try {
    const scale = req.body?.scale || 3;
    const { exec } = await import('child_process');
    const scriptPath = path.join(PROJECT_ROOT, 'tools', 'upscale_costumes.py');
    exec(
      `python3 "${scriptPath}" --scale ${scale}`,
      { cwd: PROJECT_ROOT },
      (err, stdout, stderr) => {
        if (err) console.error('[upscale-all] error:', stderr);
        else console.log('[upscale-all] done:', stdout.trim());
      }
    );
    res.json({ ok: true, message: 'Upscale started in background' });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Stats
extractRouter.get('/stats', async (_req, res) => {
  try {
    const extractedDir = path.join(PROJECT_ROOT, 'extracted');
    let bgs = 0, objs = 0, costumes = 0;
    try { bgs = (await fs.readdir(path.join(extractedDir, 'backgrounds'))).filter(f => f.endsWith('.png')).length; } catch {}
    try { objs = (await fs.readdir(path.join(extractedDir, 'objects'))).filter(f => f.endsWith('.png')).length; } catch {}
    try {
      const costumeFiles = (await fs.readdir(path.join(extractedDir, 'costumes'))).filter(f => f.endsWith('.png'));
      const akosIds = new Set(costumeFiles.map(f => f.replace(/_frame_\d+\.png$/, '')));
      costumes = akosIds.size;
    } catch {}

    const scenes = await getAllScenes();
    const imported = scenes.reduce((s, sc) => s + Object.keys(sc.assets).length, 0);

    res.json({ extracted: { backgrounds: bgs, objects: objs, costumes }, imported, scenes: scenes.length });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});
