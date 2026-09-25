# Project instructions

Read README.md for the current setup, asset policy, and limitations. This private Basement Studio repository becomes authoritative when the migration PR merges.

- Preserve original game coordinates, composition, palettes, transparency, and timing. Keep original-game data and player saves local.
- Use Git LFS for packaged media. Keep the asset manifest and provenance accurate; do not change review status merely because an asset is installed.
- Preserve manual edits and retain existing fallback artwork when no usable replacement exists.
- Keep credentials in ignored local configuration. ImageLab integration uses the basement-lab MCP server; do not silently substitute a different generation provider.
- Run relevant tests after code changes. Do not run paid generation jobs as part of tests or packaging.
- Keep source workspaces, player saves, and installation rollback backups intact.
- To inspect artwork, build per-room sheets with `tools/scene_sheets.py` and read `index.md` before opening individual PNGs or searching `assets/manifest.json`; use `lookup` for exact paths and hashes.
