import numpy as np
import pytest
from sycophancy_phase0.analysis.varcomp import u_stat_var, anova_mom_var, icc, bootstrap_var, cluster_bootstrap, two_stage_bootstrap
from sycophancy_phase0.analysis.frontier import tilt_frontier, dual_frontier, cs_bound, bernstein_bound
from sycophancy_phase0.analysis.desirability import (jensen_gap, jensen_gap_beta, jensen_gap_by_prefix, jensen_gap_exact, jensen_gap_lambda_by_prefix,
                                                     g2a_decision, reactive_weights)
from sycophancy_phase0.analysis.covvar import cov_within_prefix, policy_value_halves, cluster_bootstrap_cov
from sycophancy_phase0.analysis.power import paired_components, F_required


def test_u_stat_equals_anova_and_is_unbiased():
    rng = np.random.default_rng(0)
    M, N = 16, 128
    a, b = 2.4, 3.6                      # Beta(a,b): mean 0.4, var 0.0343
    true_var = a * b / ((a + b) ** 2 * (a + b + 1))
    ests = []
    for _ in range(400):
        q = rng.beta(a, b, N)
        K = rng.binomial(M, q)
        ests.append(u_stat_var(K, M))
        assert abs(u_stat_var(K, M) - anova_mom_var(K, M)) < 1e-12
    assert abs(np.mean(ests) - true_var) < 0.003
    # null: no between-y2 variance -> estimate centred at 0
    nulls = [u_stat_var(rng.binomial(M, 0.4, N), M) for _ in range(400)]
    assert abs(np.mean(nulls)) < 0.0015


def test_jensen_gap_lb_unbiased_in_benign_regimes_and_lower_bound_elsewhere():
    rng = np.random.default_rng(1)
    M, N = 16, 128
    for a, b in [(60.0, 40.0), (6.0, 4.0), (3.0, 3.0), (8.0, 2.0)]:
        z_true = rng.beta(a, b, 400000)
        J_true = np.log(z_true.mean()) - np.log(z_true).mean()
        lb, ser, beta = [], [], []
        for _ in range(200):
            Z = rng.binomial(M, rng.beta(a, b, N))
            r = jensen_gap(Z, M)
            lb.append(r["J"]); ser.append(r["J_series"]); beta.append(r["J_beta"])
        assert abs(np.mean(lb) - J_true) < 0.04 * J_true + 0.001          # primary: unbiased when z stays away from 0
        assert abs(np.mean(ser) - J_true) < 0.09 * J_true + 0.002         # diagnostic series: a few % low
        beta = np.array(beta)                                           # v1.4: undefined (Var<=0) fits are NaN, not a clamped ~0
        assert np.mean(np.isnan(beta)) < 0.5 and abs(np.nanmean(beta) - J_true) < 0.06 * J_true + 0.002
    nulls = [jensen_gap(rng.binomial(M, 0.6, N), M)["J"] for _ in range(300)]
    assert abs(np.mean(nulls)) < 0.0015
    # near-zero mass: the primary is a lower bound (never above truth), the series is lower still; flags fire
    lbs, sers, flags, truths = [], [], [], []
    for _ in range(100):
        z = rng.beta(60, 40, N); z[rng.random(N) < 0.02] = 0.02
        Z = rng.binomial(M, z); r = jensen_gap(Z, M)
        lbs.append(r["J"]); sers.append(r["J_series"]); flags.append(r["near_zero_mass"]); truths.append(jensen_gap_exact(z))
    assert np.mean(lbs) < np.mean(truths) and np.mean(lbs) > np.mean(sers) and np.mean(flags) > 0.5
    # low mean: the series explodes, the lower bound stays finite and below the truth
    z = rng.beta(1, 10, N); Z = rng.binomial(M, z); r = jensen_gap(Z, M)
    assert r["low_mean"] and r["J"] < jensen_gap_exact(z) and np.isfinite(r["J"])
    # per-prefix: a between-prefix-only heterogeneity must give J ≈ 0 (pooling would give a false GO)
    Zs, pref = [], []
    for p in range(40):
        zp = 0.15 + 0.7 * p / 39
        Zs.append(rng.binomial(M, zp, N)); pref.append(np.full(N, p))
    r = jensen_gap_by_prefix(np.concatenate(Zs), M, np.concatenate(pref))
    assert abs(r["J"]) < 0.01 and jensen_gap(np.concatenate(Zs), M)["J"] > 0.05 and r["n_prefix"] == 40
    assert g2a_decision(0.01, 0.005, 0.015, 0.0) == "KILL" and g2a_decision(0.01, 0.005, 0.015, 0.2) == "GO-with-caveat"
    assert g2a_decision(0.1, 0.085, 0.12, 0.5) == "GO"


