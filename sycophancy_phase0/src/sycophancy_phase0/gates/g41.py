"""G4-1 — layer selection and alpha_max (plan §7.7).

1. For `v_cap` at each candidate layer: §4.7 step 1 (teacher-forced KL / route flip) -> provisional alpha^(1)_max,L.
2. 40 A3 h_3 × {alpha = 0, alpha = −alpha^(1)_max,L} × 16 turn-3 responses per layer; L* = layer with the largest
   paired e_3 drop (ties -> earlier layer).
3. Full §4.7 (steps 2–5) for `v_cap` at L*, L*±4 and for `v_cap⊥`, `v_warrant` (S_read) at L*; coarse grid only for
   LOFO version 0, other versions inherit alpha_max and report the fine-grid differences.  alpha_max < 0.2 => switch layer.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..analysis.tost import paired_cluster_bootstrap_diff
from ..inference.calibration import FINE_GRID, KL_MAX, FLIP_MAX
from ..rollout import BankProblem, RolloutSpec, spec_from_prefix
from ..trajectory import Arm, Trajectory
from .g15 import BankPrefix

N_H3, N_PER_ARM, IDX0 = 40, 16, 64


def provisional_alpha_max(fine: Dict[float, Dict[str, float]], kl_max: float = KL_MAX, flip_max: float = FLIP_MAX) -> float:
    """Largest grid alpha such that every grid point up to it satisfies the cheap criteria (step 1 only)."""
    a_max = 0.0
    for a in sorted(fine):
        if fine[a]["kl"] > kl_max or fine[a]["flip"] > flip_max:
            break
        a_max = a
    return a_max


def layer_screen_specs(bank: Dict[str, BankProblem], h3s: Sequence[BankPrefix], run_id: str, layer: int, alpha_max_L: float,
                       direction: str = "v_cap", fold_version: int = 0, n: int = N_PER_ARM) -> List[RolloutSpec]:
    """Two arms per h_3: u = (0,0,0,0) and u = (0,0,−1,0) with this layer's provisional alpha_max."""
    specs = []
    arm_neg = Arm(u=[0, 0, -1.0, 0], direction=direction, layer=layer, alpha_max=alpha_max_L, scope="S_gen", fold_version=fold_version)
    for bp in h3s:
        pre = bp.to_prefix()
        for arm in (Arm.null(), arm_neg):
            for j in range(n):
                specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script="A3", arm=arm, trajectory_idx=IDX0 + j,
                                              block="est", stop_after=3, extra=dict(bank_prefix_id=bp.prefix_id, stage="g41_screen", layer=layer)))
    return specs


def e3_drop_by_layer(trajs: Sequence[Trajectory], n_boot: int = 1000, seed: int = 0) -> Dict[int, Dict[str, float]]:
    """Paired (by h_3) e_3 contrast alpha=0 minus alpha=−alpha_max per screened layer."""
    by: Dict[Tuple[int, str, bool], List[float]] = defaultdict(list)
    for tr in trajs:
        by[(tr.extra["layer"], tr.extra["bank_prefix_id"], tr.arm.is_null)].append(float(tr.outcomes["e"][2]))
    layers = sorted({k[0] for k in by})
    out = {}
    for L in layers:
        pids = sorted({k[1] for k in by if k[0] == L})
        x, y, cl = [], [], []
        for i, p in enumerate(pids):
            a0, a1 = by.get((L, p, True), []), by.get((L, p, False), [])
            n = min(len(a0), len(a1))
            x += a0[:n]; y += a1[:n]; cl += [i] * n
        r = paired_cluster_bootstrap_diff(np.array(x), np.array(y), np.array(cl), n_boot=n_boot, seed=seed, level=0.95)
        out[L] = dict(drop=r["est"], ci95=(r["lo"], r["hi"]), n_h3=len(pids))
    return out


def select_layer(drops: Dict[int, Dict[str, float]]) -> int:
    best = max(drops.values(), key=lambda d: d["drop"])["drop"]
    return min(L for L, d in drops.items() if d["drop"] == best)      # ties -> earlier layer


def alpha_max_entry(direction: str, layer: int, fold: int, alpha_max: float, kappa1: Optional[float], fine: Dict[float, Dict[str, float]],
                    coarse: Optional[dict], details: dict) -> dict:
    return dict(direction=direction, layer=layer, fold_version=fold, alpha_max=alpha_max, kappa1=kappa1,
                fine_grid={str(a): v for a, v in fine.items()}, coarse=coarse, **details)
