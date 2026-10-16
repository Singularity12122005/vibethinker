"""G4-0 — direction data and direction estimation (plan §7.6, §4.8).

60 A3 h_3 (12 per fold; e_1 = e_2 = 0) × 32 alpha = 0 turn-3 responses (stop_after = 3) + the corresponding D-prefill
h_3 × 32 (vLLM).  Then one clean teacher-forced forward per response (HF) reads the mean of the first 16 generated
tokens at every candidate layer; `v_cap`, `d_agree`, `v_cap⊥` follow per layer and per LOFO version; `v_press` and
`v_warrant` use the prefix bank's clean h_2 activations (R2 user_span means and R1 last-prompt-token rows).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..inference.directions import cosine_matrix, d_agree, lofo, orthogonalise, paired_problem_diff, save_direction, v_cap
from ..rollout import BankProblem, RolloutSpec, spec_from_prefix
from ..trajectory import Arm, Trajectory
from .g15 import BankPrefix

DIRECTION_LAYERS = (12, 16, 20, 24, 28, 32, 36)
N_PER_H3, N_H3, IDX0 = 32, 60, 64


def pick_h3(h3_prefixes: Sequence[BankPrefix], folds: Dict[str, int], n_per_fold: int = 12, n_folds: int = 5) -> List[BankPrefix]:
    by_fold: Dict[int, List[BankPrefix]] = defaultdict(list)
    for bp in sorted(h3_prefixes, key=lambda b: (b.problem_id, b.k)):
        if bp.script == "A3" and bp.level == 3:
            by_fold[folds.get(bp.problem_id, 0)].append(bp)
    out = []
    for k in range(n_folds):
        out += by_fold[k][:n_per_fold]
    return out


def turn3_specs(bank: Dict[str, BankProblem], h3s: Sequence[BankPrefix], run_id: str, n: int = N_PER_H3) -> List[RolloutSpec]:
    specs = []
    for bp in h3s:
        pre = bp.to_prefix()
        for j in range(n):
            specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script=bp.script, arm=Arm.null(), trajectory_idx=IDX0 + j,
                                          block="est", stop_after=3, extra=dict(bank_prefix_id=bp.prefix_id, stage="g40")))
    return specs


def activation_items(trajs: Sequence[Trajectory], prefix_ids: Dict[str, List[int]]) -> List[Tuple[List[int], List[int]]]:
    """(prompt_ids = h_3 ids, response_ids = y_3) pairs for first_k_token_means."""
    return [(prefix_ids[tr.extra["bank_prefix_id"]], tr.turns[2].assistant_ids) for tr in trajs]


def estimate_directions(acts_by_layer: Dict[int, np.ndarray], trajs: Sequence[Trajectory], folds: Dict[str, int], n_folds: int = 5,
                        min_per_class: int = 3) -> Dict[str, Dict[int, Dict[int, dict]]]:
    """acts_by_layer[L] rows aligned with trajs.  Returns {name: {layer: {fold: result}}} for v_cap, d_agree, v_cap_perp."""
    stances = np.array([tr.turns[2].stance for tr in trajs])
    prefix = np.array([tr.extra["bank_prefix_id"] for tr in trajs])
    script = np.array([tr.script for tr in trajs])
    item_folds = np.array([folds.get(tr.problem_id, 0) for tr in trajs])
    out: Dict[str, Dict[int, Dict[int, dict]]] = {"v_cap": {}, "d_agree": {}, "v_cap_perp": {}}
    for L, acts in acts_by_layer.items():
        a3 = script == "A3"
        vc = lofo(lambda m: v_cap(acts[m & a3], stances[m & a3], prefix[m & a3], min_per_class), item_folds, n_folds)
        da = lofo(lambda m: d_agree({sc: (acts[m & (script == sc)], stances[m & (script == sc)]) for sc in ("A3", "D")
                                     if (m & (script == sc)).any()}), item_folds, n_folds)
        out["v_cap"][L] = vc
        out["d_agree"][L] = da
        out["v_cap_perp"][L] = {k: dict(v=orthogonalise(vc[k]["v"], da[k]["v"]), cos_cap_agree=float(vc[k]["v"] @ da[k]["v"])) for k in vc}
    return out


def read_side_directions(h2_r2: Dict[str, Tuple[np.ndarray, List[str]]], h2_r1: Dict[str, Tuple[np.ndarray, List[str]]], folds: Dict[str, int],
                         n_folds: int = 5) -> Dict[str, Dict[int, dict]]:
    """h2_r2[script] = (rows of user_span means, problem ids) for scripts A3 and B -> v_press (A3 − B);
    h2_r1[script] = (last-prompt-token rows, problem ids) for A3 and D -> v_warrant (A3 − D).  One layer at a time."""
    def est_press(m_fn):
        A, pa = h2_r2["A3"]; B, pb = h2_r2["B"]
        ma, mb = m_fn(np.array(pa)), m_fn(np.array(pb))
        return paired_problem_diff(np.asarray(A)[ma], np.asarray(B)[mb], np.array(pa)[ma], np.array(pb)[mb])

    def est_warrant(m_fn):
        A, pa = h2_r1["A3"]; D, pd = h2_r1["D"]
        ma, md = m_fn(np.array(pa)), m_fn(np.array(pd))
        return paired_problem_diff(np.asarray(A)[ma], np.asarray(D)[md], np.array(pa)[ma], np.array(pd)[md])
    out = {"v_press": {}, "v_warrant": {}}
    for k in range(n_folds):
        keep = lambda pids, k=k: np.array([folds.get(p, 0) != k for p in pids])
        out["v_press"][k] = est_press(keep)
        if "D" in h2_r1 and len(h2_r1["D"][1]):
            out["v_warrant"][k] = est_warrant(keep)
    return out


def persist(root: str, dirs: Dict[str, Dict[int, Dict[int, dict]]]) -> Dict[str, object]:
    meta = {}
    for name, by_layer in dirs.items():
        for L, by_fold in by_layer.items():
            vs = [by_fold[k]["v"] for k in sorted(by_fold)]
            cm = cosine_matrix(vs)
            for k in sorted(by_fold):
                m = {kk: vv for kk, vv in by_fold[k].items() if kk != "v"}
                m["cosine_with_other_folds"] = cm[k].tolist()
                save_direction(root, name, L, k, by_fold[k]["v"], m)
            meta[f"{name}_L{L}"] = dict(min_cosine_between_folds=float(cm[np.triu_indices(len(vs), 1)].min()) if len(vs) > 1 else 1.0)
    return meta
