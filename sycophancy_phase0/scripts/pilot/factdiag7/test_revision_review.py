import unittest
from .revision_review import agreement,gate


class RevisionReviewTest(unittest.TestCase):
    def test_unknown_is_disagreement_even_if_bounds_match(self):
        result=agreement([((0,1),(0,1)),((1,1),(1,1)),((0,0),(0,0)),(None,(0,0))])
        self.assertEqual((result['agree'],result['unknown_or_missing'],result['raw_agreement']),(2,2,.5))

    def test_full_60_and_diagnostic_split(self):
        rows=[dict(cohort='original_diagnostic' if i<40 else 'new_holdout',
                   machine_events={'W_false':(1,1)},
                   independent_events={'W_false':(1,1) if i<48 else (0,1)}) for i in range(60)]
        quality,stats=gate(rows)
        self.assertEqual(quality['status'],'通过')
        self.assertEqual(quality['raw_agreement'],.8)
        self.assertFalse(quality['final_conclusions_released'])
        self.assertEqual(stats['new_holdout']['W_false']['raw_agreement'],.4)
        with self.assertRaises(ValueError):gate(rows[:40])


if __name__=='__main__':unittest.main()
