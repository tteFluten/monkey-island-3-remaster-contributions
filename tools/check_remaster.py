#!/usr/bin/env python3
"""Compare GPU effects with a same-tick CPU reference and exercise native controls."""
import argparse
import json
import time
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from check_aspect import Check, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/performance/visual')
    parser.add_argument('--rooms', type=int, nargs='+', default=[9, 15, 77])
    parser.add_argument('--interactions', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    grades = output / 'grades.json'
    grades.write_text(json.dumps({'schemaVersion': 1, 'rooms': {str(room): {
        'brightness': 4, 'contrast': 8, 'saturation': 5, 'gamma': 105,
        'vignetteEnabled': 1, 'vignetteAmount': 40, 'vignetteRadius': 60, 'vignetteSoftness': 50
    } for room in args.rooms}}))
    check = Check(output, 169, color_grades_path=grades,
        config_overrides={'comi': {'hd_gpu_effects': 'true', 'hd_water_shader': 'false', 'hd_depth_of_field': '2', 'hd_dof_blur': '0'},
                          'scummvm': {'vsync': 'true'}})
    results = []
    try:
        for room in args.rooms:
            check.save_load(2, 0, 9)
            if room != 9: check.jump(room)
            check.wait(lambda: check.state().get('renderBackend') == 'opengl-shaders', 'GPU effects active')
            if room == 9:
                (output / 'walk-to.txt').write_text('450 430\n')
                (output / 'motion-check.json').unlink(missing_ok=True)
                (output / 'motion-check').touch()
                check.wait(lambda: (output / 'motion-check.json').exists(), 'fixed-room interpolation endpoint', 30)
                endpoint = json.loads((output / 'motion-check.json').read_text())
                assert endpoint['different_pixels'] == 0, endpoint
                print(json.dumps({'fixedEndpoint': endpoint}), flush=True)
            if room == 77:
                start = check.state().get('cameraTop', 0)
                (output / 'camera-sweep').touch()
                check.wait(lambda: abs(check.state().get('cameraTop', 0) - start) > 10, 'vertical camera movement', 30)
                (output / 'motion-check.json').unlink(missing_ok=True)
                (output / 'motion-check').touch()
                check.wait(lambda: (output / 'motion-check.json').exists(), 'vertical interpolation endpoint', 30)
                endpoint = json.loads((output / 'motion-check.json').read_text())
                assert endpoint['different_pixels'] == 0, endpoint
                (output / 'camera-sweep').unlink(missing_ok=True)
                print(json.dumps({'verticalEndpoint': endpoint}), flush=True)
            for name in ('effects-gpu.png', 'effects-cpu.png'):
                (output / name).unlink(missing_ok=True)
            (output / 'compare-effects').touch()
            check.wait(lambda: (output / 'effects-cpu.png').exists(), 'same-tick effect comparison', 60)
            time.sleep(.5)
            gpu = Image.open(output / 'effects-gpu.png').convert('RGB')
            cpu = Image.open(output / 'effects-cpu.png').convert('RGB')
            assert gpu.size == cpu.size == (2560, 1440)
            diff = ImageChops.difference(gpu, cpu)
            mean = max(ImageStat.Stat(diff).mean)
            results.append({'room': room, 'meanChannelError': mean, 'passed': mean < 2})
            gpu.save(output / f'room-{room}-gpu.png'); cpu.save(output / f'room-{room}-cpu.png')
            diff.save(output / f'room-{room}-difference.png')
            print(json.dumps(results[-1]), flush=True)
            check.screenshot(f'room-{room}-presentation')
        if args.interactions:
            check.save_load(2, 0, 9)
            check.select(169)
            check.send('key 105'); check.screenshot('inventory'); check.send('key 105')
            check.send('resize 960 800'); check.screenshot('taller-window')
            check.send('fullscreen 1'); check.screenshot('fullscreen')
            check.send('fullscreen 0'); check.send('resize 1280 720')
            check.save_load(1, 7, 9); check.jump(15); check.save_load(2, 7, 9)
        (output / 'result.json').write_text(json.dumps({'comparisons': results,
            'passed': all(r['passed'] for r in results), 'state': check.state()}, indent=2))
        assert all(r['passed'] for r in results), results
    finally:
        check.close()

if __name__ == '__main__': main()
