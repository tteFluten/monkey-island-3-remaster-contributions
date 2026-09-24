// Read only validated local SVGs. Rasterize each scale directly from its vectors.
import sharp from '../app/node_modules/sharp/lib/index.js';
import fs from 'node:fs/promises';
const [input, output, width, height] = process.argv.slice(2);
const svg = await fs.readFile(input);
await sharp(svg, { density: 432, limitInputPixels: 100_000_000 })
  .resize(Number(width), Number(height), { fit: 'fill' }).png().toFile(output);
