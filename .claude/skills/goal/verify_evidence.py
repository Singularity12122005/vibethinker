#!/usr/bin/env python3
"""Mechanical verification of a goal-round evidence table (round-protocol v4, §4).

Every headline number of an archive record has one entry in docs/research/goal-rounds/<round>/evidence.json:

    {"id": "B1.hellinger_m32", "printed": "0.4194", "kind": "lower",
     "source": "docs/research/goal-rounds/r4/B/b1_lecam_exact.json",
     "locator": {"json": ["pairs", "F_b", "m=32", "bound_both"]},            # or {"regex": "...(value)...", "occurrence": 0}
     "conditions": "iid-within-type binomial counts, 100+100 prefixes, m=32, F_a vs F_b"}

kind:
  point   printed == source rounded half-even/half-up to the printed precision (both accepted)
  upper   printed >= source and printed - source < one unit of the printed precision (rounded UP)
  lower   printed <= source and source - printed < one unit of the printed precision (rounded DOWN)
  exact   printed equals the source exactly (integers, fractions "a/b", or identical decimal strings)
  count   integer equality
Precision = the number of decimals of the printed mantissa (scientific notation "2.80e-6" has unit 1e-8).
Sources must be files inside the repository (paths relative to the repository root); a missing file, a locator that
does not resolve, a non-numeric value or a rounding violation is a failure.  Exit status 1 if any entry fails.

Usage:  python verify_evidence.py <repo_root> <evidence.json>      |      python verify_evidence.py --selftest
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, InvalidOperation
from fractions import Fraction
from pathlib import Path


def _unit(printed: str) -> Decimal:
    s = printed.strip().lower().replace("−", "-")
    mant, _, exp = s.partition("e")
    decimals = len(mant.split(".")[1]) if "." in mant else 0
    e = int(exp) if exp else 0
    return Decimal(1).scaleb(e - decimals)


def _to_decimal(x) -> Decimal:
    if isinstance(x, bool):
        raise ValueError("boolean is not a number")
    if isinstance(x, (int, float)):
        return Decimal(repr(x)) if isinstance(x, float) else Decimal(x)
    s = str(x).strip().replace("−", "-")
    if "/" in s:
        f = Fraction(s)
        return Decimal(f.numerator) / Decimal(f.denominator)
    return Decimal(s)


def _resolve(root: Path, entry: dict):
    src = (root / entry["source"]).resolve()
    if root.resolve() not in src.parents and src != root.resolve():
        raise ValueError(f"source outside the repository: {entry['source']}")
    if not src.is_file():
        raise FileNotFoundError(entry["source"])
    loc = entry["locator"]
    if "json" in loc:
        node = json.loads(src.read_text(encoding="utf-8"))
        for key in loc["json"]:
            if isinstance(node, list):
                node = node[int(key)]
            else:
                if key not in node:
                    raise KeyError(f"{key!r} not in {sorted(node)[:12]}")
                node = node[key]
        return node
    if "regex" in loc:
        text = src.read_text(encoding="utf-8")
        hits = list(re.finditer(loc["regex"], text, flags=re.MULTILINE))
        k = int(loc.get("occurrence", 0))
        if len(hits) <= k:
            raise ValueError(f"regex matched {len(hits)} times, occurrence {k} requested")
        return hits[k].group(1)
    raise ValueError("locator needs 'json' or 'regex'")


def check_entry(root: Path, entry: dict) -> tuple[bool, str]:
    try:
        raw = _resolve(root, entry)
        kind = entry["kind"]
        printed = str(entry["printed"]).strip()
        if kind == "count":
            ok = int(Decimal(str(raw))) == int(Decimal(printed)) and Decimal(str(raw)) == int(Decimal(str(raw)))
            return ok, f"source {raw}"
        if kind == "exact":
            if "/" in printed or "/" in str(raw):
                ok = Fraction(printed) == Fraction(str(raw))
            else:
                ok = _to_decimal(raw) == _to_decimal(printed)
            return ok, f"source {raw}"
        src, pr, unit = _to_decimal(raw), _to_decimal(printed), _unit(printed)
        if kind == "point":
            q = [src.quantize(unit, rounding=m) for m in (ROUND_HALF_EVEN, ROUND_HALF_UP)]
            ok = pr in q
        elif kind == "upper":
            ok = pr >= src and pr - src < unit and pr == src.quantize(unit, rounding=ROUND_CEILING)
        elif kind == "lower":
            ok = pr <= src and src - pr < unit and pr == src.quantize(unit, rounding=ROUND_FLOOR)
        else:
            return False, f"unknown kind {kind!r}"
        return ok, f"source {raw} (unit {unit})"
    except (KeyError, ValueError, FileNotFoundError, InvalidOperation, IndexError, ZeroDivisionError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def verify(root: Path, evidence_path: Path) -> int:
    ev = json.loads(evidence_path.read_text(encoding="utf-8"))
    entries = ev["entries"]
    ids = [e["id"] for e in entries]
    dup = {i for i in ids if ids.count(i) > 1}
    fails = 0
    for e in entries:
        ok, info = check_entry(root, e)
        missing = [k for k in ("id", "printed", "kind", "source", "locator", "conditions") if not e.get(k)]
        if missing:
            ok, info = False, f"missing fields {missing}; " + info
        if e["id"] in dup:
            ok, info = False, "duplicate id; " + info
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {e['id']:<40} printed {e['printed']:<14} {e['kind']:<6} {info}")
    print(f"{len(entries) - fails}/{len(entries)} entries pass")
    return 1 if fails else 0


def _selftest() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "src.json").write_text(json.dumps({"a": {"b": [0.41942966, 0.0323317, 7]}, "f": "945238594631/1000000000000"}))
        (root / "src.out").write_text("bound=0.569359\nbound=0.135390\n")
        cases = [
            (dict(printed="0.4194", kind="lower", locator={"json": ["a", "b", 0]}, source="src.json"), True),
            (dict(printed="0.4195", kind="lower", locator={"json": ["a", "b", 0]}, source="src.json"), False),
            (dict(printed="0.4195", kind="upper", locator={"json": ["a", "b", 0]}, source="src.json"), True),
            (dict(printed="0.41943", kind="point", locator={"json": ["a", "b", 0]}, source="src.json"), True),
            (dict(printed="0.41943", kind="lower", locator={"json": ["a", "b", 0]}, source="src.json"), False),
            (dict(printed="3.24e-2", kind="upper", locator={"json": ["a", "b", 1]}, source="src.json"), True),
            (dict(printed="7", kind="count", locator={"json": ["a", "b", 2]}, source="src.json"), True),
            (dict(printed="945238594631/1000000000000", kind="exact", locator={"json": ["f"]}, source="src.json"), True),
            (dict(printed="0.1353", kind="lower", locator={"regex": r"bound=([0-9.]+)", "occurrence": 1}, source="src.out"), True),
            (dict(printed="0.5", kind="point", locator={"json": ["zz"]}, source="src.json"), False),
            (dict(printed="0.5", kind="point", locator={"json": ["a"]}, source="missing.json"), False),
        ]
        bad = 0
        for i, (e, want) in enumerate(cases):
            got, info = check_entry(root, dict(id=f"c{i}", conditions="selftest", **e))
            bad += got != want
            if got != want:
                print("selftest mismatch", i, e, got, info)
        print("selftest", "ok" if not bad else f"{bad} failures")
        return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(verify(Path(sys.argv[1]), Path(sys.argv[2])))
