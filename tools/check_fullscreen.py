#!/usr/bin/env python3
"""Verify normal-play fullscreen policy, in 16:9."""
import argparse
import json
from pathlib import Path
from check_aspect import Check, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/performance/fullscreen')
    args = parser.parse_args()
    check = Check(args.output, 169, allow_window=False,
                  config_overrides={'scummvm': {'fullscreen': 'false', 'vsync': 'true'},
                                    'comi': {'hd_gpu_effects': 'true'}})
    states = []
    try:
        aspect = 169
        if check.state()['aspectRatio'] != aspect: check.select(aspect)
        check.wait(lambda: check.window()['fullscreen'], 'macOS fullscreen transition', 15)
        check.wait(lambda: check.state().get('renderBackend') == 'opengl-shaders', 'GPU rendering restored')
        check.send('fullscreen 0')
        window = check.window()
        assert window['fullscreen'], window
        states.append({'aspect': aspect, **window})
        check.screenshot(f'fullscreen-{aspect}')
        (check.output / 'result.json').write_text(json.dumps({'passed': True, 'states': states}, indent=2))
        print('PASS: startup overrides window preference; 16:9 remains fullscreen')
    finally:
        check.close()


if __name__ == '__main__': main()
