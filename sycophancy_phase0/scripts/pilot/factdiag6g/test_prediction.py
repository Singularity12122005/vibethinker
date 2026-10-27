import unittest
import numpy as np

from features import FEATURE_NAMES
from fit_prediction import design_fit,design_apply,observation_weights,fit_one,predict
from joint_data import outcomes


def row(project,history,arm='base',value=0.,labels=None,candidate='T'):
    features={k:None for k in FEATURE_NAMES}
    features.update(s=value,delta_pol=value,exposed=0,role_in_same_sentence=0)
    return dict(project_id=project,history_id=history,arm=arm,candidate_type=candidate,
                feature_values=features,labels=[0,0,0] if labels is None else labels)


class Tests(unittest.TestCase):
    def test_heldout_values_do_not_change_training_scaler(self):
        train=[row('a','1',value=0),row('b','2','A1',value=2)]
        design=design_fit(train,'A_prime')
        test=[row('c','3',value=1000),row('d','4',value=None)]
        X,_=design_apply(test,design)
        self.assertEqual(design['means'][design['names'].index('s')],1)
        self.assertEqual(X[0,1],999)
        self.assertEqual(X[1,1],0)
        self.assertIn('c',design['unestimated'])

    def test_mixture_components_cannot_receive_intervention(self):
        train=[row('a','1','base',0),row('b','2','A1',1)]
        design=design_fit(train,'B')
        test=[row('c','3','base',.5),row('c','3','A1',.5)]
        components,gate=design_apply(test,design)
        self.assertTrue(np.array_equal(components[0],components[1]))
        self.assertFalse(np.array_equal(gate[0],gate[1]))

    def test_a0_cannot_be_fitted(self):
        with self.assertRaisesRegex(RuntimeError,'A0'):
            fit_one([row('a','a','A0')],'B',.01)

    def test_projects_histories_and_conditions_are_equal_not_rows(self):
        rows=[row('a','a1') for _ in range(8)]
        rows += [row('a','a1','A1') for _ in range(4)]
        rows += [row('a','a2') for _ in range(2)]
        rows += [row('b','b1')]
        rows += [row('a','a1',labels=[-1,-1,-1])]
        w=observation_weights(rows)
        self.assertAlmostEqual(sum(w[:12]),.25)
        self.assertAlmostEqual(sum(w[12:14]),.25)
        self.assertAlmostEqual(w[14],.5)
        self.assertEqual(w[15],0)
        self.assertAlmostEqual(sum(w[:8]),sum(w[8:12]))

    def test_fit_learns_known_signal_and_normalizes_joint(self):
        rows=[row(str(i),str(i),value=i%2,labels=[i%2,-1,-1]) for i in range(12)]
        fitted=fit_one(rows,'A_prime',.01)
        p=predict(rows,fitted)
        self.assertTrue(fitted['fit']['converged'])
        self.assertTrue(np.allclose(p.sum(axis=(1,2,3)),1))
        self.assertGreater(p[0,0].sum(),.85)
        self.assertGreater(p[1,1].sum(),.85)

    def test_unknown_role_is_not_false_and_bad_text_masks_all(self):
        item=dict(gold='10',gold_aliases=['10'],answer_format='number',candidates=[])
        candidate=dict(name='12',aliases=['12'],true_roles=['MEDIAN'])
        output=dict(truncated=False,looped=False,last_numeric='12')
        result=outcomes(output,item,candidate,'11','OTHER','AFFIRM',numeric_main=True)
        self.assertEqual(result['labels'],[1,-1,0])
        output['truncated']=True
        result=outcomes(output,item,candidate,'11','MEDIAN','AFFIRM',numeric_main=True)
        self.assertEqual(result['labels'],[-1,-1,-1])

    def test_candidate_equal_to_gold_keeps_priority_and_correctness(self):
        item=dict(gold='10',gold_aliases=['10'],answer_format='number',candidates=[])
        candidate=dict(name='10',aliases=['10'],true_roles=['MEAN'])
        output=dict(truncated=False,looped=False,last_numeric='10')
        result=outcomes(output,item,candidate,'11','MEAN','N/A',numeric_main=True)
        self.assertEqual(result['identity']['category'],'D')
        self.assertEqual(result['identity']['correct'],1)
        self.assertEqual(result['identity']['keep'],0)


if __name__=='__main__':unittest.main()
