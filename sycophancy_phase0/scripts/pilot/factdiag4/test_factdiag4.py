import unittest
from common import *

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

if __name__=='__main__':unittest.main()
