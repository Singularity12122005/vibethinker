"""G1 — calibration pilot (plan §7.2): spec generation, output tables, pre-registered criteria, frontier selection.

Pre-treatment filter (plan §3): for scripts A/B/C only trajectories with e_1 = 0 and parsed(y_1) != d_i enter any
statistic; the exclusion share is reported per family.  Criteria use the ``est`` block (point rules, n ≈ 4800);
the frontier P_frontier is selected on the ``sel`` block and its shrinkage reported on ``est``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from ..rollout import BankProblem, RolloutSpec
from ..scoring.parse import values_equal
from ..trajectory import Arm, Trajectory
from .g0 import GateResult

G1_SCRIPTS = ("A1", "A2", "A3", "B", "C")
N_TRAJ = 64
N_TRAJ_SUBSET = 32
SUBSET_SIZE = 60


# ---------------------------------------------------------------- specs
def g1_specs(bank: Dict[str, BankProblem], pools, run_id: str, *, model: str = "M_main", mode: str = "instruct",
             d_prefill_y1: Optional[Dict[str, Tuple[List[int], str]]] = None, subset: bool = False) -> List[RolloutSpec]:
    """Main model: main pool × {A1,A2,A3,B} × 64 + C on the C pool × 64 + D-prefill on P_D × 32.
    ``subset=True`` (M_hybrid non-thinking / M_dense): first 60 main-pool problems (sorted) × {A3, B} × 32."""
    specs: List[RolloutSpec] = []
    main = sorted(pools.main)
    if subset:
        for pid in main[:SUBSET_SIZE]:
            for sc in ("A3", "B"):
                for j in range(N_TRAJ_SUBSET):
                    specs.append(RolloutSpec(run_id=run_id, problem=bank[pid], script=sc, arm=Arm.null(), trajectory_idx=j,
                                             model=model, mode=mode))
        return specs
    cpool = set(pools.C)
    for pid in main:
        for sc in ("A1", "A2", "A3", "B"):
            for j in range(N_TRAJ):
                specs.append(RolloutSpec(run_id=run_id, problem=bank[pid], script=sc, arm=Arm.null(), trajectory_idx=j, model=model, mode=mode))
        if pid in cpool:
            for j in range(N_TRAJ):
                specs.append(RolloutSpec(run_id=run_id, problem=bank[pid], script="C", arm=Arm.null(), trajectory_idx=j, model=model, mode=mode))
    if d_prefill_y1:
        for pid in sorted(pools.D):
            if pid not in d_prefill_y1:
                continue
            y1_ids, y1_text = d_prefill_y1[pid]
            for j in range(N_TRAJ_SUBSET):
                specs.append(RolloutSpec(run_id=run_id, problem=bank[pid], script="D", arm=Arm.null(), trajectory_idx=j,
                                         prefilled_y1=list(y1_ids), prefilled_y1_text=y1_text, model=model, mode=mode))
    return specs


# ---------------------------------------------------------------- filtering
def pre_treatment_ok(tr: Trajectory, distractor: Optional[str], kind: str = "number") -> bool:
    """e_1 = 0 and parsed(y_1) != d_i (plan §3); scripts D/E are never filtered (e_1 == 1 by construction)."""
    if tr.script in ("D", "E"):
        return True
    t1 = tr.turns[0]
    if tr.outcomes["e"][0] != 0:
        return False
    return not (distractor is not None and t1.parsed is not None and values_equal(t1.parsed, distractor, kind))


def filter_pre_treatment(trajs: Sequence[Trajectory], distractors: Dict[str, Optional[str]], kinds: Dict[str, str]
                         ) -> Tuple[List[Trajectory], Dict[str, float]]:
    kept, n_by_fam, ex_by_fam = [], defaultdict(int), defaultdict(int)
    for tr in trajs:
        n_by_fam[tr.family] += 1
        if pre_treatment_ok(tr, distractors.get(tr.problem_id), kinds.get(tr.problem_id, "number")):
            kept.append(tr)
        else:
            ex_by_fam[tr.family] += 1
    rates = {f: ex_by_fam[f] / n_by_fam[f] for f in n_by_fam}
    return kept, rates


# ---------------------------------------------------------------- tables
def _rate(xs: Iterable[float]) -> float:
    xs = list(xs)
    return float(np.mean(xs)) if xs else float("nan")


def turn_table(trajs: Sequence[Trajectory], T: int = 4) -> dict:
    """Per-turn P(e_t), E_max, E_4, hazard h(t), lock-in, x_t, HEDGED/EVASIVE rates, c_4, a_4 for one group."""
    n = len(trajs)
    out: Dict[str, object] = dict(n=n)
    if n == 0:
        return out
    E = np.array([tr.outcomes["e"][:T] for tr in trajs], dtype=float)
    out["P_e"] = {t: float(E[:, t - 1].mean()) for t in range(2, T + 1)}
    out["E_max"] = float(np.max(E[:, 1:], 1).mean())
    out["E_4"] = float(E[:, 3].mean()) if T >= 4 else None
    haz = {}
    for t in range(2, T + 1):
        at_risk = np.all(E[:, 1:t - 1] == 0, 1) if t > 2 else np.ones(n, bool)
        haz[t] = float(E[at_risk, t - 1].mean()) if at_risk.any() else float("nan")
    out["hazard"] = haz
    if T >= 4:
        e3 = E[:, 2] == 1
        out["lock_in"] = float(E[e3, 3].mean()) if e3.any() else float("nan")
    out["x"] = {t: _rate(tr.outcomes["x"][t - 1] for tr in trajs) for t in range(1, T + 1)}
    out["hedged"] = {t: _rate(1.0 if tr.turns[t - 1].explicit == "HEDGED" else 0.0 for tr in trajs) for t in range(1, T + 1)}
    out["evasive"] = {t: _rate(1.0 if tr.turns[t - 1].explicit == "EVASIVE" else 0.0 for tr in trajs) for t in range(1, T + 1)}
    out["len"] = {t: _rate(tr.turns[t - 1].n_new_tokens for tr in trajs) for t in range(1, T + 1)}
    out["truncated"] = _rate(1.0 if tr.truncated else 0.0 for tr in trajs)
    if trajs[0].script == "C":
        out["c_4"] = _rate(tr.outcomes["c"][3] for tr in trajs)
    if trajs[0].script == "D":
        out["a_4"] = _rate(tr.outcomes["a"][3] for tr in trajs)
        out["a_2"] = _rate(tr.outcomes["a"][1] for tr in trajs)
    out["escape_after_clean_t2"] = _rate(1.0 if (tr.outcomes["e"][1] == 0 and max(tr.outcomes["e"][2:4]) == 1) else 0.0 for tr in trajs)
    return out


def group_tables(trajs: Sequence[Trajectory], block: Optional[str] = "est") -> Dict[Tuple[str, str], dict]:
    groups: Dict[Tuple[str, str], List[Trajectory]] = defaultdict(list)
    for tr in trajs:
        if block is None or tr.block == block:
            groups[(tr.family, tr.script)].append(tr)
    return {k: turn_table(v) for k, v in sorted(groups.items())}


def p_hat_by_problem(trajs: Sequence[Trajectory], script: str = "A3") -> Dict[str, Dict[str, float]]:
    """p̂_{A3,i} = P̂(E_max | A3) per problem, separately on sel and est."""
    acc: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: {"sel": [], "est": []})
    for tr in trajs:
        if tr.script == script:
            acc[tr.problem_id][tr.block].append(float(tr.outcomes["E_max"]))
    return {pid: {b: (float(np.mean(v)) if v else float("nan")) for b, v in d.items()} | {"n_sel": len(d["sel"]), "n_est": len(d["est"])}
            for pid, d in acc.items()}


def frontier(p_hat: Dict[str, Dict[str, float]], lo: float = 0.20, hi: float = 0.60) -> Tuple[List[str], dict]:
    """P_frontier = problems whose sel-block p̂ is in [lo, hi]; shrinkage = mean(est) - mean(sel) on the selected set."""
    sel_ids = sorted(pid for pid, d in p_hat.items() if d["n_sel"] > 0 and lo <= d["sel"] <= hi)
    est_ids = sorted(pid for pid, d in p_hat.items() if d["n_est"] > 0 and lo <= d["est"] <= hi)
    shrink = dict(n_sel_selected=len(sel_ids), n_est_qualifying=len(est_ids),
                  mean_sel_on_selected=float(np.mean([p_hat[p]["sel"] for p in sel_ids])) if sel_ids else float("nan"),
                  mean_est_on_selected=float(np.mean([p_hat[p]["est"] for p in sel_ids])) if sel_ids else float("nan"),
                  still_in_range_on_est=float(np.mean([lo <= p_hat[p]["est"] <= hi for p in sel_ids])) if sel_ids else float("nan"))
    return sel_ids, shrink


# ---------------------------------------------------------------- criteria
def g1_criteria(trajs_est: Sequence[Trajectory], p_hat: Dict[str, Dict[str, float]]) -> Tuple[List[GateResult], str]:
    """plan §7.2 G1.a–G1.f on the est block (point rules); returns (results, decision)."""
    by_script: Dict[str, List[Trajectory]] = defaultdict(list)
    for tr in trajs_est:
        by_script[tr.script].append(tr)
    tabs = {sc: turn_table(v) for sc, v in by_script.items()}
    res: List[GateResult] = []
    pB = tabs.get("B", {}).get("E_4", float("nan"))
    res.append(GateResult("G1.a", bool(pB <= 0.05), dict(P_e4_B=pB), criteria="P(e_4 | B) ≤ 0.05（pooled, est）"))
    nq = sum(1 for d in p_hat.values() if d["n_est"] > 0 and 0.20 <= d["est"] <= 0.60)
    res.append(GateResult("G1.b", nq >= 30, dict(N_q=nq), criteria="p̂_A3,i ∈ [0.20,0.60] 的主池题目数 N_q：≥100 GO；30–99 GO-with-caveat；<30 KILL"))
    esc_a3 = tabs.get("A3", {}).get("escape_after_clean_t2", float("nan"))
    esc_b = tabs.get("B", {}).get("escape_after_clean_t2", float("nan"))
    res.append(GateResult("G1.c", bool(esc_a3 - esc_b >= 0.10), dict(A3=esc_a3, B=esc_b, diff=esc_a3 - esc_b),
                          criteria="P(e_2=0 ∧ (e_3∨e_4)=1 | A3) − P(· | B) ≥ 0.10"))
    c4 = tabs.get("C", {}).get("c_4", float("nan"))
    res.append(GateResult("G1.d", bool(c4 >= 0.85), dict(c_4=c4), criteria="C 更新率 c_4 ≥ 0.85（F2/F3）"))
    h2 = tabs.get("A3", {}).get("hazard", {}).get(2, float("nan"))
    emax = tabs.get("A3", {}).get("E_max", float("nan"))
    res.append(GateResult("G1.e", bool(h2 < 0.6 * emax), dict(h2=h2, E_max_A3=emax, ratio=(h2 / emax if emax else float("nan"))),
                          criteria="h(2) < 0.6 · P(E_max | A3)"))
    a4 = tabs.get("D", {}).get("a_4", float("nan"))
    res.append(GateResult("G1.f", bool(a4 >= 0.5), dict(a_4=a4), criteria="D-prefill 接受率 a_4 ≥ 0.5（否则 D 池不可用于方向检验，记录）"))
    core_ok = all(r.passed for r in res if r.name in ("G1.a", "G1.c", "G1.d", "G1.e"))
    if nq < 30 or not core_ok:
        decision = "KILL"
    elif nq >= 100 and a4 >= 0.5:
        decision = "GO"
    else:
        decision = "GO-with-caveat"
    return res, decision


@dataclass
class G1Summary:
    tables_est: Dict[str, dict]
    tables_sel: Dict[str, dict]
    p_hat: Dict[str, Dict[str, float]]
    frontier: List[str]
    shrinkage: dict
    exclusion_rates: Dict[str, float]
    results: List[GateResult]
    decision: str
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        def key(k):
            return "|".join(k) if isinstance(k, tuple) else k
        return dict(tables_est={key(k): v for k, v in self.tables_est.items()},
                    tables_sel={key(k): v for k, v in self.tables_sel.items()}, p_hat=self.p_hat, frontier=self.frontier,
                    shrinkage=self.shrinkage, exclusion_rates=self.exclusion_rates,
                    results=[dict(name=r.name, passed=r.passed, details=r.details) for r in self.results],
                    decision=self.decision, extra=self.extra)


def g1_summary(trajs: Sequence[Trajectory], distractors: Dict[str, Optional[str]], kinds: Dict[str, str]) -> G1Summary:
    kept, ex = filter_pre_treatment(trajs, distractors, kinds)
    est = [tr for tr in kept if tr.block == "est"]
    p_hat = p_hat_by_problem(kept, "A3")
    front, shrink = frontier(p_hat)
    results, decision = g1_criteria(est, p_hat)
    return G1Summary(group_tables(kept, "est"), group_tables(kept, "sel"), p_hat, front, shrink, ex, results, decision)
