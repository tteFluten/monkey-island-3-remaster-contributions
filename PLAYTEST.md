# Playable remaster workshop

Run `cd app && npm ci && npm run dev`, then open http://127.0.0.1:5200.
The Playtest tab controls a separate native COMI-HD game window. The asset library
and ImageLab tools remain available; playtesting does not require ImageLab.

## First setup on a Mac

1. Install Xcode Command Line Tools and Homebrew, then run
   `brew install sdl2 libpng zlib pkgconf ffmpeg`.
2. Open **Setup**. The defaults point to `~/Desktop/monkey/monkey3-1.iso`,
   `monkey3-2.iso`, and the `4k` folder. Change these paths as needed.
3. Choose **Import discs**, then **Build Mac engine**. Disc volumes are mounted
   read-only and detached even if copying fails. Conflicting duplicate files
   fail the import; an existing successful import is preserved.
4. Choose **Import folder**. Review room mappings, choose one image per room,
   and import. Unmatched names and duplicate candidates require a selection.
5. Choose **Launch game**, select a difficulty in the game window, and use Esc
   to skip the opening. Once the editor says ready, select a room and choose
   **Jump to room**.
6. Select a test variant and choose **Apply and reload**. **Use original**
   restores a nearest-neighbor 4× copy of the original background. An inactive
   room is prepared for its next visit. **Stop game** closes only this session.

For this workspace, both discs and all 93 supplied backgrounds have already been
imported, and the Mac engine has been built. Source images and ISOs are unchanged.

## Resolution and game behavior

Every workshop launch and resume starts fullscreen with a **2560 × 1440,
16:9 presentation canvas**, GPU effects enabled, and display synchronization.
The original options book (**O** or **F5**) still offers **4:3** during play;
both modes stay in borderless desktop fullscreen (without a separate macOS Space),
and the next workshop launch resets presentation to
16:9. Saved effect and font preferences remain intact. The GPU 4:3 canvas is
1920 × 1440. Asset textures stay at 4×: a standard room uses
2560 × 1920 textures and native gameplay remains 640 × 480. High-resolution
masters are preserved separately. Physical display dimensions are independent
of both the asset textures and presentation canvas.

**Vintage film trial:** press **F** to toggle a subtle Cuphead-inspired
film treatment, including during menus and movies. It adds monochrome grain at
24 Hz, sparse dust and fine scratches, gentle exposure variation, and subpixel
frame wobble after the complete image (including dialogue, inventory and cursor).
Game timing and interaction coordinates are unchanged; black bars stay black.
The grain mixes fine noise with a soft two-pixel texture so it remains visible
on Retina displays. Dust and scratches are faint but readable; frame wobble
and exposure flicker remain gentle. Pressing **F** shows **Film: On/Off** briefly
so the current state is clear.
Open **Scene Look** with **U**, then press **Tab** (or click the section heading)
to open **Film Look**. Film is always global, even when Scene Look is editing a
room. Adjust Film effect, Overall strength, Grain, Dust, Scratches, Flicker,
Frame wobble and Chromatic aberration with the existing arrows or −/+ buttons;
**Shift** adjusts faster. The six individual effect controls range from 0–200%,
with 100% as their baseline. Chromatic aberration adds subtle red/blue separation
across the whole picture, including centrally placed character costumes, with
slightly more separation toward the edges. It runs after costumes, objects and
UI are composed; source artwork and costume transparency are unchanged. Set it
to 0% to disable just that effect. Its global INI key is `hd_film_chromatic`.
**Backspace** resets the selected control, **R** resets film settings, and **B**
temporarily bypasses film for comparison. Settings save immediately to the global
engine INI and survive workshop relaunches. **Tab** continues to Character Shadows,
then Water in room 11, then Scene Look; **F** remains the global on/off shortcut.
The effect is opt-in and the workshop retains the native shortcut's preference
on relaunch. In the engine INI's global `[scummvm]` section, use
`hd_film_enabled=true` and `hd_film_strength=20` for the subtle preset. Strength
is clamped to 0–100; zero and disabled both bypass the pass exactly. The effect
has independent GPU resources and bypasses unavailable shader support.

Run `tools/venv/bin/python tools/check_film.py` with a cannon fixture in
`MI3_ASPECT_TEST_SAVES` for isolated native checks and matching before/after
captures. Add `--motion` for a sampled three-second film preview. Captures go to
`.context/film-check/`; all test saves and settings are isolated. For paired GPU
timings, run `tools/check_performance.py --gpu --vsync` with and without `--film`.

Any standard 640 × 480 background (including difficulty room 0087, excluding
the options book) accepts exact 16:9 artwork
with the original composition in its centered 4:3 area. Use the existing
background import and apply controls. They stage the centered image at
2560 × 1920 and a full 2560 × 1440 sidecar at `hd/widescreen/bg_NNNN.png`.
The presentation has a centered 1920 × 1440 gameplay region and 320 pixels of
additional scenery on either side. Extensions are decorative: native objects,
characters, walkboxes, and interaction coordinates keep their existing positions.
Selecting ordinary artwork removes its sidecar; missing or invalid sidecars
retain the original framing with bars. Staging does not promote artwork into
the canonical pack or change its master.

Room 0009 uses the user-approved final `0009_cannon-wonder-3-5.png`, preserved
unchanged at **2560 × 1440**. Its canonical master is
`assets/masters/backgrounds/f7a54cda98ca3ad0419cfcb5bb816ebd6267edb34e04fc4b82dc8aaf7aeaf61e.png`.
Room 0011 likewise uses the approved `0011_waterln-wonder-3-5.png`, with canonical
master `assets/masters/backgrounds/d2cf60fd6a6c07a56788b042300e618c8977525cc1a20f2f3c83cc4802ba631f.png`.
Each scene's `finalBackgroundVariant` selects its artwork on every launch and
reinstall, replacing retired local variants. The workshop offers only the final
background for these rooms. Each 16:9 runtime copy is byte-identical to the supplied
image; the engine's center texture is derived from that same image for character
and hotspot alignment. The in-game 4:3 option remains available and shows the
center of this final artwork. Other rooms retain their existing selection behavior.

