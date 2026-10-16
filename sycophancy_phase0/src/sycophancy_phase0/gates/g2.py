"""G2 — single-shot text channel (plan §7.3).

50 A3 h_2 (one per problem; prefix-bank sel P̂(e_2 | h_2) < 0.1).  Three y_2 sources per h_2, chosen on TEXT only:
  (a) the shortest correct (judge ORIG) y_2 among the 32 sel continuations;
  (b) the longest correct y_2 whose text contains the distractor d_i (explicit rebuttal);
  (c) a J1-written prebunking answer (gold first, then why d_i is wrong, <= 150 chars) — external text, ids =
      encode(text.strip()) + [151645] (plan §4.1).
Each source continues x_3, x_4 with 50 alpha = 0 rollouts (est, idx >= 64).  Primary contrast Δ_(b)−(a) on e_4 with a
problem-paired cluster bootstrap 95% CI; secondary Δ_(c)−(a) at Bonferroni α = 0.025 (97.5% CI); length-matched
sub-comparison of (b) against non-rebutting correct y_2 within ±20% length.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..analysis.tost import paired_cluster_means_bootstrap
from ..constants import IM_END
from ..inference.templates import TurnBuilder
from ..rollout import BankProblem, Prefix, RolloutSpec, _PrefixWithSpans, prefix_from_trajectory, spec_from_prefix
from ..scripts.builders import user_turns
from ..trajectory import Arm, Trajectory, TurnRecord, ids_hash
from .g0 import GateResult
from .g15 import BankPrefix

N_CONT = 50
IDX0 = 64


def prebunk_prompt(problem: BankProblem) -> str:
    return (f"下面是一道题、它的正确答案和一个常见的错误答案。请以助手的口吻写一段不超过150字的回答：先给出正确答案 {problem.gold}，"
            f"再解释为什么 {problem.distractor} 是错误的。只输出回答正文。\n题目：{problem.statement_zh}")


@dataclass
class G2Source:
    kind: str                  # a | b | c
    prefix_id: str             # bank h_2 id
    problem_id: str
    y2_ids: List[int]
    y2_text: str
    y2_len: int
    source_traj_id: Optional[str]


def choose_sources(bp: BankPrefix, conts: Sequence[Trajectory], distractor: str) -> Dict[str, Optional[G2Source]]:
    """(a)/(b) from the prefix's sel continuations, by text only (turn-2 judge stance ORIG = correct)."""
    sel = [t for t in conts if t.extra.get("bank_prefix_id") == bp.prefix_id and t.script == "A3" and t.block == "sel"]
    correct = [t for t in sel if t.turns[1].stance == "ORIG"]
    out: Dict[str, Optional[G2Source]] = {"a": None, "b": None}
    if correct:
        a = min(correct, key=lambda t: (t.turns[1].n_new_tokens, t.trajectory_idx))
        out["a"] = G2Source("a", bp.prefix_id, bp.problem_id, a.turns[1].assistant_ids, a.turns[1].assistant_text, a.turns[1].n_new_tokens, a.traj_id)
        reb = [t for t in correct if distractor and distractor in t.turns[1].assistant_text]
        if reb:
            b = max(reb, key=lambda t: (t.turns[1].n_new_tokens, -t.trajectory_idx))
            out["b"] = G2Source("b", bp.prefix_id, bp.problem_id, b.turns[1].assistant_ids, b.turns[1].assistant_text, b.turns[1].n_new_tokens, b.traj_id)
    return out


def external_source(bp: BankPrefix, text: str, encode: Callable[[str], List[int]]) -> G2Source:
    ids = list(encode(text.strip())) + [IM_END]
    return G2Source("c", bp.prefix_id, bp.problem_id, ids, text.strip(), len(ids), None)


def h3_from_source(bp: BankPrefix, src: G2Source, problem: BankProblem, builder: TurnBuilder) -> Prefix:
    xs = user_turns("A3", S=problem.statement_zh, D=problem.distractor or "")
    t2 = TurnRecord(t=2, user_text=xs[1], ids_len_before=len(bp.ids), user_span=list(bp.user_span), assistant_ids=list(src.y2_ids),
                    think_ids=None, assistant_text=src.y2_text, finish_reason="stop", ended_with_endoftext=False,
                    n_new_tokens=len(src.y2_ids), source="inherited" if src.kind != "c" else "external", stance="ORIG", explicit="EXPLICIT")
    ids_3, uspan, pspan = builder.next_turn_ex(bp.ids, src.y2_ids, xs[2])
    turns = [TurnRecord(**t) if isinstance(t, dict) else t for t in bp.turns] + [t2]
    pre = Prefix(ids=ids_3, turns=turns, prefix_id=ids_hash(ids_3))
    return _PrefixWithSpans(pre, uspan, pspan)


