# Monkey Island 3 Remaster

Private Basement Studio workspace for a playable remaster of **The Curse of Monkey Island**.
The workshop manages artwork, reviews replacements, and launches a patched native COMI-HD engine.
This repository is the project's source of truth. New changes should target its `main` branch through pull requests.

## What is included

- A React/TypeScript workshop with scene browsing, before/after comparisons, PNG editing, and asset review.
- A patched macOS engine with a 16:9 presentation, panorama support, and preserved original game coordinates.
- Runtime backgrounds, character frames, objects, UI artwork, fonts, 15 HD cinematics, and 68 stereo music tracks.
- 93 supplied background masters, selected sprite/font/UI masters, and metadata describing the installed artwork.
- The repaired English disc-1 voice bundle, including repair provenance. **All 3,815 disc-1 entries are now restored and match the verified donor payloads.**
- Hash verification and reversible installation of the asset pack.

The pack is a snapshot of work in progress. Some installed artwork is an unapproved or rejected draft retained from the existing playable setup. New replacements take precedence where validated; existing artwork and original-game fallback cover the rest. No files are silently promoted to approved.

## How it works

The project connects three parts:

| Part | Role |
| --- | --- |
| Workshop | A local browser interface for inspecting scenes, comparing and editing artwork, recording review status, and launching playtests. Its Node.js backend runs the local tools. |
| Asset pack | Versioned replacement media and editable masters under `assets/`. The manifest records checksums, source relationships, review status, and installation destinations. Git LFS stores the binary media. |
| Native engine | A patched COMI-HD engine that runs the original game data with installed replacement artwork, cinematics, music, and repaired speech. It presents the game in 16:9. |

For playback, import your original game data, build the engine, and install the verified pack into the local workspace. The workshop launches the engine with the selected artwork. Available replacements cover individual assets; existing artwork and original-game fallback keep unfinished areas playable. The browser workshop and the native game run as separate applications.

For artwork work, start from the canonical master, edit and review the replacement, export its runtime files, and update the manifest. Verify and playtest the result before submitting a PR. Local edits become shared project assets when their updated masters, runtime files, and metadata are committed together.

## Access and clone

You need access to this private repository and Git LFS. Media files are stored in LFS; a checkout containing pointer files is not a usable asset pack.

```sh
brew install git-lfs
git lfs install
git clone https://github.com/basementstudio/monkey-island-3-remaster.git
cd monkey-island-3-remaster
git lfs pull
```

The pack's current file counts and logical/unique byte sizes are recorded in `assets/manifest.json` and grow as Topaz checkpoints are packaged. It includes selected Topaz 4× masters and the user-supplied inventory panel in the UI masters. Allow additional disk space for the Git LFS cache, original game data, engine build, installed copies, and rollback backups.

## Prerequisites

The tested native runtime targets macOS. Install Node.js 20 or newer, Python 3.11, Xcode Command Line Tools, and the engine/media dependencies:

```sh
xcode-select --install
brew install python@3.11 sdl2-compat libpng zlib pkgconf ffmpeg
python3.11 -m venv tools/venv
tools/venv/bin/python -m pip install -r tools/requirements-topaz.txt
npm ci --prefix app
```

Original game discs/data and player saves are not included. Use your local English edition of the game. The repaired voice bundle is accepted only for the source hashes recorded in the asset manifest. An incompatible edition stops installation before any assets are replaced.

## First playable setup

1. Start the workshop with `npm run dev --prefix app` and open **http://127.0.0.1:5200**. The backend uses port 5201.
2. Open **Setup**, select both local disc images, and choose **Import discs**. The import retains the original disc images.
3. Choose **Build Mac engine**, or run `bash tools/build_engine.sh` from the repository root. The build downloads a pinned COMI-HD source revision and applies this repository's patches.
4. Stop the game and workshop before installing the pack so the running editor cannot overwrite restored state.
5. Verify and install:

```sh
tools/venv/bin/python tools/asset_pack.py verify --media
tools/venv/bin/python tools/asset_pack.py install --target-workspace "$PWD" --dry-run
tools/venv/bin/python tools/asset_pack.py install --target-workspace "$PWD"
```

6. Restart `npm run dev --prefix app`, open **Playtest**, select the **Topaz** character pack, and launch. The installed workshop state selects the supplied background masters. Existing local selections are retained on reinstall, except for explicitly finalized backgrounds: rooms 0009 and 0011 always use their approved 2560 × 1440 cannon and waterline images.

Every launch and resume starts fullscreen at a 2560 × 1440, 16:9 presentation target with GPU effects; players have no 4:3 option. Standard rooms can display authored side extensions around the unchanged gameplay region; the options book (**O** or **F5**) is fully 16:9 with a re-laid-out options page, and its Quit prompt and other engine banners keep the book or scene visible behind them. Panoramas retain their existing layouts; unfinished backgrounds and inventory preserve their framing. Movies use HD video only. In widescreen mode they use a centered 16:9 crop without stretching, with cinematic black bars above and below on taller displays. Returning from a movie to an HD scene uses the same one-second GPU fade-in as the opening gameplay scene. All six chapter cards use the same one-second fade-in and fade-out. Leaving a chapter card or skipping a movie fades to black first; Escape preserves the movie's framing throughout that fade. Asset textures remain 4× and high-resolution masters stay separate. See [presentation and performance checks](PLAYTEST.md#resolution-and-game-behavior).

