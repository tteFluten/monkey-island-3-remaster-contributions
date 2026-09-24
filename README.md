# Monkey Island 3 Remaster

Private Basement Studio workspace for a playable remaster of **The Curse of Monkey Island**.
The workshop manages artwork, reviews replacements, and launches a patched native COMI-HD engine.
This repository is the project's source of truth. New changes should target its `main` branch through pull requests.

## What is included

- A React/TypeScript workshop with scene browsing, before/after comparisons, PNG editing, and asset review.
- A patched macOS engine with 4:3 and 16:9 display modes, panorama support, and preserved original game coordinates.
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
| Native engine | A patched COMI-HD engine that runs the original game data with installed replacement artwork, cinematics, music, and repaired speech. It provides the 4:3 and 16:9 display modes. |

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

The current pack contains 37,818 manifest entries, approximately 16.17 GiB of packaged files and 9.78 GiB of unique LFS media. It includes 3,498 selected Topaz 4× masters and the user-supplied inventory panel in the UI masters. Allow additional disk space for the Git LFS cache, original game data, engine build, installed copies, and rollback backups.

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

6. Restart `npm run dev --prefix app`, open **Playtest**, select the **Topaz** character pack, and launch. The installed workshop state selects the supplied background masters. Existing local selections are retained on reinstall.

Use the original options book (**O** or **F5**) to choose **4:3** or **16:9**. Standard rooms retain their original framing; sufficiently wide panorama rooms reveal additional existing scenery. Narrow rooms and cinematics keep their original framing. Runtime rendering is 4×; the supplied 6× masters remain separate.

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
- Some installed character/object images remain drafts or failed visual review. Their recorded status is retained to keep the current playable set complete.
- The existing external-music engine has limitations in cue offsets, looping, save-position restoration, fades, and speech ducking. Asset installation does not fix these engine behaviors.
- Room jumps are debugging tools, not proof of chapter progression. Some scenes require normal gameplay state.
- First-time loading and room/movie transitions can cause performance spikes. Full-game completion has not been verified.

## Contributions and provenance

Open branches and PRs against [basementstudio/monkey-island-3-remaster](https://github.com/basementstudio/monkey-island-3-remaster). Keep new binary media in Git LFS and update the asset manifest when changing packaged files. Do not commit local service credentials, original disc images, saves, caches, or build artifacts.

This repository starts a clean history. The original project and its PRs remain at [tteFluten/monkey-island-3-remaster](https://github.com/tteFluten/monkey-island-3-remaster); source commit IDs and file hashes are recorded in `assets/metadata/code-snapshot.json`. Existing project code, third-party engine code, and media retain their original attribution and applicable terms; this migration does not assign a new blanket license.

Further documentation: [playtesting](PLAYTEST.md), [audio preparation and recovery](AUDIO.md), [Topaz](TOPAZ.md), and [Quiver experiments](QUIVER.md).
