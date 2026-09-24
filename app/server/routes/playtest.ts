import { Router, type Request, type Response } from 'express';
import { PlaytestService } from '../services/playtest.js';

export function createPlaytestRouter(service: PlaytestService) {
  const router = Router();
  router.use((req, res, next) => {
    const origin = req.get('origin');
    const host = req.hostname;
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(host)) return res.status(403).json({ error: 'Local access only' });
    if (origin) {
      try { if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(origin).hostname)) return res.status(403).json({ error: 'Local origin required' }); }
      catch { return res.status(403).json({ error: 'Invalid origin' }); }
    }
    if (req.method !== 'GET' && !req.is('application/json')) return res.status(415).json({ error: 'JSON request required' });
    next();
  });
  const endpoint = (fn: (req: Request) => Promise<unknown>) => async (req: Request, res: Response) => {
    try { res.json((await fn(req)) ?? { ok: true }); }
    catch (error) { res.status(400).json({ error: error instanceof Error ? error.message : String(error) }); }
  };
  router.get('/', endpoint(() => service.snapshot()));
  router.put('/settings', endpoint(req => service.settings(req.body)));
  router.post('/discs', endpoint(() => service.importDiscs()));
  router.post('/build', endpoint(() => service.buildEngine()));
  router.get('/scan', endpoint(() => service.scan()));
  router.post('/import', endpoint(req => service.importBackgrounds(req.body.items)));
  router.put('/selection', endpoint(req => service.select(req.body.room, req.body.variantId)));
  router.post('/launch', endpoint(req => service.launch(req.body.resume === true)));
  router.post('/stop', endpoint(() => service.stop()));
  router.post('/jump', endpoint(req => service.jump(req.body.room)));
  router.post('/apply', endpoint(req => service.apply(req.body.room)));
  router.get('/events', (_req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders();
    const send = (status: unknown) => res.write(`data: ${JSON.stringify(status)}\n\n`);
    send(service.status);
    service.on('status', send);
    const heartbeat = setInterval(() => res.write(': heartbeat\n\n'), 15000);
    res.on('close', () => { clearInterval(heartbeat); service.off('status', send); });
  });
  return router;
}
