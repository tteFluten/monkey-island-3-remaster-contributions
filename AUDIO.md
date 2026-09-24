# COMI-HD audio tools

These tools prepare audio in Oslo and take an explicit `--target-workspace` for
the native playtest they will update. They do not modify game ISOs, player saves,
the browser app, or engine source. Python 3, ffmpeg, and ffprobe are required;
voice recovery also uses the target's prepared ScummVM source and a C++ compiler.

## Installed on this machine

- Brasilia has 68 stereo PCM16 WAV tracks for the installed engine's 125 music
  mappings, at the sources' original 44.1 kHz sample rate.
- 67 damaged disc-1 voice entries were recovered from matching disc-2 entries.
  All 347 healthy entries shared between the original bundles were byte-identical.
  Every replacement was decoded with the actual ScummVM codec under AddressSanitizer
  and UndefinedBehaviorSanitizer before installation.
- A deeper scan recovered another **702 recordings** whose compressed data was
  displaced by 505,856 or 520,192 bytes. Three long, coherent runs of matching
  compression tables establish the offsets; all 67 previously recovered disc-2
  entries independently match the displaced bytes. Each newly recovered recording
  passed the actual native decoder with no sanitizer diagnostics.
- Two more entries initially used an existing recording of the same character saying the
  same words: `PDPL406.IMX` uses `PDPL432.IMX`, and `SGSY519.IMX` uses `SSSY315.IMX`.
  The final online repair below replaces both with their exact original takes.
- One more original recording, `SKGT333.IMX`, was reconstructed by removing a
  14,336-byte sector insertion. Three possible cuts produce identical bytes,
  a 4,096-byte source overlap supports the join, both adjacent recordings match
  their installed counterparts, and native decoding passes without diagnostics.
