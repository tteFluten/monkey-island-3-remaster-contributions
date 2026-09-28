#!/usr/bin/env node
// Package the supplied painting; use the workshop's exact Sharp export pipeline.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'app/package.json'));
const sharp = require('sharp');
const source = process.argv[2];
if (!source) throw new Error('Usage: node tools/stage_voodoo_exterior.mjs supplied-background.png');
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
const input = await fs.readFile(source);
const sha = hash(input);
if (sha !== '77d0b9f10c76ae10f230f9386c8d032669535b838be69971e66e00f4443f5cb6')
  throw new Error('This layout is registered to the supplied Voodoo exterior painting');
const meta = await sharp(input).metadata();
if (meta.width !== 2560 || meta.height !== 1440) throw new Error('Expected 2560 × 1440');
const manifestPath = path.join(root, 'assets/manifest.json');
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
const master = `assets/masters/backgrounds/${sha}.png`;
const assetId = '36114439-d72e-46aa-b1f1-3d717d53ea36';
const variantId = 'voodoo-exterior-wide-77d0b9f10c76';
const previous = manifest.files.find(r => r.asset_id === 'background-room-29' && r.path !== master);
if (previous) previous.asset_id = 'background-room-29-legacy';
async function register(name, data, fields) {
  const destination = path.join(root, name);
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await fs.writeFile(destination, data);
  const record = { path: name, sha256: hash(data), bytes: data.length, ...fields };
  if (name.endsWith('.png')) {
    const image = await sharp(data).metadata();
    record.image = { width: image.width, height: image.height, mode: image.hasAlpha ? 'RGBA' : 'RGB' };
  }
  const old = manifest.files.find(r => r.path === name);
  if (old) Object.assign(old, record); else manifest.files.push(record);
}
await register(master, input, {
  category: 'masters/backgrounds', source_id: 'user-supplied:0029_voodoo-e-wonder-3-5.png',
  review_status: previous?.review_status ?? 'unreviewed', canonical: true,
  asset_id: 'background-room-29', destination: `upscaled/imported/${sha}.png`
});
const crop = { left: 320, top: 0, width: 1920, height: 1440 };
const center = await sharp(input).extract(crop).resize(2560, 1920, { fit: 'fill', kernel: 'lanczos3' }).ensureAlpha().png().toBuffer();
const wide = await sharp(input).resize(2560, 1440).ensureAlpha().png().toBuffer();
for (const [folder, data, width, height] of [['backgrounds', center, 2560, 1920], ['widescreen', wide, 2560, 1440]]) {
  await register(`assets/runtime/${folder}/bg_0029.png`, data, {
    category: `runtime/${folder}`, source_id: `user-supplied:${sha}`,
    review_status: 'installed-unreviewed', destination: `.playtest/hd/${folder}/bg_0029.png`,
    derived_from: master, transform: { kind: 'background', width, height, source_sha256: sha,
      ...(folder === 'backgrounds' ? { crop } : {}), kernel: 'lanczos3' }
  });
}
await register('assets/runtime/backgrounds/bg_0029.png.stamp', Buffer.from(`${sha}:4:lanczos3:wide-center-v1`), {
  category: 'runtime/backgrounds', source_id: `user-supplied:${sha}`, review_status: 'installed-unreviewed',
  destination: '.playtest/hd/backgrounds/bg_0029.png.stamp'
});
const statePath = 'assets/metadata/workshop-state.json';
const state = JSON.parse(await fs.readFile(path.join(root, statePath), 'utf8'));
const oldVariant = state.variants['070a6f2d-6176-4a01-b514-5f4c69863690'];
state.variants[variantId] = { ...oldVariant, id: variantId, filePath: `upscaled/imported/${sha}.png`,
  width: 2560, height: 1440, fileSize: input.length, tool: 'user-supplied',
  params: { sha256: sha, originalFile: '0029_voodoo-e-wonder-3-5.png',
    replacesVariantId: oldVariant.id, layout: 'voodoo-exterior-v1' },
  createdAt: state.variants[variantId]?.createdAt ?? new Date().toISOString(),
  reviewStatus: oldVariant.reviewStatus, engineStatus: 'untested' };
state.selections[assetId] = variantId;
await register(statePath, Buffer.from(JSON.stringify(state, null, 2) + '\n'), {
  category: 'metadata', source_id: 'snapshot', review_status: 'metadata'
});
const categories = {}, unique = new Map();
for (const row of manifest.files) {
  const category = categories[row.category] ??= { files: 0, bytes: 0 };
  category.files++; category.bytes += row.bytes;
  unique.set(row.sha256, row.bytes);
}
Object.assign(manifest, { categories, logical_bytes: manifest.files.reduce((n, r) => n + r.bytes, 0),
  unique_bytes: [...unique.values()].reduce((a, b) => a + b, 0), updated_at: new Date().toISOString() });
await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
console.log(`Packaged Voodoo exterior: ${master}; previous artwork retained.`);
