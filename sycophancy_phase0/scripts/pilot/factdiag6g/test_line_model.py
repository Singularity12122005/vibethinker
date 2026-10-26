import unittest
import numpy as np
from line_model import fit, ll, SPEC, refit_simulation
from concurrent.futures import ProcessPoolExecutor


class LineModelTests(unittest.TestCase):
    def test_joint_line_and_nested_likelihood(self):
        counts=np.array([[[8,0,0],[4,4,0],[0,8,0],[2,6,0],[6,2,0]],
                         [[0,0,8],[4,0,4],[8,0,0],[6,0,2],[2,0,6]]])
        model=fit(counts,['a','a'])
        self.assertTrue(np.all(model['loss_by_history']>=0))
        self.assertTrue(np.allclose(model['prob'].sum(axis=-1),1))
        for p in model['prob']:
            self.assertLessEqual(np.linalg.matrix_rank(p-p[0],tol=1e-8),1)

    def test_empty_training_cells_finite_predictions(self):
        counts=np.array([[[0,0,0],[0,0,0],[0,0,0]],[[0,0,1],[0,0,1],[0,0,1]]])
        model=fit(counts,['a','a'])
        self.assertTrue(np.isfinite(ll(np.ones_like(counts),model['prob'])).all())
        self.assertTrue(np.isfinite(ll(np.ones_like(counts),model['unrestricted_holdout'])).all())

    def test_parallel_schedule_preserves_results(self):
        rng=np.random.default_rng(21)
        jobs=[(rng.multinomial(4,[.2,.3,.5],size=(2,5)),['a','a']) for _ in range(3)]
        serial=list(map(refit_simulation,jobs))
        with ProcessPoolExecutor(max_workers=2) as pool:
            parallel=list(pool.map(refit_simulation,jobs))
        self.assertEqual(serial,parallel)


if __name__=='__main__':
    unittest.main()
