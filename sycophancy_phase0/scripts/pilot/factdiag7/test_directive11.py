import unittest,math
from scipy.stats import spearmanr
from .directive11 import *

class Directive11Tests(unittest.TestCase):
    def test_dedup_reuse(self):
        r=dict(generation_id='g',history_reuse_count=3)
        rows,n=deduplicate([r,r.copy()]);self.assertEqual((len(rows),n),(1,1));self.assertEqual(sum(max(0,x['history_reuse_count']-1) for x in rows),2)
    def test_collision(self):
        with self.assertRaises(ValueError):deduplicate([dict(generation_id='g',x=1),dict(generation_id='g',x=2)])
    def test_alias(self):self.assertEqual(canonical('B. Jowett',{'b. jowett':'Benjamin Jowett'},str.lower),'Benjamin Jowett')
    def test_ties_wrong(self):
        rr=[dict(identity=x) for x in ['T','T','X','X']];m=dict(author='A',T='T',dT='D',X='X');d=readings(rr,m,'translator')
        self.assertIsNone(d['c']);self.assertTrue(d['tie_flag']);self.assertEqual(d['w_wrong'],.5);self.assertIsNone(d['legacy_m_wrong'])
    def test_wilson(self):
        self.assertAlmostEqual(wilson(0,10)[1],.2775328,places=6);self.assertEqual(wilson(0,10)[0],0)
    def test_smooth(self):self.assertAlmostEqual(smooth_logit(4,4),math.log(9))
    def test_rank(self):
        x=[0,0,1,1];y=[1,2,2,4];self.assertAlmostEqual(spearman(x,y),spearmanr(x,y).statistic)
    def test_exact(self):
        self.assertAlmostEqual(exact_p([1,2,3],[1,2,3])['p'],1/3);self.assertAlmostEqual(exact_p([0,0,1,1],[0,0,1,1])['p'],1/3)
    def test_boot_undefined(self):
        b=bootstrap_corr([dict(work_id=str(i),x=1,y=i) for i in range(4)],'x','y',50)
        self.assertEqual(b['undefined'],50);self.assertIsNone(b['interval95'])
    def test_verdicts(self):
        self.assertEqual(verdict(.4,[.1,.8]),'作品层支持');self.assertEqual(verdict(.6,[-.2,.9]),'方向一致、样本不足');self.assertEqual(verdict(.2,[-.4,.5]),'不支持');self.assertEqual(verdict(None,None),'不可定义')
    def test_whitelist(self):
        class Guard(dict):
            def __getitem__(self,k):
                if k not in ALLOWED_FIELDS:raise AssertionError('越界')
                return super().__getitem__(k)
        row=Guard(blind_id='x',work_id='w',arm='S',W_side=None,notes='secret')
        self.assertEqual(set(whitelist_projection(row)),ALLOWED_FIELDS)
        with self.assertRaises(ValueError):whitelist_projection(row,['notes'])

if __name__=='__main__':unittest.main()
