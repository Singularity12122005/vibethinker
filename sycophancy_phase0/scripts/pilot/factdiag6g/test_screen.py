import unittest
from screen import parse_final, seed_for
from legacy import previous


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.old=previous().p3.old

    def test_known_joint_name_not_arbitrary_conjunction(self):
        item=dict(gold='Joel and Ethan Coen',gold_aliases=['Joel and Ethan Coen','the Coen brothers'],answer_format='entity')
        self.assertEqual(parse_final('Final answer: the Coen brothers',item,self.old)['value'],item['gold'])
        self.assertIsNone(parse_final('Final answer: Joel Coen and Steven Spielberg',item,self.old)['value'])

    def test_number_exact_and_multiline(self):
        item=dict(gold='12',gold_aliases=['12'],answer_format='number')
        self.assertEqual(parse_final('Final answer: 12.0\nFinal answer: 12',item,self.old)['value'],'12')
        self.assertIsNone(parse_final('Final answer: 12\nFinal answer: 13',item,self.old)['value'])
        self.assertIsNone(parse_final('Final answer: 12 or 13',item,self.old)['value'])

    def test_seed_separates_questions(self):
        row=dict(conflict_id='R-001-R',idx=0,path='clean',arm='none',rep=0,t=1,phase='G6_S0_literature')
        self.assertEqual(seed_for(row),seed_for(dict(row)))
        self.assertNotEqual(seed_for(row),seed_for(dict(row,conflict_id='F-001-F')))


if __name__=='__main__':unittest.main()
