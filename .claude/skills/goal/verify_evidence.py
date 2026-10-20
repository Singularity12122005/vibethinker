#!/usr/bin/env python3
"""Mechanical verification of a goal-round evidence table (round-protocol v4 §4, v5.1 §9).

Every headline number of an archive record has one entry in docs/research/goal-rounds/<round>/evidence.json, a file of the form

    {"round": "r5", "environment": "python 3.11.9, numpy 2.1.3, scipy 1.14.1; CPU (container)",      # default for every entry
     "entries": [
       {"id": "B1.hellinger_m32", "printed": "0.4194", "kind": "lower",
        "source": "docs/research/goal-rounds/r5/route2/b1_lecam_exact.json",
        "locator": {"json": ["pairs", "F_b", "m=32", "bound_both"]},     # or {"regex": "...(value)...", "occurrence": 0}
        "conditions": "iid-within-type binomial counts, 100+100 prefixes, m=32, F_a vs F_b",
        "environment": "..."}                                               # optional per entry; overrides the default
     ]}

kind:
  point   printed == source rounded half-even/half-up to the printed precision (both accepted)
  upper   printed >= source and printed - source < one unit of the printed precision (rounded UP)
  lower   printed <= source and source - printed < one unit of the printed precision (rounded DOWN)
  exact   printed equals the source exactly (integers, fractions "a/b", or identical decimal strings)
  count   integer equality; the printed value and the source must both be integers
Precision = the number of decimals of the printed mantissa (scientific notation "2.80e-6" has unit 1e-8).
Sources must be files inside the repository given as repository-relative paths (absolute and "~" paths are rejected); with
--under DIR (repeatable) they must lie under one of the repository-relative directories DIR.  "printed" must be a JSON string.  With --require-environment every entry needs a
non-empty environment (its own or the file's default).  A missing file, a locator that does not resolve, a non-numeric value
or a rounding violation is a failure.  Exit status 1 if any entry fails.

Usage:  python verify_evidence.py <repo_root> <evidence.json> [--under DIR] [--require-environment]
        python verify_evidence.py --selftest
"""
from __future__ import annotations

import json
import os
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


def _resolve(root: Path, entry: dict, under=None):
    if Path(entry["source"]).is_absolute() or str(entry["source"]).startswith("~"):
        raise ValueError(f"source must be repository-relative, got {entry['source']}")
    src = (root / entry["source"]).resolve()
    if root.resolve() not in src.parents and src != root.resolve():
        raise ValueError(f"source outside the repository: {entry['source']}")
    if under is not None:
        dirs = [under] if isinstance(under, str) else list(under)
        if not any((root / d).resolve() in src.parents for d in dirs):
            raise ValueError(f"source {entry['source']} is not under {' or '.join(dirs)}")
    if not src.is_file():
        raise FileNotFoundError(entry["source"])
    loc = entry["locator"]
    if "json" in loc:
        node = json.loads(src.read_text(encoding="utf-8"))
        for key in loc["json"]:
            if isinstance(node, list):
                node = node[int(key)]
            elif isinstance(node, dict):
                if key not in node:
                    raise KeyError(f"{key!r} not in {sorted(node)[:12]}")
                node = node[key]
            else:
                raise KeyError(f"cannot step into {type(node).__name__} with key {key!r}")
        return node
    if "regex" in loc:
        text = src.read_text(encoding="utf-8")
        hits = list(re.finditer(loc["regex"], text, flags=re.MULTILINE))
        k = int(loc.get("occurrence", 0))
        if len(hits) <= k:
            raise ValueError(f"regex matched {len(hits)} times, occurrence {k} requested")
        return hits[k].group(1)
    raise ValueError("locator needs 'json' or 'regex'")


def _is_int(d: Decimal) -> bool:
    return d == d.to_integral_value()