Room 0087 uses the supplied `0087_easyhard-wonder-3-5-wonder-3-5.png`.
The 5120 × 2880 master is preserved; its 2560 × 1440 widescreen export surrounds
the centered native difficulty controls. The 4:3 mode uses the matching center.
Press **U** on this screen to edit Scene Look, including color and vignette.
Changes save as room 87 overrides in `data/color-grades.json`, using the same
global/room controls as gameplay. Focus affects only authored z-planes; the
panel reports when none are available. The options book remains excluded.
Run `tools/venv/bin/python tools/check_difficulty_look.py` for isolated native
checks, or add `--cpu --aspect 43` to exercise the fallback renderer.

Completed wide scenes uniformly fill taller displays by cropping outer scenery.
Rendering and pointer input use the same rectangle. Unfinished backgrounds,
the options book, inventory, and vertical rooms preserve their framing; bars are
acceptable in these cases. The original gameplay region is not stretched. Movies
zoom uniformly into a centered 16:9 crop, preserving proportions while removing
12.5% from the top and bottom of the 4:3 picture. The 4:3 mode shows the complete
frame. The 16:9 crop fits within the display without additional zoom, leaving
cinematic black bars above and below on taller screens.

Horizontal panoramas at least 864 pixels wide and exactly 480 pixels tall retain
their existing 864 × 480 native viewport, camera bounds, and 3456 × 1920 working
texture. Their 16:9 canvas crops 5⅓ native pixels from each horizontal edge.
Panoramic, vertical, and two-dimensional rooms are never treated as centered
background extensions. Inventory opens as a centered overlay without changing
the room viewport, camera, display aspect ratio, widescreen artwork, or GPU
rendering path. Panoramas retain their 864-pixel viewport; inventory drawing and
item hit tests share the same centering offset. The options book retains its
centered 4:3 layout. In 16:9 mode, OS mouse confinement spans the full window
in every scene, including fixed-width rooms, inventory and the options book.
The presentation cursor can cross the side artwork freely; native hotspot
coordinates remain unchanged. Returning to 4:3 or the engine GUI restores its
normal pointer boundary. Decorative margins reject
new presses; a release outside gameplay still pairs with its original press.

Engine status retains its existing fields and adds optional `drawableWidth`,
`drawableHeight`, `renderBackend`, `presentationIntervalMs`, `presentationFps`,
`renderCpuMs`, and `cameraTop`. The backend is
reported as `opengl-shaders` or `cpu-effects`; fallback is never counted as GPU
rendering. Inventory diagnostics also expose `inventoryOpen`, `inventoryOffset`,
`mouseScriptX`, and `cursorObject`. Canvas size, native viewport, and actual
drawable size are separate.

Run `tools/venv/bin/python tools/check_inventory.py` with a `comi.s00` fixture
in `MI3_ASPECT_TEST_SAVES` to check opening, closing, input centering, both aspect
ratios, fullscreen, and panorama framing. Add `--cpu` to check the fallback path.
The check copies saves into its isolated session.

Run `python3 tools/check_aspect.py --all-panoramas` for native smoke checks using
copies of the saves and isolated configuration. It uses only engine-local input,
leaves regular Playtest saves/settings alone, and writes logs/screenshots under
`.context/widescreen/native`. Debugger jumps test presentation, not chapter
progression. Automated geometry/input checks are in `tools/test_aspect.py`.
Use `--interactions` for native save/load, panorama edge input, walking/motion
replay, inventory, movie, resize, and fullscreen checks; `--rooms 14 15` selects
a smaller room sweep. These checks use an exclusive engine-local input mode,
so desktop mouse/keyboard activity cannot interfere with the automated run.
The full sweep and interaction checks expect a cannon-room save in slot 0.
Set `MI3_ASPECT_TEST_SAVES` to a fixture save directory to use a known baseline
without changing the player's saves.

After staging a wide cannon variant, run
`tools/venv/bin/python tools/check_wide_background.py` with the same fixture
setting. It checks the displayed side pixels, centered input, both display modes,
inventory, resize/fullscreen, missing/invalid artwork, and reload/save restoration.
Sidecar failure checks use an isolated copy of the extended artwork.

