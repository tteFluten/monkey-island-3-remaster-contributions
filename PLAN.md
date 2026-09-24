# Current implementation update

The macOS Playtest workspace now imports both discs and background folders,
builds the pinned COMI-HD engine, and supports room jumps and background reloads.
Cannon room and the scrolling town room were tested with the supplied masters.
See [PLAYTEST.md](PLAYTEST.md) for the current workflow and known limitations.
The phase notes below predate this implementation.

# PLAN — Monkey Island 3 Remaster Production App

## Architecture

```
monkey-island-3-remaster/
  app/
    src/                  # React frontend (Vite + TypeScript)
      components/         # UI components
      pages/              # Main views (Library, Editor, ImageLab, Animation, Scene, Export)
      hooks/              # Custom React hooks
      lib/                # API client, types, utilities
      main.tsx
      App.tsx
      index.css           # Imports apps-common/global.css + local overrides
    server/               # Node.js backend (Express + TypeScript)
      index.ts            # Express server entry
      routes/             # API routes (assets, jobs, export)
      services/           # MCP client, file management, manifest persistence
      lib/                # Shared utilities
    shared/               # Shared types between client and server
      types.ts            # Data model (Project, Scene, Asset, Variant, Job, Review)
      schema.ts           # Manifest schema version
    package.json
    tsconfig.json
    tsconfig.server.json
    vite.config.ts
  demo-original/          # Untouched game data
  extracted/              # Extracted originals (gitignored)
  upscaled/               # Remastered variants (gitignored)
  previews/               # Comparison previews (gitignored)
  output/                 # Export packages (gitignored)
  data/                   # JSON manifests (versioned)
    project.json
    scenes/               # Per-scene manifests
```

### Key decisions

- **Standalone local app** — Not a Hub app; runs independently with `npm run dev`.
- **Single package** — One `package.json` for both frontend and backend. Vite serves the frontend; a separate Express process serves the API.
- **MCP client in backend** — Uses `@modelcontextprotocol/sdk` to spawn the MCP proxy and call imagelab-generate. No credentials in the frontend.
- **JSON manifests** — Atomic writes with temp files + rename. Schema versioned for future migrations.
- **Basement CSS** — Imports `apps-common/global.css` for palette, fonts, glass panels.
- **Canvas 2D** — For before/after comparisons, transparency checks, animation playback.
- **No database** — JSON files in `data/` are sufficient for this scale.

### MCP integration

The backend spawns the MCP proxy as a child process using the config from `../../.mcp.json`:
```
node /path/to/mcp-proxy.js https://basementlabhub.vercel.app/mcp
```
It then uses the SDK's stdio transport to call `imagelab-generate`, `imagelab-describe`, and `imagelab-improve-prompt`.

The frontend never touches MCP directly. It sends job requests to the local API, which queues them, executes via MCP, saves results to disk, and updates manifests.

### Available MCP tools (verified live)

| Tool | Key params |
|------|-----------|
| `imagelab-generate` | prompt, images[{base64, label}], model, aspect_ratio, image_size |
| `imagelab_generate` | prompt, image_base64/image_path, image_label, aspect_ratio, image_size |
| `imagelab-describe` | image_base64, focus, language |
| `imagelab-improve-prompt` | prompt, images[{base64}] |

Models: gemini-3.1-flash-image-preview, gemini-3.1-pro-image-preview, gemini-2.5-flash-image, gpt-image-2, gpt-image-1.
Sizes: 512, 1K, 2K, 4K. Aspect ratios: 1:1, 3:4, 4:3, 9:16, 16:9, etc.

### SCUMM extraction (research needed)

Tools to investigate:
- **scummvm debugger**: Can dump room backgrounds via console commands.
- **ScummPacker**: Extracts/repacks SCUMM resources (Python).
- **scumm-image-encoder**: Handles SMAP/BOMP image formats.
- **Custom parser**: COMI uses SCUMM v8; LA0 is the index, LA1+ are data bundles. Room backgrounds are SMAP chunks with zlib-compressed strips.

COMI backgrounds are typically 640x480 (single screen) or wider for scrolling rooms. The demo likely has a subset of rooms.

This is a research item — extraction viability must be confirmed before building the extraction pipeline.