def check_entry(root: Path, entry: dict, under=None, allowed_files=None) -> tuple[bool, str]:
    try:
        if not isinstance(entry.get("printed"), str):
            raise TypeError("printed must be a string exactly as the record prints it")
        if allowed_files is not None and os.path.normpath(str(entry.get("source"))) not in allowed_files:
            raise ValueError(f"source {entry.get('source')} is not one of the allowed (frozen) files")
        raw = _resolve(root, entry, under)
        kind = entry["kind"]
        printed = entry["printed"].strip()
        if kind == "count":
            src_d, pr_d = Decimal(str(raw)), Decimal(printed)
            ok = _is_int(src_d) and _is_int(pr_d) and src_d == pr_d
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
    except (KeyError, ValueError, TypeError, FileNotFoundError, InvalidOperation, IndexError, ZeroDivisionError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def verify_counts(root: Path, evidence_path: Path, under=None, require_environment: bool = False,
                  out=print, allowed_files=None, entry_check=None) -> tuple[int, int]:
    """Check every entry; return (passed, total).  An unreadable table counts as (0, -1)."""
    try:
        ev = json.loads(evidence_path.read_text(encoding="utf-8"))
        entries = ev["entries"]
        if not isinstance(entries, list):
            raise TypeError("entries is not a list")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out(f"FAIL  evidence table unreadable: {type(exc).__name__}: {exc}")
        out("0/-1 entries pass")
        return 0, -1
    default_env = str(ev.get("environment") or "").strip()
    ids = [e.get("id") for e in entries if isinstance(e, dict)]
    dup = {i for i in ids if ids.count(i) > 1}
    fails = 0
    for e in entries:
        if not isinstance(e, dict):
            fails += 1
            out(f"FAIL  entry is not an object: {e!r}")
            continue
        ok, info = check_entry(root, e, under, allowed_files)
        extra = entry_check(e) if entry_check is not None else None
        if extra:
            ok, info = False, f"{extra}; " + info
        missing = [k for k in ("id", "printed", "kind", "source", "locator", "conditions") if not e.get(k)]
        if missing:
            ok, info = False, f"missing fields {missing}; " + info
        if require_environment and not (str(e.get("environment") or "").strip() or default_env):
            ok, info = False, "no environment; " + info
        if e.get("id") in dup:
            ok, info = False, "duplicate id; " + info
        fails += not ok
        out(f"{'PASS' if ok else 'FAIL'}  {str(e.get('id')):<40} printed {str(e.get('printed')):<14} {str(e.get('kind')):<6} {info}")
    out(f"{len(entries) - fails}/{len(entries)} entries pass")
    return len(entries) - fails, len(entries)


def verify(root: Path, evidence_path: Path, under=None, require_environment: bool = False) -> int:
    passed, total = verify_counts(root, evidence_path, under, require_environment)
    return 0 if total >= 0 and passed == total else 1


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
            (dict(printed="0.4194", kind="lower", locator={"json": ["a", "b", 0]}, source=str(root / "src.json")), False),
            (dict(printed="7.9", kind="count", locator={"json": ["a", "b", 2]}, source="src.json"), False),
            (dict(printed="7", kind="count", locator={"json": ["a", "b", 1]}, source="src.json"), False),
            (dict(printed="0.5", kind="point", locator={"json": ["f", "x"]}, source="src.json"), False),
            (dict(printed=7, kind="count", locator={"json": ["a", "b", 2]}, source="src.json"), False),
        ]
        bad = 0
        for i, (e, want) in enumerate(cases):
            got, info = check_entry(root, dict(id=f"c{i}", conditions="selftest", **e))
            bad += got != want
            if got != want:
                print("selftest mismatch", i, e, got, info)
        (root / "sub").mkdir()
        (root / "sub" / "s.json").write_text(json.dumps({"v": 3}))
        e_in = dict(id="u", printed="3", kind="count", locator={"json": ["v"]}, source="sub/s.json", conditions="selftest")
        e_out = dict(e_in, source="src.json", locator={"json": ["a", "b", 2]}, printed="7")
        bad += check_entry(root, e_in, "sub")[0] is not True
        bad += check_entry(root, e_out, "sub")[0] is not False
        bad += check_entry(root, e_out, ["zz", "sub"])[0] is not False
        bad += check_entry(root, e_in, ["zz", "sub"])[0] is not True
        (root / "ev.json").write_text(json.dumps({"entries": [e_in]}))
        bad += verify_counts(root, root / "ev.json", require_environment=True, out=lambda *_: None) != (0, 1)
        (root / "ev.json").write_text(json.dumps({"environment": "selftest env", "entries": [e_in]}))
        bad += verify_counts(root, root / "ev.json", "sub", True, out=lambda *_: None) != (1, 1)
        (root / "ev.json").write_text("not json")
        bad += verify_counts(root, root / "ev.json", out=lambda *_: None) != (0, -1)
        print("selftest", "ok" if not bad else f"{bad} failures")
        return 1 if bad else 0


if __name__ == "__main__":
    import argparse
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("root")
    ap.add_argument("evidence")
    ap.add_argument("--under", action="append", default=None, help="repeatable; sources must lie under one of these")
    ap.add_argument("--require-environment", action="store_true")
    a = ap.parse_args()
    sys.exit(verify(Path(a.root), Path(a.evidence), a.under, a.require_environment))
