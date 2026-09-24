import path from 'path';
import { v4 as uuid } from 'uuid';
import type {
  Project, Scene, Asset, Variant, GenerationJob,
  SceneManifest, AssetType, ReviewStatus, EngineStatus
} from '../../shared/types.js';
import { SCHEMA_VERSION } from '../../shared/types.js';
import { writeJsonAtomic, readJsonSafe } from './files.js';

let PROJECT_ROOT = '';

export function setProjectRoot(root: string) {
  PROJECT_ROOT = root;
}

function projectPath() {
  return path.join(PROJECT_ROOT, 'data', 'project.json');
}

function scenePath(sceneId: string) {
  return path.join(PROJECT_ROOT, 'data', 'scenes', `${sceneId}.json`);
}

// --- Project ---

export async function getProject(): Promise<Project> {
  return readJsonSafe<Project>(projectPath(), {
    schemaVersion: SCHEMA_VERSION,
    id: 'mi3-demo',
    name: 'Monkey Island 3 — Demo Remaster',
    source: 'demo',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    scenes: [],
  });
}

export async function saveProject(project: Project) {
  project.updatedAt = new Date().toISOString();
  await writeJsonAtomic(projectPath(), project);
}

// --- Scenes ---

export async function getSceneManifest(sceneId: string): Promise<SceneManifest> {
  return readJsonSafe<SceneManifest>(scenePath(sceneId), {
    schemaVersion: SCHEMA_VERSION,
    scene: { id: sceneId, name: sceneId, assets: [] },
    assets: {},
    variants: {},
    jobs: {},
  });
}

export async function saveSceneManifest(sceneId: string, manifest: SceneManifest) {
  await writeJsonAtomic(scenePath(sceneId), manifest);
}

export async function createScene(name: string, roomNumber?: number, description?: string): Promise<Scene> {
  const scene: Scene = {
    id: uuid(),
    name,
    roomNumber,
    description,
    assets: [],
  };
  const manifest: SceneManifest = {
    schemaVersion: SCHEMA_VERSION,
    scene,
    assets: {},
    variants: {},
    jobs: {},
  };
  await saveSceneManifest(scene.id, manifest);

  const project = await getProject();
  project.scenes.push(scene.id);
  await saveProject(project);

  return scene;
}

export async function getAllScenes(): Promise<SceneManifest[]> {
  const project = await getProject();
  const manifests: SceneManifest[] = [];
  for (const sceneId of project.scenes) {
    manifests.push(await getSceneManifest(sceneId));
  }
  return manifests;
}

// --- Assets ---

export async function addAsset(
  sceneId: string,
  opts: {
    name: string;
    type: AssetType;
    originalPath: string;
    originalHash: string;
    width: number;
    height: number;
    frameCount?: number;
    frameDurationMs?: number;
    metadata?: Record<string, unknown>;
  }
): Promise<Asset> {
  const manifest = await getSceneManifest(sceneId);
  const asset: Asset = {
    id: uuid(),
    sceneId,
    ...opts,
    variants: [],
    createdAt: new Date().toISOString(),
  };
  manifest.assets[asset.id] = asset;
  manifest.scene.assets.push(asset.id);
  await saveSceneManifest(sceneId, manifest);
  return asset;
}

// --- Variants ---

export async function addVariant(
  sceneId: string,
  opts: {
    assetId: string;
    filePath: string;
    width: number;
    height: number;
    mimeType: string;
    fileSize: number;
    jobId?: string;
    sourceVariantId?: string;
    tool: string;
    model: string;
    prompt: string;
    params: Record<string, unknown>;
    references: { position: number; assetId: string; label?: string }[];
  }
): Promise<Variant> {
  const manifest = await getSceneManifest(sceneId);
  const variant: Variant = {
    id: uuid(),
    ...opts,
    createdAt: new Date().toISOString(),
    reviewStatus: 'unreviewed' as ReviewStatus,
    engineStatus: 'untested' as EngineStatus,
  };
  manifest.variants[variant.id] = variant;

  const asset = manifest.assets[opts.assetId];
  if (asset) {
    asset.variants.push(variant.id);
  }

  await saveSceneManifest(sceneId, manifest);
  return variant;
}

export async function updateVariantReview(
  sceneId: string,
  variantId: string,
  status: ReviewStatus,
  notes?: string
) {
  const manifest = await getSceneManifest(sceneId);
  const variant = manifest.variants[variantId];
  if (!variant) throw new Error(`Variant ${variantId} not found`);
  variant.reviewStatus = status;
  if (notes !== undefined) variant.reviewNotes = notes;
  await saveSceneManifest(sceneId, manifest);
  return variant;
}

export async function approveVariant(sceneId: string, assetId: string, variantId: string) {
  const manifest = await getSceneManifest(sceneId);
  const asset = manifest.assets[assetId];
  if (!asset) throw new Error(`Asset ${assetId} not found`);
  const variant = manifest.variants[variantId];
  if (!variant) throw new Error(`Variant ${variantId} not found`);
  variant.reviewStatus = 'approved';
  asset.approvedVariantId = variantId;
  await saveSceneManifest(sceneId, manifest);
  return { asset, variant };
}

// --- Jobs ---

export async function createJob(
  sceneId: string,
  opts: {
    assetId: string;
    tool: string;
    model: string;
    prompt: string;
    params: Record<string, unknown>;
    references: { position: number; assetId: string; label?: string }[];
    sourceVariantId?: string;
  }
): Promise<GenerationJob> {
  const manifest = await getSceneManifest(sceneId);
  const job: GenerationJob = {
    id: uuid(),
    ...opts,
    status: 'pending',
    createdAt: new Date().toISOString(),
  };
  manifest.jobs[job.id] = job;
  await saveSceneManifest(sceneId, manifest);
  return job;
}

export async function updateJob(
  sceneId: string,
  jobId: string,
  updates: Partial<GenerationJob>
) {
  const manifest = await getSceneManifest(sceneId);
  const job = manifest.jobs[jobId];
  if (!job) throw new Error(`Job ${jobId} not found`);
  Object.assign(job, updates);
  await saveSceneManifest(sceneId, manifest);
  return job;
}
