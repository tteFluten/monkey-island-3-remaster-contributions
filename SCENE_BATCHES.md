# Scene asset batches

The current workflow is **Wonder 3.5, High enhancement, 4×**, followed by **Topaz Object Matting** for transparent artwork. Enhanced RGB and edges are retained; original pixels and original alpha masks are never restored. Existing 6× paid masters may supply 4× matting inputs without being billed or enhanced again. The game remains at 4× (2560 × 1920).

Backgrounds are excluded. The difficulty screen remains unchanged except for its four knife animation cels. Solid object artwork is upscaled intact, because matting a scenery patch would erase intended artwork. Positioned layers reuse the enhanced object at its original coordinates; duplicates reuse the same result across scenes. Blank assets need no API request. Very small sprites remain listed for padded-input pilots, following the successful cannon-particle approach.

## Execution batches: 100 assets

### Workspace handoff and continuation — 2026-09-24

The active Topaz working set has moved from Brasilia to Albuquerque. Local
provider journals, paid masters, manual edits, references, and frozen budgets
were copied and verified; Brasilia remains preserved. Three saved requests now
report provider failure and remain recovery work without automatic resubmission.

Continue Guybrush first, then resume the remaining regular scene/resource
batches here in the existing order. Do not run the scene coordinator alongside
the Guybrush worker. Completion means the processing checkpoint; rejected
cutouts, tiny pilots, native effects, and provider failures stay explicit rather
than being marked approved. Finished drafts continue to install while the game
is closed, preserving manual edits.

The Guybrush worker currently stops at its frozen credit ceiling: 1,370 of
1,371 credits used, with insufficient allowance for the next two-stage source.
The last live account check returned two credits. Further paid work needs a new
authorized allowance; retain the existing ledger and never buy credits or reset
its history to bypass the cap.

The asset pack now includes 687 additional Guybrush frames across costumes
2–6: 650 automatically validated outputs, 35 rejected cleanup drafts, and two
derived copies. All are installed under the existing draft policy. Their
canonical masters, both Topaz runtime packs, cleaned references, and portable
library indexes are packaged together, bringing the selected Topaz set to 3,498.
The user-supplied 2560 × 1888 inventory panel is installed byte-for-byte as a
manual replacement and packaged as the canonical UI master, bringing the
portable gallery to 3,499 assets. Future draft installs preserve this override.
Generation journals and credentials remain local; the portable pack is a
playback/editor snapshot, not a resumable paid-job queue.

### Guybrush priority pass — 2026-09-24

`tools/topaz_guybrush.py` inventories 125 identified Guybrush-related resource
sets, including shared poses, actions, combined actor animations, disguises,
detached limbs, distant representations, and the child version. Local native
resource headers contain 6,159 cels in this selection; 6,124 are in the frozen
scene plan. Costume 29's 35 cannon-action cels were missing from that plan and
have been extracted separately for follow-up without changing frozen scene IDs.
This is an identified-resource inventory, not proof that every story interaction
has been played through.

The active worker is `tools/venv/bin/python tools/topaz_guybrush.py run
--max-credits 1371`, logging to `.context/guybrush-all.log`. Main costume 2 takes
priority, followed by other selected resources. It reuses the existing job
journals, cached masters, aliases and global workflow locks, with 16 provider
slots and checkpoints of at most 100 source images. Its **1,371-credit frozen
ceiling** cannot grow on restart or after a top-up. The available allowance does
not cover the full inventory. The earlier scene continuation is stopped at its
saved recovery checkpoint; do not start a competing worker.

Run `tools/venv/bin/python tools/topaz_guybrush.py status` to refresh the local
coverage report. Membership, native coverage, budget, progress and per-source
status live under `output/topaz-scenes/batches/guybrush-all/`. Existing paid
outputs are not re-submitted. Tiny sources, native palette effects/shadows,
ambiguous submissions, failed cutouts, and the missing extracted cels remain
explicit follow-up work. Processing does not imply animation approval or
installation; the regular draft installer preserves manual overrides and
requires the game to be closed. Create that folder's `stop-after-current` marker
to drain this worker without cancelling paid requests.

### Automatic continuation — 2026-09-24

