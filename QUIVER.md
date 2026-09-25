# Cannon character SVG workflow

The CLI uses Quiver `arrow-2` with original sprites and a character reference.
SVGs are the masters and the default runtime assets. The engine opens SVG files
directly and rasterizes them in memory at 4× the original cel dimensions, caching
the resulting RGBA textures. No PNG sidecar or browser renderer is required.
PNGs are also rasterized at 6× for delivery and 4× for optional PNG installation.
Generated material stays in ignored `output/quiver-cannon/`.
Original game data and the existing Topaz pack are preserved.

## Guybrush walking preview

`tools/quiver_walk.py` selects the 96 walking cels and 12 standing parts from
costume 2's actual AKSQ/AKCH animation records. Its real Quiver Arrow 2 outputs
live in `output/quiver-cannon/walking-vectorized/`. This is separate from the
older locally traced SVG decoder fixtures described below.

The initial reference-guided text generation shifted the pose and was rejected.
The walking workflow instead uses Quiver's Arrow 2 image-to-SVG endpoint,
`POST /v1/svgs/vectorizations`, with `auto_crop: false`. Each original is placed
inside a known square transparent reference canvas. After generation, that exact
padding transform is inverted to recover the original cel canvas; the subject
is never automatically fitted or recentered. Raw provider responses, request IDs,
token usage, corrections and output hashes remain in the journal.

```sh
tools/venv/bin/python tools/quiver_walk.py prepare --operation vectorization --output output/quiver-cannon/walking-vectorized
tools/venv/bin/python tools/quiver_walk.py pilot --output output/quiver-cannon/walking-vectorized
tools/venv/bin/python tools/quiver_walk.py accept --output output/quiver-cannon/walking-vectorized --eyes-reviewed --key FULL_ARTWORK_SHA256
tools/venv/bin/python tools/quiver_walk.py generate --output output/quiver-cannon/walking-vectorized --workers 2
tools/venv/bin/python tools/quiver_walk.py status --output output/quiver-cannon/walking-vectorized
```

Generation stops on errors or rejected geometry, drains requests already in
flight, and never repeats a paid submission automatically. `validate --key ...`
reprocesses the cached response. Small, manually reviewed anchor corrections can
be recorded in the output's `calibration.json` with a reason, uniform scale and
x/y translation. These still must pass the original strict geometry checks.

Some Arrow outputs flatten shadows into gray or omit them. Spatial comparison
with the original shadow mask identifies flattened shadow paths and restores
black at alpha 128. Only connected ground-shadow regions near the feet qualify;
partial-alpha outline fragments and detached heads are excluded. If absent, only
the original shadow mask is converted to
vector paths using the `potrace` executable (install with `brew install potrace`).
Character artwork originates from Quiver. Reviewed SVG cleanup also corrects
missing fills, white eye rims with dark dot pupils, tapered eyebrows and rounded
hair contours. Eye centers stay at the source cel's measured landmarks. Repairs
are bound to the raw response hash in `repairs.json`; raw responses remain intact.
There are no embedded PNGs. Every correction is recorded. Sharp produces exact 6× and 4× transparent PNGs;
`tools/quiver_native_render.cpp` also permits checking the masters through the
same NanoSVG decoder used by the game.

After visual review, accept all validated keys and run:

```sh
tools/venv/bin/python tools/quiver_walk.py install --output output/quiver-cannon/walking-vectorized
# Restore the previous pack if needed:
tools/venv/bin/python tools/quiver_walk.py restore --output output/quiver-cannon/walking-vectorized
```

The stand chore changes only the body; six neutral heads from talk-stop/init
complete its multipart poses. Installation requires all 108 selected cels to be accepted and preserves the
previous pack. Select Quiver and restart the game. Walking and standing use these
SVGs in room 9; speech and action cels outside this selection use original art.
Use `status` for current completion and token-based cost estimates.

The complete walking selection has 108 generated outputs: 96 walking cels and
12 multipart idle pieces. Vectorization usage, including two archived rejected
attempts, is 75,794 input / 666,673 output tokens, estimated $13.636636 at recorded
rates. The rejected text-generation pilot adds $0.166436. These are token-based
estimates, not billing receipts. All SVG masters have exact 6× and 4× transparent
PNG derivatives.

