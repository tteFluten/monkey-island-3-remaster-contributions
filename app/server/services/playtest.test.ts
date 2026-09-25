import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import sharp from 'sharp';
import { PlaytestService, roomFromFilename, assertAspect, wideBackgroundCrop, validateSettings, readFontSize, readAspectRatio, readDepthOfField, readDepthOfFieldTuning } from './playtest.js';
import { setProjectRoot } from './manifest.js';

test('aspect preference defaults to 4:3 and reads only the COMI section', () => {
  assert.equal(readAspectRatio(''), 43);
  assert.equal(readAspectRatio('[scummvm]\nhd_aspect_ratio=169'), 43);
  assert.equal(readAspectRatio('[comi]\r\nhd_aspect_ratio = 169\r\n[other]\nhd_aspect_ratio=43'), 169);
  for (const value of ['43', '0', '16:9', '169oops', '-169', '']) {
    assert.equal(readAspectRatio(`[comi]\nhd_aspect_ratio=${value}`), 43);
  }
});

test('font size defaults safely and only reads the COMI preference', () => {
  assert.equal(readFontSize(''), 65);
  assert.equal(readFontSize('[scummvm]\nhd_font_size=100\n[another]\nhd_font_size=25'), 65);
  for (const size of [25, 50, 60, 65, 70, 75, 100]) {
    assert.equal(readFontSize(`[comi]\r\nhd_font_size = ${size}\r\n[another]\r\nhd_font_size=25`), size);
  }
  for (const value of ['0', '999999', '-25', '75oops', '66']) {
    assert.equal(readFontSize(`[comi]\nhd_font_size=${value}`), 65);
  }
});

test('depth of field defaults off and reads only the COMI section', () => {
  assert.equal(readDepthOfField(''), 0);
  assert.equal(readDepthOfField('[scummvm]\nhd_depth_of_field=2'), 0);
  assert.equal(readDepthOfField('[comi]\r\nhd_depth_of_field = 1\r\n[other]\nhd_depth_of_field=2'), 1);
  assert.equal(readDepthOfField('[comi]\nhd_depth_of_field=2'), 2);
  for (const value of ['0', '3', '-1', '2oops', 'high', '']) {
    assert.equal(readDepthOfField(`[comi]\nhd_depth_of_field=${value}`), 0);
  }
});

test('depth of field tuning defaults and rejects out-of-range values', () => {
  assert.deepEqual(readDepthOfFieldTuning(''), { blur: 0, edge: 2, intensity: 100, depth: 1 });
  assert.deepEqual(readDepthOfFieldTuning('[scummvm]\nhd_dof_blur=35'), { blur: 0, edge: 2, intensity: 100, depth: 1 });
  assert.deepEqual(readDepthOfFieldTuning('[comi]\r\nhd_dof_blur = 35\r\nhd_dof_edge=0\nhd_dof_intensity=60\nhd_dof_depth=3\n[other]\nhd_dof_edge=9'),
    { blur: 35, edge: 0, intensity: 60, depth: 3 });
  assert.deepEqual(readDepthOfFieldTuning('[comi]\nhd_dof_blur=500\nhd_dof_edge=-1\nhd_dof_intensity=101\nhd_dof_depth=0'),
    { blur: 0, edge: 2, intensity: 100, depth: 1 });
});

test('room matching accepts source and engine filenames, ignores unrelated names', () => {
  assert.equal(roomFromFilename('0009_cannon-wonder-3-5.png'), 9);
  assert.equal(roomFromFilename('bg_0015.png'), 15);
  assert.equal(roomFromFilename('new-background.png'), null);
  assert.equal(roomFromFilename('9abc.png'), null);
});
test('dimensions retain scrolling geometry and reject stretched masters', () => {
  assert.doesNotThrow(() => assertAspect(12576, 2880, 2096, 480));
  assert.throws(() => assertAspect(3840, 2160, 640, 480), /Proportions/);
  assert.throws(() => assertAspect(0, 0, 640, 480));
});
test('extended room art preserves the exact central 4:3 area', () => {
  const room = { room: 9, width: 640, height: 480 };
  assert.deepEqual(wideBackgroundCrop(2560, 1440, room), { left: 320, top: 0, width: 1920, height: 1440 });
  assert.deepEqual(wideBackgroundCrop(2560, 1440, { ...room, room: 10 }), { left: 320, top: 0, width: 1920, height: 1440 });
  assert.deepEqual(wideBackgroundCrop(5120, 2880, { ...room, room: 87 }), { left: 640, top: 0, width: 3840, height: 2880 });
  assert.equal(wideBackgroundCrop(2560, 1440, { ...room, height: 2044 }), null);
  assert.equal(wideBackgroundCrop(2560, 1440, { ...room, room: 92 }), null);
  assert.equal(wideBackgroundCrop(2560, 1440, { ...room, width: 2096 }), null);
  assert.equal(wideBackgroundCrop(3840, 2880, room), null);
  assert.equal(wideBackgroundCrop(2559, 1440, room), null);
});
test('settings reject malformed paths and config injection', () => {
  assert.throws(() => validateSettings({ disc1: 'relative.iso' }));
  assert.throws(() => validateSettings({ disc1: '/tmp/a\nkey=value', disc2: '/b', backgroundFolder: '/c' }));
  assert.throws(() => validateSettings({ disc1: '/a', disc2: '/b', backgroundFolder: '/c', characterPack: 'topaz\nhd_path=/tmp' }), /Unknown character pack/);
});