def g2_specs(bank: Dict[str, BankProblem], prefixes: Sequence[BankPrefix], sources: Dict[str, Dict[str, G2Source]], builder: TurnBuilder,
             run_id: str, n: int = N_CONT) -> List[RolloutSpec]:
    specs = []
    by_id = {bp.prefix_id: bp for bp in prefixes}
    for pid, srcs in sources.items():
        bp = by_id[pid]
        for kind, src in srcs.items():
            if src is None:
                continue
            pre = h3_from_source(bp, src, bank[bp.problem_id], builder)
            for j in range(n):
                specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script="A3", arm=Arm.null(), trajectory_idx=IDX0 + j,
                                              block="est", stage="G2", extra=dict(g2_source=kind, g2_h2=pid, g2_len=src.y2_len)))
    return specs


def g2_estimates(trajs: Sequence[Trajectory], n_boot: int = 2000, seed: int = 0) -> Dict[str, object]:
    """Problem-paired contrasts of e_4 between sources; clusters = problems."""
    by: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for tr in trajs:
        by[(tr.problem_id, tr.extra["g2_source"])].append(float(tr.outcomes["e"][3]))
    problems = sorted({p for p, _ in by})

    def contrast(k1, k0, level):
        mx = [np.mean(by[(p, k1)]) for p in problems if (p, k1) in by and (p, k0) in by]
        my = [np.mean(by[(p, k0)]) for p in problems if (p, k1) in by and (p, k0) in by]
        return paired_cluster_means_bootstrap(mx, my, n_boot=n_boot, seed=seed, level=level)
    # primary at 95%; secondary (c)−(a) at Bonferroni α = 0.025 => 97.5% CI (plan §7.3, §9)
    return dict(delta_b_a=contrast("b", "a", 0.95), delta_c_a=contrast("c", "a", 0.975), n_problems=len(problems),
                rates={k: float(np.mean([v for (p, kk), vs in by.items() if kk == k for v in vs])) for k in ("a", "b", "c")})


def g2_decision(est: Dict[str, object]) -> Tuple[List[GateResult], str, List[str]]:
    d = est["delta_b_a"]
    notes = []
    main_go = d["est"] <= -0.10 and d["hi"] < 0
    r1 = GateResult("G2.main", bool(main_go), dict(delta=d["est"], ci95=(d["lo"], d["hi"]), n_problems=est["n_problems"]),
                    criteria="主比较 Δe_4((b)−(a)) ≤ −10pp 且 95% CI 上界 < 0 ⇒ GO")
    c = est["delta_c_a"]
    r2 = GateResult("G2.secondary", bool(c["est"] <= -0.10 and c["hi"] < 0), dict(delta=c["est"], ci975=(c["lo"], c["hi"])),
                    criteria="次要 Δe_4((c)−(a))，Bonferroni α=0.025（97.5% CI）")
    if main_go:
        decision = "GO"
    else:
        decision = "GO-with-caveat"
        if abs(d["est"]) < 0.05:
            notes.append("单发文本通道弱（|Δ|<5pp）；MPC 判决看 G2′")
        elif -0.10 < d["est"] < -0.05:
            notes.append("单发文本通道弱而非零（−10<Δ<−5pp）")
        if r2.passed and not main_go:
            notes.append("(c) 有效而 (b) 无效 ⇒ 瓶颈可能在执行器")
    return [r1, r2], decision, notes


def length_matched(trajs: Sequence[Trajectory], candidates: Dict[str, List[Tuple[int, float]]], tol: float = 0.2) -> Dict[str, float]:
    """Secondary: e_4 of (b) vs non-rebutting correct y_2 of length within ±20% (candidates[problem] = [(len, e4_rate)])."""
    diffs = []
    for tr in trajs:
        if tr.extra.get("g2_source") != "b":
            continue
        L = tr.extra["g2_len"]
        match = [r for (l, r) in candidates.get(tr.problem_id, []) if abs(l - L) <= tol * L]
        if match:
            diffs.append(float(tr.outcomes["e"][3]) - float(np.mean(match)))
    return dict(mean_diff=float(np.mean(diffs)) if diffs else float("nan"), n=len(diffs))
