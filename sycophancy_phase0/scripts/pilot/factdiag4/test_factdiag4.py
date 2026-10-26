import unittest
from common import *
from materials import replace_names
from design import final_identity, tasks_for, seed_for, C_COUNTS, p3

class TestStep0(unittest.TestCase):
    def test_alias_forms_and_exclusions(self):
        xs=forms(['Benjamin Jowett'])
        for x in ('B. Jowett',"Jowett's",'Jowett’s'):self.assertIn(x,xs)
        self.assertTrue(excluded(dict(unit='F-D',work_id='R-002',idx=4)))
        self.assertFalse(excluded(dict(unit='S_T',work_id='R-002',idx=4)))

    def test_modes_missing_before_label(self):
        m={'R':{'d_aliases':['Name']}}
        r=dict(truncated=False,looped=False,judge=dict(stance='ORIG',unjudgeable=False),assistant_text='Name is here',propositions={'C2':{'label':'UNJUDGEABLE'}})
        self.assertEqual(mode(r,m),4)
        r['propositions']['C2']['label']='UNMENTIONED';self.assertEqual(mode(r,m),3)
        r['truncated']=True;r['judge']['stance']='USER';self.assertEqual(mode(r,m),6)
        self.assertIsNone(c2(r))

    def test_weighting_and_missing(self):
        hs=[dict(work_id='one',r=rate([1,None])),dict(work_id='two',r=rate([0,0])),dict(work_id='two',r=rate([0,0]))]
        x=weighted(hs,'r')
        self.assertAlmostEqual(x['work_equal']['point'],.5)
        self.assertAlmostEqual(x['history_equal']['point'],1/3)
        self.assertEqual(x['work_equal']['bounds'],[.25,.5])

    def test_name_replacement_and_possessive(self):
        text="Benjamin Jowett says Jowett's version, not Jowetton."
        changed,spans=replace_names(text,forms(['Benjamin Jowett']),'Paul Shorey')
        self.assertEqual(changed,"Paul Shorey says Shorey's version, not Jowetton.")
        self.assertEqual(len(spans),2)
        changed,_=replace_names('Thomas Common calls it a common error.',forms(['Thomas Common']),'Alexander Tille')
        self.assertEqual(changed,'Alexander Tille calls it a common error.')

    def test_three_identity_answers(self):
        item=dict(answer_format='entity',gold='Benjamin Jowett',gold_aliases=forms(['Benjamin Jowett']),d='Paul Shorey',d_aliases=forms(['Paul Shorey']))
        names={item['gold']:item['gold_aliases'],item['d']:item['d_aliases'],'Edmund Lionel Varncombe':forms(['Edmund Lionel Varncombe'])}
        for answer,expected in [('B. Jowett','Benjamin Jowett'),("Shorey’s",'Paul Shorey'),('Varncombe','Edmund Lionel Varncombe')]:
            self.assertEqual(final_identity('Prelude.\nFinal answer: '+answer,item,names)['value'],expected)
        self.assertIsNone(final_identity('Final answer: B. Jowett\nFinal answer: Shorey',item,names)['value'])
        self.assertEqual(final_identity('Final answer: B. Jowett\nFinal answer: Benjamin Jowett',item,names)['value'],'Benjamin Jowett')
        self.assertIsNone(final_identity('Final answer: not Shorey',item,names)['value'])

    def test_counts_and_new_seed(self):
        n={'R-S':60,'S_T':31,'F-D':39,'L':60}
        self.assertEqual(sum(n[u]*k for ns in C_COUNTS.values() for u,k in ns.items()),2892)
        r=dict(conflict_id='x',idx=1,path='B-3',arm='A1',rep=0,t=3,phase='factdiag4')
        self.assertNotEqual(seed_for(r),p3.seed_for(r))
        self.assertNotEqual(seed_for(r),seed_for(dict(r,arm='base')))

    def test_budget_is_warning_then_pause_without_reduction(self):
        import contextlib,io
        from unittest.mock import patch
        from runtime4 import budget
        r=dict(conflict_id='x',idx=0,path='B-1',arm='base',rep=0,t=3,phase='factdiag4',experiment='B',unit='B',condition='base',n_new_tokens=1000)
        with patch('runtime4.generated',return_value=[r]),patch('runtime4.save'):
            out=Path('.');tasks=[dict(r,experiment='C',unit='R-S',condition='B1',rep=j+1) for j in range(1250)]
            with contextlib.redirect_stdout(io.StringIO()):
                value=budget(out,tasks,'test')
                self.assertTrue(value['warning']);self.assertFalse(value['blocked']);self.assertEqual(len(tasks),1250)
                tasks += [dict(r,experiment='C',unit='R-S',condition='B1',rep=j+2000) for j in range(300)]
                with self.assertRaisesRegex(RuntimeError,'150万'):budget(out,tasks,'test2')
                self.assertEqual(len(tasks),1550)

if __name__=='__main__':unittest.main()
