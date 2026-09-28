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

The Plunder Island map (room 0013) uses the supplied 2560 × 1440 painting with eight relocated destination regions and the original hover labels. Like other widescreen scenes, it fills the display without stretching, cropping excess edge artwork on taller or ultrawide screens. Input follows that framing and translates back to the original objects, preserving story restrictions; foreground actors and the boat follow the new landmarks, and a full-width water mask follows the new coastline. Its old shoreline/fog overlay is suppressed before actor drawing, including the first entry frame, because it contains fragments of the previous painting. The original artwork remains selectable, with its original layout. The source hash in the background staging stamp activates the new layout only for this painting.

All gameplay scenes share a subtitle boundary inside the visible 16:9 presentation, accounting for fullscreen cropping and horizontal, vertical, or two-axis scrolling. Speech keeps its authored speaker position where it fits; text near an edge moves inward, and the HD glyph pass respects the same boundary. Geometry checks are in `tools/test_subtitle_bounds.py`; `tools/check_subtitle_bounds.py` exercises rendered text across these scene layouts and cinematic subtitles with isolated saves at 16:9, 16:10, and ultrawide window sizes. Cinematics retain their own padded boundary within the visible movie frame.

The Voodoo exterior (room 0029) uses the supplied 16:9 painting. Its bridge and curved walking route, Murray, candle flames, hotspots, and verb coin are registered to the new landmarks; inverse pointer mapping preserves the original connected walkboxes and interaction scripts. The swamp has a matching full-width shoreline mask. Menus, inventory, dialogue choices, other rooms, and fallback artwork retain ordinary input. Registration activates only for this painting's staging hash. Run `tools/test_voodoo_exterior.py` for geometry checks and `tools/check_voodoo_exterior.py` with isolated saves for native walking and interaction checks.

Rooms 0013, 0014, 0015 and 0018 retain 1,039 verified existing Topaz outputs and add 150 Kenny animation textures in room 0015. Eighteen new cutouts remain cleanup drafts; one failed enhancement and three tiny room-0018 pieces use native fallback. The continuation used 303 credits, including the rejected tiny trial. See `assets/metadata/priority-scenes-topaz-provenance.json` for coverage and paid-job history.

Rooms 0019–0028 add 1,510 Topaz outputs while preserving 966 existing masters and reviews. The continuation accounts for 2,835 existing credits, including 3 reserved for uncertain submissions, under its 2,843-credit ceiling. 350 new cutouts remain cleanup drafts; tiny assets and held historical requests retain native fallback. Final software-renderer loading/menu checks cover all ten rooms; remaining OpenGL interaction checks need an unlocked desktop. Coverage, paid-job history, visual repair decisions and test limits are in `assets/metadata/middle-scenes-topaz-provenance.json`.

Rooms 0029 and 0030 include 195 packaged Topaz 4× costume, prop, and derived-layer drafts, including the Voodoo Lady and throne resources missing from the earlier export queue. Twenty-one cutouts still need cleanup, and one rejected tiny-frame trial retains its native fallback. Palette-driven dissolves and shader-replaced water remain native. See `assets/metadata/voodoo-topaz-provenance.json` for coverage, provider history, and validation; processing and installation do not imply artwork approval.

Room 0031 has 161 packaged Snake outputs: 153 automatically validated, one cleanup draft, and seven derived copies (one inherits the cleanup hold). All 154 regular inputs are processed; 51 native particle/shadow cels retain their fallback. The final continuation used 150 existing credits, bringing the scene to its original 308-credit ceiling. The pack is installed in the player runtime. Coverage, repair audits and test limits are in `assets/metadata/snake-topaz-provenance.json`; processing completion does not grant scene signoff.

Room 0032 has 206 packaged Quicksand outputs: 149 automatically validated, 50 cleanup drafts, and seven derived copies. All 199 regular inputs are processed, and four tiny cels retain native fallback after the padded trial failed review. Production used 396 existing credits including the trial; the pack is installed in the player runtime. Coverage, repairs, light/dark review and native test limits are in `assets/metadata/quicksand-topaz-provenance.json`; processing completion does not grant scene signoff.

