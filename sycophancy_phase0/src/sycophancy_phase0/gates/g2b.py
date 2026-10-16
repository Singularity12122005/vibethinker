"""G2′-b — steering-class Var(V_3) (plan §7.8).

The 40 G2′-a prefixes, first 32 y_2 each; every y_2 gets u_3 ∈ A (direction v_cap⊥, layer L*, its alpha_max) × 16
rollouts (turn 3 steered on HF, turn 4 alpha = 0 on vLLM); the 16 per arm split into quarters Q1..Q4 by subsplit4.
V̂^(a)_j: arm chosen on Q1 by argmin_u [p̂(e_3 + e_4 | u) + λ_dose c(u)], evaluated on Q2; V̂^(b)_j: Q3 -> Q4.
Var(V_3) := Cov_j(V̂^(a), V̂^(b)) within prefix; prefix-level bootstrap one-sided 95% lower bound > 0 => GO.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

import numpy as np

from ..analysis.covvar import cluster_bootstrap_cov, policy_value_halves
from ..constants import ACTION_GRID, LAMBDA_DOSE_PRIMARY
from ..inference.templates import TurnBuilder
from ..rollout import BankProblem, RolloutSpec, prefix_from_trajectory, spec_from_prefix
from ..trajectory import Arm, Trajectory
from .g0 import GateResult

N_Y2, N_PER_ARM, IDX0 = 32, 16, 64


def g2b_specs(bank: Dict[str, BankProblem], y2_trajs: Sequence[Trajectory], builder: TurnBuilder, first_turn_ids, run_id: str, *, direction: str,
              layer: int, alpha_max: float, fold_of_problem: Dict[str, int], n_y2: int = N_Y2, n_per_arm: int = N_PER_ARM) -> List[RolloutSpec]:
    specs = []
    by_prefix: Dict[str, List[Trajectory]] = defaultdict(list)
    for tr in y2_trajs:
        by_prefix[tr.extra["bank_prefix_id"]].append(tr)
    for pid, trs in by_prefix.items():
        for tr in sorted(trs, key=lambda t: t.trajectory_idx)[:n_y2]:
            pre = prefix_from_trajectory(tr, builder, first_turn_ids, upto_turn=3, problem=bank[tr.problem_id])
            for u in ACTION_GRID:
                arm = Arm.null() if u == 0 else Arm(u=[0, 0, u, 0], direction=direction, layer=layer, alpha_max=alpha_max, scope="S_gen",
                                                    fold_version=fold_of_problem.get(tr.problem_id, 0))
                for j in range(n_per_arm):
                    specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[tr.problem_id], script="A3", arm=arm, trajectory_idx=IDX0 + j,
                                                  block="est", extra=dict(bank_prefix_id=pid, y2_traj_id=tr.traj_id, stage="g2b", u3=float(u))))
    return specs


def quarter_table(trajs: Sequence[Trajectory]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """p_hat[n_y2, n_arms, 4]: P̂(e_3 + e_4 | arm) per quarter (mean of e_3 + e_4, 0..2); cost[n_arms] = |u|; prefix per y_2."""
    acc: Dict[Tuple[str, str], Dict[Tuple[float, int], List[float]]] = defaultdict(lambda: defaultdict(list))
    for tr in trajs:
        acc[(tr.extra["bank_prefix_id"], tr.extra["y2_traj_id"])][(tr.extra["u3"], tr.subsplit4)].append(float(tr.outcomes["e"][2] + tr.outcomes["e"][3]))
    keys = sorted(acc)
    p_hat = np.full((len(keys), len(ACTION_GRID), 4), np.nan)
    for i, k in enumerate(keys):
        for a, u in enumerate(ACTION_GRID):
            for q in range(4):
                v = acc[k].get((float(u), q), [])
                if v:
                    p_hat[i, a, q] = float(np.mean(v))
    cost = np.abs(np.array(ACTION_GRID))
    prefix = np.array([k[0] for k in keys])
    return p_hat, cost, prefix, [k[1] for k in keys]


def g2b_estimate(trajs: Sequence[Trajectory], lam: float = LAMBDA_DOSE_PRIMARY, n_boot: int = 2000, seed: int = 0) -> Dict[str, object]:
    p_hat, cost, prefix, _ = quarter_table(trajs)
    ok = ~np.isnan(p_hat).any(axis=(1, 2))
    if ok.sum() == 0:
        raise ValueError("no y_2 has all 5 arms × 4 quarters (need >= 8 rollouts per arm so every subsplit4 quarter is filled)")
    p_hat, prefix = p_hat[ok], prefix[ok]
    Va, Vb = policy_value_halves(p_hat, cost, lam)
    r = cluster_bootstrap_cov(Va, Vb, prefix, n_boot=n_boot, seed=seed)
    return dict(**r, n_y2=int(ok.sum()), n_dropped=int((~ok).sum()), lam=lam)


def g2b_gate(est: Dict[str, object]) -> Tuple[List[GateResult], str]:
    ok = est["lower95_onesided"] > 0
    r = GateResult("G2'-b", bool(ok), dict(cov=est["est"], lower95=est["lower95_onesided"], se=est["se"], n_prefix=est["n_prefix"], n_y2=est["n_y2"]),
                   criteria="λ_dose=0.05 下 Cov(V̂^(a), V̂^(b)) 的前缀级 bootstrap 单侧 95% 下界 >0 ⇒ GO；否则 KILL MPC 臂")
    return [r], ("GO" if ok else "KILL")
