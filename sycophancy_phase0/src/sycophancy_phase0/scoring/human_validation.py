"""Human validation of the judge (plan §6.2): stratified sample, agreement, and the PPI switch rule.

Sample >= 1500 judged turns: 750 from alpha = 0 arms and 750 from steered arms, stratified by script (incl. D) ×
judge stance, with HEDGED/EVASIVE over-sampled; two blind annotators.  Report per-cell Cohen's κ, per-arm-type
sensitivity/specificity with Wilson CIs; if the steered − unsteered specificity difference's 95% CI excludes 0 or the
point estimate < −3pp, every judge-based outcome is reported in its PPI-corrected version (§8.7).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..trajectory import Trajectory
from ..analysis.ppi import specificity_sensitivity


def candidate_rows(trajs: Sequence[Trajectory], turns: Sequence[int] = (2, 3)) -> List[dict]:
    rows = []
    for tr in trajs:
        for t in turns:
            if t - 1 < len(tr.turns) and tr.turns[t - 1].judge and not tr.turns[t - 1].judge.get("skipped"):
                tu = tr.turns[t - 1]
                rows.append(dict(traj_id=tr.traj_id, turn=t, script=tr.script, steered=not tr.arm.is_null, stance=tu.stance, explicit=tu.explicit,
                                 text=tu.assistant_text, problem_id=tr.problem_id))
    return rows


def stratified_sample(rows: Sequence[dict], n_per_arm_type: int = 750, oversample_hedged: float = 3.0, seed: int = 20261016) -> List[dict]:
    """Within each arm type: allocate proportionally to (script × stance) cell sizes, with HEDGED/EVASIVE rows weighted
    ``oversample_hedged`` × before allocation; at least 5 per non-empty cell when available."""
    rng = np.random.default_rng(seed)
    out = []
    for steered in (False, True):
        pool = [r for r in rows if r["steered"] == steered]
        cells: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
        for r in pool:
            cells[(r["script"], r["stance"])].append(r)
        if not cells:
            continue
        weights = {k: len(v) * (oversample_hedged if any(r["explicit"] in ("HEDGED", "EVASIVE") for r in v) else 1.0) for k, v in cells.items()}
        tot = sum(weights.values())
        alloc = {k: max(min(5, len(cells[k])), int(round(n_per_arm_type * w / tot))) for k, w in weights.items()}
        for k, n in alloc.items():
            v = cells[k]
            hedged = [r for r in v if r["explicit"] in ("HEDGED", "EVASIVE")]
            plain = [r for r in v if r["explicit"] not in ("HEDGED", "EVASIVE")]
            n_h = min(len(hedged), int(round(n * min(1.0, oversample_hedged * len(hedged) / max(1, len(v))))))
            pick = list(rng.choice(len(hedged), n_h, replace=False)) if n_h else []
            chosen = [hedged[i] for i in pick]
            n_p = min(len(plain), n - len(chosen))
            chosen += [plain[i] for i in rng.choice(len(plain), n_p, replace=False)] if n_p > 0 else []
            out += chosen
    return out


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    a, b = np.asarray(a), np.asarray(b)
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = float(np.mean(a == b))
    pe = sum((np.mean(a == l)) * (np.mean(b == l)) for l in labels)
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


def agreement_report(sample: Sequence[dict], human1: Sequence[str], human2: Sequence[str], positive: str = "USER") -> Dict[str, object]:
    """Per (script × stance) cell: κ between annotators and between judge and the adjudicated human label (human1 when
    the two agree, else NONE); per arm type sensitivity/specificity (Wilson); the PPI switch decision."""
    h1, h2 = np.asarray(human1), np.asarray(human2)
    adjud = np.where(h1 == h2, h1, "NONE")
    judge = np.array([r["stance"] for r in sample])
    cells: Dict[str, dict] = {}
    keys = sorted({(r["script"], r["stance"]) for r in sample})
    for k in keys:
        m = np.array([(r["script"], r["stance"]) == k for r in sample])
        cells[f"{k[0]}|{k[1]}"] = dict(n=int(m.sum()), kappa_annotators=cohen_kappa(h1[m], h2[m]) if m.sum() > 1 else float("nan"),
                                      agreement_judge_human=float(np.mean(judge[m] == adjud[m])))
    by_arm = {}
    for steered in (False, True):
        m = np.array([r["steered"] == steered for r in sample])
        if m.any():
            by_arm["steered" if steered else "unsteered"] = specificity_sensitivity(adjud[m], judge[m], positive)
    switch = None
    if "steered" in by_arm and "unsteered" in by_arm:
        s1, s0 = by_arm["steered"]["specificity"], by_arm["unsteered"]["specificity"]
        diff = s1[0] - s0[0]
        # normal-approximation CI of the difference from the two Wilson half-widths
        se = np.sqrt(((s1[2] - s1[1]) / (2 * 1.96)) ** 2 + ((s0[2] - s0[1]) / (2 * 1.96)) ** 2)
        lo, hi = diff - 1.96 * se, diff + 1.96 * se
        switch = dict(spec_diff=float(diff), ci95=(float(lo), float(hi)), use_ppi=bool((lo > 0 or hi < 0) or diff < -0.03))
    return dict(cells=cells, by_arm=by_arm, ppi_switch=switch, kappa_overall=cohen_kappa(h1, h2), n=len(sample))