def test_u_stat_unbalanced_and_bootstrap_t():
    rng = np.random.default_rng(7)
    a, b = 2.4, 3.6
    true_var = a * b / ((a + b) ** 2 * (a + b + 1))
    ests = []
    for _ in range(300):
        q = rng.beta(a, b, 128)
        M = rng.choice([12, 14, 16], 128)
        K = rng.binomial(M, q)
        ests.append(u_stat_var(K, M))
    assert abs(np.mean(ests) - true_var) < 0.003
    with pytest.raises(ValueError):
        u_stat_var(np.array([3, 5]), np.array([4, 4]))
    r = bootstrap_var(rng.binomial(16, rng.beta(a, b, 128)), 16, n_boot=100, seed=0, n_inner=20)
    assert r["upper95"] > r["est"] > r["lower95"] and r["upper95"] >= r["upper95_normal"] - 0.01
    # prefix-only bootstrap has smaller spread than the two-stage one (which double-counts within-prefix noise)
    groups = [rng.binomial(16, rng.beta(a, b, 32)) for _ in range(40)]
    stat = lambda gs: np.mean([u_stat_var(g, 16) for g in gs])
    assert cluster_bootstrap(stat, groups, 200, 0).std() < two_stage_bootstrap(stat, groups, 200, 0).std()


def test_reactive_weights_small_lambda_is_uniform_on_e2_zero():
    e2 = np.array([0, 1, 0, 0, 1])
    w = reactive_weights(e2, 0.01)
    assert np.allclose(w[e2 == 0], 1 / 3) and np.allclose(w[e2 == 1], 0)


def test_cov_estimator_null_and_alternative():
    rng = np.random.default_rng(2)
    n_y2, n_arms, n_pref = 32, 5, 40
    cost = np.array([1, .5, 0, .5, 1.0])
    lam = 0.05
    def simulate(hetero):
        Va, Vb, pref = [], [], []
        for p in range(n_pref):
            base = np.array([.5, .45, .4, .3, .2])
            for j in range(n_y2):
                arm_p = base + (rng.normal(0, 0.12) if hetero else 0.0)
                arm_p = np.clip(arm_p, 0.02, 0.98)
                ph = np.stack([rng.binomial(4, arm_p) / 4 for _ in range(4)], axis=1)   # [arms, 4 quarters]
                a, b = policy_value_halves(ph[None], cost, lam)
                Va.append(a[0]); Vb.append(b[0]); pref.append(p)
        return np.array(Va), np.array(Vb), np.array(pref)
    nulls = [cov_within_prefix(*simulate(False)) for _ in range(40)]
    alts = [cov_within_prefix(*simulate(True)) for _ in range(10)]
    assert abs(np.mean(nulls)) < 0.0025                 # unbiased at zero (null SE ≈ 0.0036 per the plan)
    assert np.mean(alts) > 0.008                        # positive under heterogeneity
    Va, Vb, pref = simulate(True)
    bs = cluster_bootstrap_cov(Va, Vb, pref, n_boot=200, seed=0)
    assert bs["lower95_onesided"] > 0


def test_frontier_bounds_order():
    rng = np.random.default_rng(3)
    q = rng.beta(2.4, 3.6, 128)
    kappas = [0.05, 0.1, 0.25, 0.5, 1.0]
    tilt = tilt_frontier(q, q, kappas)
    dual = dual_frontier(q, kappas)
    prev = -1
    for k in kappas:
        assert tilt[k] >= prev - 1e-9; prev = tilt[k]
        assert tilt[k] <= dual[k] + 1e-6
        assert dual[k] <= bernstein_bound(np.var(q), k) + 1e-6  # Bernstein is the KL-matched bound (takes Var(q))
        assert cs_bound(np.var(q), k) > 0                         # chi^2-minimal reference only, NOT a bound at fixed KL
    assert tilt[1.0] <= q.mean() - q.min() + 1e-9
    # cross-fit under the null (Var(q)=0): no winner's curse — mean tau* ≈ 0 at every kappa
    nulls = []
    for _ in range(150):
        Ks = rng.binomial(8, 0.4, 128); Ke = rng.binomial(8, 0.4, 128)
        nulls.append(tilt_frontier(Ks / 8, Ke / 8, [0.25, 1.0]))
    for k in (0.25, 1.0):
        vals = np.array([d[k] for d in nulls])
        assert abs(vals.mean()) < 2.5 * vals.std() / np.sqrt(len(vals)) + 1e-3


