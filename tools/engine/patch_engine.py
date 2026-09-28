#!/usr/bin/env python3
"""Deterministic, idempotent patches for the pinned COMI-HD source."""
from pathlib import Path
import sys
import hashlib
import subprocess
import time

root = Path(sys.argv[1])
# A complete patch set is repeatable. On a changed patch set, rebuild from the
# pinned archive rather than stacking text replacements over obsolete patches.
# Preserve the previous generated source tree for local debugging/manual edits.
fingerprint = hashlib.sha256()
for source in sorted(Path(__file__).parent.iterdir()):
    if source.suffix in ('.py', '.h', '.inc', '.cpp'):
        fingerprint.update(source.name.encode()); fingerprint.update(source.read_bytes())
# The embedded scene picker catalog must also be rebuilt when names change.
from patch_scene_jump import catalog_header, patch as patch_scene_jump
fingerprint.update(catalog_header().encode())
from water_regions import header as water_regions_header
fingerprint.update(water_regions_header().encode())
stamp = root / '.mi3-patches'
revision = fingerprint.hexdigest()
if stamp.exists():
    if stamp.read_text().strip() == revision:
        print('Engine patches are current')
        sys.exit(0)
    archive = root.parent / 'source.tar.gz'
    if not archive.is_file():
        raise RuntimeError('Changed patches require the pinned source.tar.gz archive')
    backup = root.with_name('source-backup-' + str(time.time_ns()))
    root.rename(backup)
    root.mkdir()
    subprocess.run(['tar', '-xzf', str(archive), '--strip-components=3', '-C', str(root), '*/scummvm/fork'], check=True)

def edit(name, before, after):
    file = root / name
    text = file.read_text()
    if after in text:
        return
    if before not in text:
        raise RuntimeError(f'Pinned engine source changed: {name}')
    file.write_text(text.replace(before, after, 1))

# SDL2-compat no longer supplies the Cocoa main trampoline.
edit('backends/platform/sdl/macosx/macosx-main.cpp', '#include "common/scummsys.h"', '#define SDL_MAIN_HANDLED\n#include "common/scummsys.h"')
edit('backends/platform/sdl/macosx/macosx-main.cpp', 'int main(int argc, char *argv[]) {', 'int main(int argc, char *argv[]) {\n\tSDL_SetMainReady();')
edit('engines/scumm/scumm.cpp', '#include "common/config-manager.h"', '#define FORBIDDEN_SYMBOL_ALLOW_ALL\n#include <cstdio>\n#include "common/formats/json.h"\n#include "common/config-manager.h"')
edit('engines/scumm/scumm.cpp', 'void ScummEngine::scummLoop(int delta) {', '#include "scumm/playtest.inc"\n\nvoid ScummEngine::scummLoop(int delta) {\n\tplaytestTick();')
edit('engines/scumm/scumm.h', '\tint _hdScale = 1;', '\tvoid playtestTick();\n\tuint32 _playtestLastPoll = 0;\n\tint _playtestCommandId = 0;\n\tCommon::String _playtestError;\n\tint _hdScale = 1;')
edit('engines/scumm/room.cpp', '#include "common/system.h"', '#include "common/config-manager.h"\n#include "common/system.h"')
# Tall/vertical rooms must not change the framebuffer scale.
legacy_scale = '_hdScale = ConfMan.hasKey("playtest_session") ? 4 : MAX(1, _hdBackgroundSurface.h / MAX(1, _screenHeight));'
configured_scale = '_hdScale = ConfMan.hasKey("playtest_session") ? (ConfMan.hasKey("playtest_scale") ? ConfMan.getInt("playtest_scale") : 6) : MAX(1, _hdBackgroundSurface.h / MAX(1, _screenHeight));'
if legacy_scale in (root / 'engines/scumm/room.cpp').read_text():
    edit('engines/scumm/room.cpp', legacy_scale, configured_scale)
edit('engines/scumm/room.cpp', '_hdScale = MAX(1, _hdBackgroundSurface.h / MAX(1, _screenHeight));', configured_scale)
edit('engines/scumm/scumm.cpp', '_hdScale = _hdAssetManager->getScale();', '''_hdScale = _hdAssetManager->getScale();
		if (ConfMan.hasKey("playtest_session")) {
			_hdScale = ConfMan.hasKey("playtest_scale") ? ConfMan.getInt("playtest_scale") : 6;
			if (_hdScale != 4 && _hdScale != 6)
				error("Playtest supports 4x or 6x rendering");
			_hdAssetManager->setScale(_hdScale);
		}''')
# Never retain another room's artwork when a background is unavailable.
edit('engines/scumm/room.cpp', 'warning("HD: no bg for room %d", room);', 'warning("HD: no bg for room %d", room);\n\t\t\t_hdBackgroundSurface.free();')
(root / 'engines/scumm/playtest.inc').write_bytes((Path(__file__).parent / 'playtest.inc').read_bytes())
print('Applied macOS entry point and playtest bridge patches')

