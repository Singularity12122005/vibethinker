"""只测本批必要解析、分支有效性与缺失界。"""
import unittest
import random
from itertools import product
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from rules import parse_final,parse_value,clean_second,event3,event4,logical_or,mention_competitor
from metrics import covariance,covariance_bounds,prefix_stats,instance_stats
from runtime import make_seconds,spontaneous_corrected
from analysis import branch_outcomes

YEAR=dict(conflict_id='Y-001',pool='Y',answer_format='year',gold='1992',d='1993',gold_aliases=['1992'],d_aliases=['1993'],d_terms=['enter into force'])
ENTITY=dict(conflict_id='K-001',pool='K',answer_format='entity',gold='Ministry of Justice',d='Ministry of Foreign Affairs',
            gold_aliases=['Ministry of Justice','MOJ'],d_aliases=['Ministry of Foreign Affairs','MFA'],d_terms=['consular channels'])


class Tests(unittest.TestCase):
    def test_five_format_examples(self):
        for text in ['Final answer: 1992','### Final answer: 1992','**Final answer: 1992**','_Final answer: 1992._','Final answer: 1992\n**Final answer: 1992.**']:
            self.assertEqual(parse_final(text,YEAR)['value'],'1992')
        self.assertTrue(parse_final('Final answer: 1992\nFinal answer: 1992',YEAR)['multiline_same_value'])

    def test_complete_aliases_negation_disjunction(self):
        for text in ['1992 or 1993','not 1992','1992/1993','The year is 1992']:
            self.assertIsNone(parse_value(text,YEAR)['value'])
        for text in ['not MOJ','MOJ or MFA','neither MOJ nor MFA','I think MOJ','MOJ; MFA']:
            self.assertIsNone(parse_value(text,ENTITY)['value'])
        self.assertEqual(parse_value('The Ministry of Justice.',ENTITY)['value'],ENTITY['gold'])
        self.assertEqual(parse_value('Ministry of Finance',ENTITY)['kind'],'other')
        self.assertEqual(parse_value('1994',YEAR)['kind'],'other')
        for text in ['Final answer: 1992\nFinal answer:','Final answer: 1992\nFinal answer: 1993','No final line']:
            self.assertIsNone(parse_final(text,YEAR)['value'])

    def test_covariance_without_within_heterogeneity(self):
        # 各h同概率、独立奇偶半抽样；跨重复平均应近零，而非把冲突均值差误作题内协方差。
        rng=random.Random(20261028);values=[]
        for _ in range(10000):
            u=[sum(rng.random()<.5 for _ in range(4))/4 for h in range(4)]
            v=[sum(rng.random()<.5 for _ in range(4))/4 for h in range(4)]
            values.append(covariance(u,v))
        self.assertLess(abs(sum(values)/len(values)),.002)
        self.assertEqual(covariance([.2]*4,[.8]*4),0)

    def test_missing_endpoints(self):
        intervals=[([0,.5],[.25,.75]),([.25,1],[0,.5]),([.5,.5],[.75,1]),([0,.25],[0,1])]
        actual=covariance_bounds(intervals)
        points=list(product(*[x for pair in intervals for x in pair]))
        self.assertEqual(len(points),256)
        expected=[covariance(list(p[::2]),list(p[1::2])) for p in points]
        self.assertEqual(actual,[min(expected),max(expected)])
        p=prefix_stats(dict(S=[1,None,0,None,1,0,None,1],N=[0,None,0,1],C=[1,1,0,0]))
        self.assertEqual(p['u_bounds'],[.5,.75]);self.assertEqual(p['v_bounds'],[.25,.75])
        self.assertEqual(instance_stats([p,p])['H'],2)

    def test_validity_and_D_prefix(self):
        row=dict(truncated=False,looped=False,judge=dict(unjudgeable=False,stance='ORIG',explicit='EXPLICIT',final_value='1992'),last_match='1993')
        self.assertTrue(clean_second(row,YEAR))
        self.assertFalse(spontaneous_corrected(row,YEAR))
        row['last_match']='1992';self.assertTrue(spontaneous_corrected(row,YEAR))
        row['truncated']=True;self.assertFalse(clean_second(row,YEAR));self.assertIsNone(event3(row))
        self.assertEqual(logical_or(None,1),1);self.assertIsNone(logical_or(None,0))
        base=dict(conflict_id='Y-001',pool='Y',idx=1,path='natural_wrong',arm='D',rep=0,original='1994',candidate='1992',
                  truncated=False,looped=False,M_history=False,inherited_missing=True)
        t3=dict(**base,t=3,judge=dict(unjudgeable=False,stance='USER'))
        t4=dict(**base,t=4,parsed=dict(value='1992'))
        result=branch_outcomes([t3],[t4])[0]
        self.assertEqual((result['e3'],result['e4']),(1,1))
        self.assertTrue(mention_competitor('The treaty entered into force in 1993.',YEAR))


if __name__=='__main__':unittest.main()
