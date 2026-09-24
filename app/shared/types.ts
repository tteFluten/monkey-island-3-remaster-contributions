// Data model for MI3 Remaster production app

export const SCHEMA_VERSION = 1;

export type AssetType = 'background' | 'character' | 'object' | 'interface' | 'animation' | 'cinematic';
export type ReviewStatus = 'unreviewed' | 'needs-correction' | 'approved';
export type EngineStatus = 'untested' | 'verified' | 'has-issues';
export type JobStatus = 'pending' | 'sending' | 'generating' | 'saving' | 'completed' | 'failed' | 'cancelled';

export interface Project {
  schemaVersion: number;
  id: string;
  name: string;
  source: 'demo' | 'full';
  createdAt: string;
  updatedAt: string;
  scenes: string[]; // scene IDs
}

export interface Scene {
  id: string;
  name: string;
  roomNumber?: number;
  description?: string;
  assets: string[]; // asset IDs
}

export interface Asset {
  id: string;
  sceneId: string;
  type: AssetType;
  name: string;
  originalPath: string; // relative to project root
  originalHash: string; // SHA-256
  width: number;
  height: number;
  frameCount?: number; // for animations
  frameDurationMs?: number;
  metadata?: Record<string, unknown>; // SCUMM-specific: room number, object ID, z-plane, etc.
  variants: string[]; // variant IDs, ordered by creation
  approvedVariantId?: string;
  createdAt: string;
}

export interface Variant {
  id: string;
  assetId: string;
  filePath: string; // relative to project root
  width: number;
  height: number;
  mimeType: string;
  fileSize: number;
  jobId?: string; // generation job that produced this
  sourceVariantId?: string; // if regenerated from another variant
  // Traceability
  tool: string; // e.g. 'imagelab-generate'
  model: string;
  prompt: string;
  params: Record<string, unknown>; // aspect_ratio, image_size, etc.
  references: { position: number; assetId: string; label?: string }[];
  createdAt: string;
  // Review
  reviewStatus: ReviewStatus;
  engineStatus: EngineStatus;
  reviewNotes?: string;
}

export interface GenerationJob {
  id: string;
  assetId: string;
  status: JobStatus;
  tool: string;
  model: string;
  prompt: string;
  params: Record<string, unknown>;
  references: { position: number; assetId: string; label?: string }[];
  sourceVariantId?: string;
  resultVariantId?: string;
  error?: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

export interface SceneManifest {
  schemaVersion: number;
  scene: Scene;
  assets: Record<string, Asset>;
  variants: Record<string, Variant>;
  jobs: Record<string, GenerationJob>;
}

// API types

export interface ImportAssetRequest {
  sceneId: string;
  name: string;
  type: AssetType;
  metadata?: Record<string, unknown>;
  // File sent as multipart
}

export interface GenerateRequest {
  assetId: string;
  sceneId: string;
  prompt: string;
  model: string;
  aspectRatio: string;
  imageSize: string;
  references: { position: number; assetId: string; label?: string }[];
  sourceVariantId?: string;
}

export interface UpdateReviewRequest {
  reviewStatus: ReviewStatus;
  reviewNotes?: string;
}

export interface UpdateEngineStatusRequest {
  engineStatus: EngineStatus;
}
