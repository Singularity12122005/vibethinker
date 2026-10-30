import math
import unittest
import numpy as np
from scipy.optimize._numdiff import approx_derivative
from scipy.stats import spearmanr
from .directive10_statistics import rank_correlation,fit_firth,firth_design,firth_objective,group_difference,safe_logit

def row(w,k0,k1,n=4):return dict(work_id=w,n0=n,n1=n,k0=k0,k1=k1)

class Directive10Tests(unittest.TestCase):
    def test_spearman_ties(self):
        rr=[dict(work_id=str(i),r1=x,y=y) for i,(x,y) in enumerate(zip([0,0,1,1,1],[.2,.3,.3,.9,.5]))]
        self.assertAlmostEqual(rank_correlation(rr,'r1','history_equal'),spearmanr([r['r1'] for r in rr],[r['y'] for r in rr]).statistic)
    def test_constant_is_undefined(self):
        rr=[dict(work_id=str(i),r1=1,y=i) for i in range(3)]
        self.assertIsNone(rank_correlation(rr,'r1','work_equal'));self.assertIsNone(group_difference(rr,'work_equal'))
    def test_saturated_firth(self):
        r=fit_firth([row('a',4,0)],interval=False)
        self.assertAlmostEqual(r['delta'],2*math.log(9),places=6)
    def test_firth_score(self):
        X,k,n=firth_design([row('a',3,1),row('b',2,0)],'history_equal');b=np.array([.4,-.2,-.7])
        num=approx_derivative(lambda x:firth_objective(x,X,k,n)[0],b).ravel()
        self.assertTrue(np.allclose(num,firth_objective(b,X,k,n)[1],atol=1e-6))
    def test_arm_swap(self):
        a=fit_firth([row('a',3,1),row('b',4,0)],interval=False)
        b=fit_firth([row('a',1,3),row('b',0,4)],interval=False)
        self.assertAlmostEqual(a['delta'],-b['delta'],places=6)
    def test_endpoint_logit(self):
        self.assertEqual(safe_logit(0),-math.inf);self.assertEqual(safe_logit(1),math.inf)
        self.assertEqual(safe_logit(.5),0)

if __name__=='__main__':unittest.main()
