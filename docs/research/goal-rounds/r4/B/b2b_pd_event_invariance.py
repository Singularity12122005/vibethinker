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
sys.path.insert(0, HERE)
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

cells = json.load(open(HERE + "/b2_failing_worlds_gclass.json"))["cells"]
pooled = {}
for w in ("F_a", "F_b", "F_c2"):
    for m in (128, 512):
        ks = [c for k, c in cells.items() if k.startswith(w + "|") and k.endswith(f"m={m}")]
        n = sum(c["reps"] for c in ks); k_nonpd = sum(round(c["non_pd"] * c["reps"]) for c in ks)
        lo = 0.0 if k_nonpd == 0 else float(stats.beta.ppf(0.025, k_nonpd, n - k_nonpd + 1))
        hi = 1.0 if k_nonpd == n else float(stats.beta.ppf(0.975, k_nonpd + 1, n - k_nonpd))
        pooled[f"{w}|m={m}"] = dict(n_cells=len(ks), reps_total=n, non_pd=k_nonpd / n, non_pd_ci95_exact=[lo, hi],
                                    width_q90_given_ok_range_HC1=[min(c["HC1"]["width_q10_50_90_given_ok"][2] for c in ks), max(c["HC1"]["width_q10_50_90_given_ok"][2] for c in ks)],
                                    width_q90_given_ok_range_CR1=[min(c["CR1"]["width_q10_50_90_given_ok"][2] for c in ks), max(c["CR1"]["width_q10_50_90_given_ok"][2] for c in ks)],
                                    size_range_HC1=[min(c["HC1"]["size_uncond"] for c in ks), max(c["HC1"]["size_uncond"] for c in ks)],
                                    size_range_CR1=[min(c["CR1"]["size_uncond"] for c in ks), max(c["CR1"]["size_uncond"] for c in ks)],
                                    verdicts_HC1=sorted({c["HC1"]["verdict"] for c in ks}), verdicts_CR1=sorted({c["CR1"]["verdict"] for c in ks}))
        print(f"{w}|m={m}", json.dumps(pooled[f"{w}|m={m}"]))
json.dump(dict(pd_event_invariance=dict(draws=n_draw, production_calls=n_checks, nonpd_draws=n_nonpd, identical=True), pooled=pooled),
          open(HERE + "/b2b_pd_event_invariance.json", "w"), indent=1)
