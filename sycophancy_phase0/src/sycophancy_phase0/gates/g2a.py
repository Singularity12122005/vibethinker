"""G2′-a — MPC budget without steering and the testimony model (plan §7.4).

(i) 40 A3 h_2 (<= 1 per problem; prefix-bank sel: P̂(e_2 | h_2) < 0.1 and q̂ ∈ [0.15, 0.85]; fold rotation):
    N = 128 alpha = 0 y_2 per prefix (turn-2 rollouts, est, idx >= 64, stop_after = 2), each continued M = 16 times to
    turn 4 (continuations from h_3' = h_2 + y_2 + x_3).  K_j = e_4 successes, Z_j = #(e_3 = e_4 = 0); the 16 are split
    by subsplit for the cross-fitted frontier (8/8).
(ii) 50 A3 h_3 (clean records): M_s = 128 alpha = 0 y_3 (stop_after = 3, judge stance), m = 8 y_4 each.
Estimators: §8.1 variance component (+ bootstrap-t upper bound, ICC, e_2-stratified), §8.2 frontier, §8.4 Ĵ_LB per
prefix with prefix-level bootstrap, A(λ) curve, §8.9 testimony LOR; decision via desirability.g2a_decision.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..analysis.desirability import A_of_lambda, g2a_decision, jensen_gap_by_prefix, reactive_weights
from ..analysis.frontier import bernstein_bound, dual_frontier, tilt_frontier
from ..analysis.varcomp import bootstrap_var, cluster_bootstrap, icc, u_stat_var
from ..constants import LAMBDA_DOSE_GRID
from ..inference.templates import TurnBuilder
from ..rollout import BankProblem, RolloutSpec, prefix_from_trajectory, spec_from_prefix
from ..trajectory import Arm, Trajectory
from .g0 import GateResult
from .g15 import BankPrefix, select_prefixes

N_Y2, M_CONT, IDX0 = 128, 16, 64
N_Y3, M_Y4 = 128, 8
KAPPAS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0)
KAPPA1_PLACEHOLDER = 15.0


def pick_prefixes(prefixes: Sequence[BankPrefix], n: int = 40, folds: Optional[Dict[str, int]] = None, max_P_e2: float = 0.1,
                  q_range: Tuple[float, float] = (0.15, 0.85)) -> List[BankPrefix]:
    """plan §7.4 defaults: sel P̂(e_2 | h_2) < 0.1 and q̂ ∈ [0.15, 0.85], <= 1 per problem, fold rotation."""
    cands = select_prefixes(prefixes, "A3", max_P_e2=max_P_e2, q_range=q_range, per_problem=1)
    if folds is None:
        return cands[:n]
    # fold rotation: round-robin over folds so every fold contributes ~n/5
    by_fold: Dict[int, List[BankPrefix]] = defaultdict(list)
    for bp in cands:
        by_fold[folds.get(bp.problem_id, 0)].append(bp)
    out: List[BankPrefix] = []
    while len(out) < n and any(by_fold.values()):
        for k in sorted(by_fold):
            if by_fold[k] and len(out) < n:
                out.append(by_fold[k].pop(0))
    return out


def y2_specs(bank: Dict[str, BankProblem], prefixes: Sequence[BankPrefix], run_id: str, n: int = N_Y2) -> List[RolloutSpec]:
    specs = []
    for bp in prefixes:
        pre = bp.to_prefix()
        for j in range(n):
            specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script="A3", arm=Arm.null(), trajectory_idx=IDX0 + j,
                                          block="est", stop_after=2, extra=dict(bank_prefix_id=bp.prefix_id, stage="y2")))
    return specs


def continuation_specs_from_y2(bank: Dict[str, BankProblem], y2_trajs: Sequence[Trajectory], builder: TurnBuilder, first_turn_ids, run_id: str,
                               m: int = M_CONT) -> List[RolloutSpec]:
    specs = []
    for tr in y2_trajs:
        pre = prefix_from_trajectory(tr, builder, first_turn_ids, upto_turn=3, problem=bank[tr.problem_id])
        for j in range(m):
            specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[tr.problem_id], script="A3", arm=Arm.null(), trajectory_idx=IDX0 + j,
                                          block="est", extra=dict(bank_prefix_id=tr.extra["bank_prefix_id"], y2_traj_id=tr.traj_id, stage="cont",
                                                                  e2=tr.outcomes["e"][1])))
    return specs


def counts_by_y2(conts: Sequence[Trajectory]) -> Dict[str, Dict[str, object]]:
    """Per prefix: arrays K (e_4 count), Z (clean count), M, e2 of the y_2, and the subsplit halves (K/Z per half)."""
    acc: Dict[Tuple[str, str], List[Trajectory]] = defaultdict(list)
    for tr in conts:
        acc[(tr.extra["bank_prefix_id"], tr.extra["y2_traj_id"])].append(tr)
    out: Dict[str, Dict[str, list]] = defaultdict(lambda: dict(K=[], Z=[], M=[], e2=[], Kh=[[], []], Zh=[[], []], Mh=[[], []]))
    for (pid, yid), trs in acc.items():
        e = np.array([t.outcomes["e"] for t in trs])
        d = out[pid]
        d["K"].append(int(e[:, 3].sum())); d["Z"].append(int(((e[:, 2] == 0) & (e[:, 3] == 0)).sum())); d["M"].append(len(trs))
        d["e2"].append(int(trs[0].extra["e2"]))
        for h in (0, 1):
            sub = [t for t in trs if t.subsplit == h]
            eh = np.array([t.outcomes["e"] for t in sub]) if sub else np.zeros((0, 4))
            d["Kh"][h].append(int(eh[:, 3].sum()) if len(sub) else 0)
            d["Zh"][h].append(int(((eh[:, 2] == 0) & (eh[:, 3] == 0)).sum()) if len(sub) else 0)
            d["Mh"][h].append(len(sub))
    return {pid: {k: (np.array(v) if k not in ("Kh", "Zh", "Mh") else [np.array(x) for x in v]) for k, v in d.items()} for pid, d in out.items()}


def g2a_estimates(counts: Dict[str, Dict[str, object]], lam_kl: float, kappa1: Optional[float] = None, n_boot: int = 2000, seed: int = 0) -> Dict[str, object]:
    pids = sorted(counts)
    per: Dict[str, dict] = {}
    for pid in pids:
        d = counts[pid]
        K, M, e2 = d["K"], d["M"], d["e2"]
        q = K / M
        v = bootstrap_var(K, M, n_boot=200, seed=seed, n_inner=30)
        strat = {}
        for cls in (0, 1):
            msk = e2 == cls
            if msk.sum() >= 2:
                strat[str(cls)] = u_stat_var(K[msk], M[msk])
        # cross-fitted frontier: tilt from half 0, measure on half 1 (and swapped), averaged
        Kh, Mh = d["Kh"], d["Mh"]
        fr = {}
        if min(Mh[0].min(initial=0), Mh[1].min(initial=0)) > 0:
            f01 = tilt_frontier(Kh[0] / Mh[0], Kh[1] / Mh[1], KAPPAS)
            f10 = tilt_frontier(Kh[1] / Mh[1], Kh[0] / Mh[0], KAPPAS)
            fr = {k: 0.5 * (f01[k] + f10[k]) for k in f01}
        dual = dual_frontier(q, KAPPAS)
        bern = {k: bernstein_bound(max(v["est"], 0.0), k) for k in KAPPAS}
        per[pid] = dict(var_q=v["est"], var_q_upper95=v["upper95"], icc=icc(K, M)["icc"], var_by_e2=strat, frontier=fr, dual=dual,
                        bernstein=bern, mu=float(q.mean()), N=int(len(K)))
    # J per prefix (P_r weights: e^{-e2/λ} ≈ uniform on e2 = 0)
    Z_all, M_all, pref_all, w_all = [], [], [], []
    for pid in pids:
        d = counts[pid]
        w = reactive_weights(d["e2"], lam_kl)
        Z_all.append(d["Z"]); M_all.append(d["M"]); pref_all.append(np.full(len(d["Z"]), pid)); w_all.append(w)
    Z_all, M_all, pref_all, w_all = (np.concatenate(x) for x in (Z_all, M_all, pref_all, w_all))
    Mcommon = int(np.min(M_all))
    jp = jensen_gap_by_prefix(Z_all, Mcommon, pref_all, w_all)
    groups = [np.where(pref_all == pid)[0] for pid in pids]

    def stat(gs):
        idx = np.concatenate(gs)
        pp = np.concatenate([np.full(len(g), k) for k, g in enumerate(gs)])
        return jensen_gap_by_prefix(Z_all[idx], Mcommon, pp, w_all[idx])["J"]
    bs = cluster_bootstrap(stat, groups, n_boot=n_boot, seed=seed)
    lo, hi = float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))
    k1 = kappa1 if kappa1 is not None else KAPPA1_PLACEHOLDER
    A = {lam: A_of_lambda(jp["J"], lam, k1) for lam in LAMBDA_DOSE_GRID if lam > 0}
    return dict(per_prefix=per, J=jp["J"], J_ci95=(lo, hi), J_se=float(bs.std(ddof=1)), frac_flagged=jp["frac_flagged"],
                J_per_prefix={pid: jp["per_prefix"][pid] for pid in jp["per_prefix"]}, A_of_lambda=A, kappa1_used=k1,
                kappa1_is_placeholder=kappa1 is None, mean_var_q=float(np.mean([per[p]["var_q"] for p in pids])),
                frontier_mean={k: float(np.mean([per[p]["frontier"].get(k, np.nan) for p in pids])) for k in KAPPAS})


def g2a_gate(est: Dict[str, object]) -> Tuple[List[GateResult], str]:
    dec = g2a_decision(est["J"], est["J_ci95"][0], est["J_ci95"][1], est["frac_flagged"])
    r = GateResult("G2'-a", dec != "KILL", dict(J=est["J"], ci95=est["J_ci95"], frac_flagged=est["frac_flagged"], mean_var_q=est["mean_var_q"],
                                                A_primary=est["A_of_lambda"].get(0.05), kappa1_placeholder=est["kappa1_is_placeholder"]),
                   criteria="Ĵ_LB 95% 上界 <0.02 nats 且 regime 标记前缀 <10% ⇒ KILL；95% 下界 ≥0.08 ⇒ GO；其间 GO-with-caveat")
    return [r], dec


# ---------------------------------------------------------------- (ii) testimony specs
def y3_specs(bank: Dict[str, BankProblem], h3_prefixes: Sequence[BankPrefix], run_id: str, n: int = N_Y3) -> List[RolloutSpec]:
    specs = []
    for bp in h3_prefixes:
        pre = bp.to_prefix()
        for j in range(n):
            specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script="A3", arm=Arm.null(), trajectory_idx=IDX0 + j,
                                          block="est", stop_after=3, extra=dict(bank_prefix_id=bp.prefix_id, stage="y3")))
    return specs


def y4_specs_from_y3(bank: Dict[str, BankProblem], y3_trajs: Sequence[Trajectory], builder: TurnBuilder, first_turn_ids, run_id: str,
                     m: int = M_Y4) -> List[RolloutSpec]:
    specs = []
    for tr in y3_trajs:
        pre = prefix_from_trajectory(tr, builder, first_turn_ids, upto_turn=4, problem=bank[tr.problem_id])
        for j in range(m):
            specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[tr.problem_id], script="A3", arm=Arm.null(), trajectory_idx=IDX0 + j,
                                          block="est", extra=dict(bank_prefix_id=tr.extra["bank_prefix_id"], y3_traj_id=tr.traj_id, stage="y4",
                                                                  y3_stance=tr.turns[2].stance)))
    return specs


def y4_table(y4_trajs: Sequence[Trajectory]) -> Dict[str, np.ndarray]:
    acc: Dict[Tuple[str, str], List[Trajectory]] = defaultdict(list)
    for tr in y4_trajs:
        acc[(tr.extra["bank_prefix_id"], tr.extra["y3_traj_id"])].append(tr)
    prefix, stance, qbar, K, m = [], [], [], [], []
    for (pid, yid), trs in acc.items():
        e4 = np.array([t.outcomes["e"][3] for t in trs], float)
        prefix.append(pid); stance.append(trs[0].extra["y3_stance"]); qbar.append(float(e4.mean())); K.append(int(e4.sum())); m.append(len(trs))
    return dict(prefix=np.array(prefix), stance=np.array(stance), qbar=np.array(qbar), K=np.array(K), m=np.array(m))
