// Read only validated local SVGs. Rasterize each scale directly from its vectors.
import sharp from '../app/node_modules/sharp/lib/index.js';
import fs from 'node:fs/promises';
const [input, output, width, height] = process.argv.slice(2);
const svg = await fs.readFile(input);
// 432 dpi as before; wide room-sized canvases lower it just enough to stay under the pixel limit.
const attr = name => Number((svg.toString().match(new RegExp(`<svg[^>]*\\s${name}="([\\d.]+)`)) || [])[1]) || 0;
const area = attr('width') * attr('height') * 36;
const density = area > 100_000_000 ? 72 * 6 * Math.sqrt(100_000_000 / area) * 0.99 : 432;
await sharp(svg, { density, limitInputPixels: 100_000_000 })
  .resize(Number(width), Number(height), { fit: 'fill' }).png().toFile(output);
