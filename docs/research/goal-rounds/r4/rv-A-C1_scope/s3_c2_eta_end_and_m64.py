import sys, glob, json, time
import numpy as np
R4 = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4"
sys.path.insert(0, glob.glob(R4 + "/A__*")[0]); sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
from route_a_lib import first_order, beta_moments
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs
Z = 1.959963984540054; n_t, n_arm, n = 100, 16, 200
worlds = {"narrow": ((20, 80), (25, 75)), "halfvar": ((40.5, 162), (50.6, 151.8))}
def run(world, g, m, reps=2000, seed=5):
    ab0, ab1 = worlds[world]; mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
    w1 = first_order(mu0, mu1, 0.5, m, n, beta=g)["width1"]
    rng = np.random.default_rng(seed); ws = []; npd = 0
    for _ in range(reps):
        t = np.repeat([0, 1], n_t); r = np.concatenate([rng.beta(*ab0, n_t), rng.beta(*ab1, n_t)])
        d = g[0] + g[1] * r + g[2] * r ** 2
        qp, qm = np.clip(r + d / 2, 0, 1), np.clip(r - d / 2, 0, 1)
        dhat = rng.binomial(n_arm, qp) / n_arm - rng.binomial(n_arm, qm) / n_arm
        o = endpoint_contrast_poly_cs(dhat, rng.binomial(m, r), m, t, degree=2)
        if o["ok"]: ws.append(2 * Z * o["se"][-1])
        else: ws.append(np.inf); npd += 1
    a = np.array(ws)
    return dict(w1=w1, non_pd=npd / reps, q50=float(np.quantile(a, .5)), q90=float(np.quantile(a, .9)), frac_gt_015=float(np.mean(a > .15)))
cases = [("narrow", "g=0 (eta-term max of c2 class)", (0, 0, 0), 128),
         ("narrow", "g=-2(r-0.2)^2 (c2 edge, eta-dominant)", (-0.08, 0.8, -2.0), 128),
         ("narrow", "g=+2(r-0.2)^2", (0.08, -0.8, 2.0), 128),
         ("narrow", "g=2r-0.4 (c2 edge, beta1=2)", (-0.4, 2.0, 0.0), 128),
         ("narrow", "linear g, m=64 (author's c2 budget)", (0.18, -0.8, 0.0), 64),
         ("narrow", "g=0, m=64", (0, 0, 0), 64),
         ("halfvar", "linear g, m=128 (check1b reproduction)", (0.18, -0.8, 0.0), 128),
         ("halfvar", "g=0, m=128", (0, 0, 0), 128)]
out = {}
for w, name, g, m in cases:
    o = run(w, g, m); out[w + "|" + name] = o
    print("%-8s %-42s m=%3d w1=%.4f nonPD=%.3f q50=%.4f q90=%.4f (x%.2f) P(w>.15)=%.2f" % (w, name, m, o["w1"], o["non_pd"], o["q50"], o["q90"], o["q90"] / o["w1"], o["frac_gt_015"]), flush=True)
json.dump(out, open(R4 + "/review_A-C1_scope/s3_c2_eta_end_and_m64.json", "w"), indent=1)