for (const roomId of [9, 13, 87]) test(`room ${roomId}: wide import stages matching center and sides; ordinary selection removes sides`, async () => {
  const number = String(roomId).padStart(4, '0');
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mi3-wide-'));
  const service = new PlaytestService(root);
  try {
    setProjectRoot(root);
    await fs.mkdir(path.join(root, 'data/scenes'), { recursive: true });
    await fs.mkdir(path.join(root, 'masters'));
    await fs.mkdir(path.join(root, 'extracted'));
    await sharp({ create: { width: 640, height: 480, channels: 4, background: '#123456' } }).png().toFile(path.join(root, 'extracted/original.png'));
    const side = async (color: string) => sharp({ create: { width: 320, height: 1440, channels: 4, background: color } }).png().toBuffer();
    const master = path.join(root, `masters/${number}_wide.png`);
    await sharp({ create: { width: 2560, height: 1440, channels: 4, background: '#00ff00' } })
      .composite([{ input: await side('#ff0000'), left: 0, top: 0 }, { input: await side('#0000ff'), left: 2240, top: 0 }])
      .png().toFile(master);
    const originalBytes = await fs.readFile(master);
    await fs.writeFile(path.join(root, 'data/project.json'), JSON.stringify({ scenes: ['scene'] }));
    await fs.writeFile(path.join(root, 'data/scenes/scene.json'), JSON.stringify({ scene: { id: 'scene', roomNumber: roomId, name: 'cannon' }, assets: { asset: { id: 'asset', type: 'background', originalPath: 'extracted/original.png', width: 640, height: 480, variants: [] } }, variants: {} }));
    await service.init();
    await service.settings({ disc1: '/a', disc2: '/b', backgroundFolder: path.join(root, 'masters') });
    await service.importBackgrounds([{ file: `${number}_wide.png`, room: roomId }]);
    const variant = (await service.rooms())[0].selectedVariantId;
    await service.apply(roomId);
    const center = path.join(root, `.playtest/hd/backgrounds/bg_${number}.png`);
    const wide = path.join(root, `.playtest/hd/widescreen/bg_${number}.png`);
    const metadata = await sharp(center).metadata();
    assert.equal(metadata.width, 2560); assert.equal(metadata.height, 1920);
    const pixel = async (file: string, left: number) => [...await sharp(file).extract({ left, top: 100, width: 1, height: 1 }).removeAlpha().raw().toBuffer()];
    assert.deepEqual(await pixel(center, 0), [0, 255, 0]);
    assert.deepEqual(await pixel(center, 2559), [0, 255, 0]);
    assert.deepEqual(await pixel(wide, 0), [255, 0, 0]);
    assert.deepEqual(await pixel(wide, 2559), [0, 0, 255]);
    await fs.rm(wide); // A missing sidecar is repaired even when the center stamp matches.
    await service.apply(roomId);
    assert.deepEqual(await pixel(wide, 0), [255, 0, 0]);
    await service.select(roomId, null); await service.apply(roomId);
    await assert.rejects(fs.access(wide));
    assert.deepEqual(await pixel(center, 0), [18, 52, 86]);
    await service.select(roomId, variant); await service.apply(roomId);
    assert.deepEqual(await pixel(wide, 2559), [0, 0, 255]);
    assert.deepEqual(await fs.readFile(master), originalBytes);
  } finally { await service.dispose(); await fs.rm(root, { recursive: true, force: true }); }
});

