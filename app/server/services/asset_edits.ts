import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';

export class AssetEdits {
  constructor(private root: string) {}

  private run(script: string, args: string[], input?: Buffer): Promise<string> {
    return new Promise((resolve, reject) => {
      const child = spawn(path.join(this.root, 'tools/venv/bin/python'), [path.join(this.root, 'tools', script), ...args],
        { cwd: this.root, stdio: ['pipe', 'pipe', 'pipe'] });
      let output = '', errors = '';
      child.stdout.on('data', data => { output += data; });
      child.stderr.on('data', data => { errors += data; });
      child.on('error', reject);
      child.stdin.on('error', () => {}); // A validation error may close stdin early.
      child.on('close', code => code === 0 ? resolve(output) : reject(new Error(errors.trim() || 'Could not save the asset.')));
      child.stdin.end(input);
    });
  }

  async replace(value: { url?: unknown; expected?: unknown; png?: unknown }) {
    if (typeof value.url !== 'string' || typeof value.expected !== 'string' || typeof value.png !== 'string'
      || !/^[a-f0-9]{64}$/.test(value.expected) || value.png.length > 45_000_000
      || !/^[A-Za-z0-9+/]+={0,2}$/.test(value.png)) throw new Error('Invalid PNG replacement request');
    const result = await this.run('asset_edits.py', ['--url', value.url, '--expected', value.expected], Buffer.from(value.png, 'base64'));
    return JSON.parse(result);
  }

  async installPending() {
    const manifestPath = path.join(this.root, 'output/asset-edits/manifest.json');
    const manifest = await fs.readFile(manifestPath, 'utf8').then(JSON.parse).catch((error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') return null; throw error;
    });
    if (!manifest) return;
    const receipt = await fs.readFile(path.join(this.root, '.playtest/draft-install/receipt.json'), 'utf8').then(JSON.parse).catch(() => ({}));
    if (Object.entries(manifest.overrides).some(([source, edit]) => receipt.assets?.[source]?.sha256 !== (edit as { sha256: string }).sha256)) {
      await this.run('install_asset_drafts.py', []);
    }
  }
}
