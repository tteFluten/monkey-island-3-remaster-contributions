# Migration snapshot

The migration PR imports the working project into the private `basementstudio/monkey-island-3-remaster` repository with a clean history. The previous repository, its PRs, and its worktree remotes are unchanged. Merge the migration PR to establish the new `main` as the source of truth.

## Sources and integration

The snapshot combines the Brasilia workshop and current local fixes, the native widescreen implementation, and Oslo's audio tooling. `assets/metadata/code-snapshot.json` records the original commit IDs and imported file hashes before migration-specific edits. Two missing vector-tool helper modules and their tests were recovered from an earlier local snapshot because the existing cannon-sequence tool imports them.

Migration changes add the portable asset pack, reversible installer, integrity checks, source-of-truth relationships, English README, and repository-local/explicit MCP configuration lookup. Original installation settings and credentials are excluded. The demo inventory is historical provenance, not a claim that the packaged remaster is limited to the demo.

## Asset inventory

- 32,256 manifest entries; 14.24 GiB logical content and 9.18 GiB unique content.
- 15 cinematics, 68 PCM music tracks, 93 background masters, 2,811 selected Topaz 4× sprite/object masters, and 43 additional current UI/font masters.
- 2,947 canonical replacement masters; 5,548 runtime records explicitly link to their canonical source. Other installed runtime assets are preserved as the current fallback/alternate packs.
- LFS inventory: 26,041 unique objects totaling 9.13 GiB. JSON, source code, mappings, and SVG text remain in regular Git. Binary media uses LFS; repeated binary contents share an object.
- The current Topaz 4× outputs, background masters, and UI masters are authoritative while replacements continue. Existing draft/rejected review status is preserved. Extracted original assets remain references/fallbacks.
- The final online voice repair supersedes the earlier incomplete bundle: 798 restored recordings, all 3,815 disc-1 payloads matching the verified donor, and zero unresolved entries. The full donor disc/download is not included.

## Validation

- Workshop production build and frontend/backend TypeScript checks pass; all 10 app tests pass.
- The integrated Python suite ran 192 tests successfully with one optional `potrace` test skipped. The updated 8-case installer suite also passes, including stale-master detection, bad/missing media, incompatible voices, active-engine refusal, idempotence, preservation of saves, and rollback after a simulated write failure.
- All 32,256 manifest entries passed size/SHA-256 validation. PNGs decode, WAVs contain complete stereo PCM16 at 44.1 kHz, and the 15 videos match their recorded dimensions, frame counts, and frame rates.
- The integrated native engine builds successfully. Native checks pass for 4:3/16:9, narrow and panorama rooms, HD backgrounds, options, save/load, walking, edge input, pixel-identical motion replay, inventory, resize/fullscreen, and cinematic return.
- Native audio smoke checks pass for the loaded save, rooms 15/11/9, pause/resume, and opening/closing the menu; no loopback/listening validation was performed.
- The native voice audit reports 3,815 structurally valid disc-1 entries, 4,675 structurally valid disc-2 entries, and zero unresolved speech entries. Repair metadata matches the installed bundle hash.
- Installation restored 9,183 files into an isolated test checkout. No original source workspace, user save, or shared Git remote was changed.

Native tests use the existing cannon-room save fixture copied into the isolated checkout. A first run with a later-room player save failed the fixture's room assertion; rerunning with the proper fixture passes. Test screenshots and full logs are kept locally under `.context/` rather than added to the asset library.

Automated checks do not establish listening quality, full-game progression, or approval of every artwork draft. The existing music cue/loop/fade limitations remain documented in AUDIO.md. Repository access and LFS delivery are verified separately after upload in the PR's validation section.

## Ongoing changes

Edit or replace canonical masters, export linked runtime files, and update manifest hashes/source hashes and review metadata together. `asset_pack.py verify` rejects stale master/runtime relationships. Keep working outputs local until incorporated into the canonical pack. Use feature branches and PRs against this repository; the previous project is retained for historical reference.