The active command is `tools/venv/bin/python tools/topaz_continue_scenes.py --start-room 19`.
It advances through remaining regular scene pairs automatically, retaining 16
provider-job slots per room, separate 100-file batches, checkpoint notifications,
and installation while the game is closed. The initial pair is rooms 19 and 21;
room 20 has reached its production checkpoint. The next pair is rooms 22 and 23.

This continuation freezes a **1,679-credit total ceiling** from the starting
available balance. Every pair reserves from the unused portion of that same
ceiling. Restarts and later top-ups cannot increase it. It stops on exhausted
credits, an explicit stop marker, or an unexpected error. Progress and budget
are under `output/topaz-scenes/batches/continuation-from-0019/`; the log is
`.context/continuous-assets.log`.

A matting request that exceeded its polling timeout keeps its paid ID and gets
one status check on resume. While still processing, it no longer blocks later
batches. Only final-stage requests may be deferred this way: unfinished upscales
still need their matting charge reserved. Uncertain submissions remain separate
recovery work and retain their estimated charge in the budget; they are never
automatically submitted again. Production checkpoints explicitly list unresolved
provider work and do not imply that those images are installed or approved.

### Two rooms, sixteen slots each — 2026-09-23

The user requested doubling room workers and then explicitly increased each
worker to **16 concurrent provider-job slots (32 total)**. The active coordinator
is `tools/topaz_parallel_scenes.py --rooms 14 15`, with log
`.context/parallel-rooms-14-15.log`. It resumes room 14's saved work alongside
room 15 (`town`, 380 regular sources), retaining scene-local 100-file batches.
Room 14's old worker drained at 408/497 credits; eight paid upscales were retained
for matting without repeating enhancement. Its original ceiling remains 497.
Room 15's ceiling is 760; the pair reserves non-overlapping allowances from the
available starting balance, stored in
`output/topaz-scenes/batches/parallel-0014-0015/budget.json`. Reservations cannot
grow on restart or after a top-up. No credits are purchased.

Both workers have independent journals and exclusive room locks. One coordinator
holds the global workflow locks, and a mutex serializes derivation, installation,
and checkpoint reports. Paid requests are never automatically retried after an
ambiguous response. Batch notifications continue; each room stops at its own
production checkpoint. Provider failures and tiny pilots remain separate.
The game is left running; installation waits until it closes. The 32-job ceiling
is an experiment, not a verified provider account limit or guaranteed speedup.

Tests cover concurrent room execution, source disjointness, frozen shared-balance
allocations, sixteen active slots, paired enhancement/matting reservations, and
resume without duplicate payment.

### Eight-slot throughput trial — 2026-09-23

Room 13 reached its production checkpoint: 265 outputs (241 validated and 24
manual-cleanup drafts), one saved provider failure, and 531 credits spent.
Installation of its latest outputs remains pending while the game is running.

The user requested parallel processing. Room 14 (`fortbase`, Puerto Pollo beach)
now runs 249 regular sources in groups of 100, 100, and 49, with **eight concurrent
provider-job slots** in one coordinator. Its frozen ceiling is 497 credits or the
starting available balance, whichever is lower. The coordinator serializes paid
submissions and journal writes, reserves enhancement plus matting together, and
never automatically retries an ambiguous paid submission. The eight-slot ceiling
is a local experiment; it is not a verified Topaz account limit or a promised 2×
speedup. Existing callers keep their previous concurrency unless explicitly set.

Worker: `.context/continue-room14.py`; log: `.context/room14-large.log`;
progress: `output/topaz-scenes/batches/room-0014-production/progress.json`.
It notifies at each batch checkpoint, installs while the game is closed, and
stops at the room-14 production checkpoint. Tiny pilots remain separate.
Regression tests cover eight active jobs, paired credit reservations, invalid
concurrency values, and resuming without paying twice.

The user requested larger batches. Production now combines the frozen costume/object work units into **up to 100 assets per execution batch**, without mixing scenes. `tools/asset_batch_groups.py` preserves source order, dependency work-unit IDs and unique membership. The original 32-file work units and their paid-job journals remain intact for provenance; they are no longer the installation/notification frequency of the active worker.

