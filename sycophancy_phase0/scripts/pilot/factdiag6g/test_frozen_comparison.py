import unittest
import numpy as np
from frozen_comparison import collapse_design,aggregate_scores,predict,log_scores
from fit_prediction import design_fit,design_apply,predict as probability_predict,observation_weights
from joint_model import JointModel,observed_mask,log_scores as probability_scores
from features import FEATURE_NAMES


class FrozenComparison(unittest.TestCase):
    def test_compression_preserves_objective_gradient_and_weight(self):
        X=np.array([[1,2],[1,2],[1,2],[1,3],[1,3]],dtype=float)
        y=np.array([[0,1,2],[0,1,2],[0,-1,2],[-1,-1,-1],[2,0,3]])
        w=np.array([.1,.2,.15,.05,.5]);gate=np.array([[1,0],[1,0],[1,0],[1,1],[1,1]],dtype=float)
        for g in (None,gate):
            m=JointModel(2,0 if g is None else 2)
            theta=np.random.default_rng(1).normal(0,.2,m.n)
            a=m.loss_gradient(theta,X,observed_mask(y),w,.01,g)
            cx,cy,cw,cg=collapse_design(X,y,w,g)
            b=m.loss_gradient(theta,cx,observed_mask(cy),cw,.01,cg)
            self.assertAlmostEqual(sum(cw),sum(w),places=14)
            self.assertAlmostEqual(a[0],b[0],places=14)
            np.testing.assert_allclose(a[1],b[1],rtol=1e-12,atol=1e-14)

    def test_hierarchical_weight_and_pair_bootstrap(self):
        rows=[dict(project_id='a',cluster_id='pair',history_id='a1',candidate_type='d',arm='base'),
              dict(project_id='a',cluster_id='pair',history_id='a2',candidate_type='d',arm='base'),
              dict(project_id='b',cluster_id='pair',history_id='b1',candidate_type='d',arm='base')]
        r=aggregate_scores(rows,[1,1,0])
        self.assertEqual(r['project_equal']['point'],.5)
        self.assertEqual(r['history_equal']['point'],2/3)
        self.assertEqual(r['clusters'],1)
        self.assertEqual(r['project_equal']['ci95'],[.5,.5])

    def test_unknown_not_zero_score(self):
        rows=[dict(project_id='a',cluster_id='a',history_id='a',candidate_type='d',arm='base')]*2
        r=aggregate_scores(rows,[np.nan,-2])
        self.assertEqual(r['observations'],1)
        self.assertEqual(r['project_equal']['point'],-2)

    def test_log_domain_matches_regular_and_extreme_is_finite(self):
        rows=[dict(feature_values={k:(float(i) if k=='s' else 0.) for k in FEATURE_NAMES},
            arm='base' if i==0 else 'A1',labels=[i,0,1],project_id=str(i),cluster_id=str(i),
            history_id=str(i),candidate_type='d') for i in range(2)]
        for kind in ('A_prime','B'):
            design=design_fit(rows,kind);X,g=design_apply(rows,design)
            model=JointModel(X.shape[1],g.shape[1] if g is not None else 0)
            fitted=dict(design=design,fit=dict(theta=np.random.default_rng(2).normal(0,.2,model.n).tolist()))
            expected=probability_scores(probability_predict(rows,fitted),[r['labels'] for r in rows])
            actual=log_scores(predict(rows,fitted),[r['labels'] for r in rows])
            for k in expected:np.testing.assert_allclose(actual[k],expected[k],rtol=1e-13,atol=1e-13)
            extreme=[dict(rows[0],feature_values=dict(rows[0]['feature_values'],s=1e8))]
            self.assertTrue(np.all(np.isfinite(predict(extreme,fitted))))
            self.assertTrue(np.isfinite(log_scores(predict(extreme,fitted),[[0,0,1]])['joint'][0]))

    def test_actual_observation_weights_preserved(self):
        rows=[dict(project_id='a' if i<3 else 'b',history_id='a' if i<3 else 'b',
            candidate_type='d',arm='base',labels=[0,0,1]) for i in range(4)]
        weights=observation_weights(rows)
        X=np.array([[1,0],[1,0],[1,0],[1,1]])
        _,_,summed,_=collapse_design(X,[r['labels'] for r in rows],weights)
        np.testing.assert_allclose(summed,[.5,.5])


if __name__=='__main__':unittest.main()