- **All 26 remaining disc-1 entries are now restored.** After the user authorized
  online sources, an [archived English disc](https://archive.org/details/The_Curse_of_Monkey_Island_LucasArts)
  supplied the original compressed recordings. All 3,787 intact original entries
  matched byte-for-byte before repair. The 26 missing recordings and two exact
  original takes passed native decoding under ASAN/UBSAN. All 3,815 installed
  disc-1 entry payloads now match that donor exactly.
- Full decoding revealed two broken recordings whose headers passed the earlier
  audit. One was repaired with the matching recording above. The other,
  `PDPL361.IMX`, was temporarily marked unavailable to trigger the existing safe-skip
  behavior. It is now restored from the verified donor. Corrupt originals remain
  in the backups, and the engine's crash protection is unchanged.
- Voices and sound effects retain their original quality; this is not an HD voice pack.

The detailed before/after audits are `.context/audio-audit.json` and
`.context/audio-audit-after.json`. They include the exact unresolved resource names,
entry indices, offsets, errors, and hashes. `downloads/voice-repair/repair.json`
records every repair and the native decoder output hashes.
The latest repair manifest is `downloads/voice-online-repair/repair.json`.
In total, **798 original recordings** were recovered; no alternate takes or
unresolved entries remain. Disc 1 has 3,815 structurally valid entries out of 3,815.
Readable subtitle lists are in `.context/restored-voices.csv` and
`.context/unresolved-voices.csv` (local game data, not committed).

## Prepare and install music

```sh
python3 tools/comi_audio.py prepare --target-workspace ../brasilia
# Stop the target game before installing.
python3 tools/comi_audio.py install --target-workspace ../brasilia
```

The cue table comes from the **installed engine**, not a moving upstream branch.
Music comes from the [soundtrack linked by comiupscale](https://archive.org/details/the-curse-of-monkey-island-soundtrack).
The [upstream instructions](https://github.com/harrytyp/comiupscale#5-cd-quality-music-optional)
describe the WAV naming convention. Downloads are verified against Archive.org's
file sizes and MD5 checksums; SHA-256 hashes are recorded for sources and outputs.

The ignored `downloads/comi-audio/` cache holds FLACs, converted WAVs, archive
metadata, and `manifest.json`. Completed files are reused; a partially downloaded
file is retried rather than trusted. `--cache PATH` relocates this cache.
Conversion preserves sample rate and explicitly selects stereo 16-bit PCM.

Installation stages a complete directory before switching the target's
`.playtest/hd/audio/`. Custom existing files are retained. The transaction journal
and original directory live in `.playtest/audio-install.json` and
`.playtest/audio-backups/`. Reruns retain the first backup. Changed installed files
are not overwritten silently. CLI invocations use advisory locks, and installation
refuses to run while the target engine is active.

```sh
python3 tools/comi_audio.py rollback --target-workspace ../brasilia
```

Rollback restores the previous audio directory and retains the disabled soundtrack
beside the backup. Interrupted directory swaps are recovered on the next command.

## Audit and recover speech

```sh
python3 tools/audit_comi_audio.py --target-workspace ../brasilia \
  --source-root ../brasilia/.playtest/game/RESOURCE \
  --output .context/audio-audit.json
python3 tools/restore_comi_voices.py prepare --target-workspace ../brasilia
# Stop the target game before installing.
python3 tools/restore_comi_voices.py install --target-workspace ../brasilia
python3 tools/audit_comi_audio.py --target-workspace ../brasilia \
  --repair-manifest downloads/voice-repair/repair.json \
  --output .context/audio-audit-after.json
```

`--source-root` can be repeated to compare additional local folders or bundles.
The audit checks LB83 directories, entry bounds, COMP tables, codec identifiers,
and block bounds. PRELOAD metadata is distinguished from playable audio. Passing
these structural checks alone is not proof of correct decoded content or language.

Recovery uses only matching named entries in the target's own disc-2 bundle and
requires identical healthy overlaps. It appends validated compressed payloads to a
copy of disc 1 and updates only their directory offsets/sizes. Other payloads,
including unresolved damaged entries, remain byte-identical. The native decoder
checks every replacement before the prepared bundle can be installed. Originals
are preserved in `downloads/voice-repair/VOXDISK1.original.BUN`; do not delete this
directory if you want to undo the repair.

```sh
python3 tools/restore_comi_voices.py rollback --target-workspace ../brasilia
```

The engine's existing malformed-speech protection is preserved.
Reimporting the original discs will restore their corruption;
the voice installer can reapply the validated repair if the source hashes match.

### Displaced-recording recovery

After the first 67 disc-2 repairs, reproduce the deeper recovery using a **new**
work directory (the tool refuses to overwrite a previous repair manifest):

```sh
python3 tools/recover_comi_voice_offsets.py --target-workspace ../brasilia \
  --source-bundle downloads/voice-repair/VOXDISK1.original.BUN \
  --work-dir downloads/voice-recovery-new \
  --equivalent-line PDPL406.IMX=PDPL432.IMX \
  --equivalent-line SGSY519.IMX=SSSY315.IMX \
  --quarantine-invalid PDPL361.IMX
```

The installed second-stage repair can be rolled back to the first-stage 67-line
repair with:

```sh
python3 tools/restore_comi_voices.py rollback --target-workspace ../brasilia \
  --work-dir downloads/voice-recovery-complete
```

Reinstall it with the same command using `install` instead of `rollback`.
To undo both repair stages, roll back the second stage first, then run the
first-stage rollback command above. The second stage's original bundle backup is
`downloads/voice-recovery-complete/VOXDISK1.original.BUN`.

### Single-recording sector repair

The third stage repairs `SKGT333.IMX`. Roll this stage back **before** rolling
back either earlier stage:

```sh
python3 tools/restore_comi_voices.py rollback --target-workspace ../brasilia \
  --work-dir downloads/voice-splice-repair
```

Reinstall with `install` instead of `rollback`. To reproduce its preparation from
the second-stage bundle, use a new work directory:

```sh
python3 tools/recover_comi_voice_splice.py --target-workspace ../brasilia \
  --source-bundle downloads/voice-repair/VOXDISK1.original.BUN \
  --previous-repair downloads/voice-recovery-complete/repair.json \
  --work-dir downloads/voice-splice-new --entry SKGT333.IMX \
  --before-shift 505856 --after-shift 520192
```

The same investigation of `PDPL361.IMX` produced two different decodable byte
sequences, with no matching sector overlap establishing either as correct. Both
were rejected. A whole-disc-2 scan found a same-length recording, but its original
compression table and identity differed, so it was also rejected. Candidate
evidence is retained in `.context/voice-splice-check.json` and
`.context/voice-disc2-scan.json`. Successful decoding alone is not proof that a
reconstructed recording contains the correct original audio.

### Verified online donor recovery

The final stage uses only `RESOURCE/VOXDISK1.BUN` from the archived English disc;
no downloaded executables are run. The donor bundle SHA-256 is
`318168bb78ac0cf38e5391e56870996597e800ed6615a5f4c296d6fae216d146`.
`downloads/voice-online/download.json` records the source URL, exact HTTP ranges,
range hashes, and complete downloaded bundle hash. The archive's whole-ISO MD5
is recorded as metadata, **not** claimed as verified: only the voice bundle's
150,287,970 bytes were downloaded. All media remains ignored by Git.

To prepare from the third-stage bundle, use a new work directory:

```sh
python3 tools/recover_comi_voice_donor.py --target-workspace ../brasilia \
  --donor-bundle downloads/voice-online/VOXDISK1.BUN \
  --previous-repair downloads/voice-splice-repair/repair.json \
  --source-provenance downloads/voice-online/download.json \
  --work-dir downloads/voice-online-new \
  --restore-original-take PDPL406.IMX --restore-original-take SGSY519.IMX
```

The tool rejects directory differences, any unexplained healthy-entry mismatch,
damaged donor entries, checksum mismatches, and native decoder diagnostics. It
appends only validated replacement payloads and verifies every resulting entry
against the donor. Existing installation and rollback guards apply.

Roll back this fourth stage **before** any earlier stage:

```sh
python3 tools/restore_comi_voices.py rollback --target-workspace ../brasilia \
  --work-dir downloads/voice-online-repair
```

Reinstall with `install` instead of `rollback`. The previous installed bundle is
preserved in `downloads/voice-online-repair/VOXDISK1.original.BUN`.

## Verification and engine limitations

The final online repair passed 33 unit tests, native ASAN/UBSAN decoding of all
28 replacements, and an isolated native smoke run covering save load, rooms
15/11/9, pause/resume, and the menu. Player save hashes and the rollback backup
were verified unchanged. See `.context/voice-online-native/results.json` and
`.context/voice-online-tests.log`. This is not a listening test of every dialogue.

```sh
python3 -m unittest discover -s tools -p 'test_*.py' -v
python3 tools/smoke_comi_audio.py --target-workspace ../brasilia \
  --report-dir .context/audio-smoke-new \
  --music-dir ../brasilia/.playtest/hd/audio
```

The smoke tool requires the game to be stopped and an existing `comi.s00` save.
It copies saves, creates an isolated config and session, loads the copied save,
visits rooms 15, 11, and 9, and exercises pause/resume and the menu. It records
engine status, audio diagnostics, and screenshots without changing player saves.
It does not perform listening or loopback-audio verification, nor certify every
dialogue interaction, music transition, or save operation.

The current upstream music implementation has pre-existing limitations that an
asset installation does not fix:

- `BundleMgr::readFile()` suppresses mapped original music whenever `_hqMusic`
  is true, even if the external WAV is missing. Its advertised fallback therefore
  cannot be relied on.
- The external mixer path starts whole OST files from the beginning. It does not
  use the offsets in upstream's JSON mapping, loop them, or resume their exact
  playback position from a save. When a track ends, it has no implemented handoff
  back to the original stream.
- Global mixer volume and pause apply to the external music; original iMUSE
  per-cue fades and speech ducking are not wired to the separate external handle.
- The failed-WAV-decoder branch deletes a stream already owned/disposed by
  `makeWAVStream()`. Do not manually install corrupt WAVs; the staging tool
  validates complete PCM WAVs before installation.

These are engine limitations, not evidence of faulty soundtrack downloads. The
installation uses the existing music interface and leaves the engine unchanged.
Full music-behavior acceptance (faithful loops, offsets, end-of-track fallback,
and all volume transitions) still requires an engine fix and listening tests.