Room 10 uses four execution groups of **100, 100, 100 and 61 files**, saved in `output/topaz-scenes/batches/room-0010-production/large-plan.json`. The first group includes already finished work, which the provider runner skips automatically. The prior worker was drained without cancelling paid jobs; 34 credits already spent remain inside the same frozen 708-credit ceiling. Processing remains at four concurrent requests. Completed drafts install at the larger batch checkpoints when the game is closed; the worker leaves a running game alone.

Room 10 reached its regular-production checkpoint: all 361 sources processed within the frozen 708-credit ceiling. Its fourth batch installed the final 10 drafts, bringing the installed inventory to 1,002 verified assets. Tiny pilots and manual cleanup remain separate; this is not full scene approval.

Room 11 (`waterln`) finished **71 regular sources** using its 142-credit ceiling: 36 passed automated validation and 35 remain manual-cleanup drafts. All 71 installed at the checkpoint, bringing the verified inventory to **1,073 assets**. Three tiny sources remain in the separate pilot queue.

Room 12 (`treasure`) completed **52 regular sources** within 101 credits (44 validated, eight manual-cleanup drafts). They and their derived assets were installed alongside the priority Guybrush frame 363, bringing the verified inventory to **1,131 assets**. Its 37 tiny sources remain in the separate pilot queue.

The active authorized continuation is **room 13 (`plndrmap`), 266 regular sources in batches of 100, 100, and 66**, capped at **531 credits** or the available starting balance if lower. Active worker: `.context/continue-room13.py`; log: `.context/room13-large.log`; progress: `output/topaz-scenes/batches/room-0013-production/progress.json`. It preserves saved jobs, installs completed drafts when the game is closed, notifies at each batch checkpoint, and stops at the room-13 production checkpoint. Manual cleanup remains separate.

## Draft installation policy

Room 13's first two execution batches reached 199 completed outputs: 181 passed
automated checks and 18 remain cleanup drafts. One saved matting request failed
(`costumes/LFLF_0013_AKOS_0064_frame_149.png`); its job ID and paid history remain
intact, without automatic repurchase. The worker continues the final 66 sources
under the original 531-credit ceiling. The latest installation added 78 drafts,
bringing the verified inventory to 1,330 assets. Later outputs wait while the game
is running. Provider failures remain explicit recovery work at the production
checkpoint.

Manual PNG edits take priority over generated drafts. **Batch outputs → Edit / erase → Replace asset** saves a revision-checked replacement, backs up the previous PNG, refreshes the preview, and installs it when the game is closed. Edits saved while playing are installed before the next library launch. **Download PNG** remains available separately. Topaz replacements retain the 4× RGBA canvas and live under `output/asset-edits/versions/`, with the current selection in `manifest.json`; provider masters and review journals remain intact. Future draft installations preserve these replacements and propagate them to dependent aliases/layers. The uploaded room-1 costume-2 frame-22 PNG is the first manual replacement. The room-13 worker was drained and resumed with the updated installer, retaining its saved jobs and original 531-credit ceiling.

The user explicitly requested installing **all completed outputs without waiting for review**, including cutouts flagged for later manual cleanup. `tools/venv/bin/python tools/install_asset_drafts.py` installs the completed 4× drafts into both game packs and the library, validates file hashes/canvas sizes, and saves dated backups under `.playtest/backups/asset-drafts-*`. It preserves artwork review/validation journals and records installed drafts separately; `installed_draft` does not mean approved artwork. Empty prepared placeholders and preserved difficulty-screen art are excluded. Paid results that have not downloaded are resumed, not invented or resubmitted.

Topaz exact-frame rendering is now enabled in every game scene. Missing frames still use native poses. Quiver retains its earlier scene scope. Native smoke checks covered rooms 16 and 51, with actual Topaz frame loads observed outside the cannon room.

The active continuation resumes `room-0010-b006` at its original 64-credit ceiling, then runs `b007` (30) and `b008` (32). Fourteen credits were already spent in b006 before a temporary DNS failure; they remain counted. Each completed batch installs all finished drafts if the game is closed; if it is running, installation waits until it closes. Workers do not terminate the user's game. Safe estimate requests retry transient failures; paid submissions never retry automatically.

## Current priority: bulk processing