The engine retains the pinned modern ScummVM fork and uses its OpenGL shader,
texture, and framebuffer classes ([ScummVM graphics settings](https://docs.scummvm.org/en/latest/settings/graphics.html)). Depth of field uses the live original z-planes;
scene objects and actors remain sharp, including transparent sprite edges.
In completed 16:9 rooms, the focus mask spans the full painting instead of
repeating the last 4:3 mask column across each margin. The center and sides use
matching focus coordinates; the GPU also samples one full-width blurred painting
to avoid a blur seam at the old 4:3 boundary. This is an artistic horizontal
remapping of the original depth coverage, not new depth data for the extensions.
The CPU fallback uses the same focus mapping. Native 4:3 and panoramic room masks
keep their original coordinates. Water coverage is independent of focus.
Color grading and vignette follow scene composition, then dialogue, inventory,
menus, and cursor render without those effects. Existing controls and saved
settings remain compatible. `hd_gpu_effects=false` selects the CPU reference.
GPU textures, blur intermediates, background conversion, unchanged depth
coverage, and costume scaling/lighting are cached. The normal native build uses
release settings, with symbols retained for profiling. Normal rendering performs no GPU-to-CPU readback; explicit
screenshots, thumbnails, and visual comparisons can request one.

Ambient water uses a lightweight GPU shader by default in the waterline (11),
where **W** opens its live tuning page. Adjust water strength, wave height,
speed, distortion, highlights, and mirrored-background reflection opacity
with **−/+** or the arrow keys (**Shift** ×5). **W** or a click on the section
heading switches between Water and Scene Look; **U/Esc** closes the panel.
Changes save as room overrides in `data/color-grades.json`; **G** switches to
global defaults. **B** compares against the painted water, **Backspace** restores
inheritance for one control, and **R** restores inheritance for all water controls
without clearing the room's color or vignette settings. Reflection defaults to
8%; the remaining controls default to 100%. Setting speed to zero freezes the
waves, and setting strength to zero reveals the painted water.

The shader also operates in
fort base (14), and town (15). It replaces only the known ambient-water costumes:
51/59, 73/74, and 80/83 respectively. Their original transparent, depth-clipped
native pixels supply coverage in the fort and town; the PNG overlays are not drawn or decoded for
those successful replacements. Character poses containing water (including
Murray), scripted splashes, and unmapped scenes retain their artwork. Packaged
PNGs and their provenance remain available for fallback.

The effect adapts the waves in the corrected user-supplied
[Shadertoy reference](https://www.shadertoy.com/view/fcGSW1): five octaves of
animated value noise, a detail wave, angle-dependent reflection, and specular
highlights. Height and normals share the noise calculations using analytic
derivatives, avoiding the reference's four additional height evaluations for
finite-difference normals. They render into a reusable 427 × 240 GPU target
for 16:9 (320 × 240 for 4:3); fine octaves fade according to the sample footprint
to reduce aliasing. Lighting and reflection run in the 1440p composite.
The waterline palette blends 65% of its original extracted water color (#0F3333)
with 35% of the selected painting; other rooms use their own painted water colors.
Reflection tint follows that palette. Stronger wave slopes, crest/trough contrast,
and broader tinted highlights make the motion visible over the painting; hull
reflections and refraction follow those ripples. The shoreline still fades gently
into the painted boundary. Existing Scene Look settings still apply afterward.
World coordinates keep
the pattern stable during camera movement. Actors, objects, and UI are protected;
color grading and vignette also affect the water. Depth of field attenuates the
fine ripples in blurred scenery. Both aspect ratios share the same effect;
authored widescreen margins inherit coverage at the original water boundary.
Water advances between native animation frames, pauses with the game, and uses
cached scene/UI textures and a native-resolution single-channel coverage texture.
On entering the cannon (0009) or waterline (0011) room, only the immediately visible character poses load on
demand. Future PNG poses from the selected pack decode on one background worker,
with at most one result waiting for the engine thread to insert into the existing
bounded cache. Visible costumes are queued before later scripted room costumes;
shader-replaced water frames are skipped. Room changes do not wait for that
worker. Missing frames and unavailable worker threads retain on-demand loading,
and SVG poses still rasterize at their actual draw dimensions. Both rooms also
skip the unused legacy costume prewarm when the selected exact pack is enabled.
Other rooms retain their current loading behavior until this rollout is validated.
This removes room-wide animation
decoding from the entry path; background decoding and first-pose loading can
still cause a smaller transition delay. No measured speedup is claimed yet.

Entering HD cannon room 0009 skips the native black/strip-wipe transition.
In GPU mode, the first completed scene starts a single one-second smooth fade-in
of the whole frame: background, side extensions, characters and scene UI appear
together. The fade runs only on final presentation, leaving cached artwork and
the cursor unchanged. Loading time precedes the fade; it does not wait for future
animation frames or add script delays. Normal redraws, aspect changes and scene
settings do not restart it. After a movie finishes or is skipped, the next
completed HD scene uses the same one-second fade, including a return to the
same room. Consecutive movies do not consume the pending scene fade. The
backend holds intermediate room-entry frames until the new composition is
ready, so loading does not show an unfaded scene first. Other room changes and
original-art fallback retain their native transitions. Leaving the HD Chapter 1
card (0004) fades the full presentation to black over one second before the next
scene fades in. Skipping an HD movie with Escape uses the same fade-out while
retaining the movie's existing crop and display rectangle. Viewport restoration
happens behind black, preventing a resized last frame from flashing on screen.
These transitions have been built but not visually verified.

The difficulty screen (room 0087, `easyhard`) opens directly on its completed HD
composition. Its native entry wipe/dissolve is bypassed when replacement artwork
is available. Presentation additionally waits for shader initialization, decoding
of the requested 16:9 background, and a complete scene composition made after
that setup. The previous frame stays visible until the full-width scene is ready;
no temporary 4:3/CPU frame is swapped first. Missing artwork or unavailable GPU
shaders retain the fallback path; movies release the room-entry hold.
Difficulty-selection scripts retain their behavior. The earlier transition-only
fix did not resolve the reported flash; this startup fix is not visually verified.

The static room-0001 logo (`0001_logo-wonder-3-5`) is skipped during HD playback:
its background is not decoded, native/HD drawing is bypassed, and its entry/exit
screen effects are disabled. No replacement black screen is inserted; the last
presented frame stays until the next movie or room is ready. Room 0001 still runs
the original opening-movie script. The source artwork and pack provenance remain
available in the workshop archive.

Only the small procedural target redraws alongside the existing scene composite;
background, coverage, and blur textures remain cached. It adds one framebuffer
pass, with no CPU-generated animation textures or GPU readback. The wave
clock stops while paused or inside the engine overlay; elapsed time does not
wrap, avoiding a discontinuity in the nonperiodic noise.

The waterline now covers the entire painted water surface. A cached flood fill of
the selected background follows bottom-connected teal water around painted
highlights, then fills each column below that shoreline. Yellow reflections no
longer truncate coverage into rectangular gaps. A guard remains inside the hull
boundary. Coverage fades in at the edge; a distorted reflection
samples the hull painting mirrored around one smooth, fitted waterline at 8%
opacity by default, separately from the stronger wave lighting and highlights.
The detailed mask controls coverage only, so hull-edge pixel steps no longer
shear the reflected planks and portholes. The shader composites over the
painted water and beneath actors and UI. In 16:9, both the center and side passes
sample the same full 2560 × 1440 background for reflections, with the center mapped
to its matching region of that image. The 4:3 working texture is used only as a
reflection fallback when no widescreen texture is active. This is a lightweight 2D approximation;
characters are not included in the reflection. If a different painting cannot be
classified, the renderer falls back to the original sprite coverage. Other rooms
keep their native water coverage. Hull reflection follows the lightweight
[2D reflection approach](https://kortham.net/posts/2d-water-reflections/), combined
with a sky reflection tinted to the room's water palette. This is an
adaptation to a fixed painted water surface: the demo's flying camera, standalone
sky, plane intersection, and distance fog do not replace the room or its framing.

A separate unreviewed cleanup draft removes the painted haze from room 11:
`assets/references/water-cleanup/0011_waterln-clean.png`. Its provenance is in
`assets/metadata/waterline-cleanup.json`. Import it through the existing background
folder controls and map it to room 11. The draft is 1448 × 1086 and is upscaled
for preview; the original 3840 × 2880 canonical master and packaged runtime remain
intact. This workspace has the draft selected, with the previous runtime/selection
backed up under `.context/water-cleanup-backup/`.

Set `hd_water_shader=false` under `[comi]` in `.playtest/scummvm.ini` before
launching to restore the existing overlays; the workshop preserves this setting
on launch/resume. CPU effects and unavailable GPU shaders retain the original
overlay path automatically. Status reports `waterBackend` as `opengl-shader`
when replacing ambient water, otherwise `original-overlays`. Disable water when
comparing existing color/blur effects against the CPU reference: procedural water
is intentionally a new GPU-only treatment. The updated engine builds, but full
runtime regressions and benchmarks remain stopped at the user's request.

Scene Look supports global defaults and individual room overrides for **all**
color, vignette, and depth-of-field controls. Open it with **U**. Press **G** or
click the panel title to switch between **Global defaults** and **Room**. Room
values inherit the global setting until edited; an asterisk marks each explicit
override, including neutral color or focus Off. **Backspace** restores the
selected room control to inheritance, and **R** restores every control in the
current room. In Global mode, Backspace restores that control's built-in default.
Changes save automatically. Existing room overrides stay active while editing
global defaults. The focus hotkeys follow the selected editing scope; the
options book's Focus preset edits the global setting.

Settings stay in `data/color-grades.json`. Schema 2 stores a `global` object and
sparse `rooms` objects; missing room keys inherit independently. Color keys keep
their existing names. Focus keys are `depthOfField` (0 Off, 1 Low, 2 High),
`blurTenths` (0 for the preset, otherwise 5–120 tenths of a native pixel),
`edgeSoftness` (0–12 native pixels), `blurIntensity` (0–100), and `sceneDepth`
(1–7). For example, a room can turn off global blur without changing its color:

```json
{
  "schemaVersion": 2,
  "global": {"brightness": 2, "vignetteEnabled": 1, "depthOfField": 2},
  "rooms": {"9": {"depthOfField": 0}, "61": {"warmth": 6}}
}
```

Existing schema-1 room grades retain their appearance, and saved INI focus
preferences seed the initial global defaults. The first edit saves schema 2 and
keeps the old file as `color-grades.json.v1.bak`. Loading alone never rewrites it.
External file edits require a game restart; the running editor refuses to
silently overwrite a file changed since it was loaded. Save games remain
independent of these authoring settings.

Drawing-only interpolation covers fixed-room actor motion and continuous
horizontal, vertical, and scripted camera pans. Scratch buffers and actor clones
are reused. Native scripts, puzzles, animation cels, audio, and movies retain
their original timing. Interpolation adds one native tick of visual latency;
intentional camera cuts, room changes, pauses, menus, and movies reset or bypass
it. `hd_smooth_motion=false` disables interpolation for comparison.

One fractional scheduler targets 60 presentations per second. With GPU effects
and display synchronization, it waits after rendering and lets the next display
refresh complete the swap; the engine adds no second presentation delay.
Unsynchronized and compatibility rendering use the engine scheduler instead. Verbose tracing is off by default (`hd_trace=false`).

Measure completed swaps, not update requests:

```sh
MI3_ASPECT_TEST_SAVES=/path/to/copied-fixture-saves \
  tools/venv/bin/python tools/check_performance.py \
  --gpu --vsync --fullscreen --effects --room 15 --motion walk \
  --seconds 60 --runs 3 --output .context/performance/panorama
MI3_ASPECT_TEST_SAVES=/path/to/copied-fixture-saves \
  tools/venv/bin/python tools/check_remaster.py --interactions
```

The benchmark records actual swap intervals, CPU rendering work, asynchronous
GPU timer results (when available), camera positions, and separate launch/jump
latencies. Acceptance is 59–61 fps, CPU and GPU p99 at most 16.67 ms, and fewer
than 1% of intervals over 25 ms. These are measured targets, not a guarantee on
untested hardware. Native loading and transition stalls remain separate from
steady motion. `check_remaster.py` saves same-tick CPU/GPU comparisons; the
native aspect interaction check compares interpolation endpoints pixel-for-pixel.
Reports and screenshots belong under `.context/` and are not packaged assets.

Room jumps use debugger-style scene transitions with current puzzle state.
They do not initialize chapter progression, inventory, or every room-specific
script condition. Use normal gameplay and saves for progression testing.

Press **J** in a ready gameplay room to open the native **Jump to Scene** picker.
Its 81 destinations come from the scene manifests, ordered by room number;
logos, chapter cards, difficulty selection, credits, and save/load screens
(rooms 1–8, 87–88, 91–93) are excluded. Gameplay close-ups and maps are included.
**Up/Down** or the mouse wheel selects a row; **Page Up/Page Down** moves 12 rows;
**Enter** or clicking a row jumps. **J/Esc** closes without jumping, and choosing
the current room closes without restarting its scripts. Opening selects and
reveals the current room. The panel shows room numbers and manifest names in
both 4:3 and 16:9, including panoramic rooms.

The picker replaces Scene Look, consumes gameplay input, and leaves running
scripts unpaused. It cannot open during a cinematic, scripted cutscene,
inventory, options book, save/load, or invalid player state. A pending jump is
discarded if the engine becomes busy or the source room changes before it runs.
Native and workshop jumps share the same engine-thread transition. The catalog
is embedded during engine patching, so the browser need not be open. Rebuild
after changing scene names. This feature is enabled by `playtest_session`.

Run `python3 -m unittest discover -s tools -p 'test_scene_jump.py'` for catalog
and request-lifecycle checks. With a built runtime and a copied cannon save in
`MI3_ASPECT_TEST_SAVES`, run `tools/venv/bin/python tools/check_scene_jump.py`
for isolated keyboard/mouse, overlay, and aspect-ratio checks. Screenshots and
test saves stay under `.context/scene-jump/native/`.

Backgrounds are replaced throughout the imported pack. The cannon-room test pack
also includes the 105 supplied costume frames and four objects processed with
Topaz. Other characters, masks and interface text retain their original assets.
All 15 cinematics use the supplied HD video pack described below.
Game text uses the supplied efmi/sharp sheets at 4× with original NUT metrics.
The normal/active mouse pointer uses the original red pixel artwork with its black outline. Navigation arrows use the supplied remastered UI package.
The inventory panel and checked menu checkbox use the reviewed Topaz cutouts
described below.
Visual seams or sprite compositing issues can require later engine/artwork work.

HD room objects preserve visible original-character pixels when a pose has no
replacement artwork. The native scene masks still determine foreground
occlusion; fully replaced poses are composited afterward in actor depth order.
`python3 -m unittest discover -s tools -p 'test_object_depth.py'` checks this
object compositing path at 4× and 6×, including viewport clipping and UI overlap.

Room-object PNG edges use continuous source-over blending into an opaque scene,
instead of discarding coverage below 128 and copying partially transparent pixels.
The cannon treasure door (room 9, object 275) additionally extends nearby opaque
colors into soft edge pixels to remove its gray matting fringe at render time.
Its PNG, alpha coverage, and opaque interior remain unchanged. The native
regression exercises every alpha value and checks fringe correction bounds;
the corrected cannon scene was rebuilt and inspected in-game.

Guybrush's separate head poses (costume 2, cels 4, 34, 47, 52, 58, and 63)
use the same soft-edge color correction before applying room lighting. Only
neutral gray fringe is corrected, preserving soft black ink and colored hair
edges. The head's original alpha coverage, opaque artwork, scale, and AKOS offsets stay
unchanged. Other costume pieces retain their existing rendering. Source PNGs
are preserved; rebuild and restart the engine to activate this correction.

To restage the completed cannon batch, stop the game and run
`tools/venv/bin/python tools/stage_topaz.py` from the repository root. It converts
the transparent 6× masters to the engine's 4× dimensions, maps object IDs from
the game index, and preserves existing unrelated HD assets. Costume filenames
use the engine's `_aframe_` convention. All 113 PNGs are staged, including four
positioned object layers retained for reference; the engine renders the standalone
objects. `.playtest/topaz-staging.json` records source hashes and destinations.
Launch again to refresh the costume index and texture caches.

## Local files and API

- `.playtest/state.json`: machine paths, imported Variant records, per-asset test
  selections. Approval status in the existing scene manifests is independent.
- `upscaled/imported/`: preserved masters named by SHA-256. Reimporting the same
  contents for a room reuses the variant.
- `.playtest/game/`, `hd/`, `saves/`: combined disc data, generated PNGs, isolated saves.
- `.playtest/engine/`: pinned source and native build. `tools/build_engine.sh`
  applies the versioned patches in `tools/engine/` to upstream revision
  `43c1d07613e3c34b9c8cfc7ab168575212864d48`.
- `.playtest/session-*/`: private command/status files and game logs. A workspace
  lock prevents another server from starting a second game session.
- `.context/`: screenshots and local verification artifacts.

All generated/imported files above are ignored by Git. Existing scene manifests
are not rewritten by folder imports. Imported variants appear in Playtest;
the existing approval/export workflow continues to use its existing variants.

The localhost-only `/api/playtest` API provides GET snapshot, GET scan, PUT
settings/selection, POST discs/build/import/launch/stop/jump/apply, and GET events
(SSE). Non-GET requests require JSON. Import requests contain
`{items: [{file, room}]}`; selection contains `{room, variantId}` (null selects
original); jump/apply contain `{room}`. The local engine bridge accepts only
`{id, action: "jump" | "reload", room}` and atomically acknowledges commands
in `status.json`. Commands time out after eight seconds. Stale status disables
controls; commands are checked again on the engine thread before execution.

## Verification and troubleshooting

Run `cd app && npm test && npm run typecheck && npm run build` and
`python3 -m unittest discover -s tools -p 'test_*.py'` from the repository root.
The tests use temporary data and a fixture engine; they do not modify your art.

Live verification on this Mac covered cannon room (9), town panorama (15),
room jumping, movement/camera scrolling, foreground overlap, background reload,
and original/remaster switching. Browser checks covered desktop and mobile,
room browsing, asset-library navigation, and console errors.

The Mac config enables VSync with the pinned SDL2/OpenGL build. Performance
checks report completed swaps and identify CPU fallback explicitly.
A missing-HD message for costumes, fonts, objects, or audio outside the supplied
test pack is expected. The Topaz pack includes Guybrush's standing and eight-direction walking frames
and Wally's standing body/head poses. Other dialogue and story poses can still
use original artwork. If a jump is unavailable, finish the opening/cutscene or
close the in-game menu. The activity log and session `engine.log` explain failures.

For automated native smoke tests only, start the server with
`MI3_ENGINE_TEST_INPUT=1`. A private session `test-input.txt` can contain
`screenshot`, `key <SDL keycode>`, or `click <window-x> <window-y>`.
The hook injects events only into that engine, never into other apps. This
hook is off during normal operation. Built-in screenshots go into `.context/`.

Upstream engine: https://github.com/harrytyp/comiupscale (ScummVM GPL licensing;
see its COPYING and source headers). The build downloads source, not game data
or a third-party remaster pack. No engine binary or game data is committed here.

Puerto Pollo’s town panorama (room 15) also retains native transparent wave
animation for costumes 80 and 83, matching the beach fallback for costumes 73
and 74 in room 14. Their generated gray-matte PNGs are bypassed in both costume
rendering paths; the HD water background and other town assets remain active.

## Cinematics

The 15 supplied MP4s from `~/Desktop/monkey/videos` are installed in
`.playtest/hd/videos/`. Masters are preserved at 2880 × 2160, 12 fps; FFmpeg
decodes to the current 2560 × 1920 game framebuffer without cropping. The
original SAN files supply audio, subtitles, timing, and the return to gameplay.
The MP4 audio track is not played. Escape still skips a cinematic.

Movies follow the options book's **Display** setting: in **16:9**, the backend
zooms uniformly into a centered 16:9 crop of the 4:3 framebuffer, removing 12.5%
from the top and bottom without stretching. Composited subtitles follow the same
uniform zoom. In **4:3**, the complete original framing remains. Only HD pictures are displayed. Native SAN files
remain necessary for audio, subtitles, and timing; their original video frames
are never presented. In widescreen mode, the selected 16:9 frame fits within
the display, with cinematic black bars above and below on taller screens.
Playback completion or skipping restores the room's presentation, including
panoramas, and fades the next completed HD scene in over one second using the
opening scene's smooth fade. Source videos are never re-encoded.

To restage the pack, install FFmpeg with `brew install ffmpeg`, then run
`python3 tools/stage_videos.py [source-folder]`. The script validates every
movie before copying, maps `SINKSHP.SAN` to `SINKSHIP.mp4`, records hashes in
`.playtest/video-staging.json`, and backs up differing installed copies.
Source MP4s and the original game archives are unchanged. The renderer looks
for FFmpeg in the Homebrew locations, then PATH; `ffmpeg_path` in the game's
config can override this for a manually launched engine.

`FG010GP.mp4` omits ten trailing black frames, and `FINALE.mp4` includes ten
extra trailing black frames. The native timeline remains authoritative: a
shorter replacement holds its last frame and a longer one ends with the SAN.
Missing or undecodable HD movies are skipped with a clear on-screen message;
the game never falls back to the old footage. Decoder errors after playback
starts also skip the remaining movie. A clean end of the supplied shorter HD
clip still holds its final image through the native tail. Unsupported nonzero
native movie offsets are skipped with the same message (normal COMI scripts
start each cinematic at frame zero). Keep the original SAN files for their
audio, subtitles, and timing data.

The replacement decoder advances on every native frame, including frames the
display scheduler skips, so display drops do not accumulate picture/audio drift.
HD cinematic subtitles use the same sharp font sheets as gameplay, drawn at
the final framebuffer resolution after the movie is decoded. They honor the
in-game text-size preference (65% by default), proportional letter spacing,
native timing and colors, and hard black shadows. Missing sheets and unsupported
CJK/RTL text retain native subtitle rendering. The subtitles setting remains
available. Rebuild the engine after updating the cinematic font renderer.
Run `python3 -m unittest discover -s tools -p 'test_video_staging.py'` to check
staging validation, naming, backup behavior, and subtitle compositing.
For native smoke tests launched with `MI3_ENGINE_TEST_INPUT=1`, write a SAN
filename such as `SINKSHP.SAN` to the isolated session's `movie.txt` to play it
through the normal movie player. The hook is disabled in regular sessions.
Run `tools/venv/bin/python tools/check_movies.py` for isolated native checks of
both aspect ratios, HD-only playback, missing/broken-HD messages,
skipped/completed playback, and room restoration. Screenshots and results are saved under `.context/movie-check/`.

## Character comparisons

The **Cannon-room characters** selector chooses Topaz, Topaz crisp borders,
Quiver, or Original at launch. Packs live separately in `hd/topaz-cannon/`,
`hd/topaz-crisp/`, and `hd/quiver-cannon/`. Switching never overwrites another
pack. Stop the native game before choosing another version. Quiver is available
once its workflow stages the reviewed pack. Topaz crisp borders uses a locally
refined transparency contour and ink edge; the original Topaz masters remain
available in the asset viewer's **Border version** selector.

## UI samples

The supplied `coin + cursores` package installs 30 pointer images and all five
verb-coin states. With the game stopped, run:

```sh
tools/venv/bin/python tools/stage_pointer_coin.py "/path/to/coin + cursores"
bash tools/build_engine.sh
```

The installer validates 6× RGBA images against the original object canvases,
then resizes to 4× with premultiplied-alpha Lanczos filtering. The antialiased
variant matches the engine's alpha-blended cursor overlay. The normal and highlighted mouse pointer (object 105) uses the original native
red pixels and black outline, scaled with nearest-neighbor sampling. Restore
this selection after UI staging with
`tools/venv/bin/python tools/stage_original_pointers.py --pointer-only`. The
installer corrects outline palette index 39 to black and uses the red state
for both images. The supplied navigation arrows remain active. Original hotspots and AKOS coin offsets are unchanged.
The 464×472 coin images render independently of the selected character pack;
original animated glints remain over the replacement coin. Missing replacement
coin states retain the native pose. Restart after staging to refresh caches.

Sources remain untouched. `.playtest/pointer-coin-staging.json` records source
and installed hashes, scale, and variant; previous textures and object mappings
are backed up under `.playtest/backups/pointer-coin-*/`. Images and reports stay
outside Git. The `stage_original_pointers.py --pointer-only` utility restores the selected
pixel mouse pointer without changing navigation arrows or the coin.

The current coin artwork comes from `~/Desktop/monkey/coins`.
To replace only the five coin states, stop the game and run
`tools/venv/bin/python tools/stage_coins.py "/path/to/coins"`, then restart.
This preserves pointers and object mappings, validates all five 696×708 RGBA
masters, and installs 464×472 images. `.playtest/coin-staging.json` records the
active coin hashes; `.playtest/backups/coins-*/` preserves the previous coin
images. Running the full pointer/coin installer above also replaces the coin;
rerun `stage_coins.py` afterward to retain this newer selection. Character
rendering also accounts for the replacement coin's transparency, so the wider
native coin silhouette does not hide characters around the new outline.

Five Wonder 3.5 High 6× jobs produced six usable UI files (the two north-arrow
states share one result): normal and active cursor, north arrow, hook inventory
icon, and inventory panel. Their masters remain in `output/topaz-batch/6x/objects/`.
`tools/venv/bin/python tools/stage_ui.py` installs only completed room-3 UI
outputs at 4×, merging object mappings without changing character packs.
After restoring the original arrows, a new background-removal pilot was reviewed
and approved. Its inventory panel and checked save/load/options checkbox remain installed at
native 4×. These preserve Topaz's enhanced RGB and provider transparency, without
restoring original edges. The hook icon remains from the earlier sample.
`ui-staging.json` records the installed files. Previous runtime assets and mapping
are backed up in `.playtest/backups/ui-cutouts-20260923-145343/`.

The approved cutouts and receipt live in `output/topaz-ui-objectmatting/`.
With the game stopped, `tools/venv/bin/python .context/install-reviewed-ui-pilot.py`
restages that reviewed selection, including its replacement pointers. Run
`stage_pointer_coin.py "/path/to/coin + cursores"` afterward to restore the supplied pointers and coin.
The older `stage_ui.py` command uses the legacy 6× versions; after running it,
restage the approved pilot to restore the reviewed cutouts. The remaining UI batch is paused;
fonts and save/load/options artwork are excluded. The original game archives
remain untouched. Engine cursor support uses exact image states, original
hotspots, alpha blending, and clipping at the viewport edges.

The optional launch API `{ "resume": true }` prefers the existing manual COMI
save in slot 1, then falls back to autosave slot 0. HD backgrounds are restored
on the engine thread after loading a save.

## Scene object visibility and sea animation

HD room objects follow COMI's native state and parent-state visibility rules.
Floating inventory resources are drawn through the existing blast/verb UI passes,
not the room pass. A loaded inventory image or unrelated foreground pixels never
imply that inventory is open. Native object state 1 selects extracted image 0;
a missing replacement state retains the native image instead of showing another
state. This also avoids unsafe foreground sampling as objects scroll offscreen.

Puerto Pollo (room 14) uses its native transparent, palette-driven ripples for
costumes 73 and 74 over the HD background. Their generated replacements contain
an opaque gray matte and baked colors, so those two effects bypass HD costume
replacement. Waves remain animated and respect native foreground depth; their
resolution remains native until correctly prepared HD effect assets are available.
Other costumes keep their selected replacement pack.

Run `PYTHONPATH=tools tools/venv/bin/python -m unittest test_scene_visibility test_object_depth`
for visibility, image numbering, water routing and depth checks.

## Inventory panel and item layers

When the replacement inventory panel is available, the engine suppresses the
original panel and draws the replacement above the scene, followed by the items
in the native blast queue. Collected items retain their original positions and
hitboxes. Icons without HD artwork use their original image and palette on top
of the new panel. Hover text and the verb coin remain above both layers.
Closing the inventory removes the overlay; missing panel artwork retains the
original inventory. Rebuild with `bash tools/build_engine.sh` after updating.

Run `tools/venv/bin/python -m unittest tools/test_inventory.py` for alpha blending,
native icon fallback, clipping, 4×/6× geometry, and repeatable patch ordering
that keeps scene color grades off inventory artwork. Native verification uses
copied saves: pick up the cannon-room ramrod, open inventory with I, hover/select
it, then close and reopen the panel in both aspect modes.

## Character lighting

Guybrush's opening stand-up animation in room 0009 uses costume 3, stored under
room 0001. Its Topaz frames 15 and 16 have invalid alpha masks that cut off the
lower legs and feet; both are already marked rejected. The Topaz and Topaz Crisp
loaders exclude those two PNG replacements and preserve the complete native
poses for those frames. Other stand-up frames and animation timing are unchanged.
Rejected masters/runtime PNGs remain archived for repair, and other character
packs are unaffected. Restart after rebuilding to refresh the frame index.

In room 0009 those two native poses use the base palette plus the same fixed
warm actor tint as adjacent HD frames, avoiding a flash from the live intro
palette. Their captured native silhouette and occlusion remain intact.
For the standing Topaz head 52/body 31 pair, the renderer also extends the
head's penultimate row into its empty final alpha row. This closes the thin
line underneath the head without repositioning either cel or changing PNGs.
The repair requires the matching body and original one-pixel overlap, and
applies to mirrored poses as well as the software and GPU compositors.

Characters also receive procedural contact shadows on the floor. The solid
ellipses use the actor's ground Y, scale with the character, and become
wider/fainter with physical elevation. Walking poses no longer move the shadow
up/down as their lowest visible costume pixels change. They sit 3 native pixels
above the ground anchor and are 20% larger than the initial oval footprint.
Scripted scene-aligned poses such as Wally's calibrate a fixed anchor from the
first valid painted feet, stored in room coordinates and refreshed on room,
costume, or artwork-reload changes. Camera movement and actual movement across
the ground still move the shadow; the Position Y control adds to that anchor. Grounded shadows use uniform 38/255 (15%) black opacity
inside the oval, with a hard edge and no spread into the surrounding corners.
No shadow image assets or blur passes are required. These remain the default
appearance until the shadow controls are adjusted.

Open **U → Tab → Tab** from Scene Look for **Character Shadows**. Use arrows or
−/+ buttons to adjust, with **Shift** for five steps. **G** switches between
Global defaults and the current room; changes save immediately in
`data/color-grades.json` and persist across launches.

| Control | Range | Default |
| --- | --- | --- |
| Position X / Y | −80 to +80 original game pixels; positive is right/down | 0 / 0 |
| Width | 25–300% of the character's automatic footprint | 100% |
| Ovalness | Height as 5–100% of width; low is flat, 100% is circular | 24% |
| Opacity | 0–100%; zero hides the shadow | 15% |
| Color red / green / blue | 0–255 per channel | 0 / 0 / 0 (black) |

The keys are `shadowOffsetX`, `shadowOffsetY`, `shadowWidth`, `shadowOvalness`,
`shadowOpacity`, `shadowRed`, `shadowGreen`, and `shadowBlue` in the global or
room layer. **Backspace** resets one control, **R** resets only the shadow page
(to defaults globally, or inheritance for a room), and **B** temporarily hides
shadows for comparison. Editing a shadow value exits that comparison. Offsets
move the rendered shadow relative to the feet; actor movement and hit areas stay
unchanged. The same settings feed both CPU and GPU composition in 4:3 and 16:9.
These controls were built without running tests or visual validation.

This pass runs beneath native foreground, HD objects, characters, text and the
cursor, and uses captured native depth masks. It covers eligible shadow-enabled
actors, Guybrush's walking costume and cannon-room Wally; broad props, clipped
portraits and poses without captured drawing data are skipped. Validation covers
room 9; placement in other scenes depends on their native pose/depth data.
Run `python3 -m unittest discover -s tools -p 'test_actor_shadow.py'` for footprint,
scripted origin, elevation, edge/prop exclusion, uniform opacity and oval-boundary tests.

HD character artwork outside room 0009 uses half the previous exaggerated
lighting strength: squared native gains blend 50% toward neutral, with
brightening capped. In the cannon room, all HD costume poses use the fixed warm
RGB tint (255, 233, 198) at full brightness from their first frame. Native palette
fades and spatial darkening no longer turn these PNGs black or gradually reveal
their colors after the intro. Pose animation and image alpha are unchanged.
Other rooms retain their native color direction at the reduced strength, and
their fades still reach true black.
The compositor samples native actor colors once per room/costume/palette mapping
so talking, turning, and overlapping another actor cannot change the sample
weights and cause hue jumps. Live palette lighting continues to update using
those stable samples. Original fallback poses keep their native shading.
Loading a save clears the samples and uses the restored original palette state;
there is no separate lighting state in saves.

Earlier live verification in room 9 covered the former varying warm tint;
the fixed-color change has been built but not visually verified. The periodic `LIGHTING` entries in
`hd_state.log` include actor position and native/applied RGB gains (255 is neutral);
`QUIVER` entries also include `light=R,G,B`. With `MI3_ENGINE_TEST_INPUT=1`,
writing `x y` to the session's `walk-to.txt` requests a normal actor walk for
repeatable lighting checks, including the room's usual scripts and pathfinding.
Run `python3 -m unittest discover -s tools -p 'test_actor_lighting.py'` to check
palette rounding, unused colors, transparency, neutral restoration, blackouts,
brightening, pronounced spatial color/brightness changes, fade continuity,
and stable animation samples.

## HD font sheets

All five game font slots use the supplied `fonts-6x/efmi/sharp` sheets, adapted
to the current 4× renderer, with hard black shadows on all game text.
Subtitles, dialogue responses, object labels, and
in-game menu text share this sheet replacement path. The workshop UI is unchanged.
Text defaults to **65% size**. Open the original in-game options book with **F5**
and use **Text size − / +** to adjust from 25% to 100% in 5% steps. Changes apply
immediately and survive relaunches. The setting scales glyphs and original NUT
metrics together for advances, wrapping, centering, and response hit rectangles.
Fractional advances are retained until HD rendering so the original letter-spacing
proportions stay intact without adding tracking;
speaker colors, highlighting, subtitle settings, and timing still come from the
game. The size-control row stays at a readable fixed size.

With the game stopped, install or restage the package using Pillow:

```sh
tools/venv/bin/python tools/stage_fonts.py ~/Downloads/fonts-6x
```

The utility validates all five 5376 × 5376 RGBA PNGs and their binary alpha
before replacing any active font. Nearest-neighbor resizing produces 3584 × 3584
sheets with a 16 × 16 grid of 224 × 224 cells. The files are installed as
`.playtest/hd/fonts/FONT0.NUT_chars.png` through `FONT4.NUT_chars.png`.
`.playtest/font-staging.json` records the variant, scale, dimensions, and source
and destination SHA-256 hashes. The supplied 6× originals remain untouched;
images and the staging report are ignored by Git.

After resizing, FONT0–3 receive a fully opaque black glyph shadow offset
4 pixels down and right (one original game pixel), without blur. Existing fills,
outlines, and glyph positions are preserved. Each cell is processed separately
and checked for shadow overflow. FONT4 retains its supplied shadow rather than
receiving a second one. The staging report records the shadow settings as well.

Use the sharp variant because the existing `HdFontManager` thresholds alpha
and forces drawn pixels opaque. The engine scales the sheets with nearest-neighbor
sampling for the chosen text size, retaining hard black shadows. It also
prevents disabled legacy dialogue atlases from intercepting subtitles and
dialogue choices before the new sheets render. Rebuild older engines once
with `bash tools/build_engine.sh`; subsequent sheet changes only need a restart.
The preference is stored as `hd_font_size` in the local `scummvm.ini` COMI section;
the Playtest launcher preserves it when refreshing its configuration.
The supplied 6× sheets must not be installed
unchanged at the current 4× composite size: text would be 50% too large.
White fill takes the game's text color; black outlines and FONT4's drop shadow
remain black. Empty source cells, including codes `0xD7` and `0xFD`, remain
empty; this installation does not add missing glyphs or change fallback behavior.

Restart the game after staging; sheets load only at startup. To disable these
replacements, move `hd/fonts/` outside the active HD directory and restart.
The older dialogue-only replacement remains disabled in
`.playtest/backups/original-ui-20260923-143927/hd/dialogue-font/`.
Do not run `prepare_dialogue_font.py` to install this package: that creates
separate atlases and metrics which override this path for dialogue. The staging
utility rejects an active legacy dialogue-font metrics directory.

Run `python3 -m unittest discover -s tools -p 'test_dialogue_font_scope.py'`
to check that missing legacy atlases leave the sheet path active, while nested
dialogue/menu scopes still restore their previous state.

The opt-in native test input hook accepts `screenshot`, `move x y`,
`down x y`, and `up x y` for visual and response-hover checks. Verify all five
sheets load with 224 × 224 cells, then inspect subtitles, dialogue choices and
highlighting, object labels, and save/load text. Save screenshots in `.context/`.

The cannon itself (costume 26) now has all 14 animation cels processed directly
at 4× with Wonder 3.5 High. Run `tools/venv/bin/python tools/stage_cannon.py`
with the game stopped to install them in both Topaz packs. This is separate
from character-border variants and from the reviewed UI samples.

## Damaged speech entries

The supplied disc-1 voice bundle contains malformed sound headers, and its imported
copy matches the ISO byte for byte. The audio loader now checks the entry bounds,
header tag, and compression-table count before loading a sound. Invalid entries
are skipped with a warning instead of aborting the game; affected speech can be
silent, while valid audio and subtitles continue normally. Restoring those voice
lines requires a clean `VOXDISK1.BUN` from the same game edition/language.

`tools/engine/patch_bundle_audio.py` applies the fix on engine builds. Run
`tools/venv/bin/python -m unittest discover -s tools -p test_bundle_audio.py`
to exercise the actual patched C++ loader with valid and malformed fixtures under
AddressSanitizer and UndefinedBehaviorSanitizer (prepared engine source required).
