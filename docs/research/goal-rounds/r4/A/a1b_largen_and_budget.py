"""r4 / Route A, claim 1 (supplement): (a) consistency of the closed-form first-order sandwich with the PRODUCTION HC1 / CR1
sandwich of endpoint_contrast_poly_cs at large n (n = 20000, where the first-order approximation should be exact up to MC noise):
sqrt(n) * se_type(production) vs sqrt(E[phi^2]) / D; (b) the first-order m-budget: smallest m with w_1 <= w_0 for each world and
response class (the DGP's g; |g|<=1 with |b1|,|b2|<=2; |g|<=1 full), at n = 200.  Environment: CPU, python 3.13.16 x86_64,
numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from route_a_lib import beta_moments, first_order, widths_from_components
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

HERE = os.path.dirname(os.path.abspath(__file__))
WORLDS = {"narrow": ((20, 80), (25, 75)), "halfvar": ((40.5, 162.0), (50.6, 151.8)), "wide": ((2, 8), (2.5, 7.5))}
G = (0.18, -0.8, 0.0)
rng = np.random.default_rng(77)
out = {"large_n": {}, "m_budget": {}}
N_BIG, REPS = 20000, 20
for wn, types in WORLDS.items():
    mu0, mu1 = beta_moments(*types[0]), beta_moments(*types[1])
    for m in (32, 128):
        fo = first_order(mu0, mu1, 0.5, m, N_BIG, beta=G)
        pred = np.sqrt(fo["Ephi2"]) / fo["D"]              # sqrt(n) * se_1
        ratios = []
        for _ in range(REPS):
            t = np.repeat([0, 1], N_BIG // 2)
            r = np.concatenate([rng.beta(*types[0], N_BIG // 2), rng.beta(*types[1], N_BIG // 2)])
            d = G[0] + G[1] * r + G[2] * r ** 2
            dhat = rng.binomial(16, np.clip(r + d / 2, 0, 1)) / 16 - rng.binomial(16, np.clip(r - d / 2, 0, 1)) / 16
            K = rng.binomial(m, r)
            q = np.repeat(np.arange(N_BIG // 4), 2); q = np.concatenate([q, q])
            res = endpoint_contrast_poly_cs(dhat, K, m, t, degree=2)
            resc = endpoint_contrast_poly_cs(dhat, K, m, t, degree=2, cluster=q)
            ratios.append([np.sqrt(N_BIG) * res["se"][-1] / pred if res["ok"] else np.nan,
                           np.sqrt(N_BIG) * resc["se"][-1] / pred if resc["ok"] else np.nan, res["ok"]])
        ratios = np.array(ratios, float)
        out["large_n"]["%s|m=%d" % (wn, m)] = dict(n=N_BIG, reps=REPS, pred_sqrt_n_se=float(pred), ok_frac=float(ratios[:, 2].mean()),
                                                     ratio_HC1_mean_sd=[float(np.nanmean(ratios[:, 0])), float(np.nanstd(ratios[:, 0]))],
                                                     ratio_CR1_mean_sd=[float(np.nanmean(ratios[:, 1])), float(np.nanstd(ratios[:, 1]))])
        print(wn, m, json.dumps(out["large_n"]["%s|m=%d" % (wn, m)]), flush=True)
    # m-budget at n = 200 (first order)
    bud = {}
    for cls in ("g", "c2", "cinf"):
        found = None
        for m in (16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 2048, 4096):
            fo = first_order(mu0, mu1, 0.5, m, 200, sup_g=True)
            w = widths_from_components(fo["term_eta"], fo["Omega"], fo["D"], 200, beta=G, coef_bounds=(None, 2.0))
            wv = {"cinf": w[0], "c2": w[1], "g": w[2]}[cls]
            bud.setdefault(cls, {})["m=%d" % m] = float(wv)
            if found is None and wv <= 0.15:
                found = m
        bud[cls]["smallest_m_with_w1_le_0.15"] = found
        bud[cls]["limit_m_inf"] = float(2 * 1.96 * np.sqrt(first_order(mu0, mu1, 0.5, 4096, 200, sup_g=True)["term_eta"] / (200 * fo["D"] ** 2)))
    out["m_budget"][wn] = bud
    print(wn, "m-budget (first order, n=200, w0=0.15):", {c: bud[c]["smallest_m_with_w1_le_0.15"] for c in bud},
          "widths@128:", {c: round(bud[c]["m=128"], 4) for c in bud}, flush=True)
json.dump(out, open(os.path.join(HERE, "a1b_largen_and_budget.json"), "w"), indent=1)
print("wrote a1b_largen_and_budget.json")
