import numpy as np
import pytest
from sycophancy_phase0.analysis.varcomp import u_stat_var, anova_mom_var, icc, bootstrap_var, cluster_bootstrap, two_stage_bootstrap
from sycophancy_phase0.analysis.frontier import tilt_frontier, dual_frontier, cs_bound, bernstein_bound
from sycophancy_phase0.analysis.desirability import (jensen_gap, jensen_gap_beta, jensen_gap_by_prefix, jensen_gap_exact, jensen_gap_lambda_by_prefix,
                                                     jensen_gap_u, g2a_decision, reactive_weights)
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
    # (a, b, reps, EB/JK upper bound on mean/J_true, Ĵ_LB tolerance (lo, hi) incl. Monte-Carlo noise); plan §8.4 numbers
    cases = [(6.0, 4.0, 100, 0.75, (-0.08, 0.08)), (8.0, 2.0, 40, 0.75, (-0.10, 0.10)), (3.0, 3.0, 40, 0.80, (-0.10, 0.06)),
             (2.0, 2.0, 40, 0.85, (-0.12, 0.04)), (60.0, 40.0, 60, 0.50, (-0.20, 0.20))]
    for a, b, reps, ub, (lo, hi) in cases:
        zt = rng.beta(a, b, 200000)
        J_true = float(np.log(zt.mean()) - np.log(zt).mean())
        eb, jk, lb = [], [], []
        for _ in range(reps):
            Z = rng.binomial(M, rng.beta(a, b, N))
            J = _plug(_eb_shrink(Z, M))
            Jd = np.array([_plug(_eb_shrink(np.delete(Z, i), M)) for i in range(N)])
            eb.append(J); jk.append(N * J - (N - 1) * Jd.mean()); lb.append(jensen_gap(Z, M)["J"])
        assert np.mean(eb) < ub * J_true and np.mean(jk) < ub * J_true, (a, b, np.mean(eb) / J_true, np.mean(jk) / J_true)
        assert lo < (np.mean(lb) - J_true) / J_true < hi, (a, b, (np.mean(lb) - J_true) / J_true)


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


def _T_K_beta(a, b, K):
    tot, e = 0.0, 1.0
    for k in range(1, K + 1):
        e *= (b + k - 1) / (a + b + k - 1)
        tot += (e - (b / (a + b)) ** k) / k
    return tot


def test_jensen_gap_u_is_unbiased_for_the_truncated_target():
    """Round 7: Ĵ_U is unbiased for T_16 = Σ_{k<=16}[E(1−z)^k − (1−μ)^k]/k (not for J_0), including the low-μ regime where the
    old delta-corrected estimator falls far below T_16; null => 0; μ̂ = 0 => 0; the reviewer's mixture gives T_16 ≈ 0.0019
    while J_0 ≈ 0.098 and the n_zero flag fires in < 1% of datasets (the remainder is not controlled by the data)."""
    rng = np.random.default_rng(11)
    M, N = 16, 128
    for a, b, reps, tol in [(6.0, 4.0, 200, 0.004), (3.0, 3.0, 200, 0.006), (1.0, 10.0, 200, 0.010), (60.0, 40.0, 200, 0.0015)]:
        T = _T_K_beta(a, b, M)
        ju = [jensen_gap_u(rng.binomial(M, rng.beta(a, b, N)), M)["J"] for _ in range(reps)]
        assert abs(np.mean(ju) - T) < tol, (a, b, np.mean(ju), T)
    assert abs(np.mean([jensen_gap_u(rng.binomial(M, 0.6, N), M)["J"] for _ in range(200)])) < 0.0007
    assert jensen_gap_u(np.zeros(16), M)["J"] == 0.0 and jensen_gap_u(np.full(16, M), M)["J"] == 0.0
    eps, p0 = np.exp(-100), 0.001
    mu = (1 - p0) * 0.6 + p0 * eps
    J0 = np.log(mu) - ((1 - p0) * np.log(0.6) + p0 * np.log(eps))
    T = sum((((1 - p0) * 0.4 ** k + p0 * (1 - eps) ** k) - (1 - mu) ** k) / k for k in range(1, M + 1))
    assert 0.098 < J0 < 0.099 and 0.0018 < T < 0.0020
    ju, flags = [], []
    for _ in range(1500):
        Z = rng.binomial(M, np.where(rng.random(N) < p0, eps, 0.6))
        r = jensen_gap(Z, M); ju.append(r["J"]); flags.append(r["near_zero_mass"])
    assert abs(np.mean(ju) - T) < 0.0004 and np.mean(flags) < 0.02 and np.mean(ju) < 0.05 * J0
    # the primary in jensen_gap is the U estimator; weights uniform on e_2 = 0 are accepted, non-uniform weights fall back
    Z = rng.binomial(M, rng.beta(6, 4, N))
    w = np.where(rng.random(N) < 0.3, 0.0, 1.0)
    r = jensen_gap(Z, M, w)
    assert r["estimator"] == "U" and r["target"] == "T_16" and abs(r["J"] - jensen_gap_u(Z[w > 0], M)["J"]) < 1e-12
    assert jensen_gap(Z, M, reactive_weights(rng.integers(0, 2, N), 0.3))["estimator"] == "approx_weighted"
    assert jensen_gap(Z, M)["zero_count_mass_ub95"] == 3.0 / N or jensen_gap(Z, M)["n_zero"] > 0


