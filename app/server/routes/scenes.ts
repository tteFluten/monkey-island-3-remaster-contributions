import { Router } from 'express';
import { createScene, getAllScenes, getSceneManifest } from '../services/manifest.js';

export const scenesRouter = Router();

scenesRouter.get('/', async (_req, res) => {
  try {
    const scenes = await getAllScenes();
    res.json(scenes);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

scenesRouter.get('/:id', async (req, res) => {
  try {
    const manifest = await getSceneManifest(req.params.id);
    res.json(manifest);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

scenesRouter.post('/', async (req, res) => {
  try {
    const { name, roomNumber, description } = req.body;
    if (!name) return res.status(400).json({ error: 'name required' });
    const scene = await createScene(name, roomNumber, description);
    res.json(scene);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});
