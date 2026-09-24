import fs from 'fs/promises';
import path from 'path';
import crypto from 'crypto';

export async function ensureDirectories(projectRoot: string) {
  const dirs = ['extracted', 'upscaled', 'previews', 'output', 'data', 'data/scenes'];
  for (const dir of dirs) {
    await fs.mkdir(path.join(projectRoot, dir), { recursive: true });
  }
}

export async function hashFile(filePath: string): Promise<string> {
  const data = await fs.readFile(filePath);
  return crypto.createHash('sha256').update(data).digest('hex');
}

export async function hashBuffer(buffer: Buffer): Promise<string> {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

/** Atomic JSON write: write to temp, then rename */
export async function writeJsonAtomic(filePath: string, data: unknown) {
  const tmp = filePath + '.tmp.' + Date.now();
  await fs.writeFile(tmp, JSON.stringify(data, null, 2), 'utf-8');
  await fs.rename(tmp, filePath);
}

export async function readJsonSafe<T>(filePath: string, fallback: T): Promise<T> {
  try {
    const raw = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}