def test_g6_split_half_iv_removes_the_measurement_error_bias():
    """Round 12: under the null (dose effect depends on true risk only; type correlated with risk) the naive type test is
    oversized, the split-half 2SLS test has nominal size and recovers the risk slope; power survives under an alternative."""
    from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_iv
    rng = np.random.default_rng(2026)
    def one(c2):
        N = 200
        typ = np.repeat([0, 1], N // 2)
        r = np.where(typ == 0, rng.beta(3, 5, N), rng.beta(5, 3, N))
        delta = 0.20 - 0.5 * r + c2 * typ
        qp, qm = np.clip(r + delta / 2, 0.02, 0.98), np.clip(r - delta / 2, 0.02, 0.98)
        dhat = rng.binomial(16, qp) / 16 - rng.binomial(16, qm) / 16
        ra, rb = rng.binomial(16, r) / 16, rng.binomial(16, r) / 16
        return endpoint_contrast_iv(dhat, ra, rb, typ)
    null = [one(0.0) for _ in range(400)]
    size_naive = np.mean([o["naive"]["p_type"] < 0.05 for o in null])
    size_iv = np.mean([o["iv"]["p_type"] < 0.05 for o in null])
    assert size_naive > 0.10 and size_iv < 0.09, (size_naive, size_iv)
    assert abs(np.mean([o["iv"]["beta"][1] for o in null]) + 0.5) < 0.05 and np.mean([o["naive"]["beta"][1] for o in null]) > -0.45
    assert np.mean([o["first_stage_F"] for o in null]) > 10 and 0.7 < np.mean([o["reliability"] for o in null]) < 1.0
    alt = [one(0.10) for _ in range(200)]
    assert np.mean([o["iv"]["p_type"] < 0.05 for o in alt]) > 0.6


def _g6_world(rng, N, r_types, c0, c1, c2, m=32, n_arm=16):
    typ = np.repeat([0, 1], N // 2)
    r = np.where(typ == 0, rng.beta(*r_types[0], N), rng.beta(*r_types[1], N))
    B = rng.binomial(1, r[:, None], size=(N, m)).astype(float)
    ra, rb, rf = B[:, : m // 2].mean(1), B[:, m // 2 :].mean(1), B.mean(1)
    delta = c0 + c1 * r + c2 * typ
    qp, qm = np.clip(r + delta / 2, 0.02, 0.98), np.clip(r - delta / 2, 0.02, 0.98)
    dhat = rng.binomial(n_arm, qp) / n_arm - rng.binomial(n_arm, qm) / n_arm
    return typ, r, ra, rb, rf, dhat


def test_g6_naive_bias_formula_and_corrected_score_estimator():
    """Round 12 P1/P2: the naive type coefficient is biased by exactly b_r(1−λ_w)Δμ; the known-variance corrected-score estimator
    (all 32 draws) is unbiased with nominal size and at least the 2SLS power when identification is strong."""
    from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_eiv, endpoint_contrast_iv, naive_type_bias
    rng = np.random.default_rng(12)
    N, c1 = 200, -0.5
    naive_gamma, eiv_p, iv_p, eiv_beta, V, s_num, dmu = [], [], [], [], [], [], []
    for _ in range(250):
        typ, r, ra, rb, rf, y = _g6_world(rng, N, ((3, 5), (5, 3)), 0.20, c1, 0.0)
        naive_gamma.append(endpoint_contrast_iv(y, ra, rb, typ)["naive"]["beta"][2])
        e = endpoint_contrast_eiv(y, rf, typ, m=32)
        assert e["ok"]
        eiv_p.append(e["p_type"]); eiv_beta.append(e["beta"])
        V.append(np.mean([np.var(r[typ == k]) for k in (0, 1)])); s_num.append(np.mean(r * (1 - r))); dmu.append(r[typ == 1].mean() - r[typ == 0].mean())
    pred = naive_type_bias(c1, np.mean(V), np.mean(s_num), 32, np.mean(dmu))
    assert abs(np.mean(naive_gamma) - pred["bias"]) < 0.006, (np.mean(naive_gamma), pred)
    assert 0.75 < pred["reliability_within"] < 0.85
    assert np.mean(np.array(eiv_p) < 0.05) < 0.09                                             # nominal size
    assert abs(np.mean([b[1] for b in eiv_beta]) - c1) < 0.03 and abs(np.mean([b[2] for b in eiv_beta])) < 0.01
    for _ in range(150):
        typ, r, ra, rb, rf, y = _g6_world(rng, N, ((3, 5), (5, 3)), 0.20, c1, 0.10)
        eiv_p.append(endpoint_contrast_eiv(y, rf, typ, m=32)["p_type"]); iv_p.append(endpoint_contrast_iv(y, ra, rb, typ)["iv"]["p_type"])
    power_eiv, power_iv = np.mean(np.array(eiv_p[250:]) < 0.05), np.mean(np.array(iv_p) < 0.05)
    assert power_eiv > 0.7 and power_iv > 0.6 and power_eiv >= power_iv - 0.08, (power_eiv, power_iv)


def test_g6_identification_strength_formula_and_weak_regime():
    """Round 12 P3: F ≈ n λ_h²/(1−λ_h²) from design quantities; the reviewer-like types (r≈0.20 vs 0.25) are weakly identified at
    n=200 (F≈4) and the corrected-score estimator refuses (non-PD) in part of the replicates; n≈520 restores F=10."""
    from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_eiv, endpoint_contrast_iv, identification_strength
    rng = np.random.default_rng(3)
    Fs, V, s_num, refusals = [], [], [], 0
    for _ in range(120):
        typ, r, ra, rb, rf, y = _g6_world(rng, 200, ((20, 80), (25, 75)), 0.18, -0.8, 0.0)
        Fs.append(endpoint_contrast_iv(y, ra, rb, typ)["first_stage_F"])
        V.append(np.mean([np.var(r[typ == k]) for k in (0, 1)])); s_num.append(np.mean(r * (1 - r)))
        refusals += not endpoint_contrast_eiv(y, rf, typ, m=32)["ok"]
    pred = identification_strength(200, float(np.mean(V)), float(np.mean(s_num)), 16)
    assert pred["weak"] and 2.5 < pred["F"] < 5.5 and abs(np.median(Fs) - pred["F"]) < 1.5, (pred, np.median(Fs))
    assert 400 < pred["n_for_F_target"] < 700                                                    # refusals (non-PD) are seed-dependent
    # deterministic refusal: no within-type variation of r̂ at all ⇒ corrected moment matrix cannot be positive definite
    typ = np.repeat([0, 1], 50)
    bad = endpoint_contrast_eiv(rng.standard_normal(100), np.where(typ == 0, 0.2, 0.25), typ, m=32)
    assert not bad["ok"] and bad["min_eig"] <= 0 and "positive definite" in bad["reason"]
    strong = identification_strength(200, 0.0258, 0.208, 16)                                  # Beta(3,5)/Beta(5,3) world
    assert not strong["weak"] and 120 < strong["F"] < 200


def test_readout_reliability_ceiling_and_disattenuation():
    """Round 12 P4/P5: in the linear-quadratic idealisation the best linear closed loop realises exactly the fraction λ of the
    oracle advantage and the plug-in controller loses to open loop when λ<1/2; the disattenuated ρ² of a probe is unbiased
    while the naive correlation with the pooled r̂ is attenuated."""
    from sycophancy_phase0.analysis.g6_iv import lq_ceiling, readout_reliability
    rng = np.random.default_rng(5)
    N, kappa, a, b = 200000, 1.0, 0.0, -2.0
    r = rng.beta(3, 5, N)
    for m in (4, 32):
        e = rng.binomial(m, r) / m - r
        c = lq_ceiling(float(np.var(r)), float(np.mean(r * (1 - r))), m, kappa, b)
        mu, lam = r.mean(), c["reliability"]
        J = lambda d: 0.5 * kappa * np.mean((d - a - b * r) ** 2)
        open_, lin, plug = J(a + b * mu), J(a + b * (mu + lam * (r + e - mu))), J(a + b * (r + e))
        assert abs((open_ - lin) / open_ - lam) < 0.01 and abs(plug - c["plug_in_regret"]) < 2e-3
        assert (plug > open_) == (lam < 0.5) == (not c["plug_in_beats_open_loop"])
    ests, truths, naive = [], [], []
    for _ in range(60):
        r = rng.beta(3, 5, 1000)
        B = rng.binomial(1, r[:, None], size=(1000, 32)).astype(float)
        z = r + 0.15 * rng.standard_normal(1000)
        out = readout_reliability(z, B[:, :16].mean(1), B[:, 16:].mean(1), n_boot=50)
        ests.append(out["rho2"]); truths.append(np.corrcoef(z, r)[0, 1] ** 2); naive.append(out["naive_corr2"])
    assert abs(np.mean(ests) - np.mean(truths)) < 0.02 and np.mean(naive) < np.mean(truths) - 0.05
    assert out["ci95"][0] < out["rho2"] < out["ci95"][1] and 0.5 < out["half_reliability"] < 0.85


def test_g6_polynomial_corrected_score_and_value_of_information():
    """Round 12 review follow-up: (i) with a quadratic Δ(r) the linear estimators (even the oracle) load the misfit on type, the
    degree-2 U-statistic corrected score does not; (ii) the exact value of information reproduces the §7.11 two-point example
    (fraction 0.024 at m=32, far below λ=0.103) and η²=λ for a Beta prior (conjugacy); (iii) the F non-centrality clears 10 with
    probability ≈0.5 at ncp=10; (iv) cluster bootstrap option of readout_reliability runs."""
    from scipy import stats
    from sycophancy_phase0.analysis.g6_iv import (endpoint_contrast_poly_cs, identification_strength, readout_reliability,
                                                  value_of_information_fraction)
    rng = np.random.default_rng(21)
    N, m = 200, 32
    typ = np.repeat([0, 1], N // 2)
    d1, d2, p1, p2 = [], [], [], []
    for _ in range(120):
        r = np.where(typ == 0, rng.beta(2, 8, N), rng.beta(3, 3, N))
        K = rng.binomial(m, r)
        y = 0.30 - 0.2 * r - 1.5 * r ** 2 + 0.15 * rng.standard_normal(N)
        e1, e2 = endpoint_contrast_poly_cs(y, K, m, typ, degree=1), endpoint_contrast_poly_cs(y, K, m, typ, degree=2)
        assert e1["ok"] and e2["ok"] and e1["se_type"] == "HC1"
        d1.append(e1["beta"][-1]); d2.append(e2["beta"][-1]); p1.append(e1["p_type"]); p2.append(e2["p_type"])
    assert np.mean(d1) > 0.025 and abs(np.mean(d2)) < 0.012, (np.mean(d1), np.mean(d2))
    assert np.mean(np.array(p1) < 0.05) > 0.09 and np.mean(np.array(p2) < 0.05) < 0.10
    with pytest.raises(ValueError):
        endpoint_contrast_poly_cs(y, K, m, typ, degree=17)
    acts = np.array([-1, -0.5, 0, 0.5, 1.0]); rg = np.array([0.20, 0.25])
    cost = np.stack([np.clip(rg + (0.9 - 4 * rg) * d, 0, 1) + 0.05 * abs(d) for d in acts], 1)
    v = value_of_information_fraction(cost, [0.5, 0.5], 32, rg)
    assert abs(v["oracle"] - 0.175) < 1e-9 and abs(v["open_loop"] - 0.225) < 1e-9 and 0.015 < v["fraction"] < 0.035 and 0.09 < v["reliability"] < 0.12
    grid = np.linspace(0.005, 0.995, 199); w = stats.beta.pdf(grid, 5, 15)
    costg = np.stack([np.clip(grid + (0.9 - 4 * grid) * d, 0, 1) + 0.05 * abs(d) for d in acts], 1)
    vb = value_of_information_fraction(costg, w, 32, grid)
    assert abs(vb["eta2"] - vb["reliability"]) < 0.01 and abs(vb["fraction"] - vb["reliability"]) < 0.05
    o = identification_strength(520, 0.00172, 0.172, 16)
    assert 9 < o["noncentrality"] < 11.5 and 0.45 < o["pass_probability"] < 0.57 and 15 < o["ncp_for_pass_prob"] < 17 and 700 < o["n_for_pass_prob"] < 950
    r = rng.beta(3, 5, 200); B = rng.binomial(1, r[:, None], size=(200, 32)).astype(float)
    z = r + 0.15 * rng.standard_normal(200)
    out = readout_reliability(z, B[:, :16].mean(1), B[:, 16:].mean(1), cluster=np.repeat(np.arange(50), 4), n_boot=100)
    assert out["bootstrap"] == "cluster" and out["ci95"][0] < out["rho2"] < out["ci95"][1] and 0.0 < out["naive_corr2"] < out["rho2"]


def _goal_r3_beta_counts(m, a, b):
    """以贝塔二项概率递推作独立有限和，不使用联合阶乘矩公式。"""
    from fractions import Fraction as Q
    from math import prod
    probabilities = [prod(Q(b + j, a + b + j) for j in range(m))]
    for k in range(m):
        probabilities.append(probabilities[-1] * Q(m - k, k + 1) * Q(a + k, b + m - k - 1))
    assert sum(probabilities) == 1
    return probabilities


def _goal_r3_count_table(m, order):
    from fractions import Fraction as Q
    from math import comb
    return [[Q(comb(k, j), comb(m, j)) if j <= k else Q(0)
             for j in range(order + 1)] for k in range(m + 1)]


def _goal_r3_group_states(probabilities, table, n):
    from itertools import combinations_with_replacement
    from math import factorial, prod
    states = []
    for counts in combinations_with_replacement(range(len(probabilities)), n):
        multiplicity = factorial(n) // prod(factorial(counts.count(k)) for k in set(counts))
        weight = multiplicity * prod(probabilities[k] for k in counts)
        means = [sum(table[k][j] for k in counts) / n for j in range(len(table[0]))]
        states.append((counts, weight, means))
    assert sum(state[1] for state in states) == 1
    return states


def test_goal_r3_a1_exact_joint_moments_and_schur_mean():
    """A1：独立计数有限和精确复核联合矩；全状态求和验证舒尔补偏移及不等类大小。"""
    from fractions import Fraction as Q
    from itertools import product
    from sycophancy_phase0.analysis.g6_iv import binomial_factorial_joint_moment

    for m, p in [(4, 2), (6, 3), (8, 2), (12, 3)]:
        table = _goal_r3_count_table(m, 2 * p)
        for a, b in [(2, 3), (3, 2)]:
            pk = _goal_r3_beta_counts(m, a, b)
            moments = [Q(1)]
            for j in range(1, min(m, 4 * p) + 1):
                moments.append(moments[-1] * Q(a + j - 1, a + b + j - 1))
            for j, k in product(range(2 * p + 1), repeat=2):
                exact = sum(q * row[j] * row[k] for q, row in zip(pk, table))
                assert binomial_factorial_joint_moment(moments, m, j, k) == exact
            # m=2p 时不需要不存在的 4p 阶风险矩。
            assert len(moments) == min(m, 4 * p) + 1
    with pytest.raises(ValueError, match="insufficient risk moments"):
        binomial_factorial_joint_moment([Q(1)] * 4, 4, 4, 4)

    m, p = 4, 2
    table = _goal_r3_count_table(m, 2 * p)
    groups = []
    for a, b in [(2, 3), (3, 2)]:
        pk = _goal_r3_beta_counts(m, a, b)
        mu = [sum(q * row[j] for q, row in zip(pk, table)) for j in range(2 * p + 1)]
        covariance = [[sum(q * (row[j] - mu[j]) * (row[k] - mu[k]) for q, row in zip(pk, table))
                       for k in range(p + 1)] for j in range(p + 1)]
        groups.append((pk, mu, covariance))
    for sizes in [(2, 2), (1, 2)]:
        weights = [Q(size, sum(sizes)) for size in sizes]
        states = [_goal_r3_group_states(group[0], table, size) for group, size in zip(groups, sizes)]
        expected = [[Q(0) for _ in range(p)] for _ in range(p)]
        for left, right in product(*states):
            probability = left[1] * right[1]
            means = [left[2], right[2]]
            for a, b in product(range(1, p + 1), repeat=2):
                expected[a - 1][b - 1] += probability * sum(
                    weight * (mean[a + b] - mean[a] * mean[b]) for weight, mean in zip(weights, means))
        bias = [[Q(0) for _ in range(p)] for _ in range(p)]
        for a, b in product(range(1, p + 1), repeat=2):
            population = sum(weight * (mu[a + b] - mu[a] * mu[b]) for weight, (_, mu, _) in zip(weights, groups))
            bias[a - 1][b - 1] = sum(weight * covariance[a][b] / size
                                       for weight, size, (_, _, covariance) in zip(weights, sizes, groups))
            assert expected[a - 1][b - 1] == population - bias[a - 1][b - 1]
        assert bias[0][0] > 0 and bias[1][1] > 0
        assert bias[0][0] * bias[1][1] - bias[0][1] ** 2 > 0


def test_goal_r3_ce_b1_four_scalar_counterexample():
    """CE-B1：225 状态、全矩阵主子式的有理数判号；四标量相同但概率严格不同。"""
    from fractions import Fraction as Q
    from itertools import permutations, product
    from math import comb, prod
    from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

    def determinant(matrix):
        n = len(matrix)
        return sum((-1) ** sum(perm[i] > perm[j] for i in range(n) for j in range(i + 1, n))
                   * prod(matrix[i][perm[i]] for i in range(n)) for perm in permutations(range(n)))

    m, p = 4, 2
    point_moments = [sum(Q(comb(j, 2 * ell), 2 ** (j - 2 * ell) * 12 ** ell)
                         for ell in range(j // 2 + 1)) for j in range(m + 1)]
    point_counts = [comb(m, k) * sum((-1) ** ell * comb(m - k, ell) * point_moments[k + ell]
                                    for ell in range(m - k + 1)) for k in range(m + 1)]
    assert point_counts == [Q(7, 36), Q(2, 9), Q(1, 6), Q(2, 9), Q(7, 36)]
    table = _goal_r3_count_table(m, 2 * p)
    # 具体边界：(4,4) 与 (0,4) 两类计数令 r、r² 两列相同，精确奇异。
    # 不把某一平台上浮点判正后求解失败的行为写成测试期望。
    singular = [[Q(1), Q(3, 4), Q(3, 4), Q(1, 2)],
                [Q(3, 4), Q(3, 4), Q(3, 4), Q(1, 4)],
                [Q(3, 4), Q(3, 4), Q(3, 4), Q(1, 4)],
                [Q(1, 2), Q(1, 4), Q(1, 4), Q(1, 2)]]
    assert determinant(singular) == 0
    assert all(row[1] - row[2] == 0 for row in singular)
    risks = []
    for eps in [Q(1, 100), Q(1, 2)]:
        moments = [(1 - eps) * value + eps / (j + 1) for j, value in enumerate(point_moments)]
        assert moments[1] == Q(1, 2)
        assert moments[2] - moments[1] ** 2 == Q(1, 12)
        assert moments[1] - moments[2] == Q(1, 6)
        # 总体弱方向仍严格为正；未使用 eps=0 的奇异边界。
        assert 4 * eps / 5 > 0 and 44 * eps / 35 - 16 * eps ** 2 / 25 > 0
        probabilities = [(1 - eps) * q + eps / (m + 1) for q in point_counts]
        states = _goal_r3_group_states(probabilities, table, 2)
        risk, bad_states = Q(0), 0
        for left, right in product(states, repeat=2):
            z0, z1 = left[2], right[2]
            matrix = [[(z0[a + b] + z1[a + b]) / 2 for b in range(p + 1)] + [z1[a] / 2]
                      for a in range(p + 1)]
            matrix.append([z1[a] / 2 for a in range(p + 1)] + [Q(1, 2)])
            good = all(determinant([row[:j] for row in matrix[:j]]) > 0 for j in range(1, p + 3))
            # 精确零特征值不能由浮点严格判号裁决；该边界仍计入下方精确风险。
            if determinant(matrix) != 0:
                observed = endpoint_contrast_poly_cs([0., 0., 0., 1.], left[0] + right[0], m, [0, 0, 1, 1], p)
                assert observed["ok"] == good
            if not good:
                risk += left[1] * right[1]
                bad_states += 1
        assert len(states) ** 2 == 225 and bad_states == 213
        risks.append(risk)
    assert risks == [Q(945238594631, 1000000000000), Q(109375919, 116640000)]
    assert risks[0] != risks[1]


def test_goal_r3_a2_joint_gaussian_misses_finite_sample_failure():
    """A2：固定窄分布的一格小检验；完整联合高斯约32%，直接计数约7%，不作预算接口。"""
    from math import comb
    from scipy import stats

    rng = np.random.default_rng(143)
    m, p, group_n = 256, 3, 100
    counts = np.arange(m + 1, dtype=np.longdouble)
    u = np.ones((m + 1, 2 * p + 1), dtype=np.longdouble)
    for j in range(1, 2 * p + 1):
        u[:, j] = u[:, j - 1] * (counts - j + 1) / (m - j + 1)
    center, scale = np.longdouble(9) / 40, np.longdouble(1) / 20
    table = np.stack([sum(comb(j, ell) * (-center) ** (j - ell) * u[:, ell] for ell in range(j + 1)) / scale ** j
                      for j in range(2 * p + 1)], axis=1)
    direct = np.ones((4000, 2, 2 * p + 1))
    gaussian = np.ones((8000, 2, 2 * p + 1))
    for t, (a, b) in enumerate([(20, 80), (25, 75)]):
        pk = stats.betabinom.pmf(np.arange(m + 1), m, a, b).astype(np.longdouble)
        pk /= pk.sum()
        mu = pk @ table
        residual = table[:, 1:] - mu[1:]
        covariance = (residual.T * pk) @ residual
        root = np.linalg.cholesky(np.asarray(covariance / group_n, dtype=float))
        r = rng.beta(a, b, size=(len(direct), group_n))
        sampled_counts = rng.binomial(m, r)
        direct[:, t, :] = np.asarray(table, dtype=float)[sampled_counts].mean(axis=1)
        gaussian[:, t, 1:] = np.asarray(mu[1:], dtype=float) + rng.normal(size=(len(gaussian), 2 * p)) @ root.T

    def failure_rate(z):
        full = np.zeros((len(z), p + 2, p + 2))
        for a in range(p + 1):
            for b in range(p + 1):
                full[:, a, b] = (z[:, 0, a + b] + z[:, 1, a + b]) / 2
            full[:, a, -1] = full[:, -1, a] = z[:, 1, a] / 2
        full[:, -1, -1] = .5
        return np.mean(np.linalg.eigvalsh(full)[:, 0] <= 0)

    actual, approximation = failure_rate(direct), failure_rate(gaussian)
    assert .04 < actual < .10, actual
    assert .28 < approximation < .37, approximation
    assert approximation - actual > .20, (actual, approximation)

    # 极限论证的有限实现检查：真实风险样本给出正定内积矩阵，而自由矩向量可违反偶次矩约束。
    # 一般满秩与全支撑结论由档案中的多项式论证给出，不由这两个有限样本外推。
    risks = np.array([[.1, .3, .5, .7], [.2, .4, .6, .8]])
    x = (risks - float(center)) / float(scale)
    true_moments = np.stack([np.mean(x ** j, axis=1) for j in range(2 * p + 1)], axis=1)[None, :, :]
    design = np.c_[np.ones(8), x.ravel(), x.ravel() ** 2, x.ravel() ** 3, np.repeat([0, 1], 4)]
    assert np.linalg.matrix_rank(design) == p + 2
    assert np.linalg.eigvalsh(design.T @ design).min() > 0
    assert failure_rate(true_moments) == 0
    impossible_moments = true_moments.copy()
    impossible_moments[:, :, 2 * p] = -1
    assert failure_rate(impossible_moments) == 1


def test_goal_r3_p6_outcome_dependent_comparator_is_not_kl():
    """维护性反例：看到抽样结果后再选比较分布，所选对数差不等于相对熵。"""
    p = np.array([.5, .5])
    q_after_y = np.array([[.9, .1], [.1, .9]])
    selected = np.sum(p * np.log(p / q_after_y.diagonal()))
    conditional_kl = np.sum(p[None, :] * np.log(p[None, :] / q_after_y), axis=1)
    assert selected == pytest.approx(np.log(.5 / .9)) and selected < 0
    assert np.all(conditional_kl > 0)
    assert conditional_kl[0] == pytest.approx(.5 * np.log(.5 / .9) + .5 * np.log(.5 / .1))
