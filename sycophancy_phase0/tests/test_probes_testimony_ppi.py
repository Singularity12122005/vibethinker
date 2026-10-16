import numpy as np
import pytest

from sycophancy_phase0.analysis.probes import auroc, g3_decision, ladder, loqo_predictions, r2, ridge_predict_all_lambdas, spearman_brown
import sycophancy_phase0.analysis.testimony as tm
from sycophancy_phase0.analysis.testimony import corrected_means, fe_logit_stance_by_stratum, ppv_npv, same_stance_icc
from sycophancy_phase0.analysis.ppi import arm_bias, ppi_difference, specificity_sensitivity


def test_ridge_dual_matches_primal_and_loqo():
    rng = np.random.default_rng(0)
    n, D = 60, 10
    X = rng.normal(size=(n, D)); beta = rng.normal(size=D)
    y = X @ beta + 0.1 * rng.normal(size=n)
    Xte = rng.normal(size=(5, D))
    lam = 3.0
    pred = ridge_predict_all_lambdas(X, y, Xte, [lam])[:, 0]
    mu, sd = X.mean(0), X.std(0)
    Xs, Xts = (X - mu) / sd, (Xte - mu) / sd
    w = np.linalg.solve(Xs.T @ Xs + lam * np.eye(D), Xs.T @ (y - y.mean()))
    assert np.allclose(pred, Xts @ w + y.mean(), atol=1e-8)
    q = np.repeat(np.arange(12), 5)
    out = loqo_predictions(X, y, q, lambdas=(0.1, 1.0, 10.0), inner_folds=3)
    assert r2(y, out["pred"]) > 0.9 and set(out["lambda_by_question"].values()) <= {0.1, 1.0, 10.0}


def test_ladder_detects_probe_signal_and_null():
    rng = np.random.default_rng(1)
    Q, P, D = 30, 6, 40
    n = Q * P
    question = np.repeat(np.arange(Q), P)
    signal = rng.normal(size=n)
    z = np.stack([signal] * 3 + [rng.normal(size=n) for _ in range(D - 3)], 1) + 0.5 * rng.normal(size=(n, D))
    base = rng.normal(size=(n, 2))
    y = 0.8 * signal + 0.3 * base[:, 0] + 0.3 * rng.normal(size=n)
    y = y - np.array([y[question == q].mean() for q in question])            # problem-demeaned target
    res = ladder([("fe", None), ("base", base), ("probe", z)], y, question, raw_target=(y > 0).astype(float) + 0.5,
                 n_boot=200, n_perm=10, perm_level="probe", seed=0, lambdas=(0.1, 1.0, 10.0, 100.0), inner_folds=3)
    lv = {r["level"]: r for r in res["levels"]}
    assert lv["fe"]["R2"] <= 0 + 1e-9 and lv["probe"]["delta_R2"] > 0.3 and lv["probe"]["delta_R2_lb975"] > 0
    assert lv["probe"]["auroc"] > 0.8 and res["perm_null"]["p"] < 0.2 and max(res["perm_null"]["null"]) < lv["probe"]["delta_R2"]
    assert g3_decision(lv["probe"]["delta_R2"], lv["probe"]["delta_R2_lb975"], rho_sh=0.6) == "GO"
    assert g3_decision(0.05, -0.01, 0.6) == "KILL" and g3_decision(0.05, 0.01, 0.6) == "KILL"
    # null: probe unrelated to y -> ΔR² ≈ 0 with lower bound <= 0
    z0 = rng.normal(size=(n, D))
    res0 = ladder([("fe", None), ("base", base), ("probe", z0)], y, question, n_boot=200, seed=1, lambdas=(1.0, 10.0, 100.0, 1000.0), inner_folds=3)
    lv0 = {r["level"]: r for r in res0["levels"]}
    assert lv0["probe"]["delta_R2"] < 0.1 and lv0["probe"]["delta_R2_lb975"] <= 0.02
    assert abs(spearman_brown(np.array([1, 2, 3, 4.0]), np.array([1.1, 1.9, 3.2, 3.9])) - 2 * 0.99 / 1.99) < 0.02
    assert auroc(np.array([1, 1, 0, 0]), np.array([0.9, 0.8, 0.2, 0.1])) == 1.0


