// Local development bridge. Included inside namespace Scumm in scumm.cpp.
// Enabled only by an explicit playtest_session setting in the isolated config.
void ScummEngine::refreshHDRoomBackground() {
	if (_game.id != GID_CMI || !ConfMan.hasKey("playtest_session")) return;
	// Loading a save bypasses startScene(), including its HD background load.
	// Refresh on the engine thread before drawing that restored room.
	if (!isSmushActive() && _currentRoom > 0 && _hdCurrentRoom != _currentRoom && _hdAssetManager->isEnabled()) {
		_hdBackgroundSurface.free();
		_hdAssetManager->loadBackground(_currentRoom, _hdBackgroundSurface);
		_hdCurrentRoom = _currentRoom;
		_hdCleanBackground.free();
		free(_hdCleanValid);
		_hdCleanValid = nullptr;
		_hdCleanValidSize = 0;
		_fullRedraw = true;
	}
}

void ScummEngine::playtestTick() {
	if (_game.id != GID_CMI || !ConfMan.hasKey("playtest_session"))
		return;
	uint32 now = _system->getMillis();
	if (now - _playtestLastPoll < 100)
		return;
	_playtestLastPoll = now;
	Common::String directory = ConfMan.get("playtest_session");
	if (directory.empty())
		return;
	refreshHDRoomBackground();
	bool ready = !isPaused() && !isSmushActive() && !_saveLoadFlag &&
		_currentRoom > 0 && _currentRoom != 87 && !vm.cutSceneStackPointer &&
		VAR_EGO != 0xFF && VAR(VAR_EGO) > 0 && VAR(VAR_EGO) < _numActors;
	// Opt-in deterministic walking for native lighting/depth smoke tests. Uses
	// the normal actor walker, so room scripts and lighting run unchanged.
	if (ready && getenv("MI3_ENGINE_TEST_INPUT")) {
		Common::String savePath = directory + "/save-load.txt";
		FILE *save = fopen(savePath.c_str(), "r");
		if (save) {
			int action = 0, slot = 0;
			int fields = fscanf(save, "%d %d", &action, &slot);
			fclose(save);
			remove(savePath.c_str());
			if (fields == 2 && (action == 1 || action == 2) && slot >= 0 && slot < 100) {
				_saveLoadFlag = action;
				_saveLoadSlot = slot;
				_saveTemporaryState = false;
				return;
			}
		}
		// Exercise an unmodified cinematic timeline using the normal SAN player.
		// This opt-in test hook never runs in regular Playtest sessions.
		Common::String moviePath = directory + "/movie.txt";
		FILE *movie = fopen(moviePath.c_str(), "r");
		if (movie) {
			char name[32] = {};
			int fields = fscanf(movie, "%31s", name);
			fclose(movie);
			remove(moviePath.c_str());
			if (fields == 1 && !strchr(name, '/') && !strchr(name, '\\') && strstr(name, ".SAN")) {
				static_cast<ScummEngine_v7 *>(this)->_splayer->play(name, 12);
				_fullRedraw = true;
				return;
			}
		}
        Common::String sweepPath = directory + "/camera-sweep";
        FILE *sweep = fopen(sweepPath.c_str(), "r");
        if (sweep) {
            fclose(sweep);
            static uint32 nextSweep = 0;
            static bool farSide = false;
            if (now >= nextSweep) {
                farSide = !farSide; nextSweep = now + 3000;
                panCameraTo(_roomWidth > _screenWidth ? (farSide ? _roomWidth - _screenWidth / 2 : _screenWidth / 2) : camera._cur.x,
                    _roomHeight > _screenHeight ? (farSide ? _roomHeight - _screenHeight / 2 : _screenHeight / 2) : camera._cur.y);
            }
        }
		Common::String walkPath = directory + "/walk-to.txt";
		FILE *walk = fopen(walkPath.c_str(), "r");
		if (walk) {
			int x = 0, y = 0;
			int fields = fscanf(walk, "%d %d", &x, &y);
			fclose(walk);
			remove(walkPath.c_str());
			if (fields == 2 && x >= 0 && y >= 0 && x < _roomWidth && y < _roomHeight)
				_actors[VAR(VAR_EGO)]->startWalkActor(x, y, -1);
		}
	}
	Common::String commandPath = directory + "/command.json";
	FILE *input = fopen(commandPath.c_str(), "rb");
	if (input) {
		char buffer[1024];
		size_t count = fread(buffer, 1, sizeof(buffer) - 1, input);
		buffer[count] = 0;
		fclose(input);
		Common::JSONValue *command = Common::JSON::parse(buffer);
		if (command && command->isObject() && command->hasChild("id") && command->child("id")->isIntegerNumber()) {
			int id = command->child("id")->asIntegerNumber();
			if (id > _playtestCommandId) {
				_playtestCommandId = id;
				_playtestError.clear();
				if (!ready) {
					_playtestError = "Game is busy. Finish the opening, cutscene, or menu before retrying.";
				} else if (!command->hasChild("action") || !command->child("action")->isString() ||
					!command->hasChild("room") || !command->child("room")->isIntegerNumber()) {
					_playtestError = "Invalid command";
				} else {
					Common::String action = command->child("action")->asString();
					int room = command->child("room")->asIntegerNumber();
					if (room < 1 || room > 94) {
						_playtestError = "Invalid COMI room";
					} else if (action == "jump") {
						_actors[VAR(VAR_EGO)]->_room = room;
						_sound->stopAllSounds();
						startScene(room, nullptr, 0);
						_fullRedraw = true;
					} else if (action == "reload" && room == _currentRoom) {
						Common::String hdPath = _hdAssetManager->getHDPath();
						_hdAssetManager->setHDPath(hdPath);
						Graphics::Surface replacement;
						if (_hdAssetManager->loadBackground(room, replacement)) {
							_hdBackgroundSurface.free();
							_hdBackgroundSurface.copyFrom(replacement);
							replacement.free();
							_hdCurrentRoom = room;
							_hdComposite.free();
							_fullRedraw = true;
						} else {
							_playtestError = "Replacement background could not be loaded";
						}
					} else {
						_playtestError = "Unsupported command or room is not active";
					}
				}
			}
		}
		delete command;
	}
    // Explicit engine-local benchmark requests; no per-frame disk writes.
    if (getenv("MI3_ENGINE_TEST_INPUT")) {
        for (int action = 0; action < 2; ++action) {
            Common::String request = directory + (action ? "/benchmark-stop" : "/benchmark-start");
            FILE *trigger = fopen(request.c_str(), "r");
            if (!trigger) continue;
            fclose(trigger); remove(request.c_str());
            auto &metrics = HdRemaster::state();
            if (!action) {
                metrics.sampleCount = metrics.droppedSamples = 0;
                ++metrics.recordSerial;
                metrics.recording = true;
            } else {
                metrics.recording = false;
                FILE *report = fopen((directory + "/frames.csv").c_str(), "w");
                if (report) {
                    fprintf(report, "at_ms,interval_ms,cpu_ms,gpu_ms,room,camera_x,camera_y,native_ms,motion_ms,scene_ms,backend_ms\n");
                    for (uint i = 0; i < metrics.sampleCount; ++i) {
                        const auto &sample = metrics.samples[i];
                        fprintf(report, "%.4f,%.4f,%.4f,%.4f,%d,%d,%d,%.4f,%.4f,%.4f,%.4f\n", sample.at, sample.interval,
                                sample.cpu, sample.gpu, sample.room, sample.cameraX, sample.cameraY, sample.native, sample.motion, sample.scene, sample.backend);
                    }
                    fclose(report);
                }
            }
        }
    }
	// Read-only actor diagnostics identify the exact cels used by live animations.
	Common::String actors = "[";
	for (int i = 0; i < _numActors; ++i) {
		Actor *actor = _actors[i];
		if (!actor || !actor->_visible || actor->_room != _currentRoom || !actor->_costume)
			continue;
		if (actors.size() > 1) actors += ",";
		actors += Common::String::format("{\"id\":%d,\"costume\":%d,\"frame\":%d,\"walkFrame\":%d,\"standFrame\":%d,\"x\":%d,\"y\":%d,\"cel\":%d,\"cels\":[",
			i, actor->_costume, actor->_frame, actor->_walkFrame, actor->_standFrame,
			(int)actor->getPos().x, (int)actor->getPos().y, actor->_hdCurrentCel);
		for (int limb = 0; limb < actor->_hdNumLimbs && limb < 16; ++limb) {
			if (limb) actors += ",";
			actors += Common::String::format("%d", actor->_hdLimbCel[limb]);
		}
		actors += "]}";
	}
	actors += "]";
	Common::String status = Common::String::format(
		"{\"protocol\":1,\"ready\":%s,\"room\":%d,\"commandId\":%d,\"error\":%s,\"backgroundLoaded\":%s,\"width\":%d,\"height\":%d,\"actors\":%s}",
		ready ? "true" : "false", _currentRoom, _playtestCommandId,
		Common::JSONValue(_playtestError).stringify().c_str(),
		_hdBackgroundSurface.getPixels() && _hdCurrentRoom == _currentRoom ? "true" : "false",
		_hdBackgroundSurface.w, _hdBackgroundSurface.h, actors.c_str());
	status.deleteLastChar();
	status += Common::String::format(",\"aspectRatio\":%d,\"outputWidth\":%d,\"outputHeight\":%d,\"viewportWidth\":%d,\"viewportHeight\":%d,\"cameraLeft\":%d,\"mouseRoomX\":%d,\"mouseRoomY\":%d}",
		hdAspectRatio(), HdRemaster::state().active && hdAspectRatio() == 43 ? 1920 : 2560,
        HdRemaster::state().active || hdAspectRatio() == 169 ? 1440 : 1920, _screenWidth, _screenHeight,
		_virtscr[kMainVirtScreen].xstart, _virtualMouse.x, _virtualMouse.y);
    status.deleteLastChar();
    const auto &render = HdRemaster::state();
    status += Common::String::format(",\"waterBackend\":\"%s\"",
        render.active && render.water ? "opengl-shader" : "original-overlays");
    status += Common::String::format(",\"drawableWidth\":%d,\"drawableHeight\":%d,\"renderBackend\":\"%s\",\"presentationIntervalMs\":%.3f}",
        render.drawableWidth, render.drawableHeight, render.active ? "opengl-shaders" : "cpu-effects", render.lastInterval);
    status.deleteLastChar();
    status += Common::String::format(",\"presentationFps\":%.3f,\"renderCpuMs\":%.3f,\"cameraTop\":%d}",
        render.fps, render.cpuMs, _screenTop);
    status.deleteLastChar();
    status += Common::String::format(",\"inventoryOpen\":%s,\"inventoryOffset\":%d,\"mouseScriptX\":%d,\"cursorObject\":%d}",
        hdInventoryOpen() ? "true" : "false", hdInventoryOffset(), VAR(VAR_MOUSE_X), _hdCursorObject);
	Common::String temporary = directory + "/status.tmp";
	FILE *output = fopen(temporary.c_str(), "wb");
	if (output) {
		fwrite(status.c_str(), 1, status.size(), output);
		fclose(output);
		rename(temporary.c_str(), (directory + "/status.json").c_str());
	}
}
