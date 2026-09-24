import type {
  Project, Scene, Asset, Variant, GenerationJob,
  SceneManifest, AssetType, GenerateRequest, ReviewStatus,
} from '@shared/types';

const BASE = '/api';

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

// Project
export async function getProject() {
  return fetchJson<{ project: Project; mcpConnected: boolean }>('/project');
}

// Scenes
export async function getScenes() {
  return fetchJson<SceneManifest[]>('/scenes');
}

export async function getScene(id: string) {
  return fetchJson<SceneManifest>(`/scenes/${id}`);
}

export async function createScene(name: string, roomNumber?: number, description?: string) {
  return fetchJson<Scene>('/scenes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, roomNumber, description }),
  });
}

// Assets
export async function importAsset(sceneId: string, file: File, name: string, type: AssetType, metadata?: Record<string, unknown>) {
  const form = new FormData();
  form.append('file', file);
  form.append('sceneId', sceneId);
  form.append('name', name);
  form.append('type', type);
  if (metadata) form.append('metadata', JSON.stringify(metadata));
  return fetchJson<Asset>('/assets/import', { method: 'POST', body: form });
}

export async function importVariant(sceneId: string, assetId: string, file: File, prompt?: string, model?: string) {
  const form = new FormData();
  form.append('file', file);
  form.append('sceneId', sceneId);
  form.append('assetId', assetId);
  if (prompt) form.append('prompt', prompt);
  if (model) form.append('model', model);
  return fetchJson<Variant>('/assets/variant/import', { method: 'POST', body: form });
}

export async function updateReview(sceneId: string, variantId: string, reviewStatus: ReviewStatus, reviewNotes?: string) {
  return fetchJson<Variant>(`/assets/${sceneId}/variants/${variantId}/review`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reviewStatus, reviewNotes }),
  });
}

export async function approveVariant(sceneId: string, assetId: string, variantId: string) {
  return fetchJson<{ asset: Asset; variant: Variant }>(
    `/assets/${sceneId}/assets/${assetId}/approve/${variantId}`,
    { method: 'POST' }
  );
}

// Jobs
export async function startGeneration(req: GenerateRequest) {
  return fetchJson<GenerationJob>('/jobs/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
}

export async function getMcpStatus() {
  return fetchJson<{ connected: boolean; error?: string }>('/jobs/mcp/status');
}

export function subscribeJobEvents(jobId: string, onUpdate: (data: unknown) => void): () => void {
  const es = new EventSource(`${BASE}/jobs/${jobId}/events`);
  es.onmessage = (e) => {
    try {
      onUpdate(JSON.parse(e.data));
    } catch {
      onUpdate(e.data);
    }
  };
  return () => es.close();
}

// Export
export async function exportScene(sceneId: string) {
  return fetchJson<{ exportDir: string; assets: unknown[] }>(`/export/scene/${sceneId}`, { method: 'POST' });
}

// Extraction
export async function syncExtracted() {
  return fetchJson<{ backgrounds: number; objects: number; skipped: number; scenes: number }>(
    '/extract/sync',
    { method: 'POST' }
  );
}

export async function getExtractStats() {
  return fetchJson<{ extracted: { backgrounds: number; objects: number }; imported: number; scenes: number }>(
    '/extract/stats'
  );
}

// Costume frames
export async function getCostumeFrames(akosId: string) {
  return fetchJson<{
    akosId: string;
    hasUpscaled: boolean;
    frames: { file: string; frame: number; url: string; upscaledUrl: string | null }[];
  }>(`/extract/costume-frames/${akosId}`);
}

export async function upscaleCostume(akosId: string, scale = 3) {
  return fetchJson<{ ok: boolean; output: string }>(`/extract/upscale-costume/${akosId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scale }),
  });
}

export async function upscaleAllCostumes(scale = 3) {
  return fetchJson<{ ok: boolean; message: string }>('/extract/upscale-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scale }),
  });
}

// File URL helper
export function assetFileUrl(relativePath: string) {
  return `/api/assets/file/${relativePath}`;
}