`tools/quiver_eye_review.py` creates aligned source/output face sheets and checks
dark pupils at original eye centers. `tools/quiver_curve_style.py` rounds sharp
Bezier joins without fitting or recentering a sprite. The approved curved eyebrow
reference is cel 649; per-cel corrections, including brows joined to nose paths,
are recorded in the output repair manifest. Run `validate --key ...` to reproduce
these local corrections without paying for generation again.

`retry-rejected --key ... --reason ...` archives a completed, identified rejected
response and marks it ready for an explicit new submission. It cannot retry an
uncertain request. `generate --key ...` can select never-submitted frames; this
does not bypass the complete-set installation gate. `accept --eyes-reviewed`
records a visual review against the current SVG hash.

The isolated preview in `.context/quiver-walk-preview/` uses the known-working
4× executable and explicit `playtest_scale=4`, matching its 4× scene assets.
Do not substitute an engine defaulting to 6× without matching scene dimensions.

## Shared brush outlines

`brush-style.json` enables the reproducible local vector-ink pass in
`tools/quiver_brush.py`. Explicit SVG strokes use a shared 1-original-pixel
base weight (4 pixels at runtime 4×), warm dark ink `#30231b`, gentle ±10%
directional pressure, and tapered open ends. NanoSVG resolves transforms first,
so detached heads and full-body frames receive the same physical stroke weight.
The resulting brush ribbons are editable filled SVG paths, with no filters,
textures, embedded raster images or random per-frame roughness. Existing filled
ink features, including pupils, tapered eyebrows and compound outline shapes,
retain their geometry and receive the shared ink color. Shadows retain alpha.
Pre-brush walking masters and derivatives are preserved in `before-brush/`.

## Wally cannon artwork

`tools/quiver_wally.py prepare` selects 221 character cels from costume 25 and
costume 28 using archive character metadata. Costume 28 cel 1 is a standalone
whip, excluded from character replacement; its attempted generation and usage
remain journaled for audit. Separate head/body parts and integrated accessories
remain in scope. The four pilots cover a head, body, armed full-body pose and
crying pose. Generation shares the walking CLI's no-retry journal, known canvas
registration, geometry checks and brush pass. Use `status` for live completion.

```sh
tools/venv/bin/python tools/quiver_wally.py prepare
tools/venv/bin/python tools/quiver_wally.py pilot --workers 2
# Accept visually reviewed pilot keys with --eyes-reviewed, then:
tools/venv/bin/python tools/quiver_wally.py generate --workers 4
tools/venv/bin/python tools/quiver_wally.py status
# After all selected Wally and Guybrush outputs are accepted:
tools/venv/bin/python tools/quiver_wally.py install
```

Wally installation assembles a complete combined pack with the existing Guybrush
walking/idle SVGs and preserves the prior runtime pack for restoration under
`output/quiver-cannon/combined-character-pack/`. Missing or rejected Wally cels
prevent installation of the combined pack.

## Earlier full-cannon extraction

The September 23 run extracted 1,114 character cels from costumes 2, 4, 25, 28,
29, 30, 31 and 33. Deduplication gives 1,086 unique images. Costumes 26 (cannon),
27 (rope) and 32 (explosion) are excluded. Complete shared Guybrush resources are
included to cover normal walking, speech and interactions; activation is confined
to room 9. This is a conservative resource selection, not a claim that every cel
in those shared resources is reachable in the room.

The first generation was **rejected**: Arrow returned an 80 × 80 SVG canvas for a
tall source sprite. The cached response is retained in `raw/`; no output was
installed and the remaining batch was not submitted. Reported usage was 779 input
and 9,653 output tokens, approximately $0.196176 at the model's recorded rates.
Use `status` for current counts rather than treating this document as a live log.

## Commands

Use the existing Python environment (`Pillow` and `numpy` from
`tools/requirements-topaz.txt`) and run `npm ci` inside `app/` for the Sharp SVG
rasterizer. Commands run from the repository root:

```sh
tools/venv/bin/python tools/quiver_cannon.py prepare
export QUIVERAI_API_KEY=YOUR_API_KEY
tools/venv/bin/python tools/quiver_cannon.py pilot
tools/venv/bin/python tools/quiver_cannon.py status
```

