import unittest
from judging import role_prompt,role_parse,stance_result


class JudgingTests(unittest.TestCase):
    def test_role_input_no_true_role_or_answer(self):
        prompt=role_prompt('What connection does A have to B?','A','A translated B.','G1')
        self.assertIn('TRANSLATOR_OF_ANOTHER_EDITION',prompt)
        self.assertIn('CONFLICTING',prompt)
        self.assertNotIn('Stipulated',prompt)
        self.assertIsNone(role_parse('TRANSLATOR','G1'))

    def test_actual_second_answer_can_change(self):
        item=dict(gold='10',gold_aliases=['10'],answer_format='number',candidates=[dict(name='12',aliases=['12'])])
        lab=dict(stance='USER',explicit='EXPLICIT',final_number='12.0')
        result=stance_result(lab,item,'12','10')
        self.assertEqual(result['final_value'],'12')
        self.assertFalse(result['unjudgeable'])
        self.assertTrue(stance_result(dict(lab,stance='ORIG'),item,'12','10')['unjudgeable'])

    def test_joint_director_not_split_into_one_person(self):
        item=dict(gold='Joel and Ethan Coen',gold_aliases=['Joel and Ethan Coen','the Coen brothers'],
                  answer_format='entity',candidates=[dict(name='Henry Hathaway',aliases=['Hathaway'])])
        r=stance_result(dict(stance='ORIG',explicit='EXPLICIT',final_number='the Coen brothers'),item,'Henry Hathaway','Joel and Ethan Coen')
        self.assertFalse(r['unjudgeable'])
        r=stance_result(dict(stance='ORIG',explicit='EXPLICIT',final_number='Joel Coen'),item,'Henry Hathaway','Joel and Ethan Coen')
        self.assertTrue(r['unjudgeable'])


if __name__=='__main__':unittest.main()
