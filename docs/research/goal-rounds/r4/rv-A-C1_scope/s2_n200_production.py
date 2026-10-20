"""Realised width at the DESIGN (n=200, m=128, degree 2) from the production function, for the g's behind A-C1's verdicts."""
import sys, glob, json, time
import numpy as np
R4 = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4"
sys.path.insert(0, glob.glob(R4 + "/A__*")[0])
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
from route_a_lib import first_order, beta_moments, sup_quadratic_over_bounded_g
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs
Z = 1.959963984540054
n_t, n_arm, m, n = 100, 16, 128, 200
narrow = ((20, 80), (25, 75))
mu0, mu1 = beta_moments(*narrow[0]), beta_moments(*narrow[1])
sup_full = first_order(mu0, mu1, 0.5, m, n, sup_g=True)
Om = np.array(sup_full["Omega"])
_, b_c2 = sup_quadratic_over_bounded_g(Om, coef_bound=2.0)
_, b_full = sup_quadratic_over_bounded_g(Om)
def centre_b0(b1, b2):
    # choose b0 so that g is centred on [0,1]: max+min = 0
    rs = [0.0, 1.0] + ([-b1 / (2 * b2)] if b2 != 0 and 0 < -b1 / (2 * b2) < 1 else [])
    v = [b1 * r + b2 * r * r for r in rs]
    return -(max(v) + min(v)) / 2
g_c2 = (centre_b0(*b_c2), float(b_c2[0]), float(b_c2[1]))
g_full = (centre_b0(*b_full), float(b_full[0]), float(b_full[1]))
print("c2 maximiser g =", g_c2, " full maximiser g =", g_full)

def run(g, tau=0.0, layout="A", reps=2000, seed=11, sigma_mode="sym"):
    rng = np.random.default_rng(seed)
    fo = first_order(mu0, mu1, 0.5, m, n, beta=g) if sigma_mode == "sym" else first_order(mu0, mu1, 0.5, m, n, beta=g, sigma2=[1 / 32])
    w1 = fo["width1"]
    res = {"HC1": [], "CR1": []}; npd = 0; clip = []
    for _ in range(reps):
        t = np.repeat([0, 1], n_t)
        r = np.concatenate([rng.beta(*narrow[0], n_t), rng.beta(*narrow[1], n_t)])
        delta = g[0] + g[1] * r + g[2] * r ** 2
        if layout == "A":   # shared questions: 2 type-0 + 2 type-1 per question
            q = np.concatenate([np.repeat(np.arange(50), 2), np.repeat(np.arange(50), 2)])
        else:               # disjoint: 4 prefixes of one type per question
            q = np.concatenate([np.repeat(np.arange(25), 4), np.repeat(25 + np.arange(25), 4)])
        aq = rng.normal(0, tau, 50)[q] if tau > 0 else 0.0
        if sigma_mode == "sym":
            qp, qm = np.clip(r + (delta + aq) / 2, 0, 1), np.clip(r - (delta + aq) / 2, 0, 1)
        else:               # arms centred at 1/2: sigma2 = (1-g^2)/32, the plan-supported bound
            qp, qm = np.clip(0.5 + (delta + aq) / 2, 0, 1), np.clip(0.5 - (delta + aq) / 2, 0, 1)
        clip.append(np.mean((r + delta / 2 > 1) | (r - delta / 2 < 0)))
        dhat = rng.binomial(n_arm, qp) / n_arm - rng.binomial(n_arm, qm) / n_arm
        K = rng.binomial(m, r)
        for lab, cl in (("HC1", None), ("CR1", q)):
            o = endpoint_contrast_poly_cs(dhat, K, m, t, degree=2, cluster=cl)
            if o["ok"]:
                res[lab].append(2 * Z * o["se"][-1])
            else:
                res[lab].append(np.inf)
                if lab == "HC1": npd += 1
    out = dict(w1=w1, clip=float(np.mean(clip)), non_pd=npd / reps)
    for lab in ("HC1", "CR1"):
        a = np.array(res[lab])
        out[lab] = dict(q50=float(np.quantile(a, .5)), q90=float(np.quantile(a, .9)), ratio_q50=float(np.quantile(a, .5) / w1), ratio_q90=float(np.quantile(a, .9) / w1),
                        frac_gt_015=float(np.mean(a > 0.15)))
    return out
cases = [("linear g (author)", dict(g=(0.18, -0.8, 0.0))),
         ("c2 maximiser", dict(g=g_c2)),
         ("full-class maximiser", dict(g=g_full)),
         ("linear g, sigma2=(1-g^2)/32 arms at 1/2", dict(g=(0.18, -0.8, 0.0), sigma_mode="half")),
         ("c2 maximiser, arms at 1/2", dict(g=g_c2, sigma_mode="half")),
         ("linear g, question effect tau=.05, shared layout", dict(g=(0.18, -0.8, 0.0), tau=0.05, layout="A")),
         ("linear g, question effect tau=.05, disjoint layout", dict(g=(0.18, -0.8, 0.0), tau=0.05, layout="B")),
         ("linear g, question effect tau=.10, disjoint layout", dict(g=(0.18, -0.8, 0.0), tau=0.10, layout="B"))]
allout = {}
t0 = time.time()
for name, kw in cases:
    o = run(**kw); allout[name] = o
    print("%-55s w1=%.4f clip=%.3f nonPD=%.3f | HC1 q50=%.4f q90=%.4f (x%.2f) P(w>.15)=%.2f | CR1 q50=%.4f q90=%.4f (x%.2f) P(w>.15)=%.2f  [%.0fs]"
          % (name, o["w1"], o["clip"], o["non_pd"], o["HC1"]["q50"], o["HC1"]["q90"], o["HC1"]["ratio_q90"], o["HC1"]["frac_gt_015"],
             o["CR1"]["q50"], o["CR1"]["q90"], o["CR1"]["ratio_q90"], o["CR1"]["frac_gt_015"], time.time() - t0), flush=True)
json.dump(allout, open(R4 + "/review_A-C1_scope/s2_n200_production.json", "w"), indent=1)
