"""Physical clipped model at boundary g's in the wide world: empirical sd of sqrt(n) b_hat (own CS estimator) and bias, vs claimed sup."""
import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_")
from route_a_lib import beta_moments, first_order
sys.path.insert(0, ".")
from s1_indep_mc import cs_estimate
ab0, ab1 = (2, 8), (2.5, 7.5)
mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
rng = np.random.default_rng(99)
n, reps = 4000, 800
for m in (128,):
    fo = first_order(mu0, mu1, 0.5, m, n, sup_g=True)
    sup_sqrtn_se = np.sqrt(fo["Ephi2"]) / fo["D"]
    print(f"m={m}: claimed sup sqrt(n) se = {sup_sqrtn_se:.4f} (width@200 {fo['width1']:.4f})")
    for G in ((1.0, -8.0, 8.0), (1.0, -2.0, 0.0), (-1.0, 2.0, 0.0), (0.0, 0.0, 0.0), (0.18, -0.8, 0.0)):
        fo_g = first_order(mu0, mu1, 0.5, m, n, beta=G)  # no-clipping formula at this g (may be invalid)
        bs = []; clip = []
        for _ in range(reps):
            t = np.repeat([0.0, 1.0], n // 2)
            r = np.concatenate([rng.beta(*ab0, n // 2), rng.beta(*ab1, n // 2)])
            d = G[0] + G[1] * r + G[2] * r ** 2
            qp, qm = r + d / 2, r - d / 2
            clip.append(np.mean((qp > 1) | (qm < 0)))
            y = rng.binomial(16, np.clip(qp, 0, 1)) / 16 - rng.binomial(16, np.clip(qm, 0, 1)) / 16
            K = rng.binomial(m, r)
            b, se = cs_estimate(y, K, m, t)
            bs.append(b[3])
        bs = np.array(bs)
        sd = np.sqrt(n) * bs.std(ddof=1)
        print(f"  g={G}: clip={np.mean(clip):.3f}  empirical sqrt(n) sd = {sd:.4f} (+-{sd/np.sqrt(2*reps):.4f})  [no-clip formula {np.sqrt(fo_g['Ephi2'])/fo_g['D']:.4f}]  ratio to claimed sup = {sd/sup_sqrtn_se:.3f}   plim bias of b_type = {bs.mean():+.4f} (+-{bs.std(ddof=1)/np.sqrt(reps):.4f})", flush=True)
