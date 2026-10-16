"""Shared helpers for the data families (plan §5.1)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from typing import Dict, Iterable, List, Optional

MAX_DENOMINATOR = 100      # v1.3 clarification: F2 golds (and g') must be exact with <= 2 decimals so that a
                           # decimal answer and a fraction answer normalise to the same Fraction (plan §6.1)


@dataclass
class BankRecord:
    problem_id: str
    family: str
    statement_zh: str
    gold: str
    gold_type: str                                   # integer | rational | string
    template: Optional[str] = None
    params: Optional[dict] = None
    modified_statement_zh: Optional[str] = None
    modified_gold: Optional[str] = None
    modification_note: Optional[str] = None
    source: Optional[dict] = None                    # provenance (dataset index, translation flags, ...)
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


def fraction_to_str(x: Fraction) -> str:
    """Canonical bank string: integers as '40'; otherwise an exact decimal ('37.5') when the denominator divides
    MAX_DENOMINATOR, else 'p/q'."""
    x = Fraction(x)
    if x.denominator == 1:
        return str(x.numerator)
    if MAX_DENOMINATOR % x.denominator == 0:
        nd = len(str(MAX_DENOMINATOR)) - 1
        s = str(abs(x.numerator) * (MAX_DENOMINATOR // x.denominator)).rjust(nd + 1, "0")
        sign = "-" if x < 0 else ""
        return f"{sign}{s[:-nd]}.{s[-nd:]}".rstrip("0").rstrip(".")
    return f"{x.numerator}/{x.denominator}"


def exact_decimal(x: Fraction) -> bool:
    return MAX_DENOMINATOR % Fraction(x).denominator == 0


def write_bank(records: Iterable[BankRecord], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_json(), ensure_ascii=False) + "\n")


def read_bank(path: str) -> List[BankRecord]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(BankRecord(**json.loads(line)))
    return out