edit('backends/events/sdl/sdl2-events.cpp', '#include "common/scummsys.h"', '#define FORBIDDEN_SYMBOL_ALLOW_ALL\n#include <cstdio>\n#include <cstdlib>\n#include "common/scummsys.h"')
edit('backends/events/sdl/sdl2-events.cpp', 'bool SdlEventSource::pollEvent(Common::Event &event) {', 'bool SdlEventSource::pollEvent(Common::Event &event) {\n#include "test_input.inc"')
(root / 'backends/events/sdl/test_input.inc').write_bytes((Path(__file__).parent / 'test_input.inc').read_bytes())
edit('backends/events/sdl/sdl2-events.cpp', '\twhile (SDL_PollEvent(&ev)) {', '''\twhile (SDL_PollEvent(&ev)) {
        // Automated runs accept only the zero-window-ID events emitted by the
        // engine-local hook; real desktop input must not contaminate a replay.
        if (getenv("MI3_ENGINE_TEST_INPUT") && getenv("MI3_ENGINE_TEST_EXCLUSIVE") &&
            (ev.type == SDL_KEYDOWN || ev.type == SDL_KEYUP || ev.type == SDL_TEXTINPUT ||
             ev.type == SDL_MOUSEMOTION || ev.type == SDL_MOUSEBUTTONDOWN || ev.type == SDL_MOUSEBUTTONUP) &&
            ev.key.windowID != 0) continue;''')

from patch_quiver import patch as patch_quiver
patch_quiver(root, edit)
print('Applied room-9 Quiver costume support')

from patch_character_pack import patch as patch_character_pack
patch_character_pack(root, edit)
print('Applied Topaz / Quiver / Original character selection')

from patch_svg import patch as patch_svg
patch_svg(root, edit)
print('Applied direct SVG costume loading')

from patch_ui import patch as patch_ui
patch_ui(root, edit)
print('Applied HD UI cursor support')

from patch_dialogue_font import patch as patch_dialogue_font
patch_dialogue_font(root, edit)
print('Applied CaslonAntique dialogue rendering')

from patch_font_size import patch as patch_font_size
patch_font_size(root, edit)
print('Applied adjustable HD font size and in-game menu controls')

from patch_object_depth import patch as patch_object_depth
patch_object_depth(root, edit)
print('Applied native actor / HD object depth preservation')

from patch_video import patch as patch_video
patch_video(root, edit)
print('Applied synchronized HD cinematics with original audio and subtitles')

from patch_video_fonts import patch as patch_video_fonts
patch_video_fonts(root, edit)
print('Applied crisp HD cinematic subtitles')

from patch_actor_lighting import patch as patch_actor_lighting
patch_actor_lighting(root, edit)
print('Applied live palette lighting to HD characters')

from patch_performance import patch as patch_performance
patch_performance(root, edit)
print('Applied independent 60 Hz HD presentation')

from patch_actor_shadow import patch as patch_actor_shadow
patch_actor_shadow(root, edit)
print('Applied procedural character contact shadows')

from patch_bundle_audio import patch as patch_bundle_audio
patch_bundle_audio(root, edit)
print('Applied damaged audio bundle header handling')

from patch_coin import patch as patch_coin
patch_coin(root, edit)
print('Applied HD verb coin independent of character pack')

from patch_motion import patch as patch_motion
patch_motion(root, edit)
print('Applied draw-only camera and parallax interpolation')

from patch_scene_visibility import patch as patch_scene_visibility
patch_scene_visibility(root, edit)
print('Applied native room-object visibility and transparent sea effects')

from patch_aspect import patch as patch_aspect
patch_aspect(root, edit)
print('Applied persistent 4:3 / 16:9 presentation and HD panorama viewports')

from patch_costume_edge import patch as patch_costume_edge
patch_costume_edge(root, edit)
print('Applied clean matte edges to Guybrush head poses')

from patch_depth_of_field import patch as patch_depth_of_field
patch_depth_of_field(root, edit)
print('Applied optional z-plane foreground depth of field')

from patch_inventory import patch as patch_inventory
patch_inventory(root, edit)
print('Applied inventory panel replacement and item layering')

from patch_color_grade import patch as patch_color_grade
patch_color_grade(root, edit)
print('Applied per-room color grades and the playtest Look panel')

from patch_wide_background import patch as patch_wide_background
patch_wide_background(root, edit)
print('Applied optional full-width cannon background presentation')

from patch_telemetry import patch as patch_telemetry
patch_telemetry(root, edit)

from patch_remaster import patch as patch_remaster
patch_remaster(root, edit)
print('Applied 1440p GPU scene effects and reusable motion storage')

from patch_water import patch as patch_water
patch_water(root, edit)
print('Applied lightweight ambient water shader')

from patch_film import patch as patch_film
patch_film(root, edit)
print('Applied optional final vintage-film presentation')

from patch_background_loading import patch as patch_background_loading
patch_background_loading(root, edit)
print('Applied shared asynchronous room background cache')

patch_scene_jump(root, edit)
print('Applied native J-key scene navigation')

from patch_banner import patch as patch_banner
patch_banner(root, edit)
print('Applied retained HD frames behind engine banners')

from patch_book import patch as patch_book
patch_book(root, edit)
print('Applied HD options book pages')

from patch_language import patch as patch_language
patch_language(root, edit)
print('Applied language packs')

from patch_camera import patch as patch_camera
patch_camera(root, edit)
print('Applied soft camera follow and fractional world presentation')

stamp.write_text(revision + "\n")