def test_power_identity_and_F_table():
    rng = np.random.default_rng(4)
    Fn, P, n = 60, 4, 32
    sig_f, sig_p, tau = 0.08, 0.10, 0.03
    taus, se2s = [], []
    for _ in range(300):
        d = tau + rng.normal(0, sig_f, (Fn, 1)) + rng.normal(0, sig_p, (Fn, P))
        p0 = np.clip(rng.beta(1.2, 2.8, (Fn, P)), 0.02, 0.98)
        pu = np.clip(p0 - d, 0.01, 0.99)
        dh = rng.binomial(n, p0) / n - rng.binomial(n, pu) / n
        vbar = np.mean((p0 * (1 - p0) + pu * (1 - pu)) / (n - 1))
        r = paired_components(dh, vbar)
        taus.append(r["tau"]); se2s.append(r["se2_tau"])
    assert abs(np.mean(se2s) - np.var(taus, ddof=1)) < 0.35 * np.var(taus, ddof=1)
    F80 = F_required(0.08 ** 2, 0.10 ** 2, 4, 32, 0.03)
    assert 100 <= F80 <= 112                           # plan §11.4 / deep-dive: ≈105 (+3)


def _eb_shrink(Z, M):
    q = Z / M
    mu = q.mean()
    var = max(u_stat_var(Z, M), 1e-6)
    s = max(mu * (1 - mu) / var - 1, 1e-3)
    a, b = mu * s, (1 - mu) * s
    return (Z + a) / (M + a + b)


def _plug(qt):
    return float(np.log(qt.mean()) - np.log(qt).mean())


def test_eb_jackknife_plugin_is_biased_low():
    """The external memo's estimator (EB-shrunk plug-in + delete-one jackknife with the prior refit per replicate) under-
    estimates J by ~40% at Beta(6,4) (M=16, N=128); the jackknife does not repair it; Ĵ_LB is within 2% (plan §8.4)."""
    rng = np.random.default_rng(7)
    M, N = 16, 128
    a, b = 6.0, 4.0
    zt = rng.beta(a, b, 200000)
    J_true = float(np.log(zt.mean()) - np.log(zt).mean())
    eb, jk, lb = [], [], []
    for _ in range(100):
        Z = rng.binomial(M, rng.beta(a, b, N))
        J = _plug(_eb_shrink(Z, M))
        Jd = np.array([_plug(_eb_shrink(np.delete(Z, i), M)) for i in range(N)])
        eb.append(J); jk.append(N * J - (N - 1) * Jd.mean()); lb.append(jensen_gap(Z, M)["J"])
    assert np.mean(eb) < 0.75 * J_true and np.mean(jk) < 0.75 * J_true          # ~ -40%
    assert abs(np.mean(lb) - J_true) < 0.10 * J_true                          # the 4% check with 200 reps is in the test above


def test_jensen_gap_beta_undefined_cases_keep_raw_variance():
    """memo S4 / v1.4: Var<=0 (all-equal counts) => NaN with reason and the raw (negative) U-statistic kept, no clamped fit."""
    r = jensen_gap_beta(np.array([10] * 8), 16)
    assert np.isnan(r["J"]) and r["reason"] == "var_le_0" and r["var"] < 0
    assert jensen_gap_beta(np.array([16] * 8), 16)["reason"] == "mu_out_of_(0,1)"
    assert jensen_gap_beta(np.array([0, 16, 0, 16]), 16)["reason"] == "var_ge_mu(1-mu)"
    g = jensen_gap(np.array([10] * 8), 16)
    assert np.isnan(g["J_beta"]) and g["J_beta_reason"] == "var_le_0"
    assert jensen_gap(np.array([2, 14, 5, 12, 3, 13, 6, 11]), 16)["J_beta_reason"] is None


def test_finite_lambda_curve_matches_small_lambda_limit():
    rng = np.random.default_rng(3)
    M, N = 16, 64
    Z = rng.integers(3, 15, N); S2 = rng.integers(0, M - Z + 1); S1 = M - Z - S2        # Z > 0: the plug-in on Z/M is finite
    e2 = np.zeros(N, int)
    pref = np.array(["a"] * (N // 2) + ["b"] * (N // 2))
    r_small = jensen_gap_lambda_by_prefix(Z, S1, S2, np.full(N, M), e2, pref, 0.01)
    plug = np.mean([_plug(Z[pref == p] / M) for p in ("a", "b")])
    assert abs(r_small["J"] - plug) < 1e-6 and r_small["n_prefix"] == 2         # λ -> 0: the plug-in on Z/M
    r1 = jensen_gap_lambda_by_prefix(Z, S1, S2, np.full(N, M), e2, pref, 1.0)
    assert np.isfinite(r1["J"]) and 0 <= r1["J"] < r_small["J"]                # failures count partially: less dispersion
    Zz = Z.copy(); Zz[:4] = 0
    assert np.isfinite(jensen_gap_lambda_by_prefix(Zz, M - Zz, np.zeros(N, int), np.full(N, M), e2, pref, 0.1)["J"])
