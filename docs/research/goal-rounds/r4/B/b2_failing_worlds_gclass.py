"""r4 route B, claim B2: the PRODUCTION degree-2 corrected-score type test (endpoint_contrast_poly_cs, HC1 and CR1-by-question)
at (n=200, m in {128, 512}) under the null b_type = 0 in the Le Cam pair F_a (narrow Beta(20,80)/(25,75)) vs F_b (half-variance
Beta(40.5,162)/(50.6,151.8)), in the exact two-point world F_c2 (same mean and variance as F_a per type), and along the
variance-scale family F_theta, for a GRID of response functions g in the bounded class (|g| <= 1 on [0,1]; q_+- clipped to
[0,1] with the clip rate reported).  eta = difference of two independent 16-draw binomial means (plan 7.11 arms halved).
Conventions of the obstacle: ok=False counts as non-rejection and as INFINITE width; q90 of the width is taken over all
replications (inf for non-PD) and, separately, over PD replications only.  Tolerances (user decision, reported for
sensitivity): |size - 0.05| <= 0.02, non-PD <= 0.02, q90(width) <= 0.15.
Derivation (b_derivation.md, B2): the corrected matrix A = sum_i M_i depends on (K, t) only, so the non-PD event is the same
for every g, every Var(eta|r) and both SEs; the score psi_i = b_1 (U_a r_i - U_{a+1}) + b_2 (U_a r_i^2 - U_{a+2}) + U_a eta_i
does not involve c, so only (b_1, b_2) and Var(eta|r) can move size and width.
Cluster composition for CR1: 50 questions, each with 2 type-0 and 2 type-1 prefixes (K_pref = 4); r iid (no question effect).
Environment tag: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19.  Scratch only."""
import json, sys, time
from fractions import Fraction as Fr
from multiprocessing import Pool
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from scipy import stats
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs, _ols, corrected_schur_mean

HERE = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/B__Le_Cam_two-point_impossibility_for_the_32-pilot_and_explicit_failing_worlds_inside_the_compatible_set__lower_bound__necessity_direction_"
OUT = HERE + "/b2_failing_worlds_gclass.json"
N_T, N_ARM, REPS, BASE_SEED = 100, 16, 2000, 4242
TOL = dict(size=0.02, non_pd=0.02, width_q90=0.15)

# ---------------------------------------------------------------------------------------------------------------- worlds
def beta_w(a0, b0, a1, b1):
    return dict(kind="beta", p=((a0, b0), (a1, b1)), label=f"Beta({a0:g},{b0:g})/Beta({a1:g},{b1:g})")

def disc_w(label, at0, w0, at1, w1):
    return dict(kind="disc", p=((at0, w0), (at1, w1)), label=label)

def theta_w(theta):
    s = 101.0 / theta - 1.0
    w = beta_w(s / 5, 4 * s / 5, s / 4, 3 * s / 4); w["label"] = f"F_theta={theta:g} " + w["label"]; return w

WORLDS = {
    "F_a": beta_w(20, 80, 25, 75),
    "F_b": beta_w(40.5, 162.0, 50.6, 151.8),
    "F_c2": disc_w("two-point same (mu,V) as F_a", (81 / 505, 6 / 25), (101 / 201, 100 / 201), (329 / 1616, 29 / 100), (1616 / 3491, 1875 / 3491)),
    "F_theta0.6": theta_w(0.6), "F_theta0.7": theta_w(0.7), "F_theta0.8": theta_w(0.8), "F_theta0.9": theta_w(0.9),
}

# ---------------------------------------------------------------------------------------------------------------- g grid
# g(r) = c + b1 r + b2 r^2 ; class: max_{[0,1]} |g| <= 1 (checked exactly below); q_+- = clip(r +- g/2, 0, 1), clip rate reported
G_GRID = {
    "g0 flat 0": (0.0, 0.0, 0.0),
    "g1 archive linear 0.18-0.8r": (0.18, -0.8, 0.0),
    "g2 archive quad 0.26-1.6r+2r^2": (0.26, -1.6, 2.0),
    "g3 archive wide-quad 0.30-1.2r+0.8r^2": (0.30, -1.2, 0.8),
    "g4 +slope -0.2+1.2r": (-0.2, 1.2, 0.0),
    "g5 -r+r^2": (0.0, -1.0, 1.0),
    "g6 0.02+1.5r-1.5r^2": (0.02, 1.5, -1.5),
    "g7 -0.02-1.5r+1.5r^2": (-0.02, -1.5, 1.5),
    "g8 +1.5r^2": (0.0, 0.0, 1.5),
    "g9 -1.5r^2": (0.0, 0.0, -1.5),
}

def max_abs_g_on_unit(c, b1, b2):
    cands = [0.0, 1.0]
    if b2 != 0:
        v = -b1 / (2 * b2)
        if 0 < v < 1:
            cands.append(v)
    return max(abs(c + b1 * r + b2 * r * r) for r in cands)