def test_testimony_model():
    assert corrected_means(0.5, 0.2, 1.0, 1.0) == (0.5, 0.2)
    mp, mm = corrected_means(0.5, 0.2, 0.9, 0.9)
    assert mp > 0.5 and mm < 0.2                                          # misclassification shrinks the observed gap
    rng = np.random.default_rng(2)
    P, Ms, m = 20, 60, 8
    prefix, stance, K, e4rows = [], [], [], []
    for p in range(P):
        base = rng.uniform(-1, 1)
        for j in range(Ms):
            s = "USER" if rng.random() < 0.4 else ("ORIG" if rng.random() < 0.9 else "NONE")
            lor = 1.0 if s == "USER" else 0.0
            q = 1 / (1 + np.exp(-(base + lor)))
            k = rng.binomial(m, q)
            prefix.append(p); stance.append(s); K.append(k)
    prefix, stance, K = np.array(prefix), np.array(stance), np.array(K)
    pt = tm.testimony_point(prefix, stance, K / m, 1.0, 1.0)
    assert 0.6 < pt["LOR"] < 1.4 and pt["n_prefix"] == P and 0 < pt["excluded_share"] < 0.2
    human = np.array(["USER"] * 50 + ["ORIG"] * 50); judge = human.copy(); judge[:5] = "ORIG"; judge[50:53] = "USER"
    cal = ppv_npv(human, judge)
    assert abs(cal["PPV"] - 45 / 48) < 1e-9 and abs(cal["NPV"] - 47 / 52) < 1e-9
    bt = tm.testimony_bootstrap(prefix, stance, K / m, human, judge, n_boot=100, seed=0)
    assert bt["LOR_ci95"][0] < bt["LOR"] < bt["LOR_ci95"][1] and bt["LOR"] > pt["LOR"] * 0.9
    strat = np.array([p % 2 for p in prefix])
    fe = fe_logit_stance_by_stratum(prefix, stance, strat, K / m)
    assert set(fe["per_stratum_LOR"]) == {"0", "1"} and all(0.4 < v["est"] < 1.6 for v in fe["per_stratum_LOR"].values())
    assert fe["homogeneity_p"] > 0.01
    icc = same_stance_icc(prefix, stance, K, m, n_perm=30)
    assert np.isfinite(icc["observed"]["USER"]) and 0 < icc["perm_p_USER"] <= 1


def test_ppi():
    rng = np.random.default_rng(3)
    n = 2000
    full, human = {}, {}
    for arm, bias_rate in (("arm1", 0.1), ("arm0", 0.0)):
        truth = rng.binomial(1, 0.4, n)
        strata = np.where(truth == 1, "USER", "ORIG")
        judge = truth.copy()
        flip = rng.random(n) < bias_rate                                  # judge over-calls USER on arm1
        judge[flip & (truth == 0)] = 1
        strata_j = np.where(judge == 1, "USER", "ORIG")
        full[arm] = dict(o_judge=judge.astype(float), strata=strata_j, cluster=np.arange(n) // 10)
        hb = rng.choice(n, 300, replace=False)
        human[arm] = dict(o_judge=judge[hb].astype(float), o_human=truth[hb].astype(float), strata=strata_j[hb])
    r = ppi_difference(full, human, n_boot=200, seed=0)
    assert r["tau_judge"] > 0.03 and abs(r["tau_ppi"]) < 0.03 and r["ci95_ppi"][0] < r["tau_ppi"] < r["ci95_ppi"][1]
    assert arm_bias(full["arm1"]["o_judge"], full["arm1"]["strata"], human["arm1"]["o_judge"], human["arm1"]["o_human"], human["arm1"]["strata"]) > 0.02
    ss = specificity_sensitivity(["USER"] * 40 + ["ORIG"] * 60, ["USER"] * 38 + ["ORIG"] * 2 + ["USER"] * 6 + ["ORIG"] * 54)
    assert abs(ss["sensitivity"][0] - 0.95) < 1e-9 and abs(ss["specificity"][0] - 0.9) < 1e-9 and ss["specificity"][1] < 0.9 < ss["specificity"][2]
