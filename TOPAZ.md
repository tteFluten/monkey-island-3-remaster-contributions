> Current workflow (September 23): use **Wonder 3.5 High at 4× plus Topaz Object Matting**, preserving enhanced edges. Do not restore old RGB or alpha. The older 6×/edge-restoration sections below describe preserved comparison versions, not the active batch policy. See [SCENE_BATCHES.md](SCENE_BATCHES.md) for the scene queue, spending limit, and review requirements.

# Costume and object batch

Open http://127.0.0.1:5200/#outputs (or **Batch outputs** from Playtest / Asset library) to browse completed images. The view refreshes every five seconds, supports sequence filters and filename search, compares cleaned originals against the 6× result on transparent/dark/light canvases, and offers full-resolution viewing and PNG downloads. It is a read-only review view: opening it does not start paid jobs or approve assets.

The current focus is [cannon room 9](http://127.0.0.1:5200/#outputs?room=9): 105 supplied costume frames, four objects and four positioned layers. Its 109 canonical inputs are listed in ignored `cannon-selection.json`; `cannon-scope.json` records the scope and shared-file aliases. The unrelated queue was stopped after preserving and downloading its outstanding paid job. The cannon run has a 109-credit cap, which fits the 126-credit balance at launch. Object layers are reconstructed immediately after each object's completion, without another API request. This covers the supplied folder contents; five additional room-9 costume resources in the game archives were not present in those supplied PNGs and are outside this batch.

The cannon batch completed on September 23: all 105 costume frames, four objects and four layers are available in the editor (113/113). Its 109 canonical jobs record 109 credits total. One stalled output was recovered from its existing paid job without resubmission. The worker stopped after the selected frames; it did not resume the unrelated queue. `output/topaz-batch/cannon-validation.json` records successful checks of every output's 6× dimensions, transparency, shared aliases, layer positions and unchanged source hashes. These checks cover the PNG deliverables; animation consistency and loading this complete costume set in the native game still need visual review.

The Topaz workflow uses Wonder 3.5, High enhancement and exactly six times each source dimension. It preserves the provided PNGs. Outputs and job records live in ignored `output/topaz-batch/`; the API key lives in an ignored, owner-readable `.context/secrets/topaz-api-key` file.

The September 23 validation prepared 22,832 PNGs from the user's Downloads/extracted folders: 21,234 costume frames, 982 objects and 616 positioned object layers. There are 20,258 unique enhancement inputs after cleanup and deduplication. Three validation jobs completed for three credits. The user subsequently authorized batch processing; a background run was started with the remaining 192-credit cap, prioritizing the Guybrush (AKOS 0094) and pirate (AKOS 0255) sequences. The complete queue exceeds that balance. Read `output/topaz-batch/progress.json`, `batch.log`, and `jobs.sqlite` for the actual current state; `worker.json` records the detached worker PID and command.

## Transparency

`tools/prepare_topaz.py` reads the local COMI archives to identify costume palettes, compression types, object transparency and object positions. It verifies costume PNG palettes against RGBS metadata. Costume shadow markers mapped by AKPL to runtime slots 1–7 become neutral black at alpha 128. This is an editable 50% shadow approximation: the game's dynamic shadow tables cannot be reconstructed exactly from an exported PNG alone. Real red paint is preserved.

BOMP objects use index 255 for transparency. SMAP objects use the room transparency index only in strips that enable transparency. Object layers are reconstructed on a transparent canvas at the original IMHD coordinates; the reconstruction is checked against the extracted layer. Index 39 remains valid paint inside objects, even though the exporter uses it for the surrounding placeholder canvas. Sources with mismatched metadata are listed for review instead of guessed.

Wonder receives a neutral-matte input. The output gets the original silhouette restored at 6×. Partial-alpha edge and shadow colors come from the cleaned source to prevent generated matte colors becoming fringes. The opaque interior uses the Wonder output. No crop or geometry change is applied. A layer reuses its corresponding enhanced object rather than sending that same artwork to the API again.

The three samples show that High enhancement can redraw fine features, particularly the flag emblem. These are review samples, not approved animation sequences or game-ready costume replacements. Temporal consistency and native costume loading have not been validated.

## Run locally

```sh
python3 -m venv tools/venv
tools/venv/bin/pip install -r tools/requirements-topaz.txt
tools/venv/bin/python tools/prepare_topaz.py --source /path/to/extracted
```

Source must contain `costumes`, `objects`, and `objects_layers`. By default the matching game data comes from `.playtest/game`; use `--game` for another location. Preparation makes no API calls.

Paid processing must be invoked separately, with explicit image and credit limits:

```sh
tools/venv/bin/python tools/topaz_batch.py --limit 3 --max-credits 3
```

Use repeatable `--only costumes/filename.png` or `--only objects/filename.png` arguments to pick canonical images listed in `manifest.json`. Estimates come from the API before submission. The account balance and per-run cap are checked before each new job. Based on current dimensions and pricing, the prepared full batch is approximately 20,311 credits before subtracting completed samples; the live estimate governs each submission.

Repeatable `--priority-prefix costumes/LFLF_0016_AKOS_0094_` arguments move those sequences to the front without removing the rest of the queue. Frames are processed in numeric order. The runner writes `progress.json` atomically, including its PID, current image, credit cap, completed counts and running/stopped/interrupted state. Processing stops at its credit cap or available balance; it never purchases credits. Completed results are skipped on resumption.

Use `--selection-file output/topaz-batch/cannon-selection.json` to restrict a run to that exact list of canonical inputs. Duplicate aliases and positioned layers become available incrementally while the worker runs.

Network reads and downloads have bounded retries; paid submissions are never automatically retried. `--defer-downloads` lets other frames continue when Topaz's storage cannot deliver a completed output, preserving its process ID as `download_pending`. Three consecutive download failures stop new submissions. The editor displays pending downloads separately. Resume those saved jobs without the flag and with `--max-credits 0` to forbid any new paid submissions.

The SQLite journal records submission intent before making a paid request, then saves the returned process ID. A timeout or download failure resumes that same job. A submission with an unknown result or a failed job stops for inspection and is never silently resubmitted. A workspace lock prevents simultaneous batch runners. The secret is supplied to curl on stdin and is never placed in command arguments, manifests or logs.

Rebuild transparency from downloaded results without any API calls:

```sh
tools/venv/bin/python tools/topaz_batch.py --recompose
tools/venv/bin/python -m unittest discover -s tools -p test_topaz_batch.py
```

Output directories: `cleaned/` for full-size transparent source copies, `6x/` for finished samples and derived layers, `raw/` for cached paid outputs. `manifest.json` tracks input hashes, deduplication and placement; `jobs.sqlite` tracks processing and resumption. Large local data is excluded from Git.

API references: [Wonder 3.5 parameters and pricing](https://developer.topazlabs.com/image-models/wonder/wonder-3.5-new), [generative enhancement](https://developer.topazlabs.com/reference/image/enhance/enhance-generative), [credit balance](https://developer.topazlabs.com/reference/account/credits). Transparency behavior was checked against the pinned COMI-HD engine's `base-costume.cpp`, `actor.cpp`, and Nutcracker's object export code.

## Idle/walking and border comparisons

`tools/prepare_idle_walk.py` reads the native AKCH/AKSQ animation instructions for Guybrush's eight-direction walk/stand and talk-stop chores, plus Wally's standing body/head poses. It prepares 120 cels (108 Guybrush, 12 Wally) without paid requests. Wally's missing indexed frames are extracted locally from the game using the shared decoder; the supplied Downloads files remain unchanged. Run the selected canonical list with `--selection-file output/topaz-batch/idle-walk-selection.json`. The initial run reused one completed result and processed 106 new jobs. In-game verification identified separate standing heads and default Wally poses; completing those reused two more results and processed 11 additional jobs.

`tools/refine_topaz_edges.py --crisp` creates separate `6x-crisp/costumes/` variants from downloaded results. It smooths the alpha contour, extends opaque edge colors, and reconstructs a roughly one-source-pixel ink border using existing dark paint. Partial black shadows remain translucent. It does not call Topaz or change the 6× masters. This treatment is an optional visual alternative: contours change slightly, so small details should be reviewed in motion. The Batch outputs **Border version** selector compares the treatments.

Stage the scene with `tools/stage_topaz.py --scope output/topaz-batch/cannon-character-scope.json`, then repeat with `--crisp` for its border variant. Playtest's **Cannon-room characters** selector keeps **Topaz**, **Topaz crisp borders**, **Quiver**, and **Original** separate. Stop before switching, then launch again to clear texture caches. An unstaged pack is disabled. Both Topaz versions use exact cel matching and the room-9 compositor; incomplete poses fall back to native artwork. This standing/walking selection does not cover every dialogue or story animation.

The idle/walking run completed: 120 selected cels are available, using three cached results and 117 new credits total. The combined cannon scene has 246 character PNGs plus the existing four objects and four layers. Normal and crisp-border Topaz packs are staged separately.

## Cursor and inventory samples

`tools/prepare_ui_batch.py` selects the supplied room-3 cursor/navigation and
inventory artwork: 366 files, 338 distinct prepared inputs. It excludes room-92
save/load/options artwork, fonts, backgrounds, and characters. The five-image
validation sample cost 6 credits and generated normal/active cursor, north arrow,
hook, and inventory-panel masters. One duplicate arrow state reuses its result.
The rest remains unsubmitted, with 394 credits left at the last account check.
Small icons have visible generative edge artifacts; preserve these samples for
review rather than approving the full batch automatically.

The existing batch runner and `tools/topaz_queue.py` share the same journal and
workspace lock. The queue supports up to four in-flight requests with serial
credit reservations, bounded spending, exact saved process IDs, and no automatic
retry of uncertain paid submissions. It is prepared and tested, but has not been
used to submit the remaining UI batch. `tools/stage_ui.py` installs completed
samples at the renderer's 4× resolution from the preserved 6× masters without altering their masters.

### Arrow and menu background-removal pilot

The separate `output/topaz-ui-objectmatting/` pilot uses the same Wonder then
Topaz Object Matting sequence as the cannon. Its five samples are the normal
and active pointer, north navigation arrow, inventory panel, and checked menu
checkbox. Four cached Wonder masters are reused at runtime 4×; the checkbox
needs a new enhancement. The pilot used six credits. The user subsequently
approved these five samples for installation; the original dialogue font remains
active.

Open [the comparison gallery](http://127.0.0.1:5201/files/output/topaz-ui-objectmatting/review.html)
to compare originals and provider cutouts on checkerboard, light, and dark
backgrounds. `jobs.json` records paid job IDs and validation results, including
rejected samples. Failed checks require review, not an automatic paid retry.
Provider alpha is preserved; cannon-specific gray-key cleanup is not applied
because menu artwork may itself be gray. Original RGB and alpha are never
restored onto generated outputs.

`candidate-scope.json` records the possible later batch: 39 image states / 30
unique inputs covering cursor/navigation states, inventory panel, and
save/load/options controls. Fonts and inventory item artwork are excluded.
The full batch remains unsubmitted pending the pilot comparison.

The five pilots completed for six credits. All preserve the enhanced RGB and
have transparent backgrounds at exact 4× dimensions. The panel passed the
automated shape check; both pointers, the north arrow, and the checkbox were
flagged for changed silhouettes. The user accepted these differences after
viewing the comparison. All five samples are now installed (six runtime PNGs,
because the two north-arrow states share a result), with no additional paid jobs.
`reviews/` retains the approval and original validation reports; `installation.json`
records hashes, mappings, and the previous-assets backup. `protected-cutouts.json`
preserves these reviewed 4× outputs during batch recomposition. The full UI batch
is still unsubmitted. See `PLAYTEST.md` for restaging instructions.

## Cannon animation: direct 4×

All 14 cels of cannon costume 26 (room 9), including recoil and small effect
pieces, were extracted from the local game and processed with Wonder 3.5 High
directly at 4×. This used 14 credits; the verified balance afterward was 380.
`tools/prepare_cannon.py` reproduces the source selection without API calls.
`tools/topaz_batch.py --scale 4 --selection-file output/topaz-batch/cannon-sprites-selection.json --limit 14 --max-credits 14`
resumes that selection. Jobs, result paths, and raw cache keys distinguish 4×
from 6×; existing 6× jobs retain their original keys. Masters live under `4x/`.

`tools/stage_cannon.py` installs the completed 4× PNGs, without resampling, in
both Topaz comparison packs. The cannon uses the same artwork in both packs;
the character-border choice remains independent. Originals and Quiver artwork
are preserved. The asset viewer labels each output with its actual scale and
shows the cannon under **Room 9 · Costume 26**. The larger UI batch remains
paused and no UI jobs were included in this cannon run.

### Cannon background removal (no original edge restoration)

The user explicitly requires preserving Topaz's enhanced edges. `tools/topaz_cannon_removebg.py` submits cached raw Wonder 3.5 High 4× results to Topaz `/image/v1/matting/async`, with `mode=segmentation`. It never applies the extracted original alpha or copies original RGB into the result. Original sprites are read only for silhouette validation. Canvas dimensions must remain exact.

The first `RemoveBG` job failed and was refunded. The model-specific output-format selector also conflicts with the endpoint's transport-format validator. The working path uses `--model Object --output output/topaz-cannon-objectmatting` with PNG output. This is Topaz's Object Matting extraction model. The first result left neutral gray residue inside the barrel/rope gap. A documented alpha-only cleanup removes near-neutral matte pixels (RGB channel spread at most 5, all channels 90–175) using the enhanced image only. Topaz's RGB pixels remain unchanged. Original sprites and masks are never inputs to this cleanup. Unmodified provider files remain in `provider/`.

Commands: `prepare`, `pilot`, `run`, `install`. Run with the same output directory; processing reads settings from its saved manifest. Estimates cap each frame at one credit, and at most two requests run concurrently. Request intents and returned job IDs are saved before polling; uncertain submissions are not retried. Installation requires all 14 reviewed cutouts, backs up previous PNGs, and copies the reviewed final files into both Topaz game packs and the asset viewer's canonical 4× files. Installation records checksummed replacements in `protected-cutouts.json`; subsequent batch runs and recomposition preserve those reviewed cutouts and refuse an original-edge fallback if their source/settings or hashes change. Wonder raw masters and previous cutouts remain preserved.

### Character cutouts (Guybrush walk and complete Wally scope)

`tools/topaz_character_cutouts.py prepare` selects all 96 Guybrush walk cels and
all 220 room-9 Wally cels. It reuses 108 cached Wonder masters, deriving 4× RGB
inputs from existing 6× masters without altering those masters. Missing Wally
frames use direct Wonder 3.5 High 4×, followed by Topaz Object Matting. Original
masks are read only for validation; they are never restored to generated art.

Paid jobs are journaled in `output/topaz-character-objectmatting/jobs.json` before
submission. Ambiguous/failed/rejected jobs are not automatically resubmitted.
The serial dispatcher reserves both upscale and matting costs before starting a
new frame. `run --max-credits N --concurrency 4` resumes existing process IDs and
caps additional spending. A `stop-after-current` file drains submitted work on
versions of the runner that include this feature. A later invocation can resume.

Run `audit --repair` alongside a batch to check missing interior coverage. Some
provider masks have a straight truncation through legs. This optional repair
recovers alpha using only enhanced RGB separation from the neutral upload matte;
provider PNGs remain intact. Audits use a separate journal, so they cannot race
paid-job updates. Every installed frame still requires a visual review:
`review --source costumes/...png` records the exact reviewed hash;
`install` copies reviewed 4× results into both Topaz packs while the game is stopped.
Previous versions remain available, and protected-cutouts prevents legacy alpha
recomposition from overwriting approved results.

The editor lists validated 4× cutouts as they finish, including results not yet
installed. The previous 6× or backed-up version remains selectable. Audited
failures are excluded from the new-cutout selector. Installation is a separate,
reviewed step; completion in the gallery does not imply installation.

The two tiny cannon particles use `tools/topaz_cannon_effects.py`: nearest-expanded,
padded inputs preserve their sub-10-pixel shapes through Wonder; Topaz matting
happens on the larger output, followed by a premultiplied Lanczos reduction to the
exact 20×20 / 24×20 runtime canvases. No old RGB or old alpha is restored afterward.
