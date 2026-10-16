"""G1.5 — prefix bank (plan §7.2b, §5.5): construction of fixed h_2 / h_3 prefixes, their alpha = 0 continuations,
and the prefix-level quantities that every later gate reads (never from G1's independent trajectories).

Per frontier problem: from the G1 **A3 sel block**, by ascending trajectory_idx, K_pref = 4 trajectories with
parsed(y_1) = g_i; each y_1 yields h_2 for scripts {A1, A3, B} (C shares A3's h_2: same ids, own continuation);
D-prefill has one h_2 per problem (fixed wrong y_1).  Each h_2 gets 64 continuations (turns 2–4; sel even / est odd).
h_3: the first sel continuation (ascending idx) with e_2 = 0 (D-prefill: a_2 = 0); its prefix-level r̂(h_3) needs
32 further sel continuations when required.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..inference.templates import TurnBuilder
from ..rollout import BankProblem, Prefix, RolloutSpec, _PrefixWithSpans, prefix_from_trajectory, spec_from_prefix
from ..scoring.parse import values_equal
from ..scripts.builders import user_turns
from ..trajectory import Arm, Trajectory, TurnRecord, ids_hash

K_PREF = 4
N_CONT = 64
PREFIX_SCRIPTS = ("A1", "A3", "B")


@dataclass
class BankPrefix:
    prefix_id: str
    problem_id: str
    script: str                 # script whose x_2 (and later x_3) the prefix carries; "C" continuations reuse A3's h_2
    level: int                  # 2 => h_2 (ids fed to turn 2); 3 => h_3
    k: int                      # which of the K_pref y_1 (0-based); D-prefill: 0
    source_traj_id: Optional[str]
    ids: List[int]
    turns: List[dict]           # inherited TurnRecords as dicts
    user_span: List[int]
    prev_span: Optional[List[int]]
    parent_prefix_id: Optional[str] = None      # h_3 -> its h_2
    stats: dict = field(default_factory=dict)   # filled by bank_stats

    def to_prefix(self) -> Prefix:
        pre = Prefix(ids=list(self.ids), turns=[TurnRecord(**t) for t in self.turns], prefix_id=self.prefix_id)
        return _PrefixWithSpans(pre, tuple(self.user_span), tuple(self.prev_span) if self.prev_span else None)

    def to_json(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- h_2 construction
def select_y1_sources(g1_trajs: Sequence[Trajectory], problem_id: str, gold: str, kind: str, k_pref: int = K_PREF
                      ) -> List[Trajectory]:
    cands = [tr for tr in g1_trajs if tr.problem_id == problem_id and tr.script == "A3" and tr.block == "sel"
             and tr.turns[0].parsed is not None and values_equal(tr.turns[0].parsed, gold, kind)]
    cands.sort(key=lambda tr: tr.trajectory_idx)
    return cands[:k_pref]


def build_h2(problem: BankProblem, y1_traj: Trajectory, script: str, k: int, builder: TurnBuilder,
             first_turn_ids: Callable[[str], List[int]]) -> BankPrefix:
    xs = user_turns(script, S=problem.statement_zh, D=problem.distractor or "", G=problem.gold,
                    D2=problem.distractor2 or "", NOTE=problem.modification_note or "")
    ids_1 = list(first_turn_ids(xs[0]))
    t1 = y1_traj.turns[0]
    ids_2, uspan, pspan = builder.next_turn_ex(ids_1, t1.assistant_ids, xs[1])
    turn1 = {**vars(t1), "source": "inherited"}
    return BankPrefix(prefix_id=ids_hash(ids_2), problem_id=problem.problem_id, script=script, level=2, k=k,
                      source_traj_id=y1_traj.traj_id, ids=ids_2, turns=[turn1], user_span=list(uspan),
                      prev_span=list(pspan))


def build_h2_dprefill(problem: BankProblem, y1_ids: List[int], y1_text: str, builder: TurnBuilder,
                      first_turn_ids: Callable[[str], List[int]], parsed_y1: Optional[str]) -> BankPrefix:
    xs = user_turns("D", S=problem.statement_zh, G=problem.gold)
    ids_1 = list(first_turn_ids(xs[0]))
    span_1 = builder.first_turn_user_span(ids_1, xs[0])
    turn1 = dict(t=1, user_text=xs[0], ids_len_before=len(ids_1), user_span=list(span_1), assistant_ids=list(y1_ids),
                 think_ids=None, assistant_text=y1_text, finish_reason="stop", ended_with_endoftext=False,
                 n_new_tokens=len(y1_ids), source="prefilled", engine=None, alpha=0.0, parsed=parsed_y1,
                 stance="OTHER", explicit="EXPLICIT")
    ids_2, uspan, pspan = builder.next_turn_ex(ids_1, y1_ids, xs[1])
    return BankPrefix(prefix_id=ids_hash(ids_2), problem_id=problem.problem_id, script="D", level=2, k=0, source_traj_id=None,
                      ids=ids_2, turns=[turn1], user_span=list(uspan), prev_span=list(pspan))


def h2_prefixes(bank: Dict[str, BankProblem], frontier_ids: Sequence[str], g1_trajs: Sequence[Trajectory], builder: TurnBuilder,
                first_turn_ids: Callable[[str], List[int]], d_prefill: Optional[Dict[str, Tuple[List[int], str, Optional[str]]]] = None,
                d_pool: Sequence[str] = ()) -> List[BankPrefix]:
    """Identical y_1 token sequences (possible for short answers) collapse to one prefix: duplicates by prefix_id are
    skipped (the first k wins) and counted in ``h2_prefixes.n_dedup``."""
    out: List[BankPrefix] = []
    seen = set()
    n_dedup = 0
    for pid in sorted(frontier_ids):
        p = bank[pid]
        srcs = select_y1_sources(g1_trajs, pid, p.gold, p.kind)
        for k, tr in enumerate(srcs):
            for sc in PREFIX_SCRIPTS:
                bp = build_h2(p, tr, sc, k, builder, first_turn_ids)
                if bp.prefix_id in seen:
                    n_dedup += 1
                    continue
                seen.add(bp.prefix_id)
                out.append(bp)
        if d_prefill and pid in d_prefill and pid in set(d_pool):
            y1_ids, y1_text, parsed = d_prefill[pid]
            bp = build_h2_dprefill(p, y1_ids, y1_text, builder, first_turn_ids, parsed)
            if bp.prefix_id not in seen:
                seen.add(bp.prefix_id)
                out.append(bp)
    h2_prefixes.n_dedup = n_dedup   # type: ignore[attr-defined]
    return out


# ---------------------------------------------------------------- continuation specs
def continuation_specs(bank: Dict[str, BankProblem], prefixes: Sequence[BankPrefix], run_id: str, n: int = N_CONT, idx0: int = 0,
                       block: Optional[str] = None, scripts_for_a3: Sequence[str] = ("A3", "C"), c_pool: Sequence[str] = (),
                       model: str = "M_main", mode: str = "instruct", stage: str = "G15") -> List[RolloutSpec]:
    """One spec per (prefix, script, trajectory_idx).  A3 prefixes also serve script C (when the problem is in the
    C pool); the C continuation shares the ids of h_2 but has its own x_3/x_4."""
    specs: List[RolloutSpec] = []
    cset = set(c_pool)
    for bp in prefixes:
        scripts = [bp.script]
        if bp.script == "A3" and bp.level == 2:
            scripts = [s for s in scripts_for_a3 if s != "C" or bp.problem_id in cset]
        for sc in scripts:
            pre = bp.to_prefix()
            for j in range(n):
                specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script=sc, arm=Arm.null(),
                                              trajectory_idx=idx0 + j, block=block, model=model, mode=mode, stage=stage,
                                              extra=dict(bank_prefix_id=bp.prefix_id, bank_level=bp.level)))
    return specs


# ---------------------------------------------------------------- prefix-level quantities
def _stats(trs: Sequence[Trajectory], script: str) -> dict:
    n = len(trs)
    if n == 0:
        return dict(n=0)
    E = np.array([tr.outcomes["e"] for tr in trs], dtype=float)
    out = dict(n=n, P_e2=float(E[:, 1].mean()), q=float(E[:, 3].mean()), r=float(np.maximum(E[:, 2], E[:, 3]).mean()),
               P_e3=float(E[:, 2].mean()))
    if script == "D":
        A = np.array([tr.outcomes["a"] for tr in trs], dtype=float)
        out.update(P_a2=float(A[:, 1].mean()), a4=float(A[:, 3].mean()))
    if script == "C":
        C = np.array([[c if c is not None else np.nan for c in tr.outcomes["c"]] for tr in trs], dtype=float)
        out.update(c4=float(np.nanmean(C[:, 3])))
    return out


def bank_stats(prefixes: Sequence[BankPrefix], conts: Sequence[Trajectory]) -> None:
    """Fill ``stats`` per prefix: sel/est P̂(e_2|h_2), q̂, r̂ (and the subsplit halves of est for split-half reliability)."""
    by_pref: Dict[Tuple[str, str], List[Trajectory]] = defaultdict(list)
    for tr in conts:
        by_pref[(tr.extra.get("bank_prefix_id", tr.prefix_id), tr.script)].append(tr)
    for bp in prefixes:
        for sc in sorted({sc for (pid, sc) in by_pref if pid == bp.prefix_id}):
            trs = by_pref[(bp.prefix_id, sc)]
            st = dict(sel=_stats([t for t in trs if t.block == "sel"], sc), est=_stats([t for t in trs if t.block == "est"], sc),
                      est_half0=_stats([t for t in trs if t.block == "est" and t.subsplit == 0], sc),
                      est_half1=_stats([t for t in trs if t.block == "est" and t.subsplit == 1], sc))
            bp.stats[sc] = st


def select_h3(bp: BankPrefix, conts: Sequence[Trajectory], builder: TurnBuilder, first_turn_ids: Callable[[str], List[int]],
              script: Optional[str] = None) -> Optional[BankPrefix]:
    """h_3 = h_2 + first sel continuation (ascending idx) whose y_2 is clean: e_2 = 0 (D-prefill: a_2 = 0)."""
    sc = script or bp.script
    cands = sorted([t for t in conts if t.extra.get("bank_prefix_id") == bp.prefix_id and t.script == sc and t.block == "sel"],
                   key=lambda t: t.trajectory_idx)
    for tr in cands:
        # plan §7.2b: first e_2 = 0 **judge ORIG** y_2 (D-prefill: a_2 = 0, i.e. not USER, and a definite stance)
        st = tr.turns[1].stance
        clean = (tr.outcomes["a"][1] == 0 and st in ("ORIG", "OTHER")) if sc == "D" else (tr.outcomes["e"][1] == 0 and st == "ORIG")
        if not clean:
            continue
        pre = prefix_from_trajectory(tr, builder, first_turn_ids, upto_turn=3)
        return BankPrefix(prefix_id=pre.prefix_id, problem_id=bp.problem_id, script=sc, level=3, k=bp.k, source_traj_id=tr.traj_id,
                          ids=list(pre.ids), turns=[vars(t) for t in pre.turns], user_span=list(pre.user_span),
                          prev_span=list(pre.prev_span) if pre.prev_span else None, parent_prefix_id=bp.prefix_id)
    return None


def h3_sel_specs(bank: Dict[str, BankProblem], h3s: Sequence[BankPrefix], run_id: str, n: int = 32, model: str = "M_main",
                 mode: str = "instruct") -> List[RolloutSpec]:
    """plan §7.2b / v1.4 (memo D4): r̂(h_3) = P̂(e_3 ∨ e_4 | h_3) from 32 **selection-only** continuations of the fixed h_3,
    trajectory_idx = 0, 2, …, 62 with block "sel"; no est half.  These rows are never used to report an effect."""
    specs = []
    for bp in h3s:
        if bp.level != 3:
            continue
        pre = bp.to_prefix()
        for j in range(n):
            specs.append(spec_from_prefix(pre, run_id=run_id, problem=bank[bp.problem_id], script=bp.script, arm=Arm.null(), trajectory_idx=2 * j,
                                          block="sel", model=model, mode=mode, stage="G15_h3sel", extra=dict(bank_prefix_id=bp.prefix_id, bank_level=3)))
    return specs


def h3_stats(h3s: Sequence[BankPrefix], conts: Sequence[Trajectory]) -> None:
    """Fill stats[script] = {sel: {n, r, P_e3, q}, est: {...}} for level-3 prefixes from their own continuations."""
    by: Dict[Tuple[str, str], List[Trajectory]] = defaultdict(list)
    for tr in conts:
        if tr.extra.get("bank_level") == 3:
            by[(tr.extra["bank_prefix_id"], tr.script)].append(tr)
    for bp in h3s:
        for (pid, sc), trs in by.items():
            if pid != bp.prefix_id:
                continue
            bp.stats[sc] = dict(sel=_stats([t for t in trs if t.block == "sel"], sc), est=dict(n=0))


# ---------------------------------------------------------------- persistence
def write_bank(prefixes: Sequence[BankPrefix], path_jsonl: str) -> None:
    os.makedirs(os.path.dirname(path_jsonl) or ".", exist_ok=True)
    with open(path_jsonl, "w", encoding="utf-8") as f:
        for bp in prefixes:
            f.write(json.dumps(bp.to_json(), ensure_ascii=False) + "\n")
    try:  # plan names prefix_bank.parquet; the JSONL is the canonical copy
        import pyarrow as pa
        import pyarrow.parquet as pq
        rows = [dict(prefix_id=b.prefix_id, problem_id=b.problem_id, script=b.script, level=b.level, k=b.k,
                     parent_prefix_id=b.parent_prefix_id, n_ids=len(b.ids), stats=json.dumps(b.stats)) for b in prefixes]
        pq.write_table(pa.Table.from_pylist(rows), os.path.splitext(path_jsonl)[0] + ".parquet")
    except Exception:
        pass


def read_bank(path_jsonl: str) -> List[BankPrefix]:
    out = []
    with open(path_jsonl, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(BankPrefix(**json.loads(line)))
    return out


def select_prefixes(prefixes: Sequence[BankPrefix], script: str, *, level: int = 2, max_P_e2: Optional[float] = None,
                    q_range: Optional[Tuple[float, float]] = None, per_problem: Optional[int] = None,
                    folds: Optional[Dict[str, int]] = None, cont_script: Optional[str] = None) -> List[BankPrefix]:
    """Pre-treatment selection on the **sel** block only (plan §0.2 rule 1/2): P̂(e_2|h_2) < max, q̂ in range."""
    sc = cont_script or script
    out = []
    per: Dict[str, int] = defaultdict(int)
    for bp in sorted(prefixes, key=lambda b: (b.problem_id, b.k)):
        if bp.script != script or bp.level != level or sc not in bp.stats:
            continue
        s = bp.stats[sc]["sel"]
        if s.get("n", 0) == 0:
            continue
        if max_P_e2 is not None and not (s["P_e2"] < max_P_e2):
            continue
        if q_range is not None and not (q_range[0] <= s["q"] <= q_range[1]):
            continue
        if per_problem is not None and per[bp.problem_id] >= per_problem:
            continue
        per[bp.problem_id] += 1
        out.append(bp)
    return out
