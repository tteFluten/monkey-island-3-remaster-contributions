import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { spawn, type ChildProcess } from 'node:child_process';
import { EventEmitter, once } from 'node:events';
import sharp from 'sharp';
import { PLAYTEST_SCALE } from '../../shared/playtest.js';
import type { Variant } from '../../shared/types.js';
import type { PlaytestSettings, PlaytestRoom, ImportCandidate, EngineState, PlaytestStatus } from '../../shared/playtest.js';
import { getAllScenes } from './manifest.js';
import { writeJsonAtomic, readJsonSafe, fileExists, hashFile } from './files.js';

export const ENGINE_REVISION = '43c1d07613e3c34b9c8cfc7ab168575212864d48';
export function readAspectRatio(config: string): 43 | 169 {
  let section = '';
  let aspect: 43 | 169 = 43;
  for (const line of config.split(/\r?\n/)) {
    const heading = /^\s*\[([^\]]+)\]\s*$/.exec(line);
    if (heading) section = heading[1];
    const setting = /^\s*hd_aspect_ratio\s*=\s*(.*?)\s*$/.exec(line);
    if (section === 'comi' && setting) aspect = setting[1] === '169' ? 169 : 43;
  }
  return aspect;
}
// Keep the preference written by the original in-game options menu on relaunch.
export function readFontSize(config: string): number {
  let section = '';
  let size = 65;
  for (const line of config.split(/\r?\n/)) {
    const heading = /^\s*\[([^\]]+)\]\s*$/.exec(line);
    if (heading) section = heading[1];
    const setting = /^\s*hd_font_size\s*=\s*(\d+)\s*$/.exec(line);
    if (section === 'comi' && setting) {
      const value = Number(setting[1]);
      size = value >= 25 && value <= 100 && value % 5 === 0 ? value : 65;
    }
  }
  return size;
}
// Depth of field is opt-in: 0 off, 1 low, 2 high (in-game options book).
export function readDepthOfField(config: string): 0 | 1 | 2 {
  let section = '';
  let level: 0 | 1 | 2 = 0;
  for (const line of config.split(/\r?\n/)) {
    const heading = /^\s*\[([^\]]+)\]\s*$/.exec(line);
    if (heading) section = heading[1];
    const setting = /^\s*hd_depth_of_field\s*=\s*(.*?)\s*$/.exec(line);
    if (section === 'comi' && setting) level = setting[1] === '1' ? 1 : setting[1] === '2' ? 2 : 0;
  }
  return level;
}
// Live-tuning hotkey values: blur in tenths of a native pixel (0 = preset),
// edge softness in native pixels, intensity in percent, z-plane depth threshold.
export function readDepthOfFieldTuning(config: string): { blur: number; edge: number; intensity: number; depth: number } {
  const tuning = { blur: 0, edge: 2, intensity: 100, depth: 1 };
  const limits = { blur: [0, 120], edge: [0, 12], intensity: [0, 100], depth: [1, 7] } as const;
  const keys = { hd_dof_blur: 'blur', hd_dof_edge: 'edge', hd_dof_intensity: 'intensity', hd_dof_depth: 'depth' } as const;
  let section = '';
  for (const line of config.split(/\r?\n/)) {
    const heading = /^\s*\[([^\]]+)\]\s*$/.exec(line);
    if (heading) section = heading[1];
    const setting = /^\s*(hd_dof_blur|hd_dof_edge|hd_dof_intensity|hd_dof_depth)\s*=\s*(\d+)\s*$/.exec(line);
    if (section !== 'comi' || !setting) continue;
    const name = keys[setting[1] as keyof typeof keys];
    const value = Number(setting[2]);
    if (value >= limits[name][0] && value <= limits[name][1]) tuning[name] = value;
  }
  return tuning;
}
export function roomFromFilename(name: string): number | null {
  const match = /^(?:bg_)?(\d+)(?:[_ .-]|$)/i.exec(name);
  return match ? Number(match[1]) : null;
}
export function assertAspect(width: number, height: number, originalWidth: number, originalHeight: number) {
  if (!width || !height || Math.abs((width / height) / (originalWidth / originalHeight) - 1) > 0.001) {
    throw new Error(`Proportions must match ${originalWidth} × ${originalHeight}; received ${width} × ${height}. Correct the source image before importing.`);
  }
}
// Extended artwork keeps each standard room in its centered 4:3 area.
// Only the decorative side scenery is presented outside the gameplay surface.
export function wideBackgroundCrop(width: number, height: number, room: Pick<PlaytestRoom, 'room' | 'width' | 'height'>) {
  if (room.room === 87 || room.room === 92 || room.width !== 640 || room.height !== 480 ||
      width <= 0 || height <= 0 || width * 9 !== height * 16) return null;
  const cropWidth = height * 4 / 3;
  return { left: (width - cropWidth) / 2, top: 0, width: cropWidth, height };
}
export function validateSettings(value: unknown): PlaytestSettings {
  if (!value || typeof value !== 'object') throw new Error('Settings are required');
  const result = {} as PlaytestSettings;
  for (const key of ['disc1', 'disc2', 'backgroundFolder'] as const) {
    const item = (value as Record<string, unknown>)[key];
    if (typeof item !== 'string' || !path.isAbsolute(item) || /[\0\r\n]/.test(item)) throw new Error(`${key} must be an absolute local path`);
    result[key] = item;
  }
  const pack = (value as Record<string, unknown>).characterPack ?? 'topaz';
  if (!['topaz', 'topaz-crisp', 'quiver', 'original'].includes(String(pack))) throw new Error('Unknown character pack');
  result.characterPack = pack as PlaytestSettings['characterPack'];
  return result;
}