The key is read only from the child process environment. The credential supplied
for this local run is stored with owner-only permissions under ignored
`.context/secrets/`; it is never put in the browser, manifests, or logs.

`pilot` checks four representative sprites: Guybrush body/head and Wally
body/head. Each paid request is journaled before submission. There are no automatic
POST retries. A timeout, rejected SVG, API error or insufficient balance stops the
run. An uncertain request is never submitted again. Completed responses are cached
before rendering so local validation can be repeated without further charges.

Inspect the SVG/PNG against the cleaned original, then record visual review:

```sh
tools/venv/bin/python tools/quiver_cannon.py accept --key FULL_ARTWORK_SHA256
tools/venv/bin/python tools/quiver_cannon.py generate
```

`accept` only accepts sprites that have already passed geometry checks. It cannot
override a rejection. It is a review record for the operator, not a second user
permission requirement. Full generation requires all four pilots to be accepted.
Review the remaining outputs, including animation sequences, before installation.

```sh
tools/venv/bin/python tools/quiver_cannon.py validate --key FULL_ARTWORK_SHA256
tools/venv/bin/python tools/quiver_cannon.py install
tools/venv/bin/python tools/quiver_cannon.py restore
```

`install` copies the approved masters to engine filenames such as
`costumes/LFLF_0009_AKOS_0030_aframe_0.svg`. Use `install --runtime-format png`
for the existing PNG path. Both deliverable PNG sizes remain in the output
directory. Choose **Quiver** in Playtest's character pack setting before launching.

The reproducible engine patch uses the pinned engine's bundled NanoSVG decoder.
It supports static paths, basic shapes, groups, transforms, fills, strokes and
gradients. Fonts, embedded images, CSS classes, scripts, clipping paths, masks,
filters and external resources are rejected. SVG files take precedence over PNGs
for the same cel in a selected costume pack; an invalid SVG falls back to the
original actor pose. A failed decode is remembered until restart, avoiding repeated
work on every animation frame. Successful textures use the existing bounded LRU
cache and are rerendered if their requested dimensions change.

The SVG canvas must have the original cel's aspect ratio. Intrinsic dimensions
may be 1× or 6×; the runtime requests exactly 4× and retains transparent margins.
Actor mirroring, screen placement and scaling are applied by the existing costume
compositor. SVG support is for the room-9 character packs; backgrounds and props
continue through their existing loaders.

`validate` reprocesses a cached response without another API call. Rejected
artwork is retained for diagnosis; there is no force-accept command. The walking
CLI has the explicit, journaled `retry-rejected` operation described above.
Installation requires the complete
selected set to pass both validation and visual review. The runtime pack lives
in `.playtest/hd/quiver-cannon/`, separate from the existing costume directory.
Restart the game after installing/restoring. `--output`, `--game`, and `--hd`
support isolated fixtures and alternate local data locations.

## Geometry and transparency

COMI's selected AKCI entries contain only width/height. The signed per-part
positions are in the AKSQ draw commands, which are preserved verbatim alongside
AKCH animation data. They must not be read from adjacent AKCI entries. The engine
records each actual draw, including cel zero and multiple parts on a limb, then
uses bounds computed by the native decoder's scaling tables. Rendering keeps the
native mirroring, depth ordering and foreground masks.

SVG validation rejects active content, embedded raster images, external resources,
changed aspect ratio, displaced silhouettes, opaque backgrounds and new clipping.
Uniform canvas normalization retains existing margins; it never fits the subject
to a new bounding box. Geometry checks do not replace visual animation review.

Palette shadow markers are exported as black at alpha 128, including BOMP slots
0–7 for Wally. This preserves the shadow footprint with a fixed-opacity
approximation; the game's dynamic palette shadow tables are not reproduced by
the exported SVG/PNG artwork. Runtime alpha is blended rather than thresholded.

The Quiver engine path is enabled only when its separate pack exists and room 9
is active. Missing, corrupt, or wrongly sized textures retain the original actor
pose. No modulo frame substitutions are allowed in this pack. Complete poses are
validated before foreground compositing. Their original sprite pixels are removed
from a display-only copy of the native scene, unwinding front to back using the
captured actor underlays. The native simulation buffer is preserved for scripts,
hit testing and masks. Only the replacement is then blended over the scene;
the later UI pass also reads the filtered scene. Native pixels drawn later protect
foreground actors and dialogue. Original pixels remain when a pose is incomplete.

