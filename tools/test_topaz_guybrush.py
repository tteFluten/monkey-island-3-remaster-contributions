import unittest

from topaz_guybrush import selection, remaining


class GuybrushPriorityTests(unittest.TestCase):
    def test_shared_frames_use_original_owner_once(self):
        body='costumes/LFLF_0001_AKOS_0002_frame_9.png'
        alias='costumes/LFLF_0040_AKOS_0254_frame_1.png'
        unrelated='costumes/LFLF_0009_AKOS_0025_frame_1.png'
        plan=dict(scenes=[dict(id='room-0009',sources=[
            dict(source=body,operation='existing',owner='topaz-character-objectmatting'),
            dict(source=unrelated,operation='upscale-matting')]),
            dict(id='room-0040',sources=[dict(source=alias,operation='alias',parent=body)])])
        _,selected,owners=selection(plan)
        self.assertEqual(set(selected),{body,alias})
        self.assertEqual(owners,{body:'../topaz-character-objectmatting'})

    def test_alias_can_resolve_to_resource_outside_character_scope(self):
        source='costumes/LFLF_0001_AKOS_0002_frame_1.png'
        parent='costumes/LFLF_0009_AKOS_0025_frame_1.png'
        plan=dict(scenes=[dict(id='room-0009',sources=[
            dict(source=source,operation='alias',parent=parent),
            dict(source=parent,operation='upscale-matting')])])
        self.assertEqual(selection(plan)[2],{parent:'room-0009'})

    def test_effects_and_tiny_sources_do_not_enter_paid_queue(self):
        entries=[dict(source='costumes/LFLF_0013_AKOS_0065_frame_1.png',operation='upscale-matting'),
                 dict(source='costumes/LFLF_0001_AKOS_0002_frame_1.png',operation='review-small')]
        _,selected,owners=selection(dict(scenes=[dict(id='room-0001',sources=entries)]))
        self.assertEqual(len(selected),2)
        self.assertEqual(owners,{})

    def test_restart_cannot_reset_credit_ceiling(self):
        budget=dict(ceiling=100,initial_cost=20)
        self.assertEqual(remaining(budget,20),100)
        self.assertEqual(remaining(budget,110),10)
        self.assertEqual(remaining(budget,121),0)


if __name__=='__main__':unittest.main()