interface LocalState {
  settings: PlaytestSettings;
  selections: Record<string, string | null>;
  variants: Record<string, Variant>;
}
export class PlaytestService extends EventEmitter {
  readonly local: string;
  private state!: LocalState;
  private child: ChildProcess | null = null;
  private session: string | null = null;
  private commandId = 0;
  private commandPending = false;
  private timer: NodeJS.Timeout | null = null;
  private task: ChildProcess | null = null;
  private pollActive = false;
  private releasing: Promise<void> = Promise.resolve();
  private launchedAt = 0;
  private async claimSession() {
    await this.releasing;
    const lock = path.join(this.local, 'engine.lock');
    try { await fs.mkdir(lock); }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
      const owner = await readJsonSafe<{ serverPid: number; gamePid?: number } | null>(path.join(lock, 'owner.json'), null);
      const alive = (pid?: number) => { if (!pid) return false; try { process.kill(pid, 0); return true; } catch { return false; } };
      if (alive(owner?.serverPid) || alive(owner?.gamePid) || (!owner && Date.now() - (await fs.stat(lock)).mtimeMs < 30000)) {
        throw new Error('Another game session owns this workspace. Close its game window and server before launching again.');
      }
      await fs.rm(lock, { recursive: true, force: true });
      await fs.mkdir(lock);
    }
    await writeJsonAtomic(path.join(lock, 'owner.json'), { serverPid: process.pid });
  }
  private releaseSession() {
    this.releasing = fs.rm(path.join(this.local, 'engine.lock'), { recursive: true, force: true });
    return this.releasing;
  }
  status: PlaytestStatus = { running: false, busy: null, gameReady: false, engineReady: false, engine: null, logs: [], error: null };
  constructor(readonly root: string, private beforeLaunch?: () => Promise<void>) {
    super();
    this.local = path.join(root, '.playtest');
  }
  async init() {
    await fs.mkdir(this.local, { recursive: true });
    const folder = path.join(os.homedir(), 'Desktop/monkey');
    this.state = await readJsonSafe<LocalState>(path.join(this.local, 'state.json'), {
      settings: { disc1: path.join(folder, 'monkey3-1.iso'), disc2: path.join(folder, 'monkey3-2.iso'), backgroundFolder: path.join(folder, '4k'), characterPack: 'topaz' },
      selections: {}, variants: {},
    });
    this.state.settings = validateSettings(this.state.settings);
    await this.checkSetup();
  }
  private async save() { await writeJsonAtomic(path.join(this.local, 'state.json'), this.state); }
  private publish() { this.emit('status', this.status); }
  private log(message: string) {
    for (const line of message.split(/\r?\n/).filter(Boolean)) this.status.logs.push(line.slice(0, 1000));
    this.status.logs = this.status.logs.slice(-100);
    this.publish();
  }
  async checkSetup() {
    const required = ['COMI.LA0', 'COMI.LA1', 'COMI.LA2', ...['MUSDISK1.BUN', 'MUSDISK2.BUN', 'VOXDISK1.BUN', 'VOXDISK2.BUN', 'FONT0.NUT', 'FONT1.NUT', 'FONT2.NUT', 'FONT3.NUT', 'FONT4.NUT'].map(n => `RESOURCE/${n}`)];
    this.status.gameReady = (await Promise.all(required.map(n => fs.stat(path.join(this.local, 'game', n)).then(s => s.isFile() && s.size > 0).catch(() => false)))).every(Boolean);
    this.status.engineReady = await fileExists(this.binary());
  }
  private binary() { return path.join(this.local, 'engine/build/scummvm'); }
  async rooms(): Promise<PlaytestRoom[]> {
    const result: PlaytestRoom[] = [];
    for (const manifest of await getAllScenes()) {
      for (const asset of Object.values(manifest.assets)) {
        if (asset.type !== 'background' || manifest.scene.roomNumber === undefined) continue;
        const variants = [...asset.variants.map(id => manifest.variants[id]).filter(Boolean), ...Object.values(this.state.variants).filter(v => v.assetId === asset.id)];
        result.push({ room: manifest.scene.roomNumber, sceneId: manifest.scene.id, assetId: asset.id, name: manifest.scene.name, originalPath: asset.originalPath, width: asset.width, height: asset.height, variants, selectedVariantId: this.state.selections[asset.id] ?? null });
      }
    }
    return result.sort((a, b) => a.room - b.room);
  }
  private async characterPacks() {
    const count = async (name: string) => (await fs.readdir(path.join(this.local, 'hd', name, 'costumes'), { withFileTypes: true }).catch((error: NodeJS.ErrnoException) => {
      if (error.code === 'ENOENT') return [];
      throw error;
    })).filter(e => e.isFile() && /\.(png|svg)$/i.test(e.name)).length;
    return { topaz: await count('topaz-cannon'), 'topaz-crisp': await count('topaz-crisp'), quiver: await count('quiver-cannon') };
  }
  async snapshot() { return { settings: this.state.settings, rooms: await this.rooms(), status: this.status, characterPacks: await this.characterPacks() }; }
  async settings(value: unknown) {
    if (this.status.busy || this.status.running) throw new Error('Stop the game and wait for the current operation before changing setup');
    this.state.settings = validateSettings(value);
    await this.save();
    return this.state.settings;
  }
  async operation<T>(label: string, action: () => Promise<T>): Promise<T> {
    if (this.status.busy) throw new Error(`Wait for ${this.status.busy}`);
    this.status.busy = label; this.status.error = null; this.publish();
    try { return await action(); }
    catch (error) { this.status.error = String(error); this.log(String(error)); throw error; }
    finally { this.status.busy = null; await this.checkSetup(); this.publish(); }
  }
  private run(command: string, args: string[]): Promise<void> {
    return new Promise((resolve, reject) => {
      const child = spawn(command, args, { cwd: this.root, stdio: ['ignore', 'pipe', 'pipe'] });
      this.task = child;
      child.stdout.on('data', data => this.log(data.toString()));
      child.stderr.on('data', data => this.log(data.toString()));
      child.on('error', reject);
      child.on('close', code => { this.task = null; code === 0 ? resolve() : reject(new Error(`${command} exited with code ${code}. See the activity log.`)); });
    });
  }
  async importDiscs() {
    if (this.child) throw new Error('Stop the game before importing discs');
    return this.operation('Importing discs', () => this.run('python3', [path.join(this.root, 'tools/import_discs.py'), this.state.settings.disc1, this.state.settings.disc2, path.join(this.local, 'game')]));
  }
  async buildEngine() {
    if (this.child) throw new Error('Stop the game before building the engine');
    return this.operation('Building Mac engine', () => this.run('bash', [path.join(this.root, 'tools/build_engine.sh')]));
  }
  async scan(): Promise<ImportCandidate[]> {
    const roomMap = new Map((await this.rooms()).map(r => [r.room, r]));
    const entries = await fs.readdir(this.state.settings.backgroundFolder, { withFileTypes: true });
    const result: ImportCandidate[] = [];
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      if (!entry.isFile() || !/\.(png|jpe?g|webp)$/i.test(entry.name)) continue;
      let candidate: ImportCandidate = { file: entry.name, room: roomFromFilename(entry.name), width: 0, height: 0 };
      if (!roomMap.has(candidate.room!)) candidate.room = null;
      try {
        const meta = await sharp(path.join(this.state.settings.backgroundFolder, entry.name)).metadata();
        candidate.width = meta.width ?? 0; candidate.height = meta.height ?? 0;
      } catch { candidate.error = 'Cannot decode image'; }
      result.push(candidate);
    }
    return result;
  }
  async importBackgrounds(value: unknown) {
    if (!Array.isArray(value) || !value.length) throw new Error('Select at least one image');
    return this.operation('Importing backgrounds', async () => {
      const rooms = new Map((await this.rooms()).map(r => [r.room, r]));
      const scanned = new Map((await this.scan()).map(c => [c.file, c]));
      const used = new Set<number>();
      const items: { room: PlaytestRoom; source: string; hash: string; width: number; height: number }[] = [];
      // Validate the entire batch before copying or changing selections.
      for (const item of value) {
        if (!item || typeof item.file !== 'string' || !Number.isInteger(item.room)) throw new Error('Each image needs a room mapping');
        const candidate = scanned.get(item.file), room = rooms.get(item.room);
        if (!candidate || !room || candidate.error) throw new Error(`Invalid image or room: ${item.file}`);
        if (used.has(room.room)) throw new Error(`Select only one image for room ${room.room}`);
        used.add(room.room);
        if (!wideBackgroundCrop(candidate.width, candidate.height, room))
          assertAspect(candidate.width, candidate.height, room.width, room.height);
        const source = path.join(this.state.settings.backgroundFolder, candidate.file);
        items.push({ room, source, hash: await hashFile(source), width: candidate.width, height: candidate.height });
      }
      let imported = 0, skipped = 0;
      const directory = path.join(this.root, 'upscaled/imported');
      await fs.mkdir(directory, { recursive: true });
      for (const item of items) {
        let variant = Object.values(this.state.variants).find(v => v.assetId === item.room.assetId && v.params.sha256 === item.hash);
        if (variant) skipped++;
        else {
          const relative = `upscaled/imported/${item.hash}${path.extname(item.source).toLowerCase()}`;
          const destination = path.join(this.root, relative);
          await fs.copyFile(item.source, destination);
          variant = { id: crypto.randomUUID(), assetId: item.room.assetId, filePath: relative, width: item.width, height: item.height, mimeType: /\.png$/i.test(relative) ? 'image/png' : /\.webp$/i.test(relative) ? 'image/webp' : 'image/jpeg', fileSize: (await fs.stat(destination)).size, tool: 'folder-import', model: '', prompt: '', params: { sha256: item.hash, originalFile: path.basename(item.source) }, references: [], createdAt: new Date().toISOString(), reviewStatus: 'unreviewed', engineStatus: 'untested' };
          this.state.variants[variant.id] = variant;
          imported++;
        }
        this.state.selections[item.room.assetId] = variant.id;
        await this.save();
        this.log(`Imported room ${item.room.room}: ${path.basename(item.source)}`);
      }
      return { imported, skipped };
    });
  }
  private async room(number: number) {
    if (!Number.isInteger(number)) throw new Error('Room must be an integer');
    const room = (await this.rooms()).find(r => r.room === number);
    if (!room) throw new Error('Unknown room');
    return room;
  }
  async select(number: number, variantId: unknown) {
    if (this.status.busy) throw new Error('Wait for the current operation');
    const room = await this.room(number);
    if (variantId !== null && (typeof variantId !== 'string' || !room.variants.some(v => v.id === variantId))) throw new Error('Unknown variant for this room');
    this.state.selections[room.assetId] = variantId as string | null;
    await this.save();
  }
  private async stageRoom(room: PlaytestRoom) {
    const variant = room.variants.find(v => v.id === room.selectedVariantId);
    const source = path.join(this.root, variant?.filePath ?? room.originalPath);
    const meta = await sharp(source).metadata();
    const crop = variant ? wideBackgroundCrop(meta.width ?? 0, meta.height ?? 0, room) : null;
    if (!crop) assertAspect(meta.width ?? 0, meta.height ?? 0, room.width, room.height);
    const destination = path.join(this.local, `hd/backgrounds/bg_${String(room.room).padStart(4, '0')}.png`);
    const wideDestination = path.join(this.local, `hd/widescreen/bg_${String(room.room).padStart(4, '0')}.png`);
    const stamp = `${await hashFile(source)}:${PLAYTEST_SCALE}:${variant ? 'lanczos3' : 'nearest'}${crop ? ':wide-center-v1' : ''}`;
    const wideExists = await fileExists(wideDestination);
    if (await fileExists(destination) && await fs.readFile(destination + '.stamp', 'utf8').catch(() => '') === stamp && wideExists === !!crop) return;
    await fs.mkdir(path.dirname(destination), { recursive: true });
    const temp = destination + '.tmp';
    const input = sharp(source);
    if (crop) input.extract(crop);
    await input.resize(room.width * PLAYTEST_SCALE, room.height * PLAYTEST_SCALE, { fit: 'fill', kernel: variant ? 'lanczos3' : 'nearest' }).ensureAlpha().png().toFile(temp);
    // Publish the matching full-width art before committing the center/stamp.
    // Switching back to any ordinary variant removes obsolete side scenery.
    if (crop) {
      await fs.mkdir(path.dirname(wideDestination), { recursive: true });
      await sharp(source).resize(2560, 1440).ensureAlpha().png().toFile(wideDestination + '.tmp');
      await fs.rename(wideDestination + '.tmp', wideDestination);
    } else await fs.rm(wideDestination, { force: true });
    await fs.rename(temp, destination);
    await fs.writeFile(destination + '.stamp', stamp);
  }
  async launch(resume = false) {
    if (this.child) throw new Error('The game is already running');
    return this.operation('Preparing game', async () => {
      await this.checkSetup();
      if (!this.status.gameReady || !this.status.engineReady) throw new Error('Import both discs and build the Mac engine first');
      const pack = this.state.settings.characterPack;
      if (pack !== 'original' && !(await this.characterPacks())[pack]) throw new Error(`The ${pack} character pack has not been staged yet. Choose Original or finish preparing that pack.`);
      const resumeSlot = resume && await fileExists(path.join(this.local, 'saves/comi.c01')) ? 1 : 0;
      if (resume && resumeSlot === 0 && !await fileExists(path.join(this.local, 'saves/comi.s00'))) throw new Error('No saved test is available');
      await this.claimSession();
      try {
        await this.beforeLaunch?.();
        for (const room of await this.rooms()) { await this.stageRoom(room); this.log(`Prepared room ${room.room}`); }
        this.session = await fs.mkdtemp(path.join(this.local, 'session-'));
        await fs.chmod(this.session, 0o700);
        const saves = path.join(this.local, 'saves');
        await fs.mkdir(saves, { recursive: true });
        const config = `[scummvm]\nscreenshotpath=${path.join(this.root, '.context')}\nsavepath=${saves}\nmacos_savepath_migrated=true\nvsync=true\nfullscreen=true\ngfx_mode=opengl\nstretch_mode=fit\naspect_ratio=false\nfiltering=true\nlast_window_width=2560\nlast_window_height=1440\ngui_theme=builtin\n\n[comi]\nengineid=scumm\ngameid=comi\npath=${path.join(this.local, 'game')}\nhd_path=${path.join(this.local, 'hd')}\nplaytest_session=${this.session}\nsavepath=${saves}\nsubtitles=true\nhd_trace=false\nhd_gpu_effects=true\n`;
        const configPath = path.join(this.local, 'scummvm.ini');
        const previousConfig = await fs.readFile(configPath, 'utf8').catch(() => '');
        const fontSize = readFontSize(previousConfig);
        const aspect = 169; // Every launch starts in the remaster presentation mode.
        const depthOfField = readDepthOfField(previousConfig);
        const tuning = readDepthOfFieldTuning(previousConfig);
        const displayConfig = config;
        await fs.writeFile(configPath, displayConfig + `playtest_character_pack=${pack}\nplaytest_scale=${PLAYTEST_SCALE}\nhd_font_size=${fontSize}\nhd_aspect_ratio=${aspect}\nhd_depth_of_field=${depthOfField}\nhd_dof_blur=${tuning.blur}\nhd_dof_edge=${tuning.edge}\nhd_dof_intensity=${tuning.intensity}\nhd_dof_depth=${tuning.depth}\nhd_aspect_ui_path=${path.join(this.root, 'extracted/objects')}\nhd_color_grades_path=${path.join(this.root, 'data/color-grades.json')}\n`);
        this.status.engine = null; this.status.error = null;
        const child = spawn(this.binary(), ['--config=' + configPath, '--debuglevel=0', ...(resume ? [`--save-slot=${resumeSlot}`] : []), 'comi'], { cwd: this.session, stdio: ['ignore', 'pipe', 'pipe'] });
        this.child = child; this.status.running = true; this.launchedAt = Date.now();
        const append = (data: Buffer) => { void fs.appendFile(path.join(this.session!, 'engine.log'), data).catch(() => {}); const lines = data.toString().split('\n').filter(l => /HD: loaded|hd_trace|error|warning|playtest/i.test(l)); if (lines.length) this.log(lines.join('\n')); };
        child.stdout?.on('data', append); child.stderr?.on('data', append);
        child.on('error', error => { this.status.error = error.message; this.publish(); });
        child.on('close', async code => {
          await identity.catch(() => {});
          if (this.timer) clearInterval(this.timer);
          this.timer = null; this.child = null; this.status.running = false; this.status.engine = null;
          if (code && !this.status.error) this.status.error = `Game exited with code ${code}. See the activity log.`;
          void fs.rm(path.join(this.local, 'process.json'), { force: true });
          void this.releaseSession();
          this.publish();
        });
        this.timer = setInterval(() => void this.poll(), 250);
        this.publish();
        const identity = writeJsonAtomic(path.join(this.local, 'engine.lock/owner.json'), { serverPid: process.pid, gamePid: child.pid })
          .then(() => writeJsonAtomic(path.join(this.local, 'process.json'), { pid: child.pid, session: this.session }));
        await identity;
      } catch (error) {
        if (this.child) await this.stop();
        else await this.releaseSession();
        throw error;
      }
    });
  }
  private async poll() {
    if (!this.session || this.pollActive || !this.child) return;
    this.pollActive = true;
    try {
      const state = await readJsonSafe<EngineState | null>(path.join(this.session, 'status.json'), null);
      if (state?.protocol === 1) {
        const age = Date.now() - (await fs.stat(path.join(this.session, 'status.json'))).mtimeMs;
        this.status.engine = { ...state, ready: state.ready && age < 2000 };
        this.publish();
      } else if (Date.now() - this.launchedAt > 30000 && !this.status.error) {
        this.status.error = 'The engine has not connected to the editor. Check the game window and activity log, or stop and rebuild the engine.';
        this.publish();
      }
    } catch { /* Atomic status files can disappear during shutdown. */ } finally { this.pollActive = false; }
  }
  private async command(action: 'jump' | 'reload', room: number) {
    if (!this.child || !this.session || !this.status.engine?.ready) throw new Error('Game is not ready. Finish the opening or close the game menu first.');
    if (this.commandPending) throw new Error('A game command is already pending');
    this.commandPending = true;
    const id = ++this.commandId;
    const commandPath = path.join(this.session, 'command.json');
    try {
      await writeJsonAtomic(commandPath, { id, action, room });
      const deadline = Date.now() + 8000;
      while (Date.now() < deadline) {
        if (!this.child) throw new Error('Game closed before acknowledging the command');
        await this.poll();
        if (this.status.engine?.commandId === id) {
          if (this.status.engine.error) throw new Error(this.status.engine.error);
          this.log(`${action === 'jump' ? 'Jumped to' : 'Reloaded'} room ${room}`);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      throw new Error('Game command timed out. Close any cutscene or menu and retry.');
    } finally { await fs.rm(commandPath, { force: true }); this.commandPending = false; }
  }
  async jump(number: number) { await this.room(number); return this.operation('Jumping to room', () => this.command('jump', number)); }
  async apply(number: number) {
    return this.operation('Applying background', async () => {
      const room = await this.room(number);
      await this.stageRoom(room);
      if (this.child && this.status.engine?.room === number) await this.command('reload', number);
      else this.log(`Room ${number} prepared; jump there to see the change`);
    });
  }
  async stop() {
    const child = this.child;
    if (!child) return;
    const closed = once(child, 'close');
    child.kill('SIGTERM');
    const timeout = setTimeout(() => child.kill('SIGKILL'), 3000);
    await closed;
    clearTimeout(timeout);
    while (this.child === child) await new Promise(resolve => setTimeout(resolve, 10));
    await this.releasing;
  }
  async dispose() {
    await this.stop();
    // Disc import owns mount cleanup; let it finish before the server exits.
    if (this.task) await once(this.task, 'close');
  }
}
