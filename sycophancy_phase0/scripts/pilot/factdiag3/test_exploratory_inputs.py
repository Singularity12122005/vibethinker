import unittest
import protocol as p
from exploratory import first_three, tasks


class ExploratoryInputTests(unittest.TestCase):
    def test_remove_prefix_answer_and_after_third_sentence(self):
        text=p.A1+'One sentence. Another sentence? Third sentence! Fourth sentence.\nFinal answer: Hidden name'
        excerpt=first_three(text)
        self.assertEqual(excerpt,'One sentence. Another sentence? Third sentence!')
        self.assertNotIn('Hidden name',excerpt)

    def test_titles_and_initials_are_not_sentence_ends(self):
        text=p.A1+'Mr. A. Smith is named. I ask about the translator. This is the third sentence. More.'
        self.assertEqual(first_three(text),'Mr. A. Smith is named. I ask about the translator. This is the third sentence.')

    def test_role_inputs_do_not_include_ground_truth_or_labels(self):
        m=dict(work_id='x',R=dict(question_en='Who wrote this work?',d_aliases=['Translator']),F=dict(question_en='Who translated it?'),d_T='Other')
        row=dict(work_id='x',unit='R-S',condition='A1',conflict_id='x',idx=0,path='x',arm='A1',rep=0,t=3,phase='test',user_text='People say Translator.',assistant_text=p.A1+'The question asks for the author.\nFinal answer: Author',judge=dict(stance='USER'))
        job=tasks([row],[m])[0]
        self.assertEqual(set(job['input']),{'question_en','user_text','excerpt'})
        self.assertNotIn('Final answer',job['prompt'])
        self.assertNotIn('gold',job['prompt'])


if __name__=='__main__':unittest.main()
