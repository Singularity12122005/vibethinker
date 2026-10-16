"""G5 — (u_2, u_3) factorial design, pilot then confirmation (plan §7.10).

Pilot 3×3 split-plot: 15 problems × 3 shared A3/C h_2 (prefix bank sel: P̂(e_2 | h_2) = 0/32, q̂ ∈ [0.15, 0.85]) = 45
prefixes; u_2 ∈ {−1, 0, 1}·alpha_max with K = 16 y_2 per cell (turn 2 steered); each y_2 is reused for the 3 u_3 cells and
continued under BOTH scripts A3 and C at turn 3 (steered) with u_4 = 0.  Y^S := 1 − 1[CE_3 ∧ CE_4].
u_3* = argmin_u [Ȳ^{A3}(0, u) + λ_dose c(u)] on the selection half (subsplit = 0), frozen; G evaluated on subsplit = 1.
G := 0.8[Ȳ^{A3}(0, u_3*) − Ȳ^{A3}(−1, u_3*)] − 0.2[Ȳ^C(−1, u_3*) − Ȳ^C(0, u_3*)]; problem-cluster bootstrap 95% CI.
Confirmation 5×5 with n = 16 per cell all evaluation (u_3* frozen).  Co-primary: x_4 drop under u_2 = −1 <= 3pp (upper).
Inoculation arm: A3, 50 problems × u_1 ∈ {0, −1}·alpha_max × 32, u_{2:4} = 0.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..analysis.factorial import G_statistic, select_u3_star
from ..analysis.tost import paired_cluster_means_bootstrap
from ..constants import ACTION_GRID, LAMBDA_DOSE_PRIMARY
from ..inference.templates import TurnBuilder
from ..rollout import BankProblem, RolloutSpec, Trajectory, prefix_from_trajectory, spec_from_prefix
from ..trajectory import Arm
from .g0 import GateResult
from .g15 import BankPrefix, select_prefixes

PILOT_GRID = (-1.0, 0.0, 1.0)
K_PILOT, N_CONFIRM, IDX0 = 16, 16, 64


def pick_pilot_prefixes(prefixes: Sequence[BankPrefix], n_problems: int = 15, per_problem: int = 3, c_pool: Optional[Sequence[str]] = None,
                        max_P_e2: float = 1e-9) -> List[BankPrefix]:
    """A3/C shared prefixes: the problem must be in the C pool (plan §7.10 '15 题 × 3 个 A3/C 共享前缀'); plan default
    P̂(e_2 | h_2) = 0/32 (``max_P_e2`` is only loosened for smoke runs)."""
    cands = select_prefixes(prefixes, "A3", max_P_e2=max_P_e2, q_range=(0.15, 0.85), per_problem=per_problem)
    if c_pool is not None:
        cset = set(c_pool)
        cands = [bp for bp in cands if bp.problem_id in cset]
    by_p: Dict[str, List[BankPrefix]] = defaultdict(list)
    for bp in cands:
        by_p[bp.problem_id].append(bp)
    full = [p for p in sorted(by_p) if len(by_p[p]) >= per_problem][:n_problems]
    return [bp for p in full for bp in by_p[p][:per_problem]]


def _arm(u2: float, u3: float, direction: str, layer: int, alpha_max: float, fold: int) -> Arm:
    if u2 == 0 and u3 == 0:
        return Arm.null()
    return Arm(u=[0, u2, u3, 0], direction=direction, layer=layer, alpha_max=alpha_max, scope="S_gen", fold_version=fold)


def y2_specs(bank: Dict[str, BankProblem], prefixes: Sequence[BankPrefix], run_id: str, *, u2_grid: Sequence[float], direction: str, layer: int,
             alpha_max: float, fold_of_problem: Dict[str, int], k: int = K_PILOT, stage: str = "G5_pilot") -> List[RolloutSpec]:
    """Turn-2 rollouts (stop_after = 2) per (prefix, u_2) — the whole-plot factor."""
    specs = []
    for bp in prefixes:
        pre = bp.to_prefix()
        for u2 in u2_grid:
            arm = _arm(u2, 0.0, direction, layer, alpha_max, fold_of_problem.get(bp.problem_id, 0))
            for j in range(k):
                specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script="A3", arm=arm, trajectory_idx=IDX0 + j, block="est",
                                              stop_after=2, stage=stage, extra=dict(bank_prefix_id=bp.prefix_id, stage="g5_y2", u2=float(u2))))
    return specs


def split_plot_specs(bank: Dict[str, BankProblem], y2_trajs: Sequence[Trajectory], builder: TurnBuilder, first_turn_ids, run_id: str, *,
                     u3_grid: Sequence[float], direction: str, layer: int, alpha_max: float, fold_of_problem: Dict[str, int],
                     scripts: Sequence[str] = ("A3", "C"), c_pool: Sequence[str] = (), stage: str = "G5_pilot") -> List[RolloutSpec]:
    """Each y_2 continues under every u_3 and both scripts (A3 and C share h_2; C has its own x_3/x_4).  One trajectory per
    (y_2, u_3, script): trajectory_idx inherits the y_2's index so subsplit (selection/evaluation half) follows the y_2."""
    specs = []
    cset = set(c_pool)
    for tr in y2_trajs:
        for sc in scripts:
            if sc == "C" and tr.problem_id not in cset:
                continue
            pre = prefix_from_trajectory(tr, builder, first_turn_ids, upto_turn=3, problem=bank[tr.problem_id], script=sc)
            for u3 in u3_grid:
                arm = _arm(tr.extra["u2"], u3, direction, layer, alpha_max, fold_of_problem.get(tr.problem_id, 0))
                specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[tr.problem_id], script=sc, arm=arm, trajectory_idx=tr.trajectory_idx,
                                              block="est", stage=stage, extra=dict(bank_prefix_id=tr.extra["bank_prefix_id"], y2_traj_id=tr.traj_id, stage="g5",
                                                                      u2=tr.extra["u2"], u3=float(u3))))
    return specs


