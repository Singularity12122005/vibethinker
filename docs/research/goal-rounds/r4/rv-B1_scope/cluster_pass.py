"""Does the 'passing world' F_a still pass at (200,128) when risks are clustered by question (Gaussian copula rho across the
2+2 prefixes of a question, Beta marginals unchanged)?  Production endpoint_contrast_poly_cs, CR1 by question and HC1."""
import sys
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from scipy import stats
from multiprocessing import Pool
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs
N_T, N_ARM, REPS = 100, 16, 1500
W = {"F_a": ((20, 80), (25, 75)), "F_b": ((40.5, 162), (50.6, 151.8))}
G = {"g1": (0.18, -0.8, 0.0), "g4": (-0.2, 1.2, 0.0)}
def cell(args):
    wn, gn, m, rho, seed = args
    rng = np.random.default_rng(seed); (c, b1, b2) = G[gn]
    t = np.repeat([0, 1], N_T); q = np.concatenate([np.repeat(np.arange(N_T // 2), 2)] * 2)
    ok_l, rh_l, rc_l, wh, wc = [], [], [], [], []
    for _ in range(REPS):
        zq = rng.standard_normal(N_T // 2)
        z = np.sqrt(rho) * zq[q] + np.sqrt(1 - rho) * rng.standard_normal(2 * N_T)
        r = np.where(t == 0, stats.beta.ppf(stats.norm.cdf(z), *W[wn][0]), stats.beta.ppf(stats.norm.cdf(z), *W[wn][1]))
        g = c + b1 * r + b2 * r * r
        qp, qm = np.clip(r + g / 2, 0, 1), np.clip(r - g / 2, 0, 1)
        dhat = rng.binomial(N_ARM, qp) / N_ARM - rng.binomial(N_ARM, qm) / N_ARM
        K = rng.binomial(m, r)
        a = endpoint_contrast_poly_cs(dhat, K, m, t, degree=2)
        b = endpoint_contrast_poly_cs(dhat, K, m, t, degree=2, cluster=q)
        ok_l.append(a["ok"])
        if a["ok"]:
            rh_l.append(abs(a["t_type"]) > 1.96); rc_l.append(abs(b["t_type"]) > 1.96)
            wh.append(2 * 1.96 * a["se"][-1]); wc.append(2 * 1.96 * b["se"][-1])
        else:
            rh_l.append(False); rc_l.append(False); wh.append(np.inf); wc.append(np.inf)
    ok = np.array(ok_l)
    return (wn, gn, m, rho, 1 - ok.mean(), np.mean(rh_l), np.mean(rc_l), np.percentile(wh, 90), np.percentile(wc, 90))
if __name__ == "__main__":
    args = []
    i = 0
    for rho in (0.0, 0.3, 0.6):
        for gn in ("g1", "g4"):
            args.append(("F_a", gn, 128, rho, 777 + i)); i += 1
    with Pool(4) as p:
        for res in p.map(cell, args):
            print("%s %s m=%d rho=%.1f nonPD=%.4f sizeHC1=%.4f sizeCR1=%.4f q90wHC1=%.3f q90wCR1=%.3f" % res, flush=True)