test('import, persistence, staging, process commands and original restoration', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mi3 playtest-'));
  const service = new PlaytestService(root);
  try {
    setProjectRoot(root);
    await fs.mkdir(path.join(root, 'data/scenes'), { recursive: true });
    await fs.mkdir(path.join(root, 'masters'));
    await fs.mkdir(path.join(root, 'extracted'));
    await sharp({ create: { width: 8, height: 6, channels: 4, background: '#123456' } }).png().toFile(path.join(root, 'extracted/original.png'));
    await sharp({ create: { width: 48, height: 36, channels: 4, background: '#aabbcc' } }).png().toFile(path.join(root, 'masters/0009_room.png'));
    await fs.writeFile(path.join(root, 'data/project.json'), JSON.stringify({ scenes: ['scene'] }));
    await fs.writeFile(path.join(root, 'data/scenes/scene.json'), JSON.stringify({ scene: { id: 'scene', roomNumber: 9, name: 'cannon' }, assets: { asset: { id: 'asset', type: 'background', originalPath: 'extracted/original.png', width: 8, height: 6, variants: [] } }, variants: {} }));
    await service.init();
    await service.settings({ disc1: '/tmp/disc1.iso', disc2: '/tmp/disc2.iso', backgroundFolder: path.join(root, 'masters') });
    const scanned = await service.scan();
    assert.equal(scanned[0].room, 9);
    await assert.rejects(service.importBackgrounds([{ file: '../escape.png', room: 9 }]));
    await assert.rejects(service.importBackgrounds([{ file: '0009_room.png', room: 9 }, { file: '0009_room.png', room: 9 }]), /only one/);
    assert.deepEqual(await service.importBackgrounds([{ file: '0009_room.png', room: 9 }]), { imported: 1, skipped: 0 });
    assert.deepEqual(await service.importBackgrounds([{ file: '0009_room.png', room: 9 }]), { imported: 0, skipped: 1 });
    const restored = new PlaytestService(root); await restored.init();
    const room = (await restored.rooms())[0];
    assert.equal(room.variants.length, 1);
    assert.equal(room.selectedVariantId, room.variants[0].id);
    await service.apply(9);
    const staged = path.join(root, '.playtest/hd/backgrounds/bg_0009.png');
    const meta = await sharp(staged).metadata();
    assert.equal(meta.width, 32); assert.equal(meta.height, 24);
    const masterPixels = await sharp(staged).raw().toBuffer();
    assert.equal(masterPixels[0], 170);
    await service.select(9, null); await service.apply(9);
    const originalPixels = await sharp(staged).raw().toBuffer();
    assert.equal(originalPixels[0], 18);
    await assert.rejects(service.select(9, 'foreign-variant'));
    await assert.rejects(service.jump(999), /Unknown room/);
    await assert.rejects(service.launch(), /Import both discs/);
    const game = path.join(root, '.playtest/game');
    await fs.mkdir(path.join(game, 'RESOURCE'), { recursive: true });
    for (const f of ['COMI.LA0', 'COMI.LA1', 'COMI.LA2', ...['MUSDISK1.BUN','MUSDISK2.BUN','VOXDISK1.BUN','VOXDISK2.BUN','FONT0.NUT','FONT1.NUT','FONT2.NUT','FONT3.NUT','FONT4.NUT'].map(n => 'RESOURCE/' + n)]) await fs.writeFile(path.join(game, f), 'fixture');
    const binary = path.join(root, '.playtest/engine/build/scummvm');
    await fs.mkdir(path.dirname(binary), { recursive: true });
    await fs.writeFile(binary, `#!${process.execPath}\nconst fs=require('fs');\nlet id=0;\nsetInterval(()=>{try {if(!fs.existsSync('ignore-command')) {const c=JSON.parse(fs.readFileSync('command.json')); id=c.id;}}catch{} fs.writeFileSync('status.tmp',JSON.stringify({protocol:1,ready:true,room:9,commandId:id,error:'',backgroundLoaded:true,width:32,height:24}));fs.renameSync('status.tmp','status.json');},40);\n`);
    await fs.chmod(binary, 0o755);
    await assert.rejects(service.launch(), /character pack has not been staged/);
    const costumeDir = path.join(root, '.playtest/hd/topaz-cannon/costumes');
    await fs.mkdir(costumeDir, { recursive: true });
    // An SVG-only pack is launchable without pre-generated PNG textures.
    await fs.writeFile(path.join(costumeDir, 'LFLF_0009_AKOS_0025_aframe_0.svg'), '<svg viewBox="0 0 20 30"><path d="M0 0h20v30z"/></svg>');
    await service.launch();
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /playtest_character_pack=topaz/);
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /playtest_scale=4/);
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /hd_font_size=65/);
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /hd_aspect_ratio=169/);
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /hd_depth_of_field=0/);
    const launchConfig = await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8');
    assert.match(launchConfig, /fullscreen=true/);
    assert.match(launchConfig, /vsync=true/);
    assert.match(launchConfig, /last_window_width=2560/);
    assert.match(launchConfig, /hd_trace=false/);
    // Per-room grades are tracked authoring data edited from the in-game Look panel.
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), new RegExp(`hd_color_grades_path=${path.join(root, 'data/color-grades.json')}`));
    await assert.rejects(service.launch(), /already running/);
    const deadline = Date.now() + 5000;
    while (!service.status.engine?.ready && Date.now() < deadline) await new Promise(r => setTimeout(r, 50));
    assert.equal(service.status.engine?.ready, true);
    await assert.rejects(restored.launch(), /Another game session/);
    await service.jump(9); await service.apply(9);
    assert.ok(service.status.engine!.commandId >= 2);
    const session = JSON.parse(await fs.readFile(path.join(root, '.playtest/process.json'), 'utf8')).session;
    await fs.writeFile(path.join(session, 'ignore-command'), '');
    await assert.rejects(service.jump(9), /timed out/);
    await assert.rejects(fs.access(path.join(session, 'command.json')));
    await fs.rm(path.join(session, 'ignore-command'));
    await service.jump(9);
    await service.stop(); assert.equal(service.status.running, false);
    await service.stop();
    await service.settings({ ...(await service.snapshot()).settings, characterPack: 'original' });
    const packRestored = new PlaytestService(root); await packRestored.init();
    assert.equal((await packRestored.snapshot()).settings.characterPack, 'original');
    // An executable that exits immediately must clear running state and expose failure.
    await fs.appendFile(path.join(root, '.playtest/scummvm.ini'), 'hd_font_size=75\nhd_aspect_ratio=43\nhd_depth_of_field=2\nhd_dof_blur=35\n');
    await fs.writeFile(binary, '#!/bin/sh\nexit 7\n');
    await service.launch();
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /hd_font_size=75/);
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /hd_aspect_ratio=169/);
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /hd_depth_of_field=2/);
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /hd_dof_blur=35\nhd_dof_edge=2\nhd_dof_intensity=100\nhd_dof_depth=1/);
    assert.match(await fs.readFile(path.join(root, '.playtest/scummvm.ini'), 'utf8'), /last_window_height=1440/);
    const exitDeadline = Date.now() + 3000;
    while (service.status.running && Date.now() < exitDeadline) await new Promise(r => setTimeout(r, 50));
    assert.match(service.status.error ?? '', /code 7/);
  } finally { await service.dispose(); await fs.rm(root, { recursive: true, force: true }); }
});