Scene Look's **Focus** control adds an optional camera depth of field: **Off** (default), **Low** or **High**. It softly blurs the painted foreground that the original z-planes place in front of characters, at draw time only; artwork, characters, HD objects and UI stay sharp, and rooms without z-planes are unchanged. Scenery in more z-planes is nearer and blurs more. During play, these keys tune it live (a readout appears top-left): **[ ]** blur, **Shift+[ ]** intensity, **; '** edge softness, **Shift+; '** depth (how near scenery must be to blur), **\\** on/off, **Shift+\\** reset. All Scene Look controls support persistent global defaults and per-room overrides in `data/color-grades.json`; existing INI focus preferences seed the initial defaults. See [Scene Look configuration](PLAYTEST.md#resolution-and-game-behavior).

Press **U** during play or on the difficulty screen (room 0087) to open or close **Scene Look** (backtick also works). Click a row's **−/+** buttons, or use **Up/Down** to select and **Left/Right** to adjust (**Shift** ×5). **Backspace** resets a row, **B** compares the original colors and vignette, and **Esc** closes the panel. The panel contains brightness, contrast, saturation, gamma, warmth, tint; depth-of-field on/off/low/high, blur, edge softness, strength, and scene depth; and vignette on/off, strength, radius, and softness. Vignette is off by default, and switching it off retains its tuning.

Press **J** during gameplay to open **Jump to Scene**, a native picker for all 81 gameplay locations, including maps and close-ups. Use **Up/Down**, the mouse wheel, or **Page Up/Page Down** to select; **Enter** or clicking a row jumps, and **J/Esc** closes. The current room starts selected. Jumps preserve inventory and puzzle progress; some destinations require story progress. The picker replaces Scene Look and is unavailable during cutscenes, inventory, or the options book. It works without the browser workshop; rebuild the engine to install it.

All Scene Look settings save to `data/color-grades.json` as global defaults with optional per-room overrides. Press **G** or click the panel title to switch scope; **Backspace** restores a room control to inheritance and **R** clears that room's overrides. Existing presets remain compatible. The vignette follows the visible frame and leaves dialogue, inventory, menus, and cursor undarkened. Extended sides receive the same color and vignette treatment as their center. Run `python3 -m unittest discover -s tools -p 'test_color_grade.py'` for mathematical checks, or `tools/venv/bin/python tools/check_look_panel.py` with a cannon fixture in `MI3_ASPECT_TEST_SAVES` for isolated native control and persistence checks.

