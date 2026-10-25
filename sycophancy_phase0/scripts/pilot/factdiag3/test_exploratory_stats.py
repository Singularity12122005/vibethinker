from itertools import product
import unittest
import numpy as np

from exploratory_stats import cov, cov_bounds, risk_gain_bounds, rate, assignment_history


class ExploratoryStatsTests(unittest.TestCase):
    def test_covariance_bounds_equal_exhaustive(self):
        x=[[-.5,.5],[0,1],[.25,.25]]; y=[[0,1],[-.5,0],[.1,.7]]
        values=[cov(a,b) for a in product(*x) for b in product(*y)]
        np.testing.assert_allclose(cov_bounds(x,y),[min(values),max(values)])

    def test_risk_gain_bounds_keep_shared_coordinates(self):
        bounds=[[[0,.5],[.25,1]],[[0,1],[0,.25]],[[0,.75],[.5,1]],[[0,.25],[.25,.75]]]
        values=[]
        for bo,ao,be,ae in product(*(list(product(*b)) for b in bounds)):
            values.append(.5*(cov(bo,np.array(be)-ae)+cov(be,np.array(bo)-ao)))
        np.testing.assert_allclose(risk_gain_bounds(*bounds),[min(values),max(values)])

    def test_crossfit_does_not_choose_and_evaluate_same_half(self):
        # 奇数半偏爱A1、偶数半偏爱基线，独立评估损失为1；同数据取优为.5。
        h=dict(work_id='x',idx=0,unit='F-D')
        h['base']=dict(odd=rate([1,1]),even=rate([0,0]),full=rate([1,1,0,0]))
        h['A1']=dict(odd=rate([0,0]),even=rate([1,1]),full=rate([0,0,1,1]))
        r=assignment_history(h)
        self.assertEqual(r['crossfit']['point'],1)
        self.assertEqual(r['plugin']['point'],.5)
        self.assertEqual(r['crossfit_application']['point'],.5)

    def test_missing_can_change_assignment(self):
        h=dict(work_id='x',idx=0,unit='R-S')
        h['base']=dict(odd=rate([None]),even=rate([1]),full=rate([None,1]))
        h['A1']=dict(odd=rate([0]),even=rate([0]),full=rate([0,0]))
        r=assignment_history(h)
        self.assertIsNone(r['crossfit']['point'])
        self.assertEqual(r['crossfit']['bounds'],[0,.5])
        self.assertEqual(r['crossfit_application']['bounds'],[.5,1])


if __name__=='__main__':unittest.main()