test('final room background overrides stale selections and stages the supplied 1440p PNG unchanged', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mi3-final-background-'));
  const service = new PlaytestService(root);
  try {
    setProjectRoot(root);
    await fs.mkdir(path.join(root, 'data/scenes'), { recursive: true });
    await fs.mkdir(path.join(root, '.playtest'));
    await fs.mkdir(path.join(root, 'masters'));
    const source = path.join(root, 'masters/0009_final.png');
    await sharp({ create: { width: 2560, height: 1440, channels: 3, background: '#123456' } }).png().toFile(source);
    const final = { id: 'final', assetId: 'asset', filePath: 'masters/0009_final.png', params: { finalBackground: true } };
    await fs.writeFile(path.join(root, 'data/project.json'), JSON.stringify({ scenes: ['scene'] }));
    await fs.writeFile(path.join(root, 'data/scenes/scene.json'), JSON.stringify({
      scene: { id: 'scene', roomNumber: 9, name: 'cannon' },
      assets: { asset: { id: 'asset', type: 'background', originalPath: 'missing-original.png', width: 640, height: 480, variants: ['final'], metadata: { finalBackgroundVariant: 'final' } } },
      variants: { final },
    }));
    await fs.writeFile(path.join(root, '.playtest/state.json'), JSON.stringify({
      settings: { disc1: '/a', disc2: '/b', backgroundFolder: path.join(root, 'masters') },
      selections: { asset: 'retired' }, variants: { retired: { id: 'retired', assetId: 'asset', filePath: 'missing-retired.png' } },
    }));
    await service.init();
    const [room] = await service.rooms();
    assert.equal(room.finalBackground, true);
    assert.equal(room.selectedVariantId, 'final');
    assert.deepEqual(room.variants, [final]);
    await assert.rejects(service.select(9, null), /final background/);
    await assert.rejects(service.select(9, 'retired'), /final background/);
    await assert.rejects(service.importBackgrounds([{ file: '0009_final.png', room: 9 }]), /final background/);
    await service.apply(9);
    const wide = path.join(root, '.playtest/hd/widescreen/bg_0009.png');
    assert.deepEqual(await fs.readFile(wide), await fs.readFile(source));
    const center = await sharp(path.join(root, '.playtest/hd/backgrounds/bg_0009.png')).metadata();
    assert.equal(center.width, 2560); assert.equal(center.height, 1920);
    await service.dispose();
    const restored = new PlaytestService(root);
    try { await restored.init(); assert.equal((await restored.rooms())[0].selectedVariantId, 'final'); }
    finally { await restored.dispose(); }
    await sharp({ create: { width: 1280, height: 720, channels: 3, background: '#123456' } }).png().toFile(source);
    await assert.rejects(service.apply(9), /2560 × 1440/);
  } finally { await service.dispose(); await fs.rm(root, { recursive: true, force: true }); }
});