Ambient water now uses the GPU wave shader in all 37 water rooms identified by the 94-room background audit, including beaches, bays, island views, ship combat and decks. Reviewed room-space masks follow the painted shorelines and camera movement while preserving characters, UI and scripted splashes. Legacy water/reflection overlays are suppressed where the shader replaces them, including the water portion of a mixed boat animation. Press **W** in any water room for live wave, RGB color, lighting and highlight controls, with per-room overrides and global defaults. Set `hd_water_shader=false` in the local engine config for the original rendering; see [water rendering and fallback](PLAYTEST.md#resolution-and-game-behavior) and the [complete coverage catalog](tools/engine/water_regions.json).

Installation overlays only listed destinations. Unrelated artwork, original data other than the selected repaired voice bundle, saves, and engine settings remain in place. All changed files are backed up under the target workspace's ignored `.playtest/asset-pack-backups/` directory.

## Verify and roll back

`verify` checks every manifest hash and file size. `verify --media` additionally decodes PNGs, validates PCM music, and checks video dimensions/frame counts/timing against staging metadata. Verification runs locally and makes no generation-service calls.

The installation command prints a transaction ID. To restore the state before that installation:

```sh
tools/venv/bin/python tools/asset_pack.py rollback \
  --target-workspace "$PWD" --transaction TRANSACTION_ID
```

Roll back newer installations before older ones. Rollback refuses to overwrite files edited after installation. Interrupted transactions must be rolled back before another installation. Keep local transaction backups until you no longer need rollback.

## Asset source of truth

The current **Topaz 4× outputs**, supplied **4K background masters**, and current **UI masters** are the authoritative replacement artwork while new assets are produced:

- `assets/masters/topaz-4x/`: current selected character/object outputs, including existing drafts and manual corrections.
- `assets/masters/backgrounds/`: supplied high-resolution backgrounds; keep their full resolution and aspect ratio.
- `assets/masters/ui-4x/`: current runtime-ready UI/font artwork not already covered by a Topaz master. Supplied higher-resolution font/coin/pointer inputs are retained in adjacent master folders.

`assets/manifest.json` marks these files with `canonical: true`. Runtime records use `derived_from` and `transform` to identify their master and whether they are copied at 4× or resized for a background. The `extracted/` library is reference/fallback material, not the authority for a completed replacement.

When a new replacement is ready, update its canonical master, export each linked runtime file, and update the manifest hashes, dimensions, and review status in the same PR. Topaz 4×/UI copies must match their master bytes; background runtime files retain the original room's 4× dimensions. Keep existing replacements for unfinished assets. Do not overwrite a manual correction with an older provider output or mark an asset approved simply because it is playable.

Use the existing staging tools for the relevant asset category; update affected background stamp files and workshop variant metadata when replacing a background. Verify the complete pack before installation. Local editor outputs and new provider downloads become authoritative only after they are incorporated into the canonical pack and reviewed through Git.

## Repository layout

| Location | Contents |
| --- | --- |
| `app/` | Workshop frontend and backend |
| `tools/` | Engine patches, asset/audio tooling, installer, and tests |
| `assets/runtime/` | Ready-to-install HD images, videos, music, and mappings |
| `assets/masters/` | Background, sprite, font, and UI source artwork |
| `assets/voices/` | Repaired voice bundle |
| `assets/manifest.json` | Checksums, sizes, review status, provenance, and destinations |
| `assets/metadata/` | Source snapshot, staging records, reviews, and repair records |
| `data/`, `extracted/`, `upscaled/`, `previews/` | Existing scene library and reference media |
| `.playtest/`, `output/`, `downloads/` | Ignored local runtime, generation work, and caches |

Sprite masters, a portable batch index, and their cleaned reference images are restored to the editable local output tree. The Topaz browser and PNG editor work immediately after installation. Historical provider responses, intermediate renders, and generation queues are not archived in this snapshot; prepare a new queue before continuing generation. See [Topaz workflow](TOPAZ.md) and [scene batches](SCENE_BATCHES.md).

## Optional generation services

Playback and asset installation do not require ImageLab, Topaz, or Quiver credentials. Generating new artwork does. Keep credentials in local environment/configuration files, which are ignored by Git.

ImageLab uses the `basement-lab` server in a local `.mcp.json` at the repository root. Set `MI3_MCP_CONFIG` to an absolute configuration path to use a shared installation. Configure your own MCP command and arguments; no machine-specific configuration or credentials are shipped. The existing tooling documentation describes the optional providers.

## Development and checks

```sh
npm run build --prefix app
npm run typecheck --prefix app
npm test --prefix app
tools/venv/bin/python -m unittest discover -s tools -p 'test_*.py'
```

Native checks require an imported game, built engine, installed pack, and a cannon-room `comi.s00` fixture save:

```sh
tools/venv/bin/python tools/check_aspect.py
tools/venv/bin/python tools/check_aspect.py --interactions
tools/venv/bin/python tools/smoke_comi_audio.py \
  --target-workspace "$PWD" --music-dir .playtest/hd/audio \
  --report-dir .context/audio-smoke
```

These checks use isolated sessions and copies of saves. They do not establish full-game puzzle progression or listening quality. See [migration validation](MIGRATION.md) for the checks completed for this snapshot.

## Known limitations

- Voice recovery restores 798 recordings, including the final 26 missing entries and the exact original takes for two earlier substitutions. Voices retain original quality; this is not a synthesized or HD voice pack.
- The game is English. A Spanish option is prepared in the options book; it needs a local language pack (text and/or voices; see [PLAYTEST.md](PLAYTEST.md#languages)) and does not yet cover cinematic voices or text painted into artwork.
- Some installed character/object images remain drafts or failed visual review. Their recorded status is retained to keep the current playable set complete.
- The existing external-music engine has limitations in cue offsets, looping, save-position restoration, fades, and speech ducking. Asset installation does not fix these engine behaviors.
- Room jumps are debugging tools, not proof of chapter progression. Some scenes require normal gameplay state.
- First-time loading and room/movie transitions can cause performance spikes. Full-game completion has not been verified.

## Contributions and provenance

Open branches and PRs against [basementstudio/monkey-island-3-remaster](https://github.com/basementstudio/monkey-island-3-remaster). Keep new binary media in Git LFS and update the asset manifest when changing packaged files. Do not commit local service credentials, original disc images, saves, caches, or build artifacts.

This repository starts a clean history. The original project and its PRs remain at [tteFluten/monkey-island-3-remaster](https://github.com/tteFluten/monkey-island-3-remaster); source commit IDs and file hashes are recorded in `assets/metadata/code-snapshot.json`. Existing project code, third-party engine code, and media retain their original attribution and applicable terms; this migration does not assign a new blanket license.

Further documentation: [playtesting](PLAYTEST.md), [audio preparation and recovery](AUDIO.md), [Topaz](TOPAZ.md), and [Quiver experiments](QUIVER.md).
