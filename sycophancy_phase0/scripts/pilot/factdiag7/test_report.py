import unittest
from stage1_report import ratio,answer_state


class ReportTest(unittest.TestCase):
    def test_overall_does_not_mix_strata_from_different_cells(self):
        rows=[{'work_id':'same','pi':.1,'metrics':{'n':[1,1],'d':[1,1]}},
              {'work_id':'same','pi':.5,'metrics':{'n':[0,0],'d':[1,1]}}]
        result=ratio(rows,'n','d',pooled=True)
        self.assertAlmostEqual(result['population_HT']['lower'],10/12)
        self.assertEqual(result['population_HT']['lower'],result['population_HT']['upper'])

    def test_unknown_denominator_is_not_smoothed(self):
        rows=[{'work_id':'one','pi':1,'metrics':{'n':[0,1],'d':[0,1]}}]
        result=ratio(rows,'n','d',pooled=True)
        self.assertEqual(result['population_HT']['lower'],0)
        self.assertIsNone(result['population_HT']['upper'])
        self.assertIsNone(result['population_HT']['conservative_interval'])

    def test_answer_states_reservation_and_unknown(self):
        item={'gold':'Writer','answer_format':'entity','people':[]}
        row={'truncated':False,'looped':False,'parsed':{'kind':'missing','reason':'no_answer_line','value':None}}
        stance={'stance':'NONE','explicit':'HEDGED','final_value':None}
        self.assertEqual(answer_state(row,item,stance)['status'],'RESERVED')
        row['truncated']=True
        self.assertEqual(answer_state(row,item,stance)['status'],'FAILED')
        row['truncated']=False;row['parsed']={'kind':'other','value':'Unverified name'}
        state=answer_state(row,item,{})
        self.assertTrue(state['answer_unjudgeable']);self.assertEqual(state['wrong'],[0,1])


if __name__=='__main__':unittest.main()