The next room-10 continuation is queued behind the active b007/b008 worker: **361 regular assets in 20 batches**, b009 through b053 where `phase=process`, capped at **708 additional credits** (or the available balance if lower). It waits for the predecessor to finish, preserves each batch's saved job IDs and spending ceiling, installs completed drafts while the game is closed, and emits a local notification/report per batch. It stops at the room-10 production checkpoint; tiny pilots and manual fixes remain separate. Progress: `output/topaz-scenes/batches/room-0010-production/progress.json`.


The user will fix difficult cutouts by hand. Continue the heavy Topaz enhancement/matting work; do not spend successive checkpoints tuning rejected edges. Keep failures and repair variants in a manual-cleanup handoff, with provider originals preserved. Report each batch as processing finishes, distinguishing successful provider outputs from reviewed/installed artwork. A production checkpoint may finish with manual work outstanding; that does not make the scene fully installed or game-tested.

The earlier bounded continuation ran `room-0087-b001` (four knife cels; up to 8 credits), `room-0016-b002` (remaining cached crisp conversions and saved jobs; up to 14 additional credits), then `room-0010-b006` (32 fresh costume frames; up to 64 credits). It reports each checkpoint and stops after those three batches. Total ceiling: 86 additional credits. The earlier cannon and rope-trial ceilings are separate completed invocations.

Rope repair attempts and original references are staged at `.playtest/manual-cleanup/cannon-rope/`; none of those trial outputs has been installed. Their trial used 14 credits. Other cannon exceptions remain flagged for later manual work. The previous repair-first proposal below is historical and is superseded by this bulk-processing priority.

## Order and scope

1. Finish the 96 selected Guybrush walk frames and all 220 Wally cannon-room frames already in flight.
2. Complete the rest of the cannon-room scope: **476 files**, including shared selected Guybrush poses, room-9 costumes, four objects, and four positioned layers. The 118 additional inputs all have cached Wonder masters; 117 need matting and one is solid artwork.
3. Process the difficulty knife's four cels only.
4. Convert the remaining **previously generated 6× crisp-border assets** before paying for unrelated new scenes. There are 321 archived crisp assets; completed 4× cutouts replace their active gallery entry. The 6× files remain accessible only as explicitly labeled archived comparisons. Cached masters are reused.
5. Continue the remaining scene/resource batches in resource-number order (10, 11, 12, …), then the remaining shared-resource groups. This ordering is explicit, not a claim that resource IDs reconstruct the game's puzzle progression. Shared Guybrush animations are owned once and reused wherever the engine calls them.

The local plan accounts for **23,070 files in 77 scene/resource groups**, recorded in **1,196 frozen work units of at most 32 files**, now combined into scene-local execution batches of up to 100 files. Exact source lists, dependencies and estimates are in ignored `output/topaz-scenes/plan.json`; `plan.md` contains the table. The full library exceeds the current balance. Planning lower bounds exclude existing in-flight work and small pilots; live API estimates determine each charge.

## Current cannon checkpoint — 2026-09-23

The previously running cannon scope has finished at its 229-credit ceiling. **454 of 476 assets are reviewed and installed; 17 of 22 cannon batches are complete.** This continuation installed 72 changed assets. The latest Wally batch (`room-0009-b019`) is complete. The scene remains open for 20 rejected cutouts (10 rope, 9 whip, 1 hook), one failed Wally provider job, and the hook's dependent layer. No additional scene was started.

The proposed next checkpoint is rope repair (`room-0009-b007`), followed by whip repair (`b011`), Wally's failed frame (`b014`), and hook/object work (`b021` → `b022`). These are recovery/review tasks: ordinary resumption deliberately does not resubmit failed or rejected jobs. Investigate saved results and any free repair options before proposing new paid attempts. The user chooses the next batch. The difficulty knife follows after the cannon handoff, unless the user explicitly defers repairs.

Final local receipt: `output/topaz-scenes/batches/cannon-handoff.json`. Refresh batch status after any subsequent changes; the counts above are this handoff's snapshot.

## Spending and recovery

The user authorized using available credits only, pausing when depleted. The runner freezes a ceiling at the lesser of its explicit limit and the starting API balance. It checks the live balance and reserves both enhancement and matting costs before a new sprite starts. It never buys credits. Later top-ups do not enlarge a running invocation's ceiling.