Scene Look's **Focus** control adds an optional camera depth of field: **Off** (default), **Low** or **High**. It softly blurs the painted foreground that the original z-planes place in front of characters, at draw time only; artwork, characters, HD objects and UI stay sharp, and rooms without z-planes are unchanged. Scenery in more z-planes is nearer and blurs more. During play, these keys tune it live (a readout appears top-left): **[ ]** blur, **Shift+[ ]** intensity, **; '** edge softness, **Shift+; '** depth (how near scenery must be to blur), **\\** on/off, **Shift+\\** reset. All Scene Look controls support persistent global defaults and per-room overrides in `data/color-grades.json`; existing INI focus preferences seed the initial defaults. See [Scene Look configuration](PLAYTEST.md#resolution-and-game-behavior).

Press **U** during play or on the difficulty screen (room 0087) to open or close **Scene Look** (backtick also works). Click a row's **−/+** buttons, or use **Up/Down** to select and **Left/Right** to adjust (**Shift** ×5). **Backspace** resets a row, **B** compares the original colors and vignette, and **Esc** closes the panel. The panel contains brightness, contrast, saturation, gamma, warmth, tint; depth-of-field on/off/low/high, blur, edge softness, strength, and scene depth; and vignette on/off, strength, radius, and softness. Vignette is off by default, and switching it off retains its tuning.

Press **J** during gameplay to open **Jump to Scene**, a native picker for all 81 gameplay locations, including maps and close-ups. Use **Up/Down**, the mouse wheel, or **Page Up/Page Down** to select; **Enter** or clicking a row jumps, and **J/Esc** closes. The current room starts selected. Jumps preserve inventory and puzzle progress; some destinations require story progress. The picker replaces Scene Look and is unavailable during cutscenes, inventory, or the options book. It works without the browser workshop; rebuild the engine to install it.

**M → Shadows** opens the shadow controls directly. Choose **Global default** to tune the default X/Y position, or **This scene** to adjust only the current scene. Each row inherits globally until edited; **Override position for this scene** pins both current coordinates. **Use global position** removes only the scene’s X/Y overrides, preserving its shadow size, opacity, and color. **Use global size, color and position** restores inheritance for all shadow properties. Changes save automatically to `data/color-grades.json`; global edits leave existing scene overrides intact.

All Scene Look settings save to `data/color-grades.json` as global defaults with optional per-room overrides. Press **G** or click the panel title to switch scope; **Backspace** restores a room control to inheritance and **R** clears that room's overrides. Existing presets remain compatible. The vignette follows the visible frame and leaves dialogue, inventory, menus, and cursor undarkened. Extended sides receive the same color and vignette treatment as their center. Run `python3 -m unittest discover -s tools -p 'test_color_grade.py'` for mathematical checks, or `tools/venv/bin/python tools/check_look_panel.py` with a cannon fixture in `MI3_ASPECT_TEST_SAVES` for isolated native control and persistence checks.

