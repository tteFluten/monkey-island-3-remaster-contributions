import unittest
from asset_batch_groups import group_batches


class BatchGroupTests(unittest.TestCase):
    def unit(self,room,number,count,phase='process'):
        return dict(id=f'room-{room:04}-b{number:03}',scene=f'room-{room:04}',room=room,
                    name='scene',phase=phase,sources=[f'{room}-{number}-{n}.png' for n in range(count)])

    def test_combines_costumes_and_splits_into_hundreds_without_loss(self):
        units=[self.unit(10,n,count) for n,count in enumerate((1,7,7,32,32,32,32,32,32,32,32,32,32,26))]
        expected=[s for b in units for s in b['sources']]
        groups=group_batches(units)
        self.assertEqual([s for g in groups for s in g['sources']],expected)
        self.assertTrue(all(len(g['sources'])==100 for g in groups[:-1]))
        self.assertLessEqual(len(groups[-1]['sources']),100)
        self.assertIn(units[0]['id'],groups[0]['work_units'])
        self.assertIn(units[2]['id'],groups[0]['work_units'])

    def test_scenes_stay_separate_and_pilots_preserves_reuse_are_excluded(self):
        units=[self.unit(10,1,70),self.unit(11,1,70),self.unit(10,2,40)]
        units += [self.unit(10,n,4,phase) for n,phase in enumerate(('pilot','preserve','reuse'),3)]
        groups=group_batches(units)
        self.assertEqual([(g['room'],len(g['sources'])) for g in groups],[(10,100),(10,10),(11,70)])
        self.assertEqual(groups,group_batches(units))

    def test_duplicate_sources_and_invalid_sizes_are_rejected(self):
        unit=self.unit(10,1,2)
        with self.assertRaises(ValueError):group_batches([unit,unit])
        for size in (0,-1,1.5,True):
            with self.subTest(size=size),self.assertRaises(ValueError):group_batches([unit],size)


if __name__=='__main__':unittest.main()
