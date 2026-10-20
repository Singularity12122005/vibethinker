"""r4 route B, claim B2 (exact part): the PD event of endpoint_contrast_poly_cs is a function of (K, t, m, degree) only.
Check: for 300 draws of (r, t, K) in F_b at m=128, run the production function with 10 different g's, 3 eta variances
(16-draw arms, 32-draw arms, eta = 0) and both SEs; assert that ok and min_eig are bit-identical across all of them.
Also pools the b2 cells: non-PD over the 10 g-cells of F_b|m=128 (20000 reps) with an exact Clopper-Pearson interval.
Environment tag: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19.  Scratch only."""
import json, sys
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from scipy import stats
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

HERE = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/B__Le_Cam_two-point_impossibility_for_the_32-pilot_and_explicit_failing_worlds_inside_the_compatible_set__lower_bound__necessity_direction_"
sys.path.insert(0, HERE); sys.path.insert(1, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/docs/research/goal-rounds/r4/B")
import b2_failing_worlds_gclass as b2

rng = np.random.default_rng(31337)
t = np.repeat([0, 1], 100)
q = np.concatenate([np.repeat(np.arange(50), 2)] * 2)
n_draw, n_nonpd, n_checks = 300, 0, 0
for _ in range(n_draw):
    r = np.concatenate([b2.draw_r(rng, b2.WORLDS["F_b"], 0), b2.draw_r(rng, b2.WORLDS["F_b"], 1)])
    K = rng.binomial(128, r)
    ref = None
    for (c0, b1, b2c) in b2.G_GRID.values():
        g = c0 + b1 * r + b2c * r * r
        for n_arm in (16, 32, None):
            if n_arm is None:
                y = g
            else:
                y = rng.binomial(n_arm, np.clip(r + g / 2, 0, 1)) / n_arm - rng.binomial(n_arm, np.clip(r - g / 2, 0, 1)) / n_arm
            for cl in (None, q):
                res = endpoint_contrast_poly_cs(y, K, 128, t, degree=2, cluster=cl)
                key = (res["ok"], res["min_eig"])
                if ref is None:
                    ref = key
                assert key == ref, (key, ref)
                n_checks += 1
    n_nonpd += (not ref[0])
print(f"PD event identical across 10 g x 3 eta-variances x 2 SEs in all {n_draw} draws ({n_checks} production calls); non-PD in {n_nonpd}/{n_draw}")


print(len(b2.G_GRID), b2.WORLDS['F_b'], b2.__file__)
