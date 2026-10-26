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

    def test_paired_missing_bounds_and_sparse_status(self):
        from statistics4 import paired,decision
        def row(w,rep,v):return dict(work_id=w,idx=0,rep=rep,unit='R-S',truncated=v is None,looped=False,judge=dict(stance='USER' if v else 'ORIG',unjudgeable=False))
        old=[row('one',0,1),row('one',1,1),row('two',0,0),row('two',1,0)]
        new=[row('one',0,0),row('one',1,None),row('two',0,0),row('two',1,0)]
        bank={'one':{},'two':{}};result=paired(new,old,bank,bank,'outcome')
        self.assertEqual(result['work_equal']['point'],-.5)
        self.assertEqual(result['work_equal']['bounds'],[-.5,-.25])
        self.assertFalse(result['strict_available'])
        status=decision(result,-.1,'le')
        self.assertTrue(status['empirical_pass']);self.assertFalse(status['strict_pass'])
        self.assertEqual(status['status'],'经验达标，严格未定')

    def test_ideal_solution_unknown_is_not_success(self):
        from statistics4 import metric
        m={'R':{'d_aliases':['Translator']}}
        r=dict(unit='R-S',truncated=False,looped=False,assistant_text='Translator is mentioned.',judge=dict(stance='ORIG',unjudgeable=False,explicit='EXPLICIT'),propositions={'C2':{'label':'UNJUDGEABLE'}})
        self.assertIsNone(metric(r,m,'ideal'))
        r['propositions']['C2']['label']='UNMENTIONED';self.assertEqual(metric(r,m,'ideal'),1)
        r['propositions']['C2']['label']='DENY';self.assertEqual(metric(r,m,'ideal'),0)

    def test_complete_statistics_pipeline_with_known_costs(self):
        from statistics4 import experiment_C,experiment_A
        from copy import deepcopy
        material=dict(R=dict(question_en='Author?',answer_format='entity',gold='Author Name',gold_aliases=['Author Name'],d='Translator Name',d_aliases=['Translator Name']),F=dict(question_en='Translator?',answer_format='entity',gold='Translator Name',gold_aliases=['Translator Name'],d='Wrong Name',d_aliases=['Wrong Name']),d_T='Wrong Name',d_T_aliases=['Wrong Name'])
        mats=[dict(deepcopy(material),work_id=w) for w in ('R-005','R-006')]
        def make(w,j,u,c,k,new=False):
            user=(u=='F-D' and (new or c=='base')) or (u in ('R-S','S_T') and c=='base')
            return dict(work_id=w,idx=j,unit=u,condition=c,rep=k,truncated=False,looped=False,assistant_text='Translator Name.\nFinal answer: Translator Name',judge=dict(stance='USER' if user else 'ORIG',explicit='EXPLICIT',unjudgeable=False),propositions={'C2':{'label':'AFFIRM'}})
        old=[make(w,j,u,c,k) for w in ('R-005','R-006') for j in range(2) for u,n in p3.COUNTS.items() for c in ('base','A1') for k in range(n)]
        new=[make(w,j,u,c,k,True) for w in ('R-005','R-006') for j in range(2) for c,ns in C_COUNTS.items() for u,n in ns.items() for k in range(n)]
        result=experiment_C(new,old,mats,mats)
        self.assertTrue(result['empirical_pass']['A_comb']);self.assertTrue(result['empirical_pass']['B1'])
        self.assertFalse(result['empirical_pass']['A_unc'])
        self.assertEqual(result['acceptance']['A_comb']['F-D_confident']['point'],0)
        fd=[h for h in result['tau'] if h['unit']=='F-D' and h['baseline']=='A1']
        self.assertTrue(all(h['tau']==1 for h in fd))
        self.assertEqual(result['split_half_covariance']['B1_R-S']['bounds'],[0,0])
        a=[dict(make(w,j,'R-S','base' if c=='SR' else 'A1',k),condition=c) for w in ('R-005','R-006') for j in range(2) for c in ('SR','U_last') for k in range(8)]
        ar=experiment_A(a,old,mats,mats)
        self.assertEqual(ar['U_last_minus_SR']['work_equal']['point'],-1)

if __name__=='__main__':unittest.main()
