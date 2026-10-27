import unittest
from formal import arm_counts,candidate_tau,last_number


class Tests(unittest.TestCase):
    def test_g1_arms(self):
        self.assertEqual(arm_counts('G1','correct','T'),{'S':4,'C':2,'S+A0':4})
        self.assertEqual(arm_counts('G1','correct','F_w'),{'S':4})
        self.assertEqual(arm_counts('G1','correct','I'),{'S':4,'C':2,'S+A1':4})

    def test_computable_main_and_control(self):
        self.assertEqual(arm_counts('G2d','constructed','d'),{'S':4,'S+A1':4})
        self.assertEqual(arm_counts('G2d','correct','d_control'),{'S':2,'S+A1':2})

    def test_last_number_with_punctuation(self):
        self.assertEqual(last_number('Mean 42, median 39. Final answer: 42.'),'42')
        self.assertEqual(last_number('Final answer: -3.5.'),'-3.5')
        self.assertIsNone(last_number('No numerical answer.'))

    def test_creator_role_distinct_from_subject_association(self):
        row=candidate_tau(dict(structure='G1'),dict(type='X'))
        self.assertEqual(row['same_subject'],0)
        self.assertEqual(row['creator_type_role'],1)


if __name__=='__main__':unittest.main()