`tools/asset_batches.py` groups each scene by costume or object type, splits large groups into at most 32 files, and records the exact source list and dependency batch IDs. Existing crisp conversions have priority within their scene. The current cannon worker was already running when checkpoints were introduced; it drains its previously authorized cannon-only scope, within the existing 229-credit ceiling. No other scene starts automatically.

The legacy work-unit CLI requires one explicit batch ID and stops after that unit; the active production worker combines units into 100-file execution batches. The previous automatic scene-traversal CLI is disabled. The batch's credit ceiling and initial journal costs persist across resumes; other batches' spending cannot consume or reset that ceiling. Failed or ambiguous submissions retain their IDs and require investigation instead of automatic re-purchase. Processing does not approve or install files.

```sh
# Local planning and current installation verification; no Topaz requests.
tools/venv/bin/python tools/asset_batches.py prepare
tools/venv/bin/python tools/asset_batches.py status

# After selecting the next batch and its spending ceiling:
tools/venv/bin/python tools/asset_batches.py run --batch-id room-0009-b019 --max-credits 10
```

The last command is an example, not a recommendation to re-run the current worker. Inspect its handoff first. Plans and current status are saved in `output/topaz-scenes/batches/README.md`, with one `room-NNNN.md` per scene, exact membership in `plan.json`, and machine-readable status in `status.json`. Each run writes `<batch-id>/handoff.json`, prints its counts and credits, and returns control without starting another batch. Refresh `status` after reviews or installation; reports are snapshots, not background monitors.

At each handoff, report the batch ID, newly installed count, pending review/repair/provider work, credits spent, and proposed next batch. Continue already authorized bulk batches; stop at the end of the explicitly selected continuation. A scene is not complete while unresolved assets remain. `installed` requires matching reviewed output hashes in both costume packs (or the runtime object path); it does not imply an animation or occlusion playtest. Preserved artwork and empty sources require no paid work. Small-source pilots remain explicitly blocked until their padded-input workflow is reviewed.

Creating `output/topaz-scenes/stop-after-current` stops new submissions and drains already-submitted work. Remove that file to resume. Workflow locks prevent a checkpoint run from duplicating the active cannon worker. Job files, images, API credentials and machine paths remain ignored local data.

## Review and game installation

The editor's **Batch outputs → Scene batches** table shows new results and remaining pilot counts. Paid provider files and raw Wonder masters remain separate from runtime PNGs. Previous versions stay available for comparison. Results that fail geometry/color checks are quarantined; they are not silently replaced by old edges.

Processing and installation are separate. A completed API job is not automatically approved artwork. Review cutouts on light, dark and checkerboard backgrounds, check animation consistency, then test movement and occlusion in the game. The current exact-cel engine path is verified for the cannon room; the difficulty room has been enabled for its knife. Other rooms require renderer and in-game validation before installation. The queue can prepare their assets while that work remains pending.

The character-specific alpha repair uses enhanced RGB only. It is not applied broadly to other scenes, gray objects or the knife. Tiny effects, rejected cutouts, native shadows, grayscale foregrounds, and ambiguous room dependencies remain explicit review work. The plan must not be interpreted as every asset being finished or game-tested.

Validation: Python regression tests cover cross-room deduplication, solid-art cache reuse, derived-layer alpha/placement, difficulty-background preservation, and the available-balance ceiling. Existing tests cover submission ambiguity, paired cost reservation, review hashes, and character coverage repair. App tests cover scene progress and completed-output visibility without exposing private metadata.

Review and installation commands (select only files that were actually inspected):

```sh
tools/venv/bin/python tools/topaz_scenes.py review --source costumes/example.png
tools/venv/bin/python tools/topaz_scenes.py install --room 9 --completed-only
```

Installation validates every selected hash and canvas before replacing runtime files, backs up prior versions, and protects aliases and object layers against legacy recomposition. Complete installation without `--completed-only` requires every scene output to be reviewed.

## Rope validation

Cannon rope uses a separate 4× geometry check because character IoU rejects small stair-step smoothing on thin props. It permits at most two runtime pixels (half a source pixel) of edge tolerance while requiring 99% reference coverage and output precision, matching end bounds, occupied rows/columns, limited area changes, and unchanged enhanced RGB. Missing ends, gaps and translucent halos are tested rejections. This check does not alter pixels or automatically approve artwork. Other costumes retain their original validation.
