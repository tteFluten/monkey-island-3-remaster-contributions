import { Router } from 'express';
import { getProject } from '../services/manifest.js';
import { isMcpConnected } from '../services/mcp.js';

export const projectRouter = Router();

projectRouter.get('/', async (_req, res) => {
  try {
    const project = await getProject();
    res.json({ project, mcpConnected: isMcpConnected() });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});
