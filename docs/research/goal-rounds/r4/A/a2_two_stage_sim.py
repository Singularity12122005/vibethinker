"""r4 / Route A, claim 2 (simulation part): the SEQUENTIAL design with an INTERNAL pilot.
Per replication: 200 prefixes (100 per type, 50 questions x (2 type-0 + 2 type-1)), r iid Beta per type (no question effect),
eta = difference of two independent 16-draw binomial means with q_± = clip(r ± g(r)/2), K32 ~ Bin(32, r), K128 = K32 + K96
(reuse), K512 = K128 + K384 (reuse), Kfresh128 ~ Bin(128, r) independent.  Null b_type = 0.
  * production endpoint_contrast_poly_cs (degree 2) at m = 32 (HC1, CR1-by-question), m = 128 reuse (HC1, CR1), m = 128 fresh (HC1),
    m = 512 reuse (HC1);  ok, t_type, se_type, min_eig recorded (ok=False = no rejection, infinite width).
  * 32-stage certificate from K32 (targets 32 and 128) and 128-stage certificate from K128 (targets 128 and 512): delta-method
    point/sd of D, first-order sup-widths (classes: |g|<=1 full; |g|<=1 & max|b1|,|b2|<=2; the DGP's own g) and kappa(m),
    with the question-cluster covariance of the per-type moment vector (orders 1..8).
Raw per-replication arrays are saved (npz) and summarised by a2_summarize.py (thresholds are applied there).
Environment: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19."""
import json, os, sys, time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from route_a_lib import pilot_theta, delta_bounds, functional_names
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

HERE = os.path.dirname(os.path.abspath(__file__))
N_T, N_ARM = 100, 16
WORLDS = {"narrow": ((20, 80), (25, 75)), "halfvar": ((40.5, 162.0), (50.6, 151.8)), "wide": ((2, 8), (2.5, 7.5))}
GS = {"linear": (0.18, -0.8, 0.0), "quad_narrow": (0.26, -1.6, 2.0), "quad_wide": (0.30, -1.2, 0.8)}
CELLS = [("narrow", "linear", 4000, 101), ("halfvar", "linear", 4000, 102), ("wide", "linear", 4000, 103),
         ("narrow", "quad_narrow", 2000, 104), ("wide", "quad_wide", 2000, 105)]
PROD = ["m32_HC1", "m32_CR1", "m128_reuse_HC1", "m128_reuse_CR1", "m128_fresh_HC1", "m512_reuse_HC1"]


def one_rep(rng, types, g):
    t = np.repeat([0, 1], N_T)
    r = np.concatenate([rng.beta(*types[0], N_T), rng.beta(*types[1], N_T)])
    q = np.concatenate([np.repeat(np.arange(N_T // 2), 2), np.repeat(np.arange(N_T // 2), 2)])   # 50 questions x 4 (2 per type)
    delta = g[0] + g[1] * r + g[2] * r ** 2
    qp_raw, qm_raw = r + delta / 2, r - delta / 2
    clipped = float(np.mean((qp_raw > 1) | (qm_raw < 0) | (qp_raw < 0) | (qm_raw > 1)))
    qp, qm = np.clip(qp_raw, 0, 1), np.clip(qm_raw, 0, 1)
    dhat = rng.binomial(N_ARM, qp) / N_ARM - rng.binomial(N_ARM, qm) / N_ARM
    K32 = rng.binomial(32, r)
    K128 = K32 + rng.binomial(96, r)
    K512 = K128 + rng.binomial(384, r)
    Kf128 = rng.binomial(128, r)
    calls = [(K32, 32, None), (K32, 32, q), (K128, 128, None), (K128, 128, q), (Kf128, 128, None), (K512, 512, None)]
    prod = np.full((len(calls), 4), np.nan)
    for i, (K, m, cl) in enumerate(calls):
        res = endpoint_contrast_poly_cs(dhat, K, m, t, degree=2, cluster=cl)
        prod[i, 0] = float(res["ok"]); prod[i, 3] = res["min_eig"]
        if res["ok"]:
            prod[i, 1] = res["t_type"]; prod[i, 2] = res["se"][-1]
    certs = []
    for K, m_pilot, targets in ((K32, 32, (32, 128)), (K128, 128, (128, 512))):
        th, Si, Sc = pilot_theta(K, t, m_pilot, cluster=q)
        db = delta_bounds(th, Sc, 0.5, 2 * N_T, N_T, N_T, targets=targets, beta=g)
        certs.append(np.concatenate([db["point"], db["sd"]]))
    return prod, certs[0], certs[1], clipped


def run_cell(args):
    wname, gname, reps, seed = args
    rng = np.random.default_rng(seed)
    types, g = WORLDS[wname], GS[gname]
    prod = np.zeros((reps, len(PROD), 4)); c32 = np.zeros((reps, 18)); c128 = np.zeros((reps, 18)); clip = np.zeros(reps)
    t0 = time.time()
    for i in range(reps):
        prod[i], c32[i], c128[i], clip[i] = one_rep(rng, types, g)
        if (i + 1) % 500 == 0:
            print("%s|%s %d/%d  %.0fs" % (wname, gname, i + 1, reps, time.time() - t0), flush=True)
    out = os.path.join(HERE, "a2_raw_%s_%s.npz" % (wname, gname))
    np.savez(out, prod=prod, cert32=c32, cert128=c128, clip=clip, prod_names=np.array(PROD),
             cert32_names=np.array(functional_names((32, 128), (None, 2.0), True)),
             cert128_names=np.array(functional_names((128, 512), (None, 2.0), True)),
             world=wname, g=gname, types=np.array(types, float), beta=np.array(g, float), seed=seed, reps=reps)
    print("wrote", out, "elapsed %.0fs" % (time.time() - t0), flush=True)
    return out


if __name__ == "__main__":
    with Pool(4) as pool:
        outs = pool.map(run_cell, CELLS, chunksize=1)
    print("done", outs)
