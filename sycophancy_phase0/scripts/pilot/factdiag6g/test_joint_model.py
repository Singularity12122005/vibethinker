import unittest
import numpy as np
from joint_model import JointModel,observed_mask,log_scores


class Tests(unittest.TestCase):
    def test_joint_probability_and_missing_marginal(self):
        model=JointModel(2,2);X=np.array([[1,.3],[1,-.2]])
        theta=np.linspace(-.1,.1,model.n)
        p=model.distribution(theta,X,X)
        self.assertTrue(np.allclose(p.sum(axis=(1,2,3)),1))
        mask=observed_mask([[1,-1,-1],[-1,-1,-1]])
        self.assertAlmostEqual((p*mask).sum(axis=(1,2,3))[0],p[0,1].sum())
        self.assertTrue(np.isnan(log_scores(p,[[1,-1,-1],[-1,-1,-1]])['joint'][1]))

    def test_analytic_gradient_for_shared_mixture_and_chain(self):
        rng=np.random.default_rng(9);X=np.column_stack([np.ones(5),rng.normal(size=(5,2))])
        gate=np.column_stack([np.ones(5),rng.normal(size=5)])
        mask=observed_mask([[0,1,2],[2,-1,0],[-1,3,1],[1,2,-1],[3,4,3]])
        for gated in (False,True):
            model=JointModel(3,2 if gated else 0);theta=rng.normal(0,.1,model.n)
            args=(X,mask,np.full(5,.2),.01,gate if gated else None)
            _,gradient=model.loss_gradient(theta,*args)
            for j in rng.choice(model.n,16,replace=False):
                step=np.zeros(model.n);step[j]=1e-6
                numeric=(model.loss_gradient(theta+step,*args)[0]-model.loss_gradient(theta-step,*args)[0])/2e-6
                self.assertAlmostEqual(gradient[j],numeric,places=6)

    def test_intervention_only_changes_mixture_weight(self):
        model=JointModel(1,2);X=np.ones((2,1));gate=np.array([[1,0],[1,1]])
        theta=np.zeros(model.n);theta[-1]=2
        theta[0]=2;theta[model.chain.n+1]=2
        p,chains,_=model.distribution(theta,X,gate,parts=True)
        self.assertTrue(np.allclose(chains[0][0][0],chains[0][0][1]))
        self.assertTrue(np.allclose(chains[1][0][0],chains[1][0][1]))
        self.assertFalse(np.allclose(p[0],p[1]))


if __name__=='__main__':unittest.main()
