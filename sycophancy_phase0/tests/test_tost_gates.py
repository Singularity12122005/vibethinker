import numpy as np
from sycophancy_phase0.analysis.tost import paired_cluster_bootstrap_diff, tost_pass, tv_distance, chi2_homogeneity_p
from sycophancy_phase0.gates.g0 import g0_3, g0_4, g0_5, g0_6, g0_7


def test_paired_bootstrap_tost_power_and_level():
    rng = np.random.default_rng(0)
    n_h3, n_cont = 200, 128
    cluster = np.repeat(np.arange(n_h3), n_cont)
    base = np.clip(rng.beta(2, 3, n_h3), 0.05, 0.95)
    # equal arms: TOST at ±1.5pp should pass most of the time
    passes = 0
    for rep in range(20):
        p = np.repeat(base, n_cont)
        x, y = rng.binomial(1, p), rng.binomial(1, p)
        r = paired_cluster_bootstrap_diff(x, y, cluster, n_boot=300, seed=rep)
        passes += tost_pass(r["lo"], r["hi"], 0.015)
    assert passes >= 14
    # a real 4pp leak must fail
    p = np.repeat(base, n_cont)
    x, y = rng.binomial(1, np.clip(p + 0.04, 0, 1)), rng.binomial(1, p)
    r = paired_cluster_bootstrap_diff(x, y, cluster, n_boot=300, seed=99)
    assert not tost_pass(r["lo"], r["hi"], 0.015)


def test_g0_6_null_rate_with_20000():
    rng = np.random.default_rng(1)
    fails = 0
    for rep in range(30):
        a = rng.integers(0, 5, 20000); b = rng.integers(0, 5, 20000)
        if not g0_6(a.tolist(), b.tolist(), deterministic=False).passed:
            fails += 1
    assert fails <= 3                                  # TV<0.02 has null q95≈0.013 at n=20000


def test_other_g0_stats():
    assert g0_3(np.array([1e-4, 2e-4, 5e-3])).passed and not g0_3(np.array([1e-4, 2e-2, 5e-3])).passed
    assert g0_7(np.array([-3.0, -10.0])).passed and not g0_7(np.array([-3.0, -70.0])).passed
    assert tv_distance([10, 10], [10, 10]) == 0.0 and chi2_homogeneity_p([50, 50], [50, 50]) == 1.0
    assert g0_6([1, 2, 3], [1, 2, 3], deterministic=True).passed and not g0_6([1, 2], [2, 1], deterministic=True).passed
    rng = np.random.default_rng(2)
    cl = np.repeat(np.arange(50), 8)
    x = rng.binomial(1, 0.3, 400); y = x.copy()
    assert g0_8(x, y, cl).passed and g0_5(x, y, cl, 1.0).passed and not g0_5(x, y, cl, 0.98).passed
    assert g0_4(x, y, cl, True, True, 1e-5, 0.0).passed and not g0_4(x, y, cl, False, True, 1e-5, 0.0).passed