# ---------------------------------------------------------------------------------------------------------------- population quantities
def world_moments(world, t, order=8):
    if world["kind"] == "beta":
        a, b = world["p"][t]
        mu = [1.0]
        for j in range(1, order + 1):
            mu.append(mu[-1] * (a + j - 1) / (a + b + j - 1))
        return mu
    at, w = world["p"][t]
    return [sum(wi * xi ** j for xi, wi in zip(at, w)) for j in range(order + 1)]

def identification_D(world):
    """Type partial variance after (1, r, r^2) with equal type proportions: D = 1/(4 + q), q = dmu' Hbar^{-1} dmu,
    Hbar = (Sigma_0 + Sigma_1)/2 pooled within-type Cov(r, r^2), dmu = E[(r, r^2)|t=1] - E[(r, r^2)|t=0]."""
    mus = [world_moments(world, t, 4) for t in (0, 1)]
    Sig = [np.array([[mu[2] - mu[1] ** 2, mu[3] - mu[1] * mu[2]], [mu[3] - mu[1] * mu[2], mu[4] - mu[2] ** 2]]) for mu in mus]
    H = 0.5 * (Sig[0] + Sig[1])
    d = np.array([mus[1][1] - mus[0][1], mus[1][2] - mus[0][2]])
    ev = np.linalg.eigvalsh(H)
    if ev[0] <= 1e-15 * max(1.0, ev[-1]):
        return dict(D=0.0, q=float("inf"), lambda_min_Hbar_w=float(ev[0]), note="pooled within-type Cov(r,r^2) singular")
    q = float(d @ np.linalg.solve(H, d))
    return dict(D=1.0 / (4.0 + q), q=q, lambda_min_Hbar_w=float(ev[0]))

def pd_margin_schur(world, m, n_t=N_T):
    """A1 (production corrected_schur_mean): pooled E[S_w(m)] = (S_0 + S_1)/2 for degree 2; its eigenvalues (float of exact-form)."""
    S = np.zeros((2, 2))
    for t in (0, 1):
        S += 0.5 * np.array(corrected_schur_mean(m, 2, world_moments(world, t, 4), n_t), float)
    ev = np.linalg.eigvalsh(S)
    return dict(lambda_min=float(ev[0]), lambda_max=float(ev[1]), S=S.tolist())

# ---------------------------------------------------------------------------------------------------------------- simulation
def draw_r(rng, world, t):
    if world["kind"] == "beta":
        a, b = world["p"][t]
        return rng.beta(a, b, N_T)
    at, w = world["p"][t]
    return rng.choice(np.array(at, float), size=N_T, p=np.array(w, float) / np.sum(w))

def cp_interval(k, n):
    lo = 0.0 if k == 0 else stats.beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(0.975, k + 1, n - k)
    return [float(lo), float(hi)]

