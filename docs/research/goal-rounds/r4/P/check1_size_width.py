"""r4 problem-phase cheap check 1: what the PRODUCTION degree-2 corrected-score type test (endpoint_contrast_poly_cs,
HC1 / CR1-by-question) actually does at (n=200, m in {32,128,512}) in the archive's narrow / wide Beta worlds, under the
null b_type = 0, with eta from two independent arms of 16 binomial draws.  The archive (r3 table) only has non-PD rates
for these cells; size and CI width were never computed.  Output: size (unconditional = ok & |t|>1.96, and conditional on
ok), non-PD rate, quantiles of the 95% CI full width 2*1.96*se_type, and the oracle (true r) OLS width for reference.
Environment: CPU, python3 / numpy 2.5.3 / scipy 1.18.1, 2026-10-19.  Scratch only; nothing in the repository is modified."""
import sys, json, time
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs, _ols

OUT = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/problem/check1_size_width.json"

WORLDS = {
    # §7.11 example-type ("narrow"): r ~ 0.20 / 0.25, within-type sd ~0.04 (archive r3 A2 narrow cell)
    "narrow": dict(types=((20, 80), (25, 75)), g=dict(linear=(0.18, -0.8, 0.0), quad=(0.26, -1.6, 2.0))),
    # archive r3 A2 wide cell
    "wide": dict(types=((2, 8), (2.5, 7.5)), g=dict(linear=(0.18, -0.8, 0.0), quad=(0.30, -1.2, 0.8))),
}
N_T, N_ARM, REPS = 100, 16, 2000


def dgp(rng, types, g, m, n_t=N_T, n_arm=N_ARM, q_per_question=4):
    n = 2 * n_t
    t = np.repeat([0, 1], n_t)
    r = np.concatenate([rng.beta(*types[0], n_t), rng.beta(*types[1], n_t)])
    c0, b1, b2 = g
    delta = c0 + b1 * r + b2 * r ** 2
    qp, qm = np.clip(r + delta / 2, 0.0, 1.0), np.clip(r - delta / 2, 0.0, 1.0)
    clipped = np.mean((r + delta / 2 > 1) | (r - delta / 2 < 0))
    dhat = rng.binomial(n_arm, qp) / n_arm - rng.binomial(n_arm, qm) / n_arm
    K = rng.binomial(m, r)
    # question labels: 2 prefixes of each type per question (50 questions); r is iid here (no question effect)
    q = np.concatenate([np.repeat(np.arange(n_t // 2), 2), np.repeat(np.arange(n_t // 2), 2)])
    return r, t, K, dhat, q, clipped


def cell(rng, types, g, m, degree, cluster, reps=REPS):
    ok, rej, width, clipr, min_eig, width_or = [], [], [], [], [], []
    for _ in range(reps):
        r, t, K, dhat, q, clipped = dgp(rng, types, g, m)
        res = endpoint_contrast_poly_cs(dhat, K, m, t, degree=degree, cluster=(q if cluster else None))
        ok.append(res["ok"]); min_eig.append(res["min_eig"]); clipr.append(clipped)
        if res["ok"]:
            rej.append(abs(res["t_type"]) > 1.96); width.append(2 * 1.96 * res["se"][-1])
        X = np.c_[np.ones(r.size), *[r ** j for j in range(1, degree + 1)], t]
        bo, seo, _ = _ols(X, dhat, (q if cluster else None))
        width_or.append(2 * 1.96 * seo[-1])
    ok = np.array(ok); rej = np.array(rej, bool); width = np.array(width)
    return dict(reps=reps, non_pd=float(1 - ok.mean()), size_unconditional=float(rej.sum() / reps),
                size_given_ok=float(rej.mean()) if rej.size else None,
                width_q10_50_90=[float(np.percentile(width, p)) for p in (10, 50, 90)] if width.size else None,
                width_oracle_q50=float(np.median(width_or)), clip_rate=float(np.mean(clipr)))


if __name__ == "__main__":
    rng = np.random.default_rng(20261019)
    out = {}
    t0 = time.time()
    for wname, w in WORLDS.items():
        for gname, g in w["g"].items():
            for m in (32, 128, 512):
                for degree in (1, 2):
                    for cluster in (False, True):
                        key = f"{wname}|g={gname}|m={m}|deg={degree}|{'CR1' if cluster else 'HC1'}"
                        out[key] = cell(rng, w["types"], g, m, degree, cluster)
                        print(key, json.dumps(out[key]), flush=True)
    print("elapsed", time.time() - t0)
    json.dump(out, open(OUT, "w"), indent=1)
