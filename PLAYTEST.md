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

The engine framebuffer is 2560 × 1920 (4× the original 640 × 480).
Full 6× masters (3840 × 2880 for standard rooms) are preserved separately.
The 6× renderer was tested, but this Mac was too slow, so runtime rendering and
all staged assets are back at 4×. The default output is 4:3 at 2560 × 1920.
In the original options book (**O** or **F5**), **Display** selects **4:3** or
**16:9**; **Esc** resumes play. The selection persists across launches.
The 16:9 presentation target is 2560 × 1440: fixed-width scenes occupy
1920 × 1440 with 320-pixel black margins on each side. Window resizing and
fullscreen scale that presentation uniformly. On a 3840 × 2160 display, a
fixed 4:3 scene occupies 2880 × 2160 with side bars.
The supplied 3840 × 2880 masters and wider/taller room images are preserved.
Engine copies use four times each **room's** original dimensions, not a fixed
screen-sized crop. Images with incompatible proportions cannot be applied.

In 16:9, horizontal rooms at least 864 pixels wide and exactly 480 pixels tall
reveal more of their existing panorama. The native viewport is 864 × 480 to
respect eight-pixel strips; its 3456 × 1920 HD working texture is uniformly
scaled to the display with 5⅓ native pixels of horizontal overscan at each edge.
This working texture is not the output resolution. Original room coordinates,
scripts, walkboxes, HD asset selections, and source images remain intact.
Narrow, vertical, and two-dimensional rooms and movies keep their existing
framing. The options book and inventory use the centered 4:3 area, including
when opened from a panorama; closing either restores the wider viewport.
Black margins are noninteractive; releasing a press that
began in gameplay releases it at the last valid position. No side artwork is
imported or generated, and future 16:9 artwork does not replace current masters.

`hd_aspect_ratio=43` (default) or `169` in `.playtest/scummvm.ini` records the
selection. Existing engine-status fields retain their meaning; additive
`aspectRatio`, `outputWidth`, `outputHeight`, `viewportWidth`, `viewportHeight`,
`cameraLeft`, and mouse-world coordinates expose presentation diagnostics.

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

The engine is built with compiler optimizations and targets 60 Hz presentation.
The HD pointer updates between native game ticks using small dirty rectangles;
it no longer waits for a full character/scene redraw. Script, movement, animation,
audio, and movie timing remain original: this does not synthesize 60 animation
cels per second or interpolate the supplied 12 fps videos. The old additional
30 fps sleep has been removed. Actor foreground masks are resolved once per
rendered row, preserving native occlusion and camera offsets.

On this Mac, room-9 testing after loading held about 60 presentation updates per
second, with typical HD composite times of 7–11 ms instead of the earlier
60–90 ms. Cold asset loads and room/video transitions can still cause spikes.
`HD-PRESENT` in the session's `hd_state.log` measures presentation frequency;
the older `FRAME-TIMING` line measures CPU composite cost, not animation FPS.
Run `PYTHONPATH=tools tools/venv/bin/python -m unittest test_frame_pacing
test_object_depth test_actor_lighting test_svg_engine test_ui_staging` for the
pacing, mask-offset, lighting, SVG, and UI regression checks.

HD horizontal scrolling rooms now interpolate camera and actor positions between
native ticks at the 60 Hz presentation rate. Intermediate renders use actor
copies, the last drawn costume pose, and scratch native buffers/masks; scripts,
walking, audio, and animation cels retain their original timing. This adds one
native tick of visual latency (about 83 ms at the beach), without extrapolation
or frame blending. Mouse world coordinates follow the displayed camera.
Room changes, large jumps, pauses, dialogue, inventory, menus, and movies bypass
interpolation. Vertical rooms retain the existing presentation path. Set
`hd_smooth_motion=false` in the engine configuration to disable it for diagnosis.
Panorama backgrounds are fully refreshed at native ticks, fixing missing vertical
strips through static sprites during scrolling.

Validation: `PYTHONPATH=tools tools/venv/bin/python -m unittest test_motion
test_frame_pacing test_object_depth test_actor_shadow test_actor_lighting`.
Native room-14 and room-15 walking checks measured approximately 60 presentations/second and
6–7 ms per intermediate render. A target-position replay matched the normal
4× compositor pixel-for-pixel (4,915,200 pixels) in both rooms. Room changes and
opening/closing the game menu also passed. With `MI3_ENGINE_TEST_INPUT=1`,
creating `motion-check` inside the active session records this comparison in
`motion-check.json` and two PNGs. The comparison runs while motion is active.

Room jumps use debugger-style scene transitions with current puzzle state.
They do not initialize chapter progression, inventory, or every room-specific
script condition. Use normal gameplay and saves for progression testing.
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

The Mac config disables VSync because SDL2-compat/SDL3 stalled in OpenGL buffer
swap on this machine. The engine's existing frame limiter remains active.
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
Missing or initially undecodable replacements use the original movie. Movie
playback starting at a nonzero native offset also uses the original.

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

## Character lighting

Characters also receive procedural contact shadows on the floor. The solid
ellipses follow the feet of complete costume poses, scale with the character,
and become wider/fainter with physical elevation. They sit 3 native pixels
higher beneath the feet and are 20% larger than the initial oval footprint. Scripted scene-aligned poses
such as Wally's use their painted feet rather than treating drawing-origin
metadata as a jump. Grounded shadows use uniform 38/255 (15%) black opacity
inside the oval, with a hard edge and no spread into the surrounding corners.
No shadow image assets or blur passes are required.

This pass runs beneath native foreground, HD objects, characters, text and the
cursor, and uses captured native depth masks. It covers eligible shadow-enabled
actors, Guybrush's walking costume and cannon-room Wally; broad props, clipped
portraits and poses without captured drawing data are skipped. Validation covers
room 9; placement in other scenes depends on their native pose/depth data.
Run `python3 -m unittest discover -s tools -p 'test_actor_shadow.py'` for footprint,
scripted origin, elevation, edge/prop exclusion, uniform opacity and oval-boundary tests.

HD character artwork uses half the previous exaggerated lighting strength:
squared native gains blend 50% toward neutral, with brightening capped. In the
cannon room, Guybrush and Wally share the same warm orange RGB proportions
(255, 233, 198); their live native luminance controls brightness independently.
Walking between the grate, floor and dark corner still changes the shading,
without switching one character to a different hue. Other rooms retain their
native color direction at the reduced strength.
Fades still reach true black, and replacement image alpha is unchanged.
The compositor samples native actor colors once per room/costume/palette mapping
so talking, turning, and overlapping another actor cannot change the sample
weights and cause hue jumps. Live palette lighting continues to update using
those stable samples. Original fallback poses keep their native shading.
Loading a save clears the samples and uses the restored original palette state;
there is no separate lighting state in saves.

Live verification in room 9 covered Guybrush's warm shaded tint and its changes
between areas of the cannon room. The periodic `LIGHTING` entries in
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
