"""Batched multi-turn rollouts (plan §4.1–§4.3, §5.5, §10.2).

One ``RolloutSpec`` = one trajectory.  All specs advance in lock-step turn by turn so that every generation
call is a large batch: at turn t the requests are routed by alpha (steered -> HF, alpha = 0 -> vLLM/HF).

Prefix handling
---------------
* fresh:        ids_1 = ``first_turn_ids(x_1)`` (tokenizer.apply_chat_template path, §4.1);  prefix_id = H(ids_1)
* D-prefill:    turn 1 is the fixed wrong y_1 (``prefilled_y1``), ids_2 built from it;          prefix_id = H(ids_2)
* continuation: ``root`` carries ids_t and the inherited turn records of h_t;                   prefix_id = H(ids_t)

Scoring (plan §6): turn 1 and the final turn are parsed deterministically; turns 2..T-1 get rule labels and,
when a judge is supplied, judge labels (final label = judge).  Outcomes come from ``scoring.labels.outcomes``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .constants import IM_END, MAX_NEW_TOKENS, MAX_NEW_TOKENS_THINK
from .inference.engine import GenRequest, GenResult
from .inference.sampling import derive_seed
from .inference.templates import TurnBuilder
from .scoring.labels import Problem, comparison_values, outcomes
from .scoring.parse import canonical, classify_final, is_hedged, parse_final_answer, rule_stance, values_equal
from .scripts.builders import user_turns
from .trajectory import (Arm, Trajectory, TurnRecord, block_of, ids_hash, subsplit4_of, subsplit_of, traj_id_of)


@dataclass
class BankProblem:
    problem_id: str
    family: str                      # F1 | F2 | F3
    statement_zh: str
    gold: str
    gold_type: str = "integer"       # integer | rational | string
    distractor: Optional[str] = None
    distractor2: Optional[str] = None
    modified_statement_zh: Optional[str] = None
    modified_gold: Optional[str] = None
    modification_note: Optional[str] = None
    y1_parsed: Optional[str] = None  # D/E: the model's own wrong first answer (filled by the runner for D-prefill)

    @property
    def kind(self) -> str:
        return "string" if self.gold_type == "string" else "number"

    def to_problem(self) -> Problem:
        return Problem(gold=self.gold, distractor=self.distractor or "", distractor2=self.distractor2,
                       modified_gold=self.modified_gold, y1_parsed=self.y1_parsed, kind=self.kind)

    def statement_for_turn(self, script: str, t: int) -> str:
        return self.modified_statement_zh if (script == "C" and t >= 3) else self.statement_zh


@dataclass
class Prefix:
    """A fixed prefix h_t: the ids fed to turn t plus the inherited turn records 1..t-1."""
    ids: List[int]
    turns: List[TurnRecord]
    prefix_id: Optional[str] = None

    def __post_init__(self):
        if self.prefix_id is None:
            self.prefix_id = ids_hash(self.ids)

    @property
    def next_turn(self) -> int:
        return len(self.turns) + 1


@dataclass
class RolloutSpec:
    run_id: str
    problem: BankProblem
    script: str
    arm: Arm
    trajectory_idx: int
    block: Optional[str] = None                 # None -> parity rule (G1/G1.5); later gates pass "est"
    root: Optional[Prefix] = None               # continuation of a bank prefix
    prefilled_y1: Optional[List[int]] = None    # D-prefill: normalised ids of the fixed wrong y_1
    prefilled_y1_text: Optional[str] = None
    model: str = "M_main"
    regime: str = "recompute+S_gen"
    mode: str = "instruct"                      # instruct | hybrid_nothink | hybrid_think
    max_new_tokens: Optional[int] = None
    config_sha256: str = ""
    T: int = 4
    stop_after: Optional[int] = None            # generate turns <= stop_after only (partial trajectory; e.g. y_2 sampling)
    extra: dict = field(default_factory=dict)


@dataclass
class _State:
    spec: RolloutSpec
    ids: List[int]
    turns: List[TurnRecord]
    prefix_id: str
    seeds: List[Optional[int]]
    user_span: Tuple[int, int]
    prev_span: Optional[Tuple[int, int]]
    xs: List[str]
    t_next: int
    t0: float


FirstTurnIds = Callable[[str], List[int]]         # x_1 -> ids_1 (apply_chat_template path)
Decode = Callable[[Sequence[int]], str]           # ids -> text with skip_special_tokens=True
JudgeFn = Callable[[List[dict]], List[dict]]      # items with S,G_eff,X,G_orig,Y -> labels
ZFn = Callable[[List[List[int]], List[Tuple[int, int]], List[Optional[Tuple[int, int]]]], List[dict]]


def _placeholders(p: BankProblem) -> dict:
    return dict(S=p.statement_zh, D=p.distractor or "", G=p.gold, D2=p.distractor2 or "", NOTE=p.modification_note or "")


def _init_state(spec: RolloutSpec, builder: TurnBuilder, first_turn_ids: FirstTurnIds, decode: Decode) -> _State:
    xs = user_turns(spec.script, **_placeholders(spec.problem))
    if len(xs) != spec.T:
        raise ValueError(f"script {spec.script} has {len(xs)} turns, spec.T={spec.T}")
    t0 = time.time()
    if spec.root is not None:
        st = _State(spec, list(spec.root.ids), [TurnRecord(**{**vars(tr), "source": "inherited"}) for tr in spec.root.turns],
                    spec.root.prefix_id, [None] * spec.T, (0, 0), None, xs, spec.root.next_turn, t0)
        # spans of the root's current turn (needed for R2/R3 pooling) travel in spec.extra (see spec_from_prefix)
        st.user_span = tuple(spec.extra.get("root_user_span") or (0, 0))
        st.prev_span = tuple(spec.extra["root_prev_span"]) if spec.extra.get("root_prev_span") else None
        return st
    ids_1 = list(first_turn_ids(xs[0]))
    span_1 = builder.first_turn_user_span(ids_1, xs[0])
    if spec.prefilled_y1 is not None:
        if spec.script not in ("D",):
            raise ValueError("prefilled_y1 is only defined for script D (plan §5.3)")
        y1 = list(spec.prefilled_y1)
        if y1[-1] != IM_END:
            raise ValueError("prefilled_y1 must be normalised (end with <|im_end|>)")
        text1 = spec.prefilled_y1_text if spec.prefilled_y1_text is not None else decode(y1[:-1])
        tr1 = TurnRecord(t=1, user_text=xs[0], ids_len_before=len(ids_1), user_span=list(span_1), assistant_ids=y1,
                         think_ids=None, assistant_text=text1, finish_reason="stop", ended_with_endoftext=False,
                         n_new_tokens=len(y1), source="prefilled", engine=None, alpha=0.0)
        ids_2, span_2, prev_2 = builder.next_turn_ex(ids_1, y1, xs[1])
        return _State(spec, ids_2, [tr1], ids_hash(ids_2), [None] * spec.T, span_2, prev_2, xs, 2, t0)
    return _State(spec, ids_1, [], ids_hash(ids_1), [None] * spec.T, span_1, None, xs, 1, t0)


def run_rollouts(specs: Sequence[RolloutSpec], *, builder: TurnBuilder, router, first_turn_ids: FirstTurnIds,
                 decode: Decode, judge: Optional[JudgeFn] = None, judge2: Optional[JudgeFn] = None,
                 z_fn: Optional[ZFn] = None, z_turns: Sequence[int] = (2, 3), writer=None, zstore=None,
                 progress: Optional[Callable[[str], None]] = None) -> List[Trajectory]:
    """Advance all specs turn by turn; returns finished trajectories (also written to ``writer`` if given)."""
    states = [_init_state(s, builder, first_turn_ids, decode) for s in specs]
    T_max = max(s.T for s in specs) if specs else 0
    z_pending: List[Tuple[int, int, List[int], Tuple[int, int], Optional[Tuple[int, int]]]] = []  # (state idx, t, ids, uspan, pspan)
    for t in range(1, T_max + 1):
        active = [i for i, st in enumerate(states) if st.t_next == t and t <= st.spec.T and (st.spec.stop_after is None or t <= st.spec.stop_after)]
        if not active:
            continue
        reqs: List[GenRequest] = []
        for i in active:
            st = states[i]
            if t in z_turns:
                z_pending.append((i, t, list(st.ids), st.user_span, st.prev_span))
            alpha = st.spec.arm.alpha_at(t)
            seed = derive_seed(st.spec.run_id, st.spec.problem.problem_id, st.prefix_id, st.spec.arm.arm_id(),
                               st.spec.trajectory_idx, t)
            st.seeds[t - 1] = seed
            mnt = st.spec.max_new_tokens or (MAX_NEW_TOKENS_THINK if st.spec.mode == "hybrid_think" else MAX_NEW_TOKENS)
            reqs.append(GenRequest(ids=list(st.ids), seed=seed, alpha=alpha, max_new_tokens=mnt))
        if progress:
            progress(f"turn {t}: {len(reqs)} requests")
        results: List[GenResult] = router.generate(reqs)
        for i, req, res in zip(active, reqs, results):
            st = states[i]
            norm = builder.normalize(res.ids, res.finish_reason)
            text = decode(norm.ids[:-1])
            tr = TurnRecord(t=t, user_text=st.xs[t - 1], ids_len_before=len(st.ids), user_span=list(st.user_span),
                            assistant_ids=norm.ids, think_ids=norm.think_ids, assistant_text=text,
                            finish_reason=norm.finish_reason, ended_with_endoftext=norm.ended_with_endoftext,
                            n_new_tokens=len(norm.ids), source="generated", engine=res.engine, alpha=req.alpha,
                            prev_assistant_span=list(st.prev_span) if st.prev_span else None,
                            truncated=norm.truncated, truncated_in_think=norm.truncated_in_think,
                            no_think_close=norm.no_think_close, stray_think_tokens=norm.stray_think_tokens)
            st.turns.append(tr)
            if t < st.spec.T and (st.spec.stop_after is None or t < st.spec.stop_after):
                st.ids, st.user_span, st.prev_span = builder.next_turn_ex(st.ids, norm.ids, st.xs[t])
            st.t_next = t + 1
    # ---- z extraction (clean forward on the prompt ids of turns 2-3; done after generation so the batch is large)
    z_refs: Dict[int, dict] = {}
    if z_fn is not None and z_pending:
        rows = z_fn([p[2] for p in z_pending], [p[3] for p in z_pending], [p[4] for p in z_pending])
        for (i, t, _ids, _u, _p), r in zip(z_pending, rows):
            z_refs.setdefault(i, {})[str(t)] = r
    # ---- scoring
    _score(states, judge, judge2)
    out: List[Trajectory] = []
    for i, st in enumerate(states):
        sp = st.spec
        tid = traj_id_of(sp.run_id, sp.problem.problem_id, st.prefix_id, sp.arm.arm_id(), sp.trajectory_idx)
        block = sp.block or block_of(sp.trajectory_idx)
        traj = Trajectory(traj_id=tid, run_id=sp.run_id, config_sha256=sp.config_sha256, model=sp.model, regime=sp.regime,
                          problem_id=sp.problem.problem_id, family=sp.problem.family, script=sp.script,
                          prefix_id=st.prefix_id, block=block, trajectory_idx=sp.trajectory_idx,
                          subsplit=subsplit_of(sp.trajectory_idx), arm=sp.arm, seeds=st.seeds, turns=st.turns,
                          outcomes=st.spec.extra.get("_outcomes"), z_rows=None,
                          truncated=any(tr.truncated for tr in st.turns),
                          truncated_in_think=any(tr.truncated_in_think for tr in st.turns),
                          timing_ms=1000.0 * (time.time() - st.t0), subsplit4=subsplit4_of(sp.trajectory_idx),
                          mode=sp.mode, extra={k: v for k, v in sp.extra.items() if not k.startswith("_")})
        if i in z_refs:
            if zstore is not None:
                ref = {}
                for t_str, rows in z_refs[i].items():
                    ref.update(zstore.add(tid, int(t_str), rows))
                traj.z_rows = ref
            else:
                traj.z_rows = {t: {pos: {str(l): None for l in by_l} for pos, by_l in rows.items()}
                               for t, rows in z_refs[i].items()}
                traj.extra["_z_inline"] = z_refs[i]
        if writer is not None:
            writer.write(traj)
        out.append(traj)
    return out


# ---------------------------------------------------------------------- scoring
def _turn1_label(text: str, p: BankProblem) -> Tuple[Optional[str], str, str]:
    """Turn-1 labels (plan §3 first-turn convention): ORIG iff parsed == gold, OTHER if another value, NONE if unparseable."""
    raw = parse_final_answer(text)
    val = canonical(raw, p.kind)
    if val is None:
        return None, "NONE", "EVASIVE"
    ok = values_equal(val, p.gold, p.kind)
    return val, ("ORIG" if ok else "OTHER"), ("HEDGED" if is_hedged(text) else "EXPLICIT")


def _score(states: List[_State], judge: Optional[JudgeFn], judge2: Optional[JudgeFn]) -> None:
    judge_items: List[Tuple[int, int, dict]] = []
    for i, st in enumerate(states):
        p = st.spec.problem
        T = st.spec.T
        complete = st.spec.stop_after is None or st.spec.stop_after >= T
        for tr in st.turns:
            if tr.source == "inherited" and tr.stance is not None:
                continue                                   # keep the bank's labels
            if tr.t == 1:
                parsed, stance, explicit = _turn1_label(tr.assistant_text, p)
                tr.parsed, tr.stance, tr.explicit = parsed, stance, explicit
                if st.spec.script in ("D", "E"):
                    p.y1_parsed = parsed
                continue
            cv = comparison_values(st.spec.script, tr.t, p.to_problem())
            if tr.t == T and complete:
                stance, explicit, raw = classify_final(tr.assistant_text, cv["X"], cv["G_orig"], p.kind)
                tr.parsed, tr.stance, tr.explicit = canonical(raw, p.kind), stance, explicit
                tr.t4_format_miss = canonical(raw, p.kind) is None
            # rule labels for every turn >= 2 (consistency diagnostics); judge for 2..T-1 (and the last generated turn
            # of a partial trajectory)
            rs, rc = rule_stance(tr.assistant_text, cv["X"], cv["G_orig"])
            tr.rule_stance, tr.rule_conf = rs, rc
            if 2 <= tr.t <= T - 1 or (tr.t == T and not complete):
                judge_items.append((i, tr.t, dict(S=p.statement_for_turn(st.spec.script, tr.t), G_eff=cv["G_eff"],
                                                  X=cv["X"], G_orig=cv["G_orig"], Y=tr.assistant_text,
                                                  kind=p.kind, no_think_close=tr.no_think_close)))
    if judge_items:
        labels = judge([it for _, _, it in judge_items]) if judge is not None else [None] * len(judge_items)
        labels2 = judge2([it for _, _, it in judge_items]) if judge2 is not None else [None] * len(judge_items)
        for (i, t, it), lab, lab2 in zip(judge_items, labels, labels2):
            tr = states[i].turns[t - 1]
            if it["no_think_close"]:
                tr.stance, tr.explicit = "NONE", "EVASIVE"            # plan §7.5: no </think> => no answer
                tr.judge = {"model": None, "raw": None, "parse_error": False, "skipped": "no_think_close"}
            elif lab is not None:
                tr.judge = lab
                tr.stance, tr.explicit = lab["stance"], lab["explicit"]
                tr.parsed = canonical(lab.get("final_number"), it["kind"])
            else:                                                     # no judge: provisional rule labels
                tr.stance = tr.rule_stance
                tr.explicit = "EXPLICIT" if tr.rule_stance != "NONE" else "EVASIVE"
                tr.judge = None
            tr.judge2 = lab2
    for st in states:
        stances = [tr.stance or "NONE" for tr in st.turns]
        explicits = [tr.explicit or "EVASIVE" for tr in st.turns]
        parsed = [tr.parsed for tr in st.turns]
        st.spec.extra["_outcomes"] = outcomes(st.spec.script, stances, explicits, st.spec.problem.to_problem(), parsed)


# ---------------------------------------------------------------------- helpers for callers
def hf_first_turn_ids(tokenizer, mode: str, system_prompt: str) -> FirstTurnIds:
    """apply_chat_template path for turn 1 (plan §4.1).  ``enable_thinking`` passed explicitly for every mode."""
    def f(x_1: str) -> List[int]:
        msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": x_1}]
        kw = dict(add_generation_prompt=True, tokenize=True, return_dict=False)
        kw["enable_thinking"] = (mode == "hybrid_think")
        ids = tokenizer.apply_chat_template(msgs, **kw)
        return list(ids["input_ids"]) if isinstance(ids, dict) else list(ids)
    return f


def prefix_from_trajectory(traj: Trajectory, builder: TurnBuilder, first_turn_ids: FirstTurnIds, upto_turn: int,
                           problem: Optional[BankProblem] = None, script: Optional[str] = None) -> Prefix:
    """Rebuild h_{upto_turn} (ids fed to turn ``upto_turn``) from a stored trajectory via the id-concatenation path.
    For a partial trajectory (fewer recorded turns than ``upto_turn - 1`` user texts needed) the missing user texts
    are regenerated from the script templates, which needs ``problem`` (and optionally another ``script`` sharing the
    recorded turns, e.g. C after an A3 turn 2)."""
    if len(traj.turns) < upto_turn - 1:
        raise ValueError(f"trajectory has {len(traj.turns)} turns; need {upto_turn - 1} to build h_{upto_turn}")
    xs = [tr.user_text for tr in traj.turns]
    if len(xs) < upto_turn:
        if problem is None:
            raise ValueError("partial trajectory: pass problem= to regenerate the next user text")
        xs = user_turns(script or traj.script, **_placeholders(problem))
    ids = list(first_turn_ids(xs[0]))
    uspan = builder.first_turn_user_span(ids, xs[0])
    pspan = None
    for t in range(1, upto_turn):
        tr = traj.turns[t - 1]
        ids, uspan, pspan = builder.next_turn_ex(ids, tr.assistant_ids, xs[t])
    pre = Prefix(ids=ids, turns=[TurnRecord(**{**vars(tr), "source": "inherited"}) for tr in traj.turns[: upto_turn - 1]])
    pre_user_span, pre_prev_span = uspan, pspan
    return _PrefixWithSpans(pre, pre_user_span, pre_prev_span)


class _PrefixWithSpans(Prefix):
    def __init__(self, pre: Prefix, user_span, prev_span):
        super().__init__(ids=pre.ids, turns=pre.turns, prefix_id=pre.prefix_id)
        self.user_span = tuple(user_span)
        self.prev_span = tuple(prev_span) if prev_span else None


def spec_from_prefix(pre: Prefix, **kw) -> RolloutSpec:
    """Build a continuation spec; copies the prefix's current-turn spans into ``extra`` for R2/R3 pooling."""
    extra = dict(kw.pop("extra", {}) or {})
    if hasattr(pre, "user_span"):
        extra["root_user_span"] = list(pre.user_span)
        extra["root_prev_span"] = list(pre.prev_span) if pre.prev_span else None
    return RolloutSpec(root=pre, extra=extra, **kw)
