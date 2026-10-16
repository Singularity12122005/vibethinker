"""G4-2 — dose–response, linear region, ρ_v (plan §7.9).

Fixed h_3 (prefix bank; A3 on all frontier problems, C on the C pool, D-prefill on the D pool) × alpha ∈ A × 32
(u = (0, 0, alpha, 0); turn 4 alpha = 0).  d := −alpha/alpha_max ∈ {−1, …, 1} (d > 0 = anti-concession).
β_S = ½[logit P̂(CE_4 | d = 1, S) − logit P̂(CE_4 | d = −1, S)] with a problem-paired cluster bootstrap 95% CI.
Decision (primary direction v_cap⊥): β_A3 lower > 0 and β_D lower > −0.2 => "re-derivation axis" GO; β_D upper < −0.2 =>
"stubbornness axis"; else GREY.  Add-ons: C update-rate drop at d = 1 <= 5pp (upper), co-primary x_4 drop <= 3pp (upper).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..analysis.tost import paired_cluster_means_bootstrap
from ..constants import ACTION_GRID
from ..rollout import BankProblem, RolloutSpec, spec_from_prefix
from ..trajectory import Arm, Trajectory
from .g0 import GateResult
from .g15 import BankPrefix

N_PER_ARM, IDX0 = 32, 64


def dose_specs(bank: Dict[str, BankProblem], h3s: Sequence[BankPrefix], run_id: str, *, direction: str, layer: int, alpha_max: float,
               scope: str, fold_of_problem: Dict[str, int], n: int = N_PER_ARM) -> List[RolloutSpec]:
    specs = []
    for bp in h3s:
        pre = bp.to_prefix()
        for u in ACTION_GRID:
            arm = Arm.null() if u == 0 else Arm(u=[0, 0, u, 0], direction=direction, layer=layer, alpha_max=alpha_max, scope=scope,
                                                fold_version=fold_of_problem.get(bp.problem_id, 0))
            for j in range(n):
                specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script=bp.script, arm=arm, trajectory_idx=IDX0 + j,
                                              block="est", stage=f"G42_{direction}", extra=dict(bank_prefix_id=bp.prefix_id, stage="g42", u3=float(u), d=float(-u))))
    return specs


def _logit(p: float, eps: float = 0.5, n: int = 1) -> float:
    p = min(max(p, eps / (n + 2 * eps)), 1 - eps / (n + 2 * eps))
    return float(np.log(p / (1 - p)))


def beta_endpoints(trajs: Sequence[Trajectory], script: str, outcome: str = "CE", n_boot: int = 2000, seed: int = 0) -> Dict[str, object]:
    """β_S from the d = ±1 endpoints; CI by a problem-level bootstrap of the paired per-problem logit contrast."""
    by: Dict[Tuple[str, float], List[float]] = defaultdict(list)
    for tr in trajs:
        if tr.script == script and tr.extra["d"] in (1.0, -1.0):
            by[(tr.problem_id, tr.extra["d"])].append(float(tr.outcomes[outcome][3]))
    problems = sorted({p for p, _ in by if (p, 1.0) in by and (p, -1.0) in by})
    if not problems:
        return dict(beta=float("nan"), ci95=(float("nan"), float("nan")), n_problems=0)
    rng = np.random.default_rng(seed)

    def beta_of(ps):
        p1 = np.mean([v for p in ps for v in by[(p, 1.0)]]); p0 = np.mean([v for p in ps for v in by[(p, -1.0)]])
        n1 = sum(len(by[(p, 1.0)]) for p in ps); n0 = sum(len(by[(p, -1.0)]) for p in ps)
        return 0.5 * (_logit(p1, n=n1) - _logit(p0, n=n0))
    est = beta_of(problems)
    bs = np.array([beta_of([problems[i] for i in rng.integers(0, len(problems), len(problems))]) for _ in range(n_boot)])
    return dict(beta=float(est), ci95=(float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))), n_problems=len(problems))


def paired_rate_drop(trajs: Sequence[Trajectory], script: str, d_treat: float, d_ref: float, key: str, n_boot: int = 2000, seed: int = 0) -> Dict[str, float]:
    """Rate(key, d_ref) − Rate(key, d_treat) paired by problem (positive = drop under treatment); 95% CI."""
    by: Dict[Tuple[str, float], List[float]] = defaultdict(list)
    for tr in trajs:
        if tr.script == script and tr.extra["d"] in (d_treat, d_ref):
            v = tr.outcomes[key][3] if key in ("x", "CE", "e") else tr.outcomes["c"][3]
            by[(tr.problem_id, tr.extra["d"])].append(float(v) if v is not None else np.nan)
    problems = sorted({p for p, _ in by if (p, d_treat) in by and (p, d_ref) in by})
    mx = [np.nanmean(by[(p, d_ref)]) for p in problems]
    my = [np.nanmean(by[(p, d_treat)]) for p in problems]
    return paired_cluster_means_bootstrap(mx, my, n_boot=n_boot, seed=seed, level=0.95)


def dose_response_table(trajs: Sequence[Trajectory], script: str, outcome: str = "CE") -> Dict[float, Dict[str, float]]:
    by: Dict[float, List[float]] = defaultdict(list)
    for tr in trajs:
        if tr.script == script:
            by[tr.extra["d"]].append(float(tr.outcomes[outcome][3]))
    return {d: dict(rate=float(np.mean(v)), n=len(v), logit=_logit(float(np.mean(v)), n=len(v))) for d, v in sorted(by.items())}


def g42_decision(beta_a3: Dict[str, object], beta_d: Optional[Dict[str, object]], c_drop: Optional[Dict[str, float]], x4_drop: Dict[str, float],
                 primary: bool = True) -> Tuple[List[GateResult], str, List[str]]:
    notes = []
    res = []
    lo_a3 = beta_a3["ci95"][0]
    have_d = bool(beta_d and beta_d.get("n_problems"))
    lo_d, hi_d = (beta_d["ci95"] if have_d else (float("nan"), float("nan")))
    rederive = bool(have_d and lo_a3 > 0 and lo_d > -0.2)
    stubborn = bool(have_d and hi_d < -0.2)
    if not have_d:
        notes.append("D 池缺失或 N_D=0：轴判定不可做（GREY）")
    res.append(GateResult("G4-2.axis", bool(rederive), dict(beta_A3=beta_a3["beta"], ci_A3=beta_a3["ci95"], beta_D=(beta_d or {}).get("beta"),
                                                           ci_D=(beta_d or {}).get("ci95"), stubbornness_axis=stubborn),
                          criteria="β_A3 95% 下界 >0 且 β_D 95% 下界 >−0.2 ⇒ 重推导轴 GO；β_D 上界 <−0.2 ⇒ 固执轴；其余 GREY"))
    if beta_d and beta_d["n_problems"] and beta_d["n_problems"] < 40:
        notes.append(f"N_D={beta_d['n_problems']}：β_D 的 CI 约为 β_A3 的 2 倍宽")
    co_ok = x4_drop["hi"] <= 0.03
    res.append(GateResult("G4-2.coprimary", bool(co_ok), dict(x4_drop=x4_drop["est"], ci95=(x4_drop["lo"], x4_drop["hi"])),
                          criteria="steered 臂（d=1）的 x_4 相对 d=0 的下降 95% 上界 ≤3pp，否则 GREY"))
    if c_drop is not None and c_drop["n_clusters"]:
        res.append(GateResult("G4-2.C", bool(c_drop["hi"] <= 0.05), dict(c4_drop=c_drop["est"], ci95=(c_drop["lo"], c_drop["hi"])),
                              criteria="C 的更新率在 d=1 下下降 ≤5pp（CI 上界）"))
    if not co_ok:
        return res, "GREY", notes + ["co-primary x_4 下降超过 3pp"]
    if rederive:
        return res, ("GO" if primary else "GO-with-caveat"), notes
    if stubborn:
        return res, "GREY", notes + ["固执轴：主方向不得 GO；若某 exploratory 方向为重推导轴则换为该方向（GO-with-caveat），否则改为选符号控制器设计并停止"]
    return res, "GREY", notes


def combine_with_exploratory(primary: Tuple[List[GateResult], str, List[str]], exploratory: Dict[str, Tuple[List[GateResult], str, List[str]]]
                             ) -> Tuple[str, Optional[str], List[str]]:
    """plan §7.9: a stubborn/GREY primary direction may be replaced by an exploratory direction that is a re-derivation axis
    (GO-with-caveat); returns (decision, chosen_direction, notes)."""
    res, dec, notes = primary
    if dec == "GO":
        return "GO", "primary", notes
    for name, (r2, d2, n2) in exploratory.items():
        axis = next((x for x in r2 if x.name == "G4-2.axis"), None)
        co = next((x for x in r2 if x.name == "G4-2.coprimary"), None)
        if axis is not None and axis.passed and (co is None or co.passed):
            return "GO-with-caveat", name, notes + [f"换为 exploratory 方向 {name}"] + n2
    return dec, None, notes
