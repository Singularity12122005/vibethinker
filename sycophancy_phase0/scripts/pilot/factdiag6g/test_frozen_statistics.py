import unittest
import numpy as np
from frozen_statistics import sigmoid_fit,regression_weights,history_intervals,prediction_checks,EVENTS


class FrozenStatistics(unittest.TestCase):
    def test_zero_event_unestimable(self):
        r=sigmoid_fit(np.array([[1,0],[1,1]],float),np.zeros(2),np.ones(2)/2)
        self.assertEqual(r['status'],'不可估')
        self.assertNotIn('beta',r)

    def test_quasi_separation_unestimable(self):
        X=np.array([[1,0],[1,0],[1,1],[1,1]],float)
        r=sigmoid_fit(X,np.array([0,0,0,1]),np.ones(4)/4)
        self.assertEqual(r['status'],'不可估')
        self.assertIn('分离',r['reason'])

    def test_finite_balanced_fit(self):
        X=np.array([[1,0],[1,0],[1,1],[1,1]],float)
        r=sigmoid_fit(X,np.array([0,1,0,1]),np.ones(4)/4)
        self.assertEqual(r['status'],'可估')
        np.testing.assert_allclose(r['beta'],[0,0],atol=1e-6)

    def test_regression_weights_and_cluster_repeat(self):
        rows=[dict(work_id=w,history_id=h,candidate_type='d',arm='S') for w,h in [('a','h1'),('a','h2'),('b','h3')]]
        np.testing.assert_allclose(regression_weights(rows),[.25,.25,.5])
        np.testing.assert_allclose(regression_weights(rows,{'a':2,'b':1}),[1/3,1/3,1/3])

    def test_zero_event_not_validation_and_no_degenerate_interval(self):
        rows=[dict(work_id=w,cluster_id=w,history_id=w,candidate_type='C',arm='S',
            structure='G1',path='correct',feature_values={'exposed':0},**{k:0 for k in EVENTS}) for w in ('a','b')]
        intervals=history_intervals(rows)
        self.assertIsNone(intervals['tables'][0]['metrics']['adopt']['point']['ci95'])
        checks=prediction_checks(rows,{},dict(frozen=dict(screen_states={})))['checks']
        check=next(c for c in checks if c['prediction']=='G1_all_M_S_C')
        self.assertEqual(check['numerical_status'],'通过')
        self.assertEqual(check['status'],'未定')
        self.assertTrue(check['zero_event'])


if __name__=='__main__':unittest.main()