def cell_outcomes(trajs: Sequence[Trajectory], half: Optional[int]) -> Dict[Tuple[str, float, float], np.ndarray]:
    """Y^S per (script, u2, u3) on the given subsplit half (None = all)."""
    out: Dict[Tuple[str, float, float], List[float]] = defaultdict(list)
    for tr in trajs:
        if half is not None and tr.subsplit != half:
            continue
        ce3, ce4 = tr.outcomes["CE"][2], tr.outcomes["CE"][3]
        out[(tr.script, float(tr.extra["u2"]), float(tr.extra["u3"]))].append(1.0 - float(ce3 and ce4))
    return {k: np.array(v) for k, v in out.items()}


def g5_estimate(trajs: Sequence[Trajectory], u3_star: Optional[float], lam: float = LAMBDA_DOSE_PRIMARY, n_boot: int = 2000, seed: int = 0,
                confirm: bool = False) -> Dict[str, object]:
    """Pilot: u_3* from subsplit 0, G from subsplit 1.  Confirmation: u_3* given (frozen), G from all trajectories."""
    if u3_star is None:
        sel = cell_outcomes(trajs, 0)
        u3_star = select_u3_star(sel, sorted({k[2] for k in sel if k[0] == "A3"}), lam)
    ev_trajs = [t for t in trajs if confirm or t.subsplit == 1]
    cells = cell_outcomes(ev_trajs, None)
    G = G_statistic(cells, u3_star)
    problems = sorted({t.problem_id for t in ev_trajs})
    rng = np.random.default_rng(seed)
    by_problem = {p: [t for t in ev_trajs if t.problem_id == p] for p in problems}
    bs = []
    for _ in range(n_boot):
        pick = [problems[i] for i in rng.integers(0, len(problems), len(problems))]
        c = cell_outcomes([t for p in pick for t in by_problem[p]], None)
        try:
            bs.append(G_statistic(c, u3_star))
        except KeyError:
            continue
    bs = np.array(bs)
    x4 = _x4_drop(ev_trajs, u3_star, n_boot, seed)
    return dict(G=G, ci95=(float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))) if bs.size else (float("nan"),) * 2, u3_star=u3_star,
                n_problems=len(problems), x4_drop=x4, cells={f"{k[0]}|u2={k[1]:g}|u3={k[2]:g}": float(v.mean()) for k, v in cells.items()})


def _x4_drop(trajs: Sequence[Trajectory], u3_star: float, n_boot: int, seed: int) -> Dict[str, float]:
    by: Dict[Tuple[str, float], List[float]] = defaultdict(list)
    for tr in trajs:
        if tr.script == "A3" and tr.extra["u3"] == u3_star and tr.extra["u2"] in (0.0, -1.0):
            by[(tr.problem_id, tr.extra["u2"])].append(float(tr.outcomes["x"][3]))
    problems = sorted({p for p, _ in by if (p, 0.0) in by and (p, -1.0) in by})
    return paired_cluster_means_bootstrap([np.mean(by[(p, 0.0)]) for p in problems], [np.mean(by[(p, -1.0)]) for p in problems],
                                          n_boot=n_boot, seed=seed, level=0.95)


def var_c_lrt(trajs: Sequence[Trajectory], u_grid: Sequence[float] = PILOT_GRID) -> Dict[str, object]:
    """plan §8.8 / §7.10: per-prefix WLS a_i − g_i u_3 − c_i u_2 − κ_i u_2 u_3 on the A3 Y^S cell counts (all rows), then the
    LRT of Var(c_i) = 0 with the sampling variances explicit; returns p, τ², the DL pooled c and the EB-shrunk c̃_i."""
    from ..analysis.factorial import dersimonian_laird, eb_shrink, fit_prefix, lrt_random_effect
    cells: Dict[str, Dict[Tuple[float, float], List[float]]] = defaultdict(lambda: defaultdict(list))
    for tr in trajs:
        if tr.script == "A3":
            ce3, ce4 = tr.outcomes["CE"][2], tr.outcomes["CE"][3]
            cells[tr.extra["bank_prefix_id"]][(float(tr.extra["u2"]), float(tr.extra["u3"]))].append(1.0 - float(ce3 and ce4))
    est, var, pids = [], [], []
    for pid, by in cells.items():
        keys = [(u2, u3) for u2 in u_grid for u3 in u_grid if (float(u2), float(u3)) in by]
        if len(keys) < 4:
            continue
        u2 = np.array([k[0] for k in keys]); u3 = np.array([k[1] for k in keys])
        k = np.array([sum(by[kk]) for kk in keys]); K = np.array([len(by[kk]) for kk in keys])
        f = fit_prefix(u2, u3, k, K)
        est.append(f["c"]); var.append(float(f["cov"][2, 2])); pids.append(pid)
    if len(est) < 3:
        return dict(p=None, tau2=None, n_prefix=len(est))
    est, var = np.array(est), np.array(var)
    lrt = lrt_random_effect(est, var)
    dl = dersimonian_laird(est, var)
    return dict(p=lrt["p"], tau2=lrt["tau2"], c_pooled=dl["mu"], c_se=dl["se"], c_tilde={p: float(v) for p, v in zip(pids, eb_shrink(est, var, dl["mu"], dl["tau2"]))},
                n_prefix=len(est))


