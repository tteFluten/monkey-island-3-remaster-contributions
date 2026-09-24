#!/usr/bin/env python3
"""Run an isolated native audio smoke test with copies of the player's saves."""
import argparse
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from comi_audio import atomic_json, ensure_stopped


def run(target, folder, audio):
    ensure_stopped(target)
    local = target / '.playtest'
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copytree(local / 'saves', folder / 'saves')
    hd = folder / 'hd'
    hd.mkdir()
    for child in (local / 'hd').iterdir():
        if child.name != 'audio':
            (hd / child.name).symlink_to(child.resolve(), target_is_directory=child.is_dir())
    (hd / 'audio').symlink_to(audio.resolve(), target_is_directory=True)
    config = configparser.ConfigParser()
    config.read(local / 'scummvm.ini')
    for section in ('scummvm', 'comi'):
        config[section]['savepath'] = str(folder / 'saves')
    config['scummvm']['screenshotpath'] = str(folder)
    config['comi']['playtest_session'] = str(folder)
    config['comi']['hd_path'] = str(hd)
    with (folder / 'scummvm.ini').open('w') as f:
        config.write(f)
    lock = local / 'engine.lock'
    lock.mkdir()
    atomic_json(lock / 'owner.json', dict(serverPid=os.getpid()))
    child = None
    observations = []
    try:
        with (folder / 'engine.log').open('w') as log:
            child = subprocess.Popen([str(local / 'engine/build/scummvm'),
                '--config=' + str(folder / 'scummvm.ini'), '--debuglevel=5', '--save-slot=0', 'comi'],
                cwd=folder, env={**os.environ, 'MI3_ENGINE_TEST_INPUT': '1'}, stdout=log, stderr=log)
            atomic_json(lock / 'owner.json', dict(serverPid=os.getpid(), gamePid=child.pid))

            def status():
                if child.poll() is not None:
                    raise RuntimeError('Native engine exited: ' + str(child.returncode))
                path = folder / 'status.json'
                try:
                    return json.loads(path.read_text())
                except (FileNotFoundError, json.JSONDecodeError):
                    return {}

            def wait(seconds):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    status()
                    time.sleep(.2)

            def key(code):
                (folder / 'test-input.txt').write_text(f'key {code}\n')
                wait(1)

            deadline = time.monotonic() + 45
            while not status().get('ready'):
                if time.monotonic() > deadline:
                    raise RuntimeError('Engine did not become ready')
                time.sleep(.2)
            observations.append(dict(step='loaded_copy_of_save', status=status()))
            # The loaded save opens the 11.57-second LeChuck music cue.
            # Remain alive beyond its end before requesting another scene.
            wait(16)
            for command_id, room in enumerate([15, 11, 9], 1):
                atomic_json(folder / 'command.json', dict(id=command_id, action='jump', room=room))
                deadline = time.monotonic() + 15
                while status().get('commandId', 0) < command_id:
                    if time.monotonic() > deadline:
                        raise RuntimeError('Room command timed out')
                    time.sleep(.2)
                observations.append(dict(step=f'jump_{room}', status=status()))
                if status().get('error') or status().get('room') != room:
                    raise RuntimeError('Room transition failed: ' + str(status()))
                wait(12)
            key(32)  # Space pauses COMI.
            observations.append(dict(step='pause_key', status=status()))
            key(32)
            observations.append(dict(step='resume_key', status=status()))
            key(1073741886)  # F5: save/load/options menu; copied saves only.
            observations.append(dict(step='menu_open', status=status()))
            (folder / 'test-input.txt').write_text('screenshot\n')
            wait(1)
            key(27)
            observations.append(dict(step='menu_closed', status=status()))
            (folder / 'test-input.txt').write_text('screenshot\n')
            wait(1)
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if (lock / 'owner.json').exists() and json.loads((lock / 'owner.json').read_text()).get('serverPid') == os.getpid():
            shutil.rmtree(lock)
        text = (folder / 'engine.log').read_text(errors='replace') if (folder / 'engine.log').exists() else ''
        atomic_json(folder / 'results.json', dict(observations=observations,
            audio_log=[line for line in text.splitlines() if any(s in line for s in ['HQ-MUSIC', 'Skipping', 'iMUS header', 'MAP ', 'ERROR'])],
            limitations='Process/engine diagnostics only; no loopback recording or listening verification.'))
    print('Native smoke results: ' + str(folder / 'results.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-workspace', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    parser.add_argument('--music-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.target_workspace.resolve(), args.report_dir.resolve(), args.music_dir.resolve())
