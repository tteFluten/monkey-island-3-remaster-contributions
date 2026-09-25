import type { Variant } from './types';

export interface PlaytestSettings {
  disc1: string;
  disc2: string;
  backgroundFolder: string;
  characterPack: 'topaz' | 'topaz-crisp' | 'quiver' | 'original';
}
export interface PlaytestRoom {
  room: number;
  sceneId: string;
  assetId: string;
  name: string;
  originalPath: string;
  width: number;
  height: number;
  variants: Variant[];
  selectedVariantId: string | null;
}
export interface ImportCandidate {
  file: string;
  room: number | null;
  width: number;
  height: number;
  error?: string;
}
export interface EngineState {
  protocol: number;
  ready: boolean;
  room: number;
  commandId: number;
  error: string;
  backgroundLoaded: boolean;
  width: number;
  height: number;
  aspectRatio?: 43 | 169;
  drawableWidth?: number;
  drawableHeight?: number;
  renderBackend?: 'opengl-shaders' | 'cpu-effects';
  waterBackend?: 'opengl-shader' | 'original-overlays';
  presentationIntervalMs?: number;
  presentationFps?: number;
  renderCpuMs?: number;
  cameraTop?: number;
  outputWidth?: number;
  outputHeight?: number;
  viewportWidth?: number;
  viewportHeight?: number;
  cameraLeft?: number;
  mouseRoomX?: number;
  mouseRoomY?: number;
}
export interface PlaytestStatus {
  running: boolean;
  busy: string | null;
  gameReady: boolean;
  engineReady: boolean;
  engine: EngineState | null;
  logs: string[];
  error: string | null;
}
export interface PlaytestSnapshot {
  settings: PlaytestSettings;
  rooms: PlaytestRoom[];
  status: PlaytestStatus;
  characterPacks: { topaz: number; 'topaz-crisp': number; quiver: number };
}
export const PLAYTEST_SCALE = 4;
