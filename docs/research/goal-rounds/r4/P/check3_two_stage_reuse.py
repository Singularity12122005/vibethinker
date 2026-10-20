"""r4 problem-phase cheap check 3: the pilot is INTERNAL (the 32 sel continuations are kept inside the 128), so the
'adopt 128' decision is a function of the first 32 draws of the very counts the final corrected-score test uses.
Does conditioning on a MARGINAL pilot decision change the size of the degree-2 type test at m = 128?
Compare: (i) one-stage m=128 (no selection); (ii) two-stage with REUSE: decide on K32, final K128 = K32 + K96, keep only
runs where the rule fired; (iii) two-stage with FRESH K128 independent of K32 (decision only selects the budget).
Decision rule: pooled within-type unbiased V_hat (from K32) exceeds a threshold chosen near the median of its sampling
distribution (the most selective case) and, as a second rule, the degree-2 corrected matrix at m=32 being PD.
World: narrow Beta(20,80)/(25,75), linear g (0.18 - 0.8 r), eta from 16 + 16 draws, HC1.  Null b_type = 0.
Environment: CPU, python3 / numpy 2.5.3 / scipy 1.18.1, 2026-10-19."""
import json, sys
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

OUT = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/problem/check3_two_stage_reuse.json"
N_T, N_ARM, M0, M1 = 100, 16, 32, 128
TYPES = ((20, 80), (25, 75)); G = (0.18, -0.8, 0.0)


def U(K, j, m):
    out = np.ones_like(K, float)
    for i in range(j):
        out *= (K - i) / (m - i)
    return out


def vhat_pooled(K, t, m):
    v = []
    for k in (0, 1):
        Kk = K[t == k]; n = Kk.size
        u1, u2 = U(Kk, 1, m), U(Kk, 2, m)
        v.append(u2.mean() - (u1.sum() ** 2 - (u1 ** 2).sum()) / (n * (n - 1)))
    return 0.5 * (v[0] + v[1])


def draw(rng):
    t = np.repeat([0, 1], N_T)
    r = np.concatenate([rng.beta(*TYPES[0], N_T), rng.beta(*TYPES[1], N_T)])
    delta = G[0] + G[1] * r + G[2] * r ** 2
    qp, qm = np.clip(r + delta / 2, 0, 1), np.clip(r - delta / 2, 0, 1)
    dhat = rng.binomial(N_ARM, qp) / N_ARM - rng.binomial(N_ARM, qm) / N_ARM
    K32 = rng.binomial(M0, r); K96 = rng.binomial(M1 - M0, r); Kfresh = rng.binomial(M1, r)
    return r, t, dhat, K32, K32 + K96, Kfresh


def summarize(rows):
    rows = np.array(rows, float)   # columns: fired, ok_reuse, rej_reuse, ok_fresh, rej_fresh, se_reuse, se_fresh
    f = rows[:, 0] == 1
    def sz(ok, rej):
        return dict(non_pd=float(1 - ok.mean()), size_uncond=float((ok * rej).mean()), size_given_ok=float(rej[ok == 1].mean()) if (ok == 1).any() else None)
    return dict(P_fired=float(f.mean()), n_fired=int(f.sum()),
                all_runs=dict(reuse=sz(rows[:, 1], rows[:, 2]), fresh=sz(rows[:, 3], rows[:, 4])),
                fired_only=dict(reuse=sz(rows[f, 1], rows[f, 2]), fresh=sz(rows[f, 3], rows[f, 4])),
                not_fired_only=dict(reuse=sz(rows[~f, 1], rows[~f, 2]), fresh=sz(rows[~f, 3], rows[~f, 4])),
                median_se_type_fired=dict(reuse=float(np.nanmedian(rows[f, 5])), fresh=float(np.nanmedian(rows[f, 6]))))


if __name__ == "__main__":
    rng = np.random.default_rng(20261019)
    REPS = 4000
    # calibrate the marginal threshold: median of pooled V_hat over 2000 pilots
    vh = np.array([vhat_pooled(draw(rng)[3], np.repeat([0, 1], N_T), M0) for _ in range(2000)])
    thr = float(np.median(vh))
    print("pooled V_hat from K32: mean %.5f sd %.5f median %.5f  P(<=0) %.3f  (true V ~ %.5f)" % (vh.mean(), vh.std(), thr, (vh <= 0).mean(), 0.5 * (20 * 80 / (100 ** 2 * 101) + 25 * 75 / (100 ** 2 * 101))))
    rules = {"Vhat32 > median": lambda K32, t, ok32: vhat_pooled(K32, t, M0) > thr,
             "deg2 matrix PD at m=32": lambda K32, t, ok32: ok32}
    out = {"threshold_Vhat": thr}
    for name, rule in rules.items():
        rows = []
        for _ in range(REPS):
            r, t, dhat, K32, K128, Kfresh = draw(rng)
            res32 = endpoint_contrast_poly_cs(dhat, K32, M0, t, degree=2)
            fired = bool(rule(K32, t, res32["ok"]))
            ru = endpoint_contrast_poly_cs(dhat, K128, M1, t, degree=2)
            rf = endpoint_contrast_poly_cs(dhat, Kfresh, M1, t, degree=2)
            rows.append([fired, ru["ok"], ru["ok"] and abs(ru["t_type"]) > 1.96, rf["ok"], rf["ok"] and abs(rf["t_type"]) > 1.96,
                         ru["se"][-1] if ru["ok"] else np.nan, rf["se"][-1] if rf["ok"] else np.nan])
        out[name] = summarize(rows)
        print(name, json.dumps(out[name]), flush=True)
    json.dump(out, open(OUT, "w"), indent=1)