def confirmation_F(trajs: Sequence[Trajectory], u3_star: float, delta: float = 0.05, n_cell: int = 16) -> Dict[str, object]:
    """plan §7.10 / §8.6: F_80 from the pilot's paired contrast d_fp = Ȳ^{A3}(0,u3*) − Ȳ^{A3}(−1,u3*) per (problem f, prefix p)."""
    from ..analysis.power import F_required, paired_components
    acc: Dict[Tuple[str, str, float], List[float]] = defaultdict(list)
    for tr in trajs:
        if tr.script == "A3" and tr.extra["u3"] == u3_star and tr.extra["u2"] in (0.0, -1.0):
            ce3, ce4 = tr.outcomes["CE"][2], tr.outcomes["CE"][3]
            acc[(tr.problem_id, tr.extra["bank_prefix_id"], float(tr.extra["u2"]))].append(1.0 - float(ce3 and ce4))
    by_problem: Dict[str, Dict[str, float]] = defaultdict(dict)
    vbars = []
    for (pid, pre, u2), vals in acc.items():
        if (pid, pre, 0.0) in acc and (pid, pre, -1.0) in acc and u2 == 0.0:
            a, b = np.array(acc[(pid, pre, 0.0)]), np.array(acc[(pid, pre, -1.0)])
            by_problem[pid][pre] = float(a.mean() - b.mean())
            n = min(len(a), len(b))
            if n > 1:
                vbars.append((a.mean() * (1 - a.mean()) + b.mean() * (1 - b.mean())) / (n - 1))
    P = min((len(v) for v in by_problem.values()), default=0)
    probs = [p for p, v in by_problem.items() if len(v) >= P and P > 0]
    if len(probs) < 2 or P < 2:                       # sigma_p^2 needs P >= 2 prefixes per problem (plan P = 3)
        return dict(F_80=None, reason="not enough problems/prefixes (need >= 2 problems with >= 2 paired prefixes)")
    d = np.array([[by_problem[p][pre] for pre in sorted(by_problem[p])[:P]] for p in probs])
    comp = paired_components(d, float(np.mean(vbars)) if vbars else 0.0)
    pbar = float(np.mean([np.mean(v) for (pid, pre, u2), v in acc.items()]))
    # plan §8.6: F_80 = 7.85 [σ²_{f,UB80} + σ²_p/P + 2 p̄(1−p̄)/(P n)] / δ² (+3 t correction)
    F80 = F_required(comp["sigma_f2_ub80"], comp["sigma_p2"], P=P, n=n_cell, delta=delta, pbar=pbar)
    return dict(F_80=F80, components=comp, P=P, n_problems_pilot=len(probs), pbar=pbar)


def g5_decision(est: Dict[str, object], var_c_lrt_p: Optional[float], confirm: bool = False) -> Tuple[List[GateResult], str]:
    lo = est["ci95"][0]
    go = est["G"] >= 0.05 and lo > 0
    res = [GateResult("G5.G", bool(go), dict(G=est["G"], ci95=est["ci95"], u3_star=est["u3_star"], n_problems=est["n_problems"]),
                      criteria="G ≥ 5pp 且 95% 下界 >0 ⇒ GO" + ("；否则 KILL（确认阶段无灰区）" if confirm else "；G<3pp 且 Var(c_i) LRT p>0.1 ⇒ KILL；其余 GREY"))]
    co_ok = est["x4_drop"]["hi"] <= 0.03 if est["x4_drop"]["n_clusters"] else True
    res.append(GateResult("G5.coprimary", bool(co_ok), dict(x4_drop=est["x4_drop"].get("est"), ci95=(est["x4_drop"].get("lo"), est["x4_drop"].get("hi"))),
                          criteria="u_2=−α_max 臂的 x_4 相对 u_2=0 的下降 95% 上界 ≤3pp，否则 GREY"))
    if not co_ok:
        return res, "GREY"
    if go:
        return res, "GO"
    if confirm:
        return res, "KILL"
    if est["G"] < 0.03 and var_c_lrt_p is not None and var_c_lrt_p > 0.1:
        return res, "KILL"
    return res, "GREY"
