import unittest
from s0_report import status_table, history_summary


class Tests(unittest.TestCase):
    def test_structure_gate_does_not_select_individual_projects(self):
        trial=dict(qualifying_items=['a','b','c','d'])
        result=status_table('computable',[dict(item_id=str(i),k=1) for i in range(15)],[],trial)
        self.assertEqual(result['T1']['status'],'未检验')
        self.assertEqual(result['T5_main']['status'],'可检验')

    def test_stability_uses_current_answer_not_first_answer(self):
        item=dict(item_id='i',gold='Truth',gold_aliases=['Truth'],answer_format='entity',
                  candidates=[dict(type='d',name='Other',aliases=['Other'])])
        row=dict(conflict_id='i',work_id='i',idx=0,path='natural_wrong',arm='shared',rep=0,t=2,
                 phase='test',first_value='Other',current_value='Truth',current_missing=False,
                 truncated=False,looped=False,changed_from_t1=True)
        result=history_summary({'i':item},[dict(item_id='i',answer_counts={'Other':8})],[row])[0]
        self.assertEqual(result['s'],0)
        self.assertFalse(result['stable_wrong'])
        self.assertTrue(result['first_wrong'])


if __name__=='__main__':unittest.main()
