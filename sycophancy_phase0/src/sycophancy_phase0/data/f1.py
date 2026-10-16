"""F1 — GSM8K test subset with Chinese statements (plan §2.3).

* indices: ``random.Random(20261016).sample(range(1319), 150)``; calibration set for §4.7 step 2:
  ``random.Random(20261017).sample([i for i in range(1319) if i not in F1], 400)`` (v1.3 clarification).
* gold: text after ``#### `` with thousands separators removed.
* Chinese statement: ``meta-math/GSM8K_zh`` ``test`` ``question_zh`` aligned by index when the numeric multiset
  matches the English question; otherwise the record is marked ``needs_translation`` (J2 translation + J1
  back-translation at run time, kept only if the numeric multiset check passes).
"""
from __future__ import annotations

import random
import re
from collections import Counter
from typing import Dict, List, Optional, Sequence

from .common import BankRecord

N_TEST = 1319
SEED_F1, N_F1 = 20261016, 150
SEED_CAL, N_CAL = 20261017, 400
NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def numeric_multiset(text: str) -> Counter:
    vals = []
    for m in NUM_RE.findall(text):
        v = m.replace(",", "").rstrip(".")
        if v:
            vals.append(v)
    return Counter(vals)


def numbers_consistent(en: str, zh: str) -> bool:
    return numeric_multiset(en) == numeric_multiset(zh)


def gsm8k_gold(answer: str) -> str:
    return answer.split("####")[-1].strip().replace(",", "")


def f1_indices(seed: int = SEED_F1, n: int = N_F1) -> List[int]:
    return random.Random(seed).sample(range(N_TEST), n)


def calibration_indices(exclude: Sequence[int], seed: int = SEED_CAL, n: int = N_CAL) -> List[int]:
    pool = [i for i in range(N_TEST) if i not in set(exclude)]
    return random.Random(seed).sample(pool, n)


def build_f1(gsm_rows: Sequence[dict], zh_rows: Optional[Sequence[dict]] = None, indices: Optional[Sequence[int]] = None,
             family: str = "F1", prefix: str = "F1") -> List[BankRecord]:
    """gsm_rows: ``openai/gsm8k`` ``main`` ``test`` rows in order; zh_rows: ``meta-math/GSM8K_zh`` ``test`` rows."""
    if len(gsm_rows) != N_TEST:
        raise ValueError(f"expected {N_TEST} GSM8K test rows, got {len(gsm_rows)}")
    idxs = list(indices) if indices is not None else f1_indices()
    out = []
    for i in idxs:
        row = gsm_rows[i]
        q_en, gold = row["question"], gsm8k_gold(row["answer"])
        zh = None
        zh_ok = False
        if zh_rows is not None and i < len(zh_rows):
            cand = zh_rows[i].get("question_zh") or zh_rows[i].get("question")
            en_cand = zh_rows[i].get("question") if "question_zh" in zh_rows[i] else None
            aligned = (en_cand is None) or (en_cand.strip() == q_en.strip())
            if cand and aligned and numbers_consistent(q_en, cand):
                zh, zh_ok = cand.strip(), True
        out.append(BankRecord(problem_id=f"{prefix}-gsm8k-{i:04d}", family=family, statement_zh=zh or "", gold=gold,
                              gold_type="integer", template="gsm8k",
                              source=dict(gsm8k_test_index=i, question_en=q_en, zh_source="GSM8K_zh" if zh_ok else None,
                                          needs_translation=not zh_ok)))
    return out


def translation_prompt(question_en: str) -> str:
    return ("请把下面这道数学应用题准确地翻译成中文。保持所有数字、单位和条件完全不变，不要解题，不要添加任何解释，只输出译文。\n\n"
            + question_en)


def back_translation_prompt(question_zh: str) -> str:
    return ("Translate the following Chinese math word problem into English. Keep every number, unit and condition exactly "
            "as given; do not solve it; output the translation only.\n\n" + question_zh)


def apply_translations(records: List[BankRecord], zh_texts: Dict[str, str], back_texts: Dict[str, str]) -> List[BankRecord]:
    """Fill ``statement_zh`` for ``needs_translation`` records; keep only those whose numeric multisets match both ways."""
    kept = []
    for r in records:
        if not r.source.get("needs_translation"):
            kept.append(r)
            continue
        zh = zh_texts.get(r.problem_id)
        back = back_texts.get(r.problem_id)
        en = r.source["question_en"]
        ok = zh is not None and numbers_consistent(en, zh) and (back is None or numbers_consistent(en, back))
        r.source["translation_ok"] = bool(ok)
        if ok:
            r.statement_zh = zh.strip()
            r.source["zh_source"] = "J2+J1"
            kept.append(r)
    return kept


def load_from_hub():
    """Returns (gsm_rows, zh_rows or None) using ``datasets`` (network required)."""
    from datasets import load_dataset
    gsm = list(load_dataset("openai/gsm8k", "main", split="test"))
    try:
        zh = list(load_dataset("meta-math/GSM8K_zh", split="test"))
    except Exception:
        zh = None
    return gsm, zh
