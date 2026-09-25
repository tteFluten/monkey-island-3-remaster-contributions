# Cannon and waterline quality pass

Only `0009_cannon` and `0011_waterln` are active. Other scene batches remain
paused until the user chooses the next scene. Neither scene is signed off.

The complete existing snapshot is installed and packaged in PR #6: 4,124
selected assets, 40,318 verified packaged files, including 625 additions.
Rejected drafts retain their flags. Manual edits and player saves are preserved.

## Coverage baseline

The audit reads the original DCOS/AKHD resource headers instead of assuming the
old batch plan is complete. It includes each room's full costume resources,
shared Guybrush costume 2, scene objects/layers, relevant opening inventory
icons, and an installation check for both backgrounds.

| Scope | Selected sources | Missing selected Topaz draft | Rejected drafts | Native cels absent from old plan |
| --- | ---: | ---: | ---: | ---: |
| Cannon, including shared assets | 1,130 | 129 | 40 | 83 |
| Waterline, including shared assets | 1,065 | 339 | 56 | 291 |

Shared sources appear in both rows and must not be paid for twice. Missing means
no selected Topaz draft; the native/legacy game fallback may still be playable.
There are 1,475 distinct native cels in the inspected resource sets. Of these,
374 were absent from the old plan, including entire Guybrush action resources.

Reproduce with `tools/venv/bin/python tools/audit_scene_focus.py`. Detailed local
results and comparison sheets are under `.context/scene-focus/`. Original-game
extractions and provider journals remain local.

## Findings and next checks

- Waterline costume 57: matting removed whole ripples/splashes from Murray's
  animation. Recovering alpha from the existing enhanced RGB produces improved
  candidates without restoring source pixels or masks. These remain candidates,
  not scene approval.
- Waterline costume 51: an opaque gray wedge survives on a water piece. Check
  the entire 48-cel resource, including 38 cels omitted from the old plan.
- Cannon costumes 27/28/31: thin ropes/lines need tip, continuity and fringe
  checks; area overlap alone cannot establish quality.
- Cannon costume 29: the first newly processed pilot passes automated checks,
  but its shoes/ground boundary needs close visual inspection before approval.
- Missing cannon resource 32 includes smoke/debris; preserve animation placement
  and tiny fragments rather than treating every frame as an ordinary character.
- Inventory icons need both visible states and native hitbox/position checks.
  Backgrounds need in-game composition review; their presence is not approval.

Eight Topaz pilots were processed for previously omitted resources 29, 50, 52,
53, 54, 55, 56 and 60. All passed automated checks. They are held for visual
review and are not silently installed or counted in the 4,124-asset snapshot.
Twenty waterline alpha-repair candidates also pass automated checks and remain
separate from installed artwork.

## Completion criteria

- Every native cel and interaction item is accounted for, with explicit handling
  of aliases, empty images, tiny effects and palette-dependent effects.
- No clipped body parts, missing water, disconnected rope tips, gray rectangles,
  white fringe or accidental opaque backgrounds on contrasting backgrounds.
- Adjacent cels preserve silhouette, color and detail consistency.
- Both scenes are played through with Topaz selected, including pickup/use,
  dialogue, recoil, effects and inventory interactions at the original positions.
- Reviewed output hashes match installed and packaged copies. Automated
  validation, still-image review and animation review remain distinct.

The eight pilots used 16 credits from the existing unused allowance, leaving
1,804 after the original continuation's 1,182 credits. This is not a new credit
allowance. Broad continuation stays stopped; future accounting must include
`output/topaz-scenes/focus-0009-0011/pilot-01/jobs.json` before spending more.

## Active review checkpoint

A detached, scene-restricted batch now processes at most 50 unique waterline
character frames from resources 52, 53, 55, 56 and 60, following inspection of
the eight pilot comparisons. Already-paid pilot inputs and duplicate inputs are
excluded. Cannon resource 29 remains held for the shoe/ground-edge check.

The batch reserves at most 100 credits from the existing net remainder of 1,804;
it does not create a new allowance. Its immutable budget and cumulative paid
journal are under `output/topaz-scenes/focus-0009-0011/waterline-characters-01/`.
Future remaining-credit calculations must subtract **both** focused journals
from the parent allowance remainder. Up to 1,704 credits remain unreserved.

The worker stops after this checkpoint, keeps failures/uncertain jobs for
inspection, and neither installs results nor advances to another scene. Local
worker metadata and logs are `.context/scene-focus/worker.json` and
`.context/scene-focus/character-batch.log`.

## Cannon completion pass — 2026-09-24

Every cannon source in the audit scope now has a packaged master: the scene sheet
(`tools/scene_sheets.py build --scene 9 --scope .context/scene-focus/coverage.json`) reports
1,131 tiles, 0 missing, 0 audit sources and 0 room files off the sheets. This is packaging,
not sign-off; states are recorded as produced and nothing was marked approved.

- **Focus outputs imported.** `tools/import_focus_outputs.py` packaged the 182 finished
  focus-batch outputs (cannon and waterline) plus 2 aliases from the workspace that ran them:
  168 validated, 14 rejected, 2 draft-derived. The 80 user approvals from its local install
  receipt are carried into `artwork-review.json` only where the bytes match.
- **Topaz fix batch** (`fix-01`, 146 credits): 73 rejected/missing cannon items. 37 validated
  are packaged. Guybrush heads still lose the chin, standing bodies lose the floor shadow, and
  thin ropes/lines erode; those stay flagged.
- **Topaz finish batch** (`finish-01`, 58 credits): 11 inventory-icon states and 18 costume-32
  cels, tiny cels through the small-effect workflow. 16 validated; 9 near-threshold results that
  are visually usable are packaged as `rejected` playable drafts.
- **Redraws** (`draft-redraw`, 20 sources): costume-27 ropes and costume-31 arcs redrawn with
  Arrow 2 prompted generation (soft edges, same path; three ropes shifted back onto the source
  path); costume-31 frames 24–29, Guybrush frame 561 and three translucent costume-32 smoke
  puffs rebuilt locally as soft strokes/upscales; one skeleton-arm icon state via Arrow 2
  vectorization. `artwork-review.json` records the method for each.

Credit accounting: both Topaz batches draw on allowance `albuquerque-20260924-3002`, but their
journals live in the packaging workspace under
`output/topaz-scenes/focus-0009-0011/{fix-01,finish-01}/jobs.json`. Subtract them (204 credits)
together with both focused journals; 1,247 credits remained afterwards. Quiver Arrow 2 usage
was about $3.44 at recorded rates (one failed request is conservatively reserved at $0.50),
journaled in `output/quiver-sources/*/jobs.sqlite`.

Still flagged in the cannon: 20 Guybrush frames, 10 costume-32 cels, costume 28 (2 cels),
3 inventory-icon states and costume 31 frame 30. The ropes, smoke and icons need in-game review
during the cannon sequence and inventory use.

