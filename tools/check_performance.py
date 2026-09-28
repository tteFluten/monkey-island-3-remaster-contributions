#!/usr/bin/env python3
"""Native swap benchmarks. Isolated saves/config, explicit CPU/GPU effects."""
import argparse
import csv
import json
from pathlib import Path
import statistics
import time
from check_aspect import Check, ROOT


def summarize(path):
    rows = list(csv.DictReader(path.open()))[1:]
    if not rows:
        return {'passed': False, 'error': 'No completed presentation samples'}
    def column(key):
        return [float(row[key]) for row in rows if float(row[key]) >= 0]
    def p99(values):
        return sorted(values)[min(len(values) - 1, int(len(values) * .99))] if values else None
    intervals, cpu, gpu = column('interval_ms'), column('cpu_ms'), column('gpu_ms')
    fps = 1000 / statistics.mean(intervals)
    late = sum(v > 25 for v in intervals) / len(intervals) * 100
    result = dict(frames=len(rows), fps=fps, intervalP99Ms=p99(intervals), cpuP99Ms=p99(cpu),
                  gpuP99Ms=p99(gpu), gpuSamples=len(gpu), over25MsPercent=late, maximumIntervalMs=max(intervals))
    result['cameraPositions'] = len({(row.get('camera_x'), row.get('camera_y')) for row in rows})
    if 'visual_camera_x' in rows[0]:
        poses = [(float(r['visual_camera_x']), float(r['visual_camera_y'])) for r in rows]
        result['visualCameraPositions'] = len(set(poses))
        result['fractionalCameraFrames'] = sum(any(abs(v - round(v)) > .0001 for v in p) for p in poses)
        result['followFrames'] = sum(r['camera_follow'] == '1' for r in rows)
        result['maximumCameraStep'] = max((max(abs(a-b) for a,b in zip(p,q))
                                           for p,q in zip(poses, poses[1:])), default=0)

    result['passed'] = 59 <= fps <= 61 and p99(cpu) <= 1000 / 60 and (not gpu or p99(gpu) <= 1000 / 60) and late < 1
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / '.context/performance/run')
    p.add_argument('--engine', type=Path)
    p.add_argument('--room', type=int, default=15)
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--runs', type=int, default=3)
    p.add_argument('--gpu', action='store_true')
    p.add_argument('--vsync', action='store_true')
    p.add_argument('--film', action='store_true', help='Enable subtle vintage film at strength 20')
    p.add_argument('--fullscreen', action='store_true')
    p.add_argument('--effects', action='store_true')
    p.add_argument('--motion', choices=['walk', 'camera', 'idle'], default='walk')
    args = p.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    grades = output / 'grades.json'
    grades.write_text(json.dumps({'schemaVersion': 1, 'rooms': {str(args.room): {
        'brightness': 4, 'contrast': 8, 'saturation': 5, 'gamma': 105, 'warmth': 4,
        'vignetteEnabled': 1, 'vignetteAmount': 40, 'vignetteRadius': 60, 'vignetteSoftness': 50
    }} if args.effects else {}}))
    launch_started = time.monotonic()
    check = Check(output, 169, color_grades_path=grades, engine_path=args.engine, allow_window=not args.fullscreen,
        config_overrides={'scummvm': {'vsync': str(args.vsync).lower(), 'fullscreen': str(args.fullscreen).lower(),
            'last_window_width': '2560', 'last_window_height': '1440',
            'hd_film_enabled': str(args.film).lower(), 'hd_film_strength': '20'},
            'comi': {'hd_gpu_effects': str(args.gpu).lower(), 'hd_trace': 'false',
                     'hd_depth_of_field': '2' if args.effects else '0', 'hd_dof_blur': '0',
                     'hd_dof_intensity': '100', 'hd_dof_edge': '2', 'hd_dof_depth': '1'}})
    results = []
    try:
        if args.fullscreen:
            check.wait(lambda: check.window()["fullscreen"], "fullscreen presentation", 15)
        launch_seconds = time.monotonic() - launch_started
        transition_started = time.monotonic()
        check.jump(args.room)
        transition_seconds = time.monotonic() - transition_started
        time.sleep(5)
        for run in range(args.runs):
            (output / 'benchmark-start').write_text('')
            check.wait(lambda: not (output / 'benchmark-start').exists(), 'benchmark started')
            end = time.monotonic() + args.seconds
            next_walk = 0
            right = True
            actor_positions = set()
            while time.monotonic() < end:
                now = time.monotonic()
                for actor in check.state().get('actors', []):
                    if actor['id'] == 1: actor_positions.add((actor['x'], actor['y']))
                if args.motion == 'walk' and now >= next_walk:
                    # Normal actor walker; room 15 has a continuous horizontal street.
                    x = (1450 if right else 650) if check.state().get('width', 0) > 2560 else (450 if right else 190)
                    (output / 'walk-to.txt').write_text(f'{x} 430\n')
                    right = not right; next_walk = now + 4
                elif args.motion == 'camera':
                    (output / 'camera-sweep').touch(exist_ok=True)
                time.sleep(.1)
            (output / 'benchmark-stop').write_text('')
            check.wait(lambda: (output / 'frames.csv').exists() and not (output / 'benchmark-stop').exists(), 'benchmark saved')
            report = output / f'frames-{run+1}.csv'; (output / 'frames.csv').rename(report)
            result = summarize(report)
            result['actorPositions'] = len(actor_positions)
            result['motionVerified'] = (len(actor_positions) > 1 if args.motion == 'walk' else result['cameraPositions'] > 1 if args.motion == 'camera' else True)
            result['passed'] = result['passed'] and result['motionVerified']
            results.append(result)
            print(json.dumps({'run': run+1, **result}), flush=True)
        check.screenshot('presentation')
        (output / 'result.json').write_text(json.dumps({'settings': vars(args) | {'output': str(output), 'engine': str(args.engine)},
            'state': check.state(), 'loading': {'launchSeconds': launch_seconds, 'jumpSeconds': transition_seconds}, 'runs': results, 'passed': all(r['passed'] for r in results)}, indent=2))
    finally:
        check.close()

if __name__ == '__main__': main()