def run_cell(args):
    wname, gname, m, seed = args
    world, (c0, b1, b2) = WORLDS[wname], G_GRID[gname]
    rng = np.random.default_rng(seed)
    t = np.repeat([0, 1], N_T)
    q = np.concatenate([np.repeat(np.arange(N_T // 2), 2)] * 2)             # 50 questions x (2 type-0 + 2 type-1)
    rec = {k: [] for k in ("ok", "rej_h", "rej_c", "w_h", "w_c", "clip", "w_or_h", "w_or_c", "min_eig")}
    for _ in range(REPS):
        r = np.concatenate([draw_r(rng, world, 0), draw_r(rng, world, 1)])
        g = c0 + b1 * r + b2 * r * r
        qp_raw, qm_raw = r + g / 2, r - g / 2
        rec["clip"].append(float(np.mean((qp_raw > 1) | (qm_raw < 0) | (qp_raw < 0) | (qm_raw > 1))))
        qp, qm = np.clip(qp_raw, 0, 1), np.clip(qm_raw, 0, 1)
        dhat = rng.binomial(N_ARM, qp) / N_ARM - rng.binomial(N_ARM, qm) / N_ARM
        K = rng.binomial(m, r)
        rh = endpoint_contrast_poly_cs(dhat, K, m, t, degree=2)
        rc = endpoint_contrast_poly_cs(dhat, K, m, t, degree=2, cluster=q)
        assert rh["ok"] == rc["ok"]                                             # PD event is SE-free (same A)
        rec["ok"].append(rh["ok"]); rec["min_eig"].append(rh["min_eig"])
        if rh["ok"]:
            rec["rej_h"].append(abs(rh["t_type"]) > 1.96); rec["rej_c"].append(abs(rc["t_type"]) > 1.96)
            rec["w_h"].append(2 * 1.96 * rh["se"][-1]); rec["w_c"].append(2 * 1.96 * rc["se"][-1])
        else:
            rec["rej_h"].append(False); rec["rej_c"].append(False)
            rec["w_h"].append(np.inf); rec["w_c"].append(np.inf)
        X = np.c_[np.ones(2 * N_T), r, r * r, t]
        rec["w_or_h"].append(2 * 1.96 * _ols(X, dhat)[1][-1]); rec["w_or_c"].append(2 * 1.96 * _ols(X, dhat, q)[1][-1])
    ok = np.array(rec["ok"], bool)
    out = dict(world=world["label"], g=gname, g_coef=[c0, b1, b2], max_abs_g_on_unit=max_abs_g_on_unit(c0, b1, b2), m=m, reps=REPS, seed=seed,
               clip_rate=float(np.mean(rec["clip"])), non_pd=float(1 - ok.mean()), non_pd_ci95=cp_interval(int((~ok).sum()), REPS),
               min_eig_q05_50=[float(np.percentile(rec["min_eig"], 5)), float(np.percentile(rec["min_eig"], 50))])
    for se, rej, w, wor in (("HC1", "rej_h", "w_h", "w_or_h"), ("CR1", "rej_c", "w_c", "w_or_c")):
        rj, ww = np.array(rec[rej], bool), np.array(rec[w], float)
        fin = ww[np.isfinite(ww)]
        size = float(rj.mean())
        q90_all = float(np.percentile(ww, 90)) if np.isfinite(ww).mean() > 0.9 else float("inf")
        d = dict(size_uncond=size, size_ci95=cp_interval(int(rj.sum()), REPS), size_given_ok=float(rj[ok].mean()) if ok.any() else None,
                 width_q10_50_90_given_ok=[float(np.percentile(fin, p)) for p in (10, 50, 90)] if fin.size else None,
                 width_q90_all_inf_for_nonpd=q90_all, frac_width_gt_0p5_given_ok=float((fin > 0.5).mean()) if fin.size else None,
                 width_oracle_q50=float(np.median(rec[wor])))
        fails = []
        if abs(size - 0.05) > TOL["size"]: fails.append("size")
        if out["non_pd"] > TOL["non_pd"]: fails.append("non_pd")
        if not (q90_all <= TOL["width_q90"]): fails.append("width_q90")
        d["verdict"] = "pass" if not fails else "fail:" + ",".join(fails)
        out[se] = d
    return out

if __name__ == "__main__":
    t0 = time.time()
    cells = []
    for wname in ("F_a", "F_b"):
        for gname in G_GRID:
            for m in (128, 512):
                cells.append((wname, gname, m))
    for wname in ("F_c2",):
        for gname in ("g0 flat 0", "g1 archive linear 0.18-0.8r", "g2 archive quad 0.26-1.6r+2r^2"):
            for m in (128, 512):
                cells.append((wname, gname, m))
    for wname in ("F_theta0.6", "F_theta0.7", "F_theta0.8", "F_theta0.9"):
        for m in (128, 512):
            cells.append((wname, "g1 archive linear 0.18-0.8r", m))
    args = [(w, g, m, BASE_SEED + 1000 * i) for i, (w, g, m) in enumerate(cells)]
    with Pool(4) as pool:
        results = pool.map(run_cell, args)
    out = dict(environment="CPU, python 3.13.16 x86_64, numpy %s, scipy 1.18.1, 4 cores, 2026-10-19" % np.__version__,
               reps=REPS, base_seed=BASE_SEED, tolerances=TOL, g_grid=G_GRID, population={}, cells={})
    for wname, world in WORLDS.items():
        out["population"][wname] = dict(label=world["label"], D=identification_D(world),
                                        pd_margin_E_S_w={f"m={m}": pd_margin_schur(world, m) for m in (32, 128, 512)})
        print("POP", wname, json.dumps(out["population"][wname]), flush=True)
    for (w, g, m), res in zip(cells, results):
        key = f"{w}|{g}|m={m}"
        out["cells"][key] = res
        print(key, f"clip={res['clip_rate']:.2e} nonPD={res['non_pd']:.4f} {res['non_pd_ci95']} | HC1 size={res['HC1']['size_uncond']:.4f} "
              f"w(q10/50/90|ok)={res['HC1']['width_q10_50_90_given_ok']} q90all={res['HC1']['width_q90_all_inf_for_nonpd']:.3f} {res['HC1']['verdict']} "
              f"| CR1 size={res['CR1']['size_uncond']:.4f} w(q10/50/90|ok)={res['CR1']['width_q10_50_90_given_ok']} q90all={res['CR1']['width_q90_all_inf_for_nonpd']:.3f} {res['CR1']['verdict']} "
              f"| oracle w50 {res['HC1']['width_oracle_q50']:.3f}", flush=True)
    out["elapsed_s"] = time.time() - t0
    json.dump(out, open(OUT, "w"), indent=1)
    print("elapsed", out["elapsed_s"])
