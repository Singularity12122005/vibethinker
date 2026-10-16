"""G6 — proposition 2: action-conditional heterogeneity under matched risk and policy regret (plan §7.11).

200 h_3 (LOFO): 100 type 1 (A1 wording; fixed y_2 shorter than the problem's bank median and without d_i) + 100 type 2
(A3 wording; y_2 contains an explicit rebuttal of d_i).  Each × alpha ∈ A × 32 (turn 3 steered, turn 4 alpha = 0), split
into fit/eval halves by subsplit (16 per arm each).
Matched-risk heterogeneity: logit P(CE_4) ~ prefix FE + d_cat + d_cat × type + d_cat × logit r̂^sel (prefix-cluster-robust
SE); statistic = [(d = 1) − (d = −1)] × type interaction, two-sided p < 0.05.
Regret: per prefix on the fit half, WLS logit p_i(d) = a_i + b_i d + γ_i d² (EB-shrunk b_i, γ_i), û_i* = argmin on the
shrunk curve of J = P(e_3 ∨ e_4) + λ_dose c(u); π_a*(a) = best arm per quintile bin of a = logit r̂^sel on the training
fold; both evaluated on the eval half; Regret_a = E_i[J(h_i, π_a*) − J(h_i, û_i*)].
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..analysis.factorial import dersimonian_laird, eb_shrink, empirical_logit
from ..analysis.glm import logit_fit, wald
from ..constants import ACTION_GRID, LAMBDA_DOSE_PRIMARY
from ..rollout import BankProblem, RolloutSpec, spec_from_prefix
from ..trajectory import Arm, Trajectory
from .g0 import GateResult
from .g15 import BankPrefix

N_PER_ARM, IDX0 = 32, 64


def g6_specs(bank: Dict[str, BankProblem], h3s: Sequence[Tuple[BankPrefix, int, float]], run_id: str, *, direction: str, layer: int, alpha_max: float,
             fold_of_problem: Dict[str, int], n: int = N_PER_ARM) -> List[RolloutSpec]:
    """h3s: (prefix, type in {1, 2}, r_hat_sel)."""
    specs = []
    for bp, typ, r_sel in h3s:
        pre = bp.to_prefix()
        for u in ACTION_GRID:
            arm = Arm.null() if u == 0 else Arm(u=[0, 0, u, 0], direction=direction, layer=layer, alpha_max=alpha_max, scope="S_gen",
                                                fold_version=fold_of_problem.get(bp.problem_id, 0))
            for j in range(n):
                specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script=bp.script, arm=arm, trajectory_idx=IDX0 + j,
                                              block="est", extra=dict(bank_prefix_id=bp.prefix_id, stage="g6", type=int(typ), r_sel=float(r_sel),
                                                                      u3=float(u), d=float(-u))))
    return specs


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return float(np.log(p / (1 - p)))


def matched_risk_interaction(trajs: Sequence[Trajectory]) -> Dict[str, object]:
    """Prefix FE + d_cat (5 levels, ref d = −1) + d_cat × type2 + d_cat × logit r̂^sel; test the (d=1 vs d=−1) × type contrast."""
    prefix = np.array([t.extra["bank_prefix_id"] for t in trajs])
    d = np.array([t.extra["d"] for t in trajs])
    typ2 = np.array([1.0 if t.extra["type"] == 2 else 0.0 for t in trajs])
    lr = np.array([_logit(t.extra["r_sel"]) for t in trajs])
    y = np.array([float(t.outcomes["CE"][3]) for t in trajs])
    ups = np.unique(prefix)
    levels = [lv for lv in ACTION_GRID if lv != -1.0]            # d levels; reference −1
    cols = [np.where(prefix == p, 1.0, 0.0) for p in ups]
    names = [f"fe_{p}" for p in ups]
    for lv in levels:
        ind = (d == -lv * -1.0) * 1.0 if False else (d == lv).astype(float)
        cols += [ind, ind * typ2, ind * lr]
        names += [f"d{lv:g}", f"d{lv:g}_x_type2", f"d{lv:g}_x_lr"]
    X = np.stack(cols, 1)
    fit = logit_fit(X, y, cluster=prefix)
    c = np.zeros(len(names)); c[names.index("d1_x_type2")] = 1.0
    w = wald(fit["beta"], fit["cov_robust"], c)
    return dict(interaction=w, n=int(len(y)), n_prefix=int(len(ups)), coef={n: float(b) for n, b in zip(names, fit["beta"]) if not n.startswith("fe_")})


def per_prefix_curves(trajs: Sequence[Trajectory], half: int, lam: float = LAMBDA_DOSE_PRIMARY) -> Dict[str, Dict[str, object]]:
    """On ``half``: per prefix the J(u) = P̂(e_3 ∨ e_4) + λ|u| per arm and a WLS quadratic logit fit p(d) = a + b d + γ d²."""
    acc: Dict[str, Dict[float, List[float]]] = defaultdict(lambda: defaultdict(list))
    meta = {}
    for t in trajs:
        if t.subsplit != half:
            continue
        acc[t.extra["bank_prefix_id"]][t.extra["d"]].append(float(max(t.outcomes["e"][2], t.outcomes["e"][3])))
        meta[t.extra["bank_prefix_id"]] = dict(type=t.extra["type"], r_sel=t.extra["r_sel"], problem_id=t.problem_id)
    out = {}
    for pid, by_d in acc.items():
        ds = np.array(sorted(by_d)); k = np.array([sum(by_d[x]) for x in ds]); K = np.array([len(by_d[x]) for x in ds])
        L, w = empirical_logit(k, K)
        X = np.stack([np.ones_like(ds), ds, ds ** 2], 1)
        W = np.sqrt(w)
        beta, *_ = np.linalg.lstsq(X * W[:, None], L * W, rcond=None)
        cov = np.linalg.pinv(X.T @ (X * w[:, None]))
        J = {float(x): float(np.mean(by_d[x]) + lam * abs(x)) for x in ds}
        out[pid] = dict(a=float(beta[0]), b=float(beta[1]), gamma=float(beta[2]), var_b=float(cov[1, 1]), var_gamma=float(cov[2, 2]), J=J, **meta[pid])
    return out


def shrunk_argmin(curves: Dict[str, Dict[str, object]], lam: float = LAMBDA_DOSE_PRIMARY) -> Dict[str, float]:
    """EB-shrink b_i and γ_i across prefixes (DL), then û_i* = argmin_d of sigmoid(a + b̃ d + γ̃ d²) + λ|d| over the grid."""
    pids = sorted(curves)
    b = np.array([curves[p]["b"] for p in pids]); vb = np.array([curves[p]["var_b"] for p in pids])
    g = np.array([curves[p]["gamma"] for p in pids]); vg = np.array([curves[p]["var_gamma"] for p in pids])
    db, dg = dersimonian_laird(b, vb), dersimonian_laird(g, vg)
    bt, gt = eb_shrink(b, vb, db["mu"], db["tau2"]), eb_shrink(g, vg, dg["mu"], dg["tau2"])
    out = {}
    for i, p in enumerate(pids):
        best, best_v = None, np.inf
        for d in ACTION_GRID:
            v = 1 / (1 + np.exp(-(curves[p]["a"] + bt[i] * d + gt[i] * d * d))) + lam * abs(d)
            if v < best_v:
                best, best_v = float(d), v
        out[p] = best
    return out


def quintile_policy(curves_fit: Dict[str, Dict[str, object]], n_bins: int = 5) -> Tuple[np.ndarray, Dict[int, float]]:
    """π_a*: per quintile bin of a = logit r̂^sel, the arm with the lowest mean J on the fit half."""
    pids = sorted(curves_fit)
    a = np.array([_logit(curves_fit[p]["r_sel"]) for p in pids])
    edges = np.quantile(a, np.linspace(0, 1, n_bins + 1))
    bins = np.clip(np.searchsorted(edges, a, side="right") - 1, 0, n_bins - 1)
    pol = {}
    for b in range(n_bins):
        members = [pids[i] for i in range(len(pids)) if bins[i] == b]
        if not members:
            continue
        best, best_v = None, np.inf
        for d in ACTION_GRID:
            v = np.mean([curves_fit[p]["J"].get(float(d), np.nan) for p in members])
            if v < best_v:
                best, best_v = float(d), v
        pol[b] = best
    return edges, pol


def regret(curves_fit: Dict[str, Dict[str, object]], curves_eval: Dict[str, Dict[str, object]], n_boot: int = 2000, seed: int = 0,
           lam: float = LAMBDA_DOSE_PRIMARY) -> Dict[str, object]:
    u_star = shrunk_argmin(curves_fit, lam)
    edges, pol = quintile_policy(curves_fit)
    pids = sorted(set(curves_fit) & set(curves_eval))
    per, problems = [], []
    for p in pids:
        a = _logit(curves_eval[p]["r_sel"])
        b = int(np.clip(np.searchsorted(edges, a, side="right") - 1, 0, len(edges) - 2))
        ua = pol.get(b, 0.0)
        Je = curves_eval[p]["J"]
        if float(ua) in Je and float(u_star[p]) in Je:
            per.append(Je[float(ua)] - Je[float(u_star[p])]); problems.append(curves_eval[p]["problem_id"])
    per = np.array(per); problems = np.array(problems)
    ups = np.unique(problems)
    rng = np.random.default_rng(seed)
    idx = {q: np.where(problems == q)[0] for q in ups}
    bs = np.array([per[np.concatenate([idx[q] for q in ups[rng.integers(0, len(ups), len(ups))]])].mean() for _ in range(n_boot)]) if per.size else np.array([])
    return dict(regret=float(per.mean()) if per.size else float("nan"), lower95=float(np.quantile(bs, 0.05)) if bs.size else float("nan"),
                upper95=float(np.quantile(bs, 0.95)) if bs.size else float("nan"), n_prefix=int(per.size), policy=pol, u_star=u_star)


def g6_decision(inter: Dict[str, object], reg: Dict[str, object], x4_drop_hi: float) -> Tuple[List[GateResult], str]:
    res = [GateResult("G6.interaction", bool(inter["interaction"]["p"] < 0.05), dict(est=inter["interaction"]["est"], p=inter["interaction"]["p"], n_prefix=inter["n_prefix"]),
                      criteria="[(d=1)−(d=−1)]×类型 交互对比，题目 cluster-robust SE，双侧 p<0.05"),
           GateResult("G6.regret", bool(reg["lower95"] > 0), dict(regret=reg["regret"], lower95=reg["lower95"], n_prefix=reg["n_prefix"]),
                      criteria="Regret_a(λ_dose=0.05) 的 cluster bootstrap 95% 下界 >0"),
           GateResult("G6.coprimary", bool(x4_drop_hi <= 0.03), dict(x4_drop_hi=x4_drop_hi), criteria="d=1 臂的 x_4 下降 95% 上界 ≤3pp")]
    if x4_drop_hi > 0.03:
        return res, "GREY"
    return res, ("GO" if (res[0].passed and res[1].passed) else "GO-with-caveat")
