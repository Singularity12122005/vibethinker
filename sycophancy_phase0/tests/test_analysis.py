import numpy as np
import pytest
from sycophancy_phase0.analysis.varcomp import u_stat_var, anova_mom_var, icc, bootstrap_var
from sycophancy_phase0.analysis.frontier import tilt_frontier, dual_frontier, cs_bound, bernstein_bound
from sycophancy_phase0.analysis.desirability import jensen_gap, reactive_weights
from sycophancy_phase0.analysis.covvar import cov_within_prefix, policy_value_halves, two_stage_bootstrap_cov
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


def test_jensen_gap_series_is_nearly_unbiased():
    rng = np.random.default_rng(1)
    M, N = 16, 128
    for a, b in [(6.0, 4.0), (3.0, 3.0), (8.0, 2.0)]:
        z_true = rng.beta(a, b, 400000)
        J_true = np.log(z_true.mean()) - np.log(z_true).mean()
        ser, beta, delta = [], [], []
        for _ in range(300):
            Z = rng.binomial(M, rng.beta(a, b, N))
            r = jensen_gap(Z, M)
            ser.append(r["J"]); beta.append(r["J_beta"]); delta.append(r["delta"])
        assert abs(np.mean(ser) - J_true) < 0.06 * J_true + 0.002       # 4th-order series: a few % bias
        assert abs(np.mean(beta) - J_true) < 0.06 * J_true + 0.002      # parametric cross-check (Beta truth)
        assert np.mean(delta) < J_true * 1.02                            # delta term is a lower bound here
    nulls = [jensen_gap(rng.binomial(M, 0.6, N), M)["J"] for _ in range(300)]
    assert abs(np.mean(nulls)) < 0.002


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
    bs = two_stage_bootstrap_cov(Va, Vb, pref, n_boot=200, seed=0)
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
        assert dual[k] <= bernstein_bound(q, k) + 1e-6          # Bernstein is the KL-matched bound
        assert cs_bound(q, k) > 0                                 # chi^2-minimal reference only, NOT a bound at fixed KL
    assert tilt[1.0] <= q.mean() - q.min() + 1e-9


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
