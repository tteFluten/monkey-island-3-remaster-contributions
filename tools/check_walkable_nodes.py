#!/usr/bin/env python3
"""Regress scene 29 corner dragging and simple clipping at cropped ratios."""
import argparse
import re
from pathlib import Path
from check_aspect import Check, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.context/walkable-nodes-check')
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    masks = out/'scene-masks.json'
    masks.write_text('{"schemaVersion":1,"scenes":{}}\n')
    header = (ROOT/'tools/engine/hd_voodoo_exterior.h').read_text()
    axes = {axis: [tuple(map(float, p)) for p in re.findall(r'\{(\d+),(\d+)\}',
            re.search(r'k'+axis+r'\[\] = (.*?);', header, re.S)[1])] for axis in ('X', 'Y')}

    def paint(value, axis):
        points = axes[axis]
        i = next((i for i in range(1, len(points)) if value <= points[i][0]), len(points)-1)
        a, b = points[i-1:i+1]
        return a[1]+(b[1]-a[1])*(value-a[0])/(b[0]-a[0])

    c = Check(out/'native', config_overrides={'comi': {'hd_scene_masks_path': str(masks)}})
    def state(): return c.state().get('maskEditor', {})
    window = {}
    def screen(x, y):
        h = max(window['height'], window['width']*9/16)
        return (round((window['width']-h*854/480)/2+x*h/480),
                round((window['height']-h)/2+y*h/480))
    def corner(x, y): return screen(paint(x, 'X')*854/2048, paint(y, 'Y')*480/1152)
    def button(slot):c.mask_button(slot)
    def actor():
        a = next(a for a in c.state()['actors'] if a['id'] == 1)
        return a['x'], a['y']
    def drag(x, y, area):
        px, py = corner(x, y)
        before = state()['document']['walkboxes']
        feet = actor()
        if area == 1:
            c.send(f'click {px+2} {py+2}')
            assert state()['document']['walkboxes'] == before, 'Selecting near a handle must not move it'
        c.send(f'down {px} {py}')
        assert state()['selected'] == area, state()
        c.send(f'move {px+8} {py+5}')
        c.send(f'up {px+8} {py+5}')
        c.wait(lambda: state()['document']['walkboxes'] != before, 'drag accepted')
        assert not state()['error'], state()['error']
        assert actor() == feet, 'Editor drag reached gameplay'

    try:
        c.jump(29)
        c.send('key 109')
        c.wait(lambda: state().get('visible'), 'walkable editor')
        assert not state()['moreOptions'], 'Scene tools should start with the simple controls'
        original = state()['document']['walkboxes']
        for width, height in ((1280, 720), (1280, 827), (1720, 720)):
            c.send(f'resize {width} {height}')
            window = c.window()
            button(19)
            c.wait(lambda: state()['moreOptions'], 'show extra options')
            assert any(b['slot'] == 17 for b in state()['controls'])
            button(19)
            c.wait(lambda: not state()['moreOptions'], 'hide extra options')
            # This corner is outside the shared segment; it used to snap back.
            drag(0, 429, 1)
            # Grab another area's handle directly while area 1 remains selected.
            drag(462, 301, 6)
            c.screenshot(f'editable-corners-{width}x{height}')
            for _ in range(2): c.send('key 122 192')
            c.wait(lambda: state()['document']['walkboxes'] == original, 'undo both edits')
            c.send('key 116')
            c.wait(lambda: state()['test'], 'Test mode')
            # The header and gaps are menu space, including in Play mode.
            tab = next(b for b in state()['controls'] if b['slot'] == 0)
            px, py = screen(tab['x']+10, tab['y']-8)
            feet = actor()
            c.send(f'click {px} {py}')
            assert actor() == feet and state()['test'], 'Menu header click reached gameplay'
            button(6)
            c.wait(lambda: not state()['test'], 'Select returns to editing')
            drag(0, 429, 1)
            c.send('key 122 192')
            c.wait(lambda: state()['document']['walkboxes'] == original, 'undo after Select')
            c.send('key 116')
            button(0)
            if state()['moreOptions']:button(19)
            c.wait(lambda: not state()['test'], 'Walkable tab returns to editing')
            button(2)
            button(15)
            c.wait(lambda: state()['bypass'], 'Peek actor')
            for slot, a, b in ((7, (280, 210), (340, 365)), (8, (325, 310), (285, 230))):
                button(slot)
                assert not state()['bypass'], 'Drawing must restore real clipping after Peek'
                px, py = corner(*a); xx, yy = corner(*b)
                c.send(f'down {px} {py}'); c.send(f'move {xx} {yy}'); c.send(f'up {xx} {yy}')
                c.wait(lambda: bool(state()['document']['foreground']), 'quick clip applied')
            clips = state()['document']['foreground']
            assert clips[0]['order'] == [1, -1], clips
            c.screenshot(f'simple-clipping-{width}x{height}')
            button(10)
            c.wait(lambda: not state()['document']['foreground'][0]['holes'], 'undo Show actor')
            button(11)
            c.wait(lambda: state()['document']['foreground'] == clips, 'redo Show actor')
            button(17)
            c.wait(lambda: not state()['document']['foreground'], 'reset clipping')
            button(0)
            if state()['moreOptions']:button(19)
        print('PASS: partial shared edges, direct corner switching, input isolation, undo/redo, Test-to-edit controls, Hide/Show rectangles, Peek restoration, three display ratios', flush=True)
    finally:
        c.close()


if __name__ == '__main__': main()