Ambient water now uses the GPU wave shader in all 37 water rooms identified by the 94-room background audit, including beaches, bays, island views, ship combat and decks. Reviewed room-space masks follow the painted shorelines and camera movement while preserving characters, UI and scripted splashes. Legacy water/reflection overlays are suppressed where the shader replaces them, including the water portion of a mixed boat animation. Press **W** in any water room for live wave, RGB color, lighting and highlight controls, with per-room overrides and global defaults. Set `hd_water_shader=false` in the local engine config for the original rendering; see [water rendering and fallback](PLAYTEST.md#resolution-and-game-behavior) and the [complete coverage catalog](tools/engine/water_regions.json).

Puerto Pollo beach (room 0014) shades the full painted bay using a shoreline mask in panorama coordinates. Its fort, sand, welcome signs, vegetation, and wreckage remain outside the water effect; the original ripple sprites remain available when the shader is disabled.

Puerto Pollo town (room 0015) uses an artwork-specific water mask in `data/scene-masks.json` for the sea beside the lemonade stand and the harbor around the docks. Coverage follows the full panorama while excluding the promenade, buildings, foliage, and wooden structures. The mask remains editable with **M → Water**. Its water shader omits reflected-sky lighting and specular highlights while retaining waves and painted color; other rooms and the shader-disabled fallback keep their existing rendering.

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

### Scene tools

Press **M** in a playable scene to open the native **Scene tools** menu: **Walk areas / Water / Clipping / Animations / Head / Shadows**. Drag any walkable area's square corner directly to reshape it while the game keeps running; click inside an area to select it and number its corners. Arrow keys nudge the selected corner. **Play [T]** returns clicks to gameplay with the outlines still visible; press **T**, click **Select / drag**, or choose a layer tab to resume editing. Walking starts with water hidden: green means walkable, gold marks the selected area, and dashed gray means blocked. The feet marker shows Guybrush's current area. Connections are optional; Water displays handles on the selected shape; Clipping shows handles on every editable outline.

The tool tabs, **Play / Edit**, **Save**, and **Close** stay in fixed positions. The second row contains the current tool's main actions and Undo/Redo. **More options** expands tracing, layer controls, filters, fine head adjustments, and reset/revert; **Less options** collapses them. The header shows Edit or Play mode and whether there are unsaved changes. Short instructions update as you select or draw. All menu clicks stay inside the menu, including in Play mode. **Menu to bottom / Menu to top** moves the controls out of the way when you need to edit geometry underneath.

Select an existing walkbox before **Add area**, then click four corners along a shared horizontal or vertical edge. New areas inherit its scale/depth properties. **Disable area** disables a walkbox without changing its ID; **Enable area** restores it. Shared edges move together; edits that break a connection or leave an actor outside the walkable areas are rejected. The original narrow, collapsed walkboxes remain supported.

On **Water**, Add area/Add hole starts a polygon; click its corners and press **Enter** to finish. Drag nodes, nudge with arrow keys (Shift moves five units), press **E** or Insert near an edge of the selected polygon to insert a node, and Delete to remove a selected node. Color filter switches between the scene's original filter and unrestricted polygon coverage. Convert traces the current automatic coverage into editable outlines, including holes; in sprite-driven scenes it captures the currently visible water coverage. The blue fill shows actual shader coverage, which can differ from the outline because of color filtering and shoreline edge protection.

On **Clipping**, choose **Hide Guybrush** or **Show Guybrush**, then drag a rectangle over the part of the character you want to change. Release to apply; the new shape is selected so you can immediately adjust its corners. Escape cancels an unfinished shape. Purple shows where characters are hidden; green outlines mark areas that reveal them. The latest overlapping clip wins, so Hide can paint over Show and vice versa. Undo reverses each completed edit. The editor initially selects Guybrush's depth plane; use **< Clip layer / Clip layer >** to inspect the others. **Peek actor** temporarily disables the selected plane to diagnose unwanted clipping; **Restore clips** ends the preview. Choosing Hide Guybrush or Show Guybrush also restores clipping so the edit is visible. This preview never saves and ends when switching tabs, closing the editor, entering another room, or opening a modal screen.

Clipping precision controls are always visible. Switch **Shape: box** to **Shape: outline**, choose Hide or Show, click around the scenery, and press **Enter**. Click an edge to select an outline; **Add point** then an edge click (or **E** at the pointer) inserts a point on that edge. **Delete point** removes the selected vertex, keeping at least three. Arrow keys default to **1/4 native pixel** steps (one pixel in the 4x actor compositor); the Nudge button switches to whole pixels. Hold **Shift while dragging** for one-tenth-speed adjustments. Selected-point coordinates appear below the controls.

Use **Zoom** or the mouse wheel for 1x, 2x, and 4x views; the wheel keeps the location under the pointer fixed unless the view reaches a painting boundary. Hold **Space and drag**, or drag with the middle button, to pan. **Reset view / 0** restores the full scene. Zoom requires the OpenGL scene renderer. The mask handles, picking, and artwork share the same zoom transform, including custom paintings and camera scrolling. **Fill** cycles through full, light, and outlines-only coverage. Play mode returns to the normal view and gameplay input; switching back to Edit restores your working zoom. Room changes reset the view. These view settings do not change saved masks.

**Edit nodes** converts original pixel clipping in the visible scene into editable outlines and immediately shows their square handles. It preserves existing Hide/Show shapes, fractional coordinates, and overlap priority. Repeated clicks leave converted shapes unchanged. **Previous shape / Next shape** selects overlapping outlines and reveal holes. If a layer is empty, use **Clip layer >**. Conversion is undoable and only persists after Save. Click an outline, then choose **More options → Simplify points** (or press **S**) to reduce its pixel-stepped corners. For a custom polygon, choose Hide Guybrush or Show Guybrush, press **P**, click its corners, then press **Enter**. E inserts a node near an edge; Delete removes a selected node. **Reset clips** restores the original live mask on just that plane. Use **Play** to check characters moving behind the scenery, then **Save**. Foreground overrides affect native costume drawing and HD replacements. The verb coin and script hit tests retain their original behavior.

Foreground shapes use native room coordinates and the same custom-painting registration as actors. A traced mask replaces only the viewport captured by Edit nodes; unedited regions of scrolling rooms continue to use live native masks. Traced regions capture the current object state, so use small Hide Guybrush / Show Guybrush corrections when scenery changes during scripts. Foreground edits affect character occlusion; the Scene Look depth-of-field blur retains its original mask.

On **Head** (press **H** while the editor is open), drag the gold head box to position Guybrush’s head artwork relative to his body. Arrow keys or Left/Right/Up/Down nudge it; Shift moves five steps, and **Step: 1/4 px** enables fine adjustments. Cyan outlines the body, gray marks the original head bounds, and **Peek original** temporarily shows the unmodified position. **Reset sequence / Reset frame** removes the offset for the selected scope; **Revert saved** restores its saved offset. Blinking and speech keep working during a drag; scripted actor movement, costume changes, or a room transition cancels it. The normal Guybrush costume’s separate walking, turning, and speaking heads are supported; poses with the head baked into a full-body image cannot be adjusted separately.

Head offsets follow native scaling, mirroring, camera scrolling, and the custom painting registration. **Save** in Head writes only head edits, under `characterHeads` in the same versioned `data/scene-masks.json`, keyed by character pack and costume. Sequence adjustments follow all supported head poses across scenes in that pack; frame adjustments apply only to their frame. Both remain separate from game saves and do not alter body artwork, gameplay coordinates, or source images. Head has its own Undo/Redo history; saving scene masks leaves unsaved head changes alone, and saving heads leaves unsaved scene masks alone.

**Undo/Redo** (Ctrl+Z / Ctrl+Shift+Z), **Save** (Ctrl+S), **Revert saved**, and **Reset room** operate on the current scene in Walk areas and Water. Clipping has **Reset clips** for the selected layer. Closing the editor retains unsaved drafts until the process exits. Saved overrides live in `data/scene-masks.json`, keyed by room and selected artwork identity, and reload without rebuilding. Reset is an editable change: Save it to persist the reset. The launcher supplies `hd_scene_masks_path`; standalone configurations can point this at an absolute mask-file path. Original game resources and savegame formats are unchanged.

Validation: `python3 -m unittest discover -s tools -p 'test_scene_masks.py'`; `tools/venv/bin/python tools/check_scene_masks.py` exercises the native editor with isolated saves and a separate mask file. Screenshots are written under `.context/mask-editor-check/`.

Clipping validation: `tools/venv/bin/python tools/check_clipping_nodes.py` checks Edit nodes on original masks alongside authored corrections, shape cycling, direct point selection, every clipping layer in rooms 9 and 14, history, and persistence across restart. `tools/venv/bin/python tools/check_foreground_masks.py` checks visible actor clipping, drag-to-hide/show rectangles, overlapping edits, cancellation, custom outlines, tracing/simplification, history, save restoration, restarts, and display ratios using isolated saves and masks. Screenshots go to `.context/foreground-check/`. `tools/venv/bin/python tools/check_walkable_nodes.py` checks partial shared edges, direct corner selection, returning from Test mode, and dragging at three display ratios.

The custom Voodoo exterior brings Guybrush in through the bottom edge along the painted path, and reverses that movement on exit. His draw position eases into the original bridge position; scripts, navigation, scale, other actors, and the original-art fallback keep their native behavior. `tools/venv/bin/python tools/check_voodoo_entrance.py` exercises the actual map entrance and return exit.

**Head** and **Animations** both offer **Onion: on/off**, **Edit: whole sequence / Edit: frame**, and **< Frame / Frame >**. Let the animation play to capture its frames; the frame arrows browse those captured images. Faint cyan and purple neighbors help compare alignment, while a gold frame preview stays selectable even when the live animation advances. **Whole sequence** moves every frame together. **Frame** adds a correction only to that PNG/frame; changing the sequence position preserves those individual corrections. The live animation continues underneath, and **Play** hides onion skins so you can check the final motion. A bounded, temporary frame cache clears when the actor moves or the room changes; saved offsets persist independently of those previews.

On **Animations**, drag a sprite’s blue outline to move its entire PNG sequence. Gold marks the selected instance; **Previous / Next** or **Tab** selects small sprites. The flames in scene 29 have independent positions even when they share the same frames. Arrow keys or direction buttons nudge by **1/4 px** or **1 px**; Shift + arrows moves five steps, and Shift + drag makes fine adjustments. The animation keeps playing while you edit. **Reset sequence / Reset frame** removes the offset for the selected editing scope; **More options → Revert saved position** restores its saved offset. Undo/Redo uses the scene history. **Play** returns input to gameplay; **Save** persists positions together with the scene masks.

On **Animations → Mask PNG**, edit a sprite’s alpha mask using **Keep area** or **Cut hole**: click outline points and press **Enter**. Drag square nodes, nudge with arrows, or use **Add point / Delete point** for precise borders. The mouse wheel zooms up to 4×; Space + drag pans. **Edit: whole sequence / Edit: frame** selects the scope; frame arrows browse previews without changing that scope. Whole-sequence and frame masks combine, so a frame can trim its sequence mask further. The selected frame stays visible while you edit, with optional onion neighbors; **Play** shows the running result.

**Edge: original** preserves the PNG’s alpha, **Edge: hard** makes it crisp, and **Edge: soft** feathers inward without revealing transparent matte colors. **Softness** cycles through ¼–8 native pixels. A frame inherits the sequence’s edge treatment until you choose its own. **Reset mask** clears the current scope, and **More options → Revert saved mask** restores it from disk. Save persists masks under `animationMasks`, keyed by art pack, actor, costume, and optionally frame, in the current scene entry. Outlines use normalized, unmirrored sprite coordinates and follow positioning edits, scaling, and camera movement; original PNGs remain untouched.

The **M** menu is translucent at 65% opacity by default, including the Shadows panel. **More options → Panel %** cycles its opacity; **Menu to bottom / top** moves it away from the area you’re editing.

Sprite-mask validation: `tools/venv/bin/python tools/check_sprite_masks.py` exercises outlines, holes, point editing, scopes, history, opacity, input isolation, and persistence. `tools/venv/bin/python tools/check_sprite_mask_render.py` verifies actual PNG removal and restoration with temporary fixture artwork. Both keep production masks, artwork, and saves untouched.

Animation offsets are stored in the scene’s optional `animations` object in `data/scene-masks.json`, keyed by actor instance and costume for the sequence, with an optional third frame ID for individual corrections. They use native room coordinates and follow scrolling and custom painting registration. They change only rendered placement, preserving script coordinates, animation timing, depth planes, and source PNGs. Room/artwork identity separates scene drafts. A room transition, modal screen, or scripted actor movement/costume change cancels an active drag. Sprites with available PNG replacements are editable; the candle flames also support their original animated palette frames when the selected art pack has no replacement. Guybrush, the verb coin, and shader water are excluded.

Animation validation: `tools/venv/bin/python tools/check_scene_animations.py` checks independent flame instances, animation continuity, drag/nudge/history, rendered movement, room drafts, persistence, and restart using isolated files.

Head validation: `python3 -m unittest discover -s tools -p "test_actor_head.py"`; `tools/venv/bin/python tools/check_actor_head.py` checks actual head rendering, body/input isolation, drag cancellation, nudging, history, save/load/restart, conflicts, and display ratios with isolated data.

Precision clipping validation: `tools/venv/bin/python tools/check_clipping_precision.py` exercises zoomed artwork and picking, fractional edits, outline tools, panning, input isolation, display ratios, and persistence with isolated saves.

Onion-skin validation: `tools/venv/bin/python tools/check_sprite_onion.py` checks frame capture, per-frame versus sequence offsets, onion toggling, history, and restart persistence for flames and heads.
