import unittest
from unittest.mock import patch
from pathlib import Path
from trials import policy_readouts,tasks


class TrialTests(unittest.TestCase):
    def test_policy_uses_actual_second_answer_and_excludes_equal_candidate(self):
        h=dict(conflict_id='i',work_id='i',idx=0,path='correct',arm='shared',rep=0,t=2,
               phase='G6_S0_HISTORY',current_missing=False,current_value='old')
        item=dict(item_id='i',work_id='i',question_en='q',gold='right',gold_aliases=['right'],
                  answer_format='entity',candidates=[dict(type='d',name='old'),dict(type='N',name='other')])
        with patch('trials.load',return_value=[h]),patch('trials.collection_items',return_value={'i':item}),patch.object(Path,'glob',return_value=[]):
            result=policy_readouts(Path('.'),['test'])
        self.assertEqual(len(result['excluded']),1)
        d=next(iter(result['definitions'].values()))
        self.assertEqual((d['left'],d['right']),('old','other'))

    def test_four_trials_continue_the_same_second_history(self):
        class Main:
            def continue_from(self,row,text):
                self.row=row;return [1,2,3]
        main=Main()
        h=dict(conflict_id='i',work_id='i',idx=2,path='correct',arm='shared',rep=0,t=2,
               phase='G6_S0_HISTORY',current_value='actual',n_new_tokens=10)
        result=tasks(main,[(h,dict(type='D',name='candidate'))])
        self.assertIs(main.row,h)
        self.assertEqual([r['rep'] for r in result],[0,1,2,3])
        self.assertTrue(all(r['original']=='actual' and r['phase']=='G6_S0_TRIAL' for r in result))


if __name__=='__main__':unittest.main()
