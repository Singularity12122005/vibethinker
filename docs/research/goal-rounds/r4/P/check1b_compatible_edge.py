"""r4 problem-phase cheap check 1b: the production degree-2 type test at (200, m) in risk worlds that a 100-per-type pilot at
m=32 cannot separate from the narrow Beta(20,80)/(25,75) world (check2 Le Cam): the literal §7.11 two-point example
(point masses 0.20 / 0.25, V = 0), half-variance Betas and double-variance Betas with the same means.  Linear g, eta 16+16,
HC1; also the tail of the CI width (fraction of ok runs with width > 0.5, max width) to expose weak identification.
Environment: CPU, python3 / numpy 2.5.3 / scipy 1.18.1, 2026-10-19."""
import sys, json
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs, _ols

OUT = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/problem/check1b_compatible_edge.json"
N_T, N_ARM, REPS, G = 100, 16, 2000, (0.18, -0.8, 0.0)
WORLDS = {"point_mass_0.20/0.25": None, "half_var_Beta(40.5,162)/(50.6,152)": ((40.5, 162.0), (50.6, 151.8)),
          "narrow_Beta(20,80)/(25,75)": ((20, 80), (25, 75)), "double_var_Beta(9.5,38)/(12,36)": ((9.5, 38.0), (12.0, 36.0))}


def run(rng, types, m, degree=2):
    ok, rej, width, wor = [], [], [], []
    for _ in range(REPS):
        t = np.repeat([0, 1], N_T)
        if types is None:
            r = np.where(t == 0, 0.20, 0.25)
        else:
            r = np.concatenate([rng.beta(*types[0], N_T), rng.beta(*types[1], N_T)])
        delta = G[0] + G[1] * r + G[2] * r ** 2
        dhat = rng.binomial(N_ARM, np.clip(r + delta / 2, 0, 1)) / N_ARM - rng.binomial(N_ARM, np.clip(r - delta / 2, 0, 1)) / N_ARM
        K = rng.binomial(m, r)
        res = endpoint_contrast_poly_cs(dhat, K, m, t, degree=degree)
        ok.append(res["ok"])
        if res["ok"]:
            rej.append(abs(res["t_type"]) > 1.96); width.append(2 * 1.96 * res["se"][-1])
        if types is not None:
            X = np.c_[np.ones(2 * N_T), *[r ** j for j in range(1, degree + 1)], t]
            wor.append(2 * 1.96 * _ols(X, dhat)[1][-1])
    ok, rej, width = np.array(ok), np.array(rej, bool), np.array(width)
    return dict(non_pd=float(1 - ok.mean()), size_uncond=float(rej.sum() / REPS), size_given_ok=float(rej.mean()) if rej.size else None,
                width_q10_50_90=[float(np.percentile(width, p)) for p in (10, 50, 90)] if width.size else None,
                width_max=float(width.max()) if width.size else None, frac_ok_width_gt_0p5=float((width > 0.5).mean()) if width.size else None,
                width_oracle_q50=float(np.median(wor)) if wor else "singular (type collinear with r)")


if __name__ == "__main__":
    rng = np.random.default_rng(7)
    out = {}
    for name, types in WORLDS.items():
        for m in (128, 512):
            key = f"{name}|m={m}|deg=2|HC1"
            out[key] = run(rng, types, m)
            print(key, json.dumps(out[key]), flush=True)
    json.dump(out, open(OUT, "w"), indent=1)
