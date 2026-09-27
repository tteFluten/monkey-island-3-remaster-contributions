#!/usr/bin/env python3
"""Verify depth of field reaches decorative margins and matches CPU fallback."""
import argparse
import json
import shutil
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from check_aspect import Check, ROOT

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/performance/wide-blur')
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    hd = output / 'hd'; hd.mkdir(exist_ok=True)
    for source in (ROOT / '.playtest/hd').iterdir():
        if source.name != 'widescreen' and not (hd / source.name).exists():
            (hd / source.name).symlink_to(source, target_is_directory=source.is_dir())
    (hd / 'widescreen').mkdir(exist_ok=True)
    shutil.copyfile(ROOT / '.playtest/hd/widescreen/bg_0009.png', hd / 'widescreen/bg_0009.png')
    grades = output / 'grades.json'; grades.write_text('{"schemaVersion":1,"rooms":{}}')
    pictures = {}
    for name, gpu, level in [('sharp', True, 0), ('gpu', True, 2), ('cpu', False, 2)]:
        check = Check(output / name, 169, hd_path=hd, color_grades_path=grades,
                      config_overrides={'comi': {'hd_gpu_effects': str(gpu).lower(), 'hd_depth_of_field': str(level),
                          'hd_dof_blur': '0', 'hd_dof_intensity': '100', 'hd_dof_edge': '2', 'hd_dof_depth': '1'}})
        try:
            check.screenshot('presentation')
            pictures[name] = Image.open(check.output / 'presentation.png').convert('RGB')
        finally: check.close()
    w, h = pictures['sharp'].size
    results = []
    for side, bounds in [('left', (2, 2, w // 8 - 3, h - 2)), ('right', (w * 7 // 8 + 3, 2, w - 2, h - 2))]:
        crops = {key: img.crop(bounds) for key, img in pictures.items()}
        changed = max(ImageStat.Stat(ImageChops.difference(crops['gpu'], crops['sharp'])).mean)
        error = max(ImageStat.Stat(ImageChops.difference(crops['gpu'], crops['cpu'])).mean)
        results.append({'side': side, 'blurDifference': changed, 'cpuGpuMeanError': error, 'passed': changed > .05 and error < 2})
    (output / 'result.json').write_text(json.dumps({'sides': results, 'passed': all(r['passed'] for r in results)}, indent=2))
    print(json.dumps(results), flush=True)
    assert all(r['passed'] for r in results), results

if __name__ == '__main__': main()