---

## Phases

### Phase 0 — Inspection and viability
- [x] Read project files and instructions
- [x] Verify MCP connection and tool schemas
- [x] Research COMI extraction tools — nutcracker (Python) confirmed working
- [ ] Test demo in ScummVM
- [x] Document confirmed vs hypothetical (see below)

### Phase 1 — Local app (functional core)
- [x] Scaffold frontend + backend
- [x] Data model and manifest persistence
- [x] Manual image import (drag & drop or file picker)
- [x] Asset library with filtering
- [x] Before/after editor (slider, side-by-side, overlay, zoom)
- [x] Variant history and approval workflow
- [x] Persistence across restarts
- [x] Export approved variants with manifest

**Acceptance**: Import an original and a variant, compare, approve, restart, state preserved.

### Phase 2 — ImageLab generation
- [x] MCP client connection in backend
- [x] Job queue with status tracking
- [x] Generation panel in frontend (prompt editor, model/params selection)
- [x] Result saving and traceability
- [x] Error handling and retry
- [x] Real generation with demo asset — cannon room & waterline backgrounds generated successfully
- [x] MCP auto-reconnect on connection drop

**Acceptance**: Generate and regenerate from UI, compare results, choose variant.

### Phase 3 — Extraction and animation review
- [x] COMI resource extraction — nutcracker extracts 745+ images (backgrounds, objects)
- [x] Maintain original IDs and metadata (room numbers, object names preserved)
- [ ] Animation sequence loading and playback
- [ ] Synchronized original/remaster comparison
- [ ] Scene composition view

**Acceptance**: Demo scene resources identified and visually reviewable with animations.

### Phase 4 — Game integration
- [x] ScummVM HD replacement research — comiupscale (harrytyp/comiupscale) is a ScummVM fork loading external HD textures from hd/ directory
- [ ] Implement resource loading (C++ mod or alternative)
- [ ] Test with remastered background + character + object
- [ ] Verify interaction, movement, depth, occlusion

**Acceptance**: Scene playable in-game with remastered resources.

### Phase 5 — Expansion
- [ ] Batch processing (after prototype validation)
- [ ] Additional scenes
- [ ] Coverage tracking
- [ ] Full game support when files available
- [ ] Cinematic pipeline (separate workflow)

---

## Risks and unknowns

1. **COMI extraction**: RESOLVED — nutcracker (pip) extracts backgrounds, objects from COMI v8 files. 745+ images from demo.
2. **ScummVM HD replacement**: RESOLVED in principle — comiupscale fork loads external HD textures at 4x. Needs building and testing.
3. **ImageLab fidelity**: Generative output won't perfectly match original geometry. Requires visual QA per asset.
4. **Animation coherence**: Frame-by-frame generation may produce flickering. Needs consistent reference strategy.
5. **Demo scope**: Limited rooms/assets. Full game requires separate data files.

---

## Confirmed vs hypothetical

### Confirmed
- **Extraction**: nutcracker extracts COMI v8 backgrounds + objects as PNG. 5 backgrounds (640x480), 740+ objects from demo.
- **MCP connection**: Backend connects to Basement MCP proxy, calls imagelab-generate successfully.
- **Generation quality**: gemini-2.5-flash-image produces faithful remasters (same composition, style, palette). Output: 1184x864 (~1.85x).
- **Model availability**: gemini-2.5-flash-image works reliably. gemini-3.1-flash-image-preview timed out on first try.
- **HD integration path**: comiupscale (github.com/harrytyp/comiupscale) is a working ScummVM fork that loads 4x HD textures.
- **App pipeline**: Import → generate → compare → approve → export flow works end-to-end.

### Hypothetical (not yet tested)
- ScummVM execution of the demo (not yet run).
- comiupscale build and integration with our generated assets.
- AKOS costume/character sprite extraction (nutcracker base version may not support it; comiupscale's fork does).
- Animation sequence extraction and consistency across frames.
- True 4K output (current max is 1184x864 from gemini-2.5-flash).
- Full game extraction (requires complete game files).

---

## Next concrete task

Add batch import of extracted backgrounds to the app. Implement the animation viewer for extracted sprite sequences. Test all demo backgrounds through the generation pipeline.