## Verification

```sh
tools/venv/bin/python -m unittest discover -s tools -p 'test_*.py'
python3 tools/engine/patch_engine.py .playtest/engine/source
make -C .playtest/engine/build -j8
cd app
npm test
npm run typecheck
npm run build
```

The initial extractor matched 857 previously prepared character images exactly.
Tests cover codecs, canvas preservation, bad SVGs, alignment, review gating,
uncertain submissions, token accounting, installation and restoration. Native
SVG decoder tests compile against the pinned NanoSVG headers and verify canvas
transforms, straight alpha, transparent margins, gradients, both resolutions,
malformed input and unsupported content. Run `tools/build_engine.sh` first if the
engine source is absent; otherwise these native tests report a skip. App tests
also cover launching a pack containing only SVG files.

The SVG smoke test in `.context/svg-engine-test/` uses 220 original-art Wally SVG
fixtures and no costume PNGs. In room 9, 41 distinct head/body cels loaded with no
decoder errors and each was rasterized once across repeated animation draws.
The screenshot and `verification.json` record this isolated test; these are not
Quiver redraws. Earlier PNG fixtures remain in `.context/quiver-engine-test/`.
The subsequent Guybrush preview adds all 688 costume-2 cels, including all 96
walking cels identified from chore 2. `guybrush-verification.json` confirms that
every sampled walking cel loaded as SVG; 42 distinct walking cels were rasterized
with no SVG rejection. `scummvm-comi-00002.png` captures Guybrush walking in room 9.
These preview vectors trace original pixels and are not newly generated artwork.
The underlay regression test in `.context/svg-underlay-check/` uses intentionally
transparent Guybrush SVGs. Its screenshot confirms that Guybrush's original
sprite is absent while the background, Wally and cannon remain visible. A native
unit test also checks removal order for overlapping actors, dialogue preservation
and fallback when a replacement is missing. The visible preview retains its
original traced geometry; there are no embedded PNG images in those SVG files.
Those fixtures establish decoder and compositing behavior only. Actual Quiver
walking artwork uses the separate workflow above; the full Guybrush/Wally cannon
redraw remains a larger, unfinished selection.

### Cannon recoil sequence (costume 26)

`tools/quiver_cannon_sequence.py` operates on the 14 extracted room-9 cannon cels in `output/topaz-batch/extracted-cannon`. Its separate output is `output/quiver-cannon/cannon-sequence`. This uses [Arrow 2 image-to-SVG](https://docs.quiver.ai/developers/models/image-to-svg) with automatic cropping disabled, padded references, and an inverse padding transform. Provider responses and usage are journaled before validation; uncertain paid requests are never automatically retried. Representative pilots cover the stationary cannon, recoil, and a tiny effect piece. Maximum batch concurrency is two.

Run `prepare`, `pilot`, and (after visual review recorded via `quiver_cannon.review`) `generate`. `status` reports token usage and estimated cost. Both Sharp and the native NanoSVG renderer must pass alignment checks. Raw responses are immutable; documented SVG repairs are bound to the original response hash in `repairs.json`. The `install` command requires all 14 cels accepted and all reviewed hashes intact. It merges only cannon SVGs into the Quiver pack, preserving character art and both Topaz comparison packs. Runtime stays 4×; SVG and 6× PNG masters remain available.

## Source-list passes (`tools/quiver_sources.py`)

`prepare --output DIR KEY...` takes any list of costume/object/layer/background sources;
`generate --max-usd N` runs one request at a time and reserves a conservative cost before
each, so the ceiling cannot be exceeded; failed or uncertain requests are never retried.
`--prompt` switches to prompted redraw (`/svgs/generations`) with the source as reference and a
loose geometry check (stays on and covers the original path); `sheet` writes original | render
comparisons. Results are review candidates only; `tools/package_candidates.py` packages chosen
ones as 4x masters with their runtime copies, rebuilt object layers and aliases.

Findings from the cannon pass: vectorizing nearest-enlarged pixel art traces the pixel staircase
on thin ropes and loses one-pixel lines; smoothing the input made colours and placement worse.
Prompted redraw gives soft, reinterpreted ropes/lines on the same path but can drift on very
narrow canvases. Larger sprites and icons vectorize well.

