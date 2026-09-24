// Opt-in native smoke-test input. No OS-wide keyboard/mouse automation.
// Enable MI3_ENGINE_TEST_INPUT=1 only for the spawned engine under test.
if (getenv("MI3_ENGINE_TEST_INPUT") && ConfMan.hasKey("playtest_session", "comi")) {
	static uint32 lastPoll = 0;
	uint32 now = SDL_GetTicks();
	if (now - lastPoll > 100) {
		lastPoll = now;
		Common::String file = ConfMan.get("playtest_session", "comi") + "/test-input.txt";
		FILE *input = fopen(file.c_str(), "r");
		if (input) {
			char command[80] = {};
			fgets(command, sizeof(command), input);
			fclose(input);
			remove(file.c_str());
			int key = 0, x = 0, y = 0;
			if (strncmp(command, "window", 6) == 0) {
				int w, h;
				SDL_GetWindowSize(_graphicsManager->getWindow()->getSDLWindow(), &w, &h);
				FILE *output = fopen((ConfMan.get("playtest_session", "comi") + "/test-window.json").c_str(), "w");
				if (output) {
					fprintf(output, "{\"width\":%d,\"height\":%d,\"dpi\":%f}\n", w, h,
						_graphicsManager->getWindow()->getSdlDpiScalingFactor());
					fclose(output);
				}
			} else if (sscanf(command, "fullscreen %d", &key) == 1) {
				g_system->beginGFXTransaction();
				g_system->setFeatureState(OSystem::kFeatureFullscreenMode, key != 0);
				g_system->endGFXTransaction();
			} else if (sscanf(command, "resize %d %d", &x, &y) == 2 && x >= 320 && y >= 240) {
				SDL_SetWindowSize(_graphicsManager->getWindow()->getSDLWindow(), x, y);
			} else if (strncmp(command, "screenshot", 10) == 0) {
				g_system->saveScreenshot();
			} else if (sscanf(command, "key %d", &key) == 1) {
				SDL_Event native = {};
				native.type = SDL_KEYDOWN;
				native.key.keysym.sym = (SDL_Keycode)key;
				native.key.state = SDL_PRESSED;
				SDL_PushEvent(&native);
				native.type = SDL_KEYUP;
				native.key.state = SDL_RELEASED;
				SDL_PushEvent(&native);
			} else if (sscanf(command, "move %d %d", &x, &y) == 2 ||
				sscanf(command, "down %d %d", &x, &y) == 2 ||
				sscanf(command, "up %d %d", &x, &y) == 2) {
				SDL_Event native = {};
				native.type = SDL_MOUSEMOTION;
				native.motion.x = x; native.motion.y = y;
				SDL_PushEvent(&native);
				if (command[0] != 'm') {
					native.type = command[0] == 'd' ? SDL_MOUSEBUTTONDOWN : SDL_MOUSEBUTTONUP;
					native.button.button = SDL_BUTTON_LEFT;
					native.button.state = command[0] == 'd' ? SDL_PRESSED : SDL_RELEASED;
					native.button.x = x; native.button.y = y;
					SDL_PushEvent(&native);
				}
			} else if (sscanf(command, "click %d %d", &x, &y) == 2) {
				SDL_Event native = {};
				native.type = SDL_MOUSEMOTION;
				native.motion.x = x; native.motion.y = y;
				SDL_PushEvent(&native);
				native.type = SDL_MOUSEBUTTONDOWN;
				native.button.button = SDL_BUTTON_LEFT;
				native.button.state = SDL_PRESSED;
				native.button.x = x; native.button.y = y;
				SDL_PushEvent(&native);
				native.type = SDL_MOUSEBUTTONUP;
				native.button.state = SDL_RELEASED;
				SDL_PushEvent(&native);
			}
		}
	}
}
