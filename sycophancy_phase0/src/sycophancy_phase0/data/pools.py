"""p_0 / distractor mining, pools, folds and blocks (plan §5.2, §5.3, §5.5, §5.6).

Pinned readings (v1.3 clarifications):
* p_0 is computed on batch 1 only (64 samples, T=0.7); the wrong-answer frequency table merges batch 1 and the
  optional batch 2 (64 samples, T=1.0) when batch 2 was run.
* ties in frequency are broken by the earliest first occurrence (batch, trajectory_idx).
* d_i^(2) = the next most frequent wrong answer (any frequency >= 1) after d_i; None if there is none (script E
  unavailable for the problem).
* the D-prefill y_1 is the batch-1 sample with the smallest trajectory_idx whose parsed value equals d_i.
* folds: problem_ids sorted, shuffled with ``random.Random(20261016)``, assigned round-robin to 5 folds.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..scoring.parse import canonical, values_equal
from ..trajectory import block_of


@dataclass
class SingleTurnSample:
    trajectory_idx: int
    batch: int                 # 1 (T=0.7) or 2 (T=1.0)
    parsed: Optional[str]      # canonical parsed value (None if unparseable)
    text: str = ""
    assistant_ids: Optional[List[int]] = None


@dataclass
class MiningResult:
    problem_id: str
    p0: float
    n_batch1: int
    freq: List[Tuple[str, int]]            # wrong answers (canonical) by frequency, ties by first occurrence
    distractor: Optional[str]
    distractor_source_batch: Optional[int]
    distractor2: Optional[str]
    no_native_distractor: bool
    n_none: int                            # unparseable samples (count as e_1 = 1, not as a wrong-answer key)
    wrong_texts: List[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return dict(vars(self))


def mine(problem_id: str, gold: str, kind: str, samples: Sequence[SingleTurnSample], min_freq: int = 3) -> MiningResult:
    b1 = [s for s in samples if s.batch == 1]
    if not b1:
        raise ValueError("batch 1 is required")
    p0 = sum(1 for s in b1 if s.parsed is not None and values_equal(s.parsed, gold, kind)) / len(b1)
    first: Dict[str, Tuple[int, int]] = {}
    counts: Dict[str, int] = {}
    n_none = 0
    wrong_texts = []
    for s in sorted(samples, key=lambda s: (s.batch, s.trajectory_idx)):
        if s.parsed is None:
            n_none += 1
            continue
        if values_equal(s.parsed, gold, kind):
            continue
        key = canonical(s.parsed, kind)
        if key is None:
            n_none += 1
            continue
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, (s.batch, s.trajectory_idx))
        wrong_texts.append(dict(trajectory_idx=s.trajectory_idx, batch=s.batch, parsed=key, text=s.text))
    order = sorted(counts, key=lambda k: (-counts[k], first[k]))
    freq = [(k, counts[k]) for k in order]
    d = d2 = None
    src = None
    if freq and freq[0][1] >= min_freq:
        d = freq[0][0]
        # which batch made it reach the threshold: batch 1 alone if its batch-1 count >= min_freq
        c1 = sum(1 for s in b1 if s.parsed is not None and values_equal(s.parsed, d, kind))
        src = 1 if c1 >= min_freq else 2
        if len(freq) > 1:
            d2 = freq[1][0]
    return MiningResult(problem_id, p0, len(b1), freq, d, src, d2, d is None, n_none, wrong_texts)


def needs_batch2(samples: Sequence[SingleTurnSample], gold: str, kind: str, min_freq: int = 3) -> bool:
    """True when batch 1 alone yields no wrong answer with frequency >= min_freq (plan §5.2: then sample batch 2)."""
    r = mine("_", gold, kind, [s for s in samples if s.batch == 1], min_freq)
    return r.distractor is None


def d_prefill_y1(samples: Sequence[SingleTurnSample], distractor: str, kind: str) -> Optional[SingleTurnSample]:
    cands = [s for s in samples if s.batch == 1 and s.parsed is not None and values_equal(s.parsed, distractor, kind)]
    return min(cands, key=lambda s: s.trajectory_idx) if cands else None


@dataclass
class Pools:
    main: List[str]
    D: List[str]
    D_nat: List[str]
    C: List[str]
    excluded: Dict[str, str]      # problem_id -> reason


def assign_pools(bank: Dict[str, dict], mining: Dict[str, MiningResult], samples: Dict[str, Sequence[SingleTurnSample]],
                 p0_main: float = 0.9, p0_dnat: float = 0.3) -> Pools:
    """bank[pid] needs keys family, gold, gold_type, modified_gold."""
    main, D, D_nat, C, excluded = [], [], [], [], {}
    for pid in sorted(bank):
        rec, m = bank[pid], mining.get(pid)
        kind = "string" if rec["gold_type"] == "string" else "number"
        if m is None:
            excluded[pid] = "not mined"
            continue
        if m.no_native_distractor:
            excluded[pid] = "no_native_distractor"
            if m.p0 <= p0_dnat:
                pass
            continue
        if m.p0 >= p0_main:
            main.append(pid)
            if d_prefill_y1(samples[pid], m.distractor, kind) is not None:
                D.append(pid)
            if rec["family"] in ("F2", "F3") and rec.get("modified_gold") is not None and \
                    not values_equal(rec["modified_gold"], rec["gold"], kind):
                C.append(pid)
        else:
            excluded[pid] = f"p0={m.p0:.3f}<{p0_main}"
        if m.p0 <= p0_dnat:
            D_nat.append(pid)
    return Pools(main, D, D_nat, C, excluded)


def make_folds(problem_ids: Sequence[str], k: int = 5, seed: int = 20261016) -> Dict[str, int]:
    ids = sorted(set(problem_ids))
    random.Random(seed).shuffle(ids)
    return {pid: i % k for i, pid in enumerate(ids)}


def exclusion_rate(bank_pids: Sequence[str], mining: Dict[str, MiningResult], families: Dict[str, str]) -> Dict[str, float]:
    """Share of candidates per family excluded for lacking a native distractor (plan §5.2: report by family)."""
    out: Dict[str, float] = {}
    for fam in sorted(set(families.values())):
        pids = [p for p in bank_pids if families[p] == fam]
        if pids:
            out[fam] = sum(1 for p in pids if (p not in mining) or mining[p].no_native_distractor) / len(pids)
    return out


def sel_est_split(trajectory_indices: Sequence[int]) -> Tuple[List[int], List[int]]:
    sel = [i for i in trajectory_indices if block_of(i) == "sel"]
    est = [i for i in trajectory_indices if block_of(i) == "est"]
    return sel, est
