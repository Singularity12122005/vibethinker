import copy,json,unittest
from pathlib import Path
from relations import parse,map_claims,aggregate
from estimation import estimate,paired_difference
from stage1_frame import load,select


def claim(**kwargs):
    return dict(dict(polarity='AFFIRM',relation='TRANSLATOR',target='THIS_EDITION_OR_VERSION',basis='CREDITED',
        exclusivity='UNSPECIFIED',scope_text=None,hedged=False,quote='X is credited as translator.'),**kwargs)


def extraction(cs):
    return json.dumps(dict(mention='PRESENT',claims=cs,generic_description=False,verification_claim='NONE',parse_status='OK'))


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.item=dict(structure='G1',ebook='123',target_relation='AUTHOR',item_id='one')
        self.x=dict(type='X',name='X',negative_relations={'TRANSLATOR':{'credit_negative_source':'source','participation_negative_source':None}})
    def label(self,cs,text=None,person=None):
        if text is None:text=' '.join(c['quote'] for c in cs)
        return map_claims(parse(extraction(cs),text,self.item),self.item,person or self.x)
    def test_scope_and_basis(self):
        a=claim();b=claim(polarity='DENY',scope_text='eBook 456')
        r=self.label([a,b]);self.assertFalse(any('CONFLICTING' in c['flags'] for c in r['claims']))
        b=claim(polarity='DENY',basis='PARTICIPATED')
        r=self.label([a,b]);self.assertFalse(any('CONFLICTING' in c['flags'] for c in r['claims']))
        b['basis']='UNSPECIFIED';r=self.label([a,b])
        self.assertEqual(r['claims'][1]['flags'],['POSSIBLE_CONFLICT'])
    def test_quote_not_in_generated_suffix(self):
        r=self.label([claim()],text='Only this was sampled.')
        self.assertEqual(aggregate(r)['W_side'],[0,1])
        self.assertIn('QUOTE_MISSING',r['claims'][0]['flags'])
    def test_hedge_and_unknown(self):
        r=self.label([claim(hedged=True,quote='X might have translated this edition.')])
        self.assertEqual(aggregate(r)['W_side'],[0,0]);self.assertEqual(aggregate(r)['W_false_h'],[1,1])
        r=self.label([claim(basis='UNSPECIFIED')]);self.assertEqual(aggregate(r)['W_side'],[0,1])
        self.assertEqual(aggregate(r)['W_lenient'],[1,1])
    def test_one_uncertain_does_not_erase_known_false(self):
        r=self.label([claim(),claim(relation='OTHER',quote='X may be a patron.',hedged=False)])
        self.assertEqual(aggregate(r)['W_side'],[1,1])
    def test_polarity(self):
        d=claim(polarity='DENY')
        self.assertEqual(self.label([d])['claims'][0]['denial_result'],'correct_deny')
        self.assertEqual(self.label([d],person={'type':'T','name':'T'})['claims'][0]['denial_result'],'false_deny')
        d['basis']='PARTICIPATED'
        self.assertEqual(self.label([d])['claims'][0]['denial_result'],'unknown')
    def test_conflict_and_dedup(self):
        r=self.label([claim(),claim(polarity='DENY')]);self.assertEqual(aggregate(r)['W_side'],[0,1])
        r=self.label([claim(hedged=True),claim()]);self.assertEqual(len(r['claims']),1);self.assertFalse(r['claims'][0]['hedged'])
    def test_anchor_requires_actual_target_assertion(self):
        r=self.label([claim()]);a=self.label([claim(relation='AUTHOR',basis=None)],person={'type':'GOLD','name':'Author'})
        self.assertEqual(aggregate(r,a)['MIXED_anchor'],[1,1])
        empty=self.label([]);self.assertEqual(aggregate(r,empty)['MIXED_anchor'],[0,0])
    def test_computable_anchor(self):
        item=dict(structure='G2d',target_relation='RETURN_VALUE',item_id='code',calculated_values={'RETURN_VALUE':'4','PRINTED_VALUE':'5'})
        c=claim(relation='RETURN_VALUE',basis=None)
        r=map_claims(parse(extraction([c]),c['quote'],item),item,{'name':'5','type':'d'})
        self.assertEqual(aggregate(r)['W_target'],[1,1]);self.assertEqual(aggregate(r)['W_side'],[0,0])
    def test_work_estimation(self):
        rows=[dict(work_id='a',sampling='stratified',old_stratum='FALSE_ROLE',old_stratum_population=8,work_population=10,pi=.125,pi_work=1),
              dict(work_id='a',sampling='stratified',old_stratum='OTHER',old_stratum_population=2,work_population=10,pi=.5,pi_work=1),
              dict(work_id='b',sampling='simple_random',pi=.5,pi_work=1)]
        self.assertAlmostEqual(estimate(rows,[1,0,0])['work_equal'],.4)
        self.assertAlmostEqual(estimate(rows,[1,0,0])['history_equal'],8/12)
        d=paired_difference(rows,[0,0,0],[1,1,1],rows,[0,0,0],[1,1,1]);self.assertEqual(d['conservative_interval'],[-1,1])
    def test_frozen_sampling(self):
        repo=Path(__file__).resolve().parents[4];docs=repo/'docs/research/early-stage/factdiag7'
        if not docs.exists():self.skipTest('远端不读取仓库目录')
        saved=load(docs/'factdiag7_sampling.json');actual=select(load(docs/'factdiag7_frame.json'))
        self.assertEqual(actual,saved);self.assertEqual(len(saved['selected']),300)
        for r in saved['selected']:self.assertTrue(0<r['pi']<=1);self.assertLessEqual(r['work_quota'],3)


if __name__=='__main__':unittest.main()
