#!/usr/bin/env python3
"""Mechanical parts of a /goal round (round-protocol v5.1, §9).  This tool measures; the workflow decides.

    python round_gate.py <repo_root> <round> --module <repo-relative module> [--tests <repo-relative tests>]
        [--only part,part,...] [--state-dir <absolute dir outside the repository>] [--baseline-sha HEX]
        [--copy-from <scratch round dir>] [--backup-dir <absolute dir>] [--expect JSON] [--ledger-sha HEX]

Parts (default: verifier,pytest,ledger,record,frozen,module,scope):
  baseline  writes <state-dir>/baseline.json: HEAD and every path `git status --porcelain=v2 -z --untracked-files=all`
            lists, with the sha256 of its content (null if absent); reports the count, HEAD and the file's sha256
  backup    copies the module and the tests file into --backup-dir unless copies are already there; reports their sha256
  restore   copies the --backup-dir copies back over the module and the tests file; reports whether the restored files
            have the backed-up sha256
  hashes    sha256 of the module and the tests file
  copy      copies every text file (decided by content: no NUL byte, valid UTF-8) of --copy-from into the evidence directory,
            layout kept, no __pycache__, nothing > 5 MB; writes PATHS.md; reports copied files that git ignores
  snapshot  copies the module to <evidence>/code/module_after_review.py
  verifier  verify_evidence.py on <evidence>/evidence.json with --require-environment; sources must lie in the frozen
            working material (problem/, route<k>/, review/, rewrite/, code/)
  pytest    `python -m pytest -q -p no:cacheprovider` in <repo>/sycophancy_phase0 (python = the interpreter running this tool);
            the counts come from the last pytest summary line of stdout
  ledger    recompute every version's truth label, v4 label and blind status from <evidence>/review-verdicts/ledger.json with
            the same rule and isolation audit as goal-round.js; compare with the stored labels, with --expect and, with
            --ledger-sha, the canonical sha256 of the whole ledger with the workflow's; the reviewers' own verdict.json copies
            are compared as warnings
  record    "### <round>" headings in the archive and the characters of the first one (to the next ##/### heading); every
            [E:<id>] tag must name an evidence entry whose printed value occurs, as a whole number token, between the
            previous tag and this one (at most 120 characters back); a tag in code font (`[E:x]`) is a mention and is skipped
  frozen    sha256 over the copied working material and the ledger (<evidence>/{problem,route<k>,review,rewrite,code,
            review-verdicts}/**), names and contents
  module    top-level statements of the review-time snapshot that are missing or changed (by AST, decorators included) in
            the current module, plus new top-level statements that are not new imports, plain new functions or classes
            (only @dataclass allowed), or that rebind a snapshot name (violations -1: no snapshot)
  scope     changed paths outside the allowed set (archive, tests, module, evidence directory) that are not baseline paths
            with unchanged content, baseline paths whose content changed (also when git no longer lists them), and a moved HEAD

The last output line is "GATE " followed by one JSON object with one key per part.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import symtable
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_evidence as ve  # noqa: E402

ARCHIVE_REL = "docs/research/sycophancy-phase0-goal.md"
TESTS_REL = "sycophancy_phase0/tests/test_analysis.py"
LBL_OK, LBL_REF, LBL_CAND = "独立复核", "已驳回", "候选"
LENSES = ("math", "blind_replication", "applicability")
FROZEN_TOP = re.compile(r"^(problem|review|rewrite|code|review-verdicts|route[0-9]+)$")
SOURCE_TOP = re.compile(r"^(problem|review|rewrite|code|route[0-9]+)$")
MAX_COPY_BYTES = 5 * 1024 * 1024
SUMMARY = re.compile(r"\b(\d+ (passed|failed|errors?|skipped|xfailed|xpassed|deselected)|no tests ran)\b.* in \d")


# ------------------------------------------------------------------------------------------------ isolation audit and truth rule
# These mirror goal-round.js exactly (strip, normalised, under, pathOk, decide); the stub suite cross-checks them.
def _bad_char(s: str) -> bool:
    """Control, format and line/paragraph separator characters (Unicode Cc, Cf, Zl, Zp); goal-round.js uses the same classes."""
    return any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in s)


def strip(p) -> str:
    return re.sub(r"/+$", "", re.sub(r"^[ \t\r\n]+|[ \t\r\n]+$", "", str(p)))


def normalised(s) -> bool:
    return (isinstance(s, str) and s.startswith("/") and "//" not in s and not re.search(r"/\.{1,2}(/|$)", s)
            and not _bad_char(s))


def under(s: str, p: str) -> bool:
    return s == p or s.startswith(p + "/")


def path_ok(f, own, iso: dict) -> bool:
    s = strip(f)
    if not normalised(s):
        return False
    if own and under(s, own):
        return True
    if any(under(s, p) for p in iso["forbid_prefix"]):
        return False
    if any(x in s for x in iso["forbid_sub"]):
        return False
    return not any(re.search(rx, s) for rx in iso["forbid_re"])


def decide(verdicts: dict, iso: dict) -> dict:
    m, b, ap = (verdicts.get(k) for k in LENSES)
    files = b.get("files_read") if b is not None else None
    audit = b is not None and isinstance(files, list) and len(files) > 0 and all(path_ok(f, b.get("review_dir"), iso) for f in files)
    blind_status = "missing" if b is None else "ok" if audit else "audit_failed"

    def clean(v):
        return v is not None and v.get("refuted") is False and v.get("severity") == "none"

    if clean(m) and clean(b) and b.get("reproduced_numbers") is True and audit:
        truth = LBL_OK
    elif any(v is not None and v.get("severity") == "wrong" for v in (m, b)):
        truth = LBL_REF
    else:
        truth = LBL_CAND
    v4 = LBL_REF if truth == LBL_REF else LBL_OK if truth == LBL_OK and ap is not None and ap.get("severity") == "none" else LBL_CAND
    return {"truth_label": truth, "v4_label": v4, "blind_status": blind_status,
            "missing_lenses": [k for k in LENSES if verdicts.get(k) is None]}


def canonical_sha(obj) -> str:
    """sha256 of the ASCII-escaped compact JSON; goal-round.js computes the same bytes from JSON.stringify."""
    return hashlib.sha256(json.dumps(obj, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()


# ------------------------------------------------------------------------------------------------ helpers
def _sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def _git(root: Path, *args) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True).stdout


def _git_changed(root: Path) -> list[str]:
    """Paths of `git status --porcelain=v2 -z --untracked-files=all` (both sides of renames and copies)."""
    recs = _git(root, "status", "--porcelain=v2", "-z", "--untracked-files=all").decode("utf-8", "surrogateescape").split("\0")
    paths, i = [], 0
    while i < len(recs):
        r = recs[i]
        if r.startswith("1 "):
            paths.append(r.split(" ", 8)[8])
        elif r.startswith("2 "):
            paths.append(r.split(" ", 9)[9])
            paths.append(recs[i + 1])          # the original path follows as its own record
            i += 1
        elif r.startswith("u "):
            paths.append(r.split(" ", 10)[10])
        elif r.startswith("? "):
            paths.append(r[2:])
        i += 1
    return sorted({p for p in paths if p})


def _index_map(root: Path) -> dict:
    """path -> blob id of every index entry (all stages joined), from `git ls-files -s -z`."""
    out = {}
    for rec in _git(root, "ls-files", "-s", "-z").decode("utf-8", "surrogateescape").split("\0"):
        if not rec:
            continue
        meta, _, path = rec.partition("\t")
        out[path] = (out[path] + "," if path in out else "") + meta.split(" ")[1]
    return out


def _head(root: Path):
    try:
        return _git(root, "rev-parse", "HEAD").decode().strip()
    except subprocess.CalledProcessError:
        return None


def _is_text(p: Path) -> bool:
    try:
        data = p.read_bytes()
    except OSError:
        return False
    if b"\0" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


# ------------------------------------------------------------------------------------------------ parts
def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=True, indent=0), encoding="ascii")
    tmp.replace(path)


def _expect(state_dir: Path | None):
    if state_dir is None:
        return None
    try:
        return json.loads((state_dir / "expect.json").read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None


def part_accept(root: Path, module: str, tests: str, state_dir: Path) -> dict:
    """Record the current module and tests file as the expected state (after a reviewed, accepted code change)."""
    exp = {"module_sha": _sha(root / module), "tests_sha": _sha(root / tests)}
    _write_json(state_dir / "expect.json", exp)
    return {"accepted": True, **exp}


def part_baseline(root: Path, state_dir: Path, module: str, tests: str) -> dict:
    _write_json(state_dir / "expect.json", {"module_sha": _sha(root / module), "tests_sha": _sha(root / tests)})
    idx = _index_map(root)
    paths = [{"path": p, "sha256": _sha(root / p), "index": idx.get(p)} for p in _git_changed(root)]
    state = {"head": _head(root), "paths": paths}
    state_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(state, ensure_ascii=True, indent=0)
    (state_dir / "baseline.json").write_text(text, encoding="ascii")
    return {"count": len(paths), "head": state["head"], "file": str(state_dir / "baseline.json"),
            "sha256": hashlib.sha256(text.encode("ascii")).hexdigest()}


def _load_baseline(state_dir: Path | None, want_sha: str | None):
    if state_dir is None:
        raise ValueError("scope needs --state-dir")
    text = (state_dir / "baseline.json").read_text(encoding="ascii")
    if want_sha and hashlib.sha256(text.encode("ascii")).hexdigest() != want_sha:
        raise ValueError("baseline.json differs from the recorded reference")
    return json.loads(text)


def part_backup(root: Path, module: str, tests: str, bdir: Path, state_dir: Path | None = None) -> dict:
    bdir.mkdir(parents=True, exist_ok=True)
    created = []
    for name, rel in (("module.orig", module), ("tests.orig", tests)):
        dst = bdir / name
        if not dst.exists():                  # never overwrite: a resumed run must keep the pre-change copy
            shutil.copyfile(root / rel, dst)
            created.append(name)
    res = {"created": created, "module_sha": _sha(bdir / "module.orig"), "tests_sha": _sha(bdir / "tests.orig"),
           "module_now": _sha(root / module), "tests_now": _sha(root / tests)}
    exp = _expect(state_dir)
    res["matches_expected"] = bool(exp) and res["module_sha"] == res["module_now"] == exp["module_sha"] and res["tests_sha"] == res["tests_now"] == exp["tests_sha"]
    return res


def part_restore(root: Path, module: str, tests: str, bdir: Path, state_dir: Path | None = None) -> dict:
    if not (bdir / "module.orig").is_file() or not (bdir / "tests.orig").is_file():
        return {"restored": False, "matches_expected": False, "error": f"no backup in {bdir}"}
    shutil.copyfile(bdir / "module.orig", root / module)
    shutil.copyfile(bdir / "tests.orig", root / tests)
    ok = _sha(root / module) == _sha(bdir / "module.orig") and _sha(root / tests) == _sha(bdir / "tests.orig")
    exp = _expect(state_dir)
    return {"restored": ok, "module_sha": _sha(root / module), "tests_sha": _sha(root / tests),
            "matches_expected": bool(ok and exp and _sha(root / module) == exp["module_sha"] and _sha(root / tests) == exp["tests_sha"])}


def part_hashes(root: Path, module: str, tests: str, state_dir: Path | None = None) -> dict:
    res = {"module_sha": _sha(root / module), "tests_sha": _sha(root / tests)}
    exp = _expect(state_dir)
    if exp:
        res["module_changed"] = res["module_sha"] != exp["module_sha"]
        res["matches_expected"] = res["module_sha"] == exp["module_sha"] and res["tests_sha"] == exp["tests_sha"]
    return res


def part_fresh(scratch_round: Path | None, evd: Path) -> dict:
    """Whether this round's scratch directory and evidence directory already hold anything (a reused round name)."""
    count = lambda d: sum(1 for _ in d.rglob("*")) if d is not None and d.is_dir() else 0  # noqa: E731
    return {"scratch_entries": count(scratch_round), "evidence_entries": count(evd)}


def part_copy(root: Path, src: Path, evd: Path) -> dict:
    if not src.is_dir():
        return {"copied": 0, "skipped": [], "error": f"no directory {src}"}
    copied, skipped, lines, dsts = 0, [], [], []
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if f.is_symlink() or not f.is_file() or "__pycache__" in rel.parts:
            continue
        try:
            rel.as_posix().encode("utf-8")
        except UnicodeEncodeError:            # a file name that is not valid UTF-8 cannot be committed portably
            skipped.append(rel.as_posix().encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace"))
            continue
        if f.stat().st_size > MAX_COPY_BYTES or not _is_text(f):
            skipped.append(rel.as_posix())
            continue
        dst = evd / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dst)
        copied += 1
        dsts.append(dst.relative_to(root).as_posix())
        lines.append(f"- `{f}` → `{dsts[-1]}`")
    evd.mkdir(parents=True, exist_ok=True)
    (evd / "PATHS.md").write_text("# Scratch → repository paths\n\n" + "\n".join(lines) +
                                  ("\n\nNot copied (binary, > 5 MB, or a file name that is not UTF-8):\n" + "\n".join(f"- `{s}`" for s in skipped) if skipped else "") + "\n",
                                  encoding="utf-8")
    ignored = []
    if dsts:
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "--stdin", "-z"], input="\0".join(dsts).encode(),
                           capture_output=True)
        ignored = [p for p in r.stdout.decode("utf-8", "surrogateescape").split("\0") if p]
    return {"copied": copied, "skipped": skipped[:50], "skipped_count": len(skipped), "ignored_by_git": ignored, "ignored_count": len(ignored)}


def part_snapshot(root: Path, module: str, evd: Path, state_dir: Path | None = None) -> dict:
    """Copy the module to code/module_after_review.py.  An existing snapshot equal to the reference is kept: on a resume
    the writer may already have added code to the module, and the module part judges those additions."""
    dst = evd / "code" / "module_after_review.py"
    dst.parent.mkdir(parents=True, exist_ok=True)
    exp = _expect(state_dir)
    kept = bool(exp) and dst.is_file() and _sha(dst) == exp["module_sha"]
    if not kept:
        shutil.copyfile(root / module, dst)
    return {"path": dst.relative_to(root).as_posix(), "sha256": _sha(dst), "kept": kept,
            "matches_expected": bool(exp) and _sha(dst) == exp["module_sha"]}


def part_verifier(root: Path, evd_rel: str) -> dict:
    evd = root / evd_rel
    allowed = {os.path.normpath(f"{evd_rel}/{rel}") for rel, kind, _ in _frozen_entries(evd, SOURCE_TOP) if kind == "f"}
    kinds = {}
    try:
        led = json.loads((evd / "review-verdicts" / "ledger.json").read_text(encoding="utf-8"))
        for v in led.get("versions", []) + led.get("not_reviewed", []):
            for n in v.get("numbers", []):
                kinds.setdefault((v.get("id"), n.get("name")), set()).add(n.get("kind"))
    except (OSError, ValueError, TypeError, AttributeError):
        pass

    def kind_check(e):                    # an entry that names its claim and number must carry that number's kind
        if not (e.get("claim") and e.get("number")):
            return None
        k = kinds.get((e["claim"], e["number"]))
        if k is None:
            return f"claim {e['claim']} has no number {e['number']!r} in the ledger"
        return None if e.get("kind") in k else f"kind {e.get('kind')!r} but the ledger's number is {sorted(k)}"

    lines: list[str] = []
    passed, total = ve.verify_counts(root, evd / "evidence.json", None, True, out=lines.append, allowed_files=allowed,
                                     entry_check=kind_check)
    return {"passed": passed, "total": total, "failures": [x for x in lines if x.startswith("FAIL")][:10]}


def part_pytest(root: Path, state_dir: Path | None = None) -> dict:
    junit = None
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if state_dir is not None:
        state_dir.mkdir(parents=True, exist_ok=True)
        junit = state_dir / f"pytest-{os.getpid()}.xml"
        cmd.append(f"--junit-xml={junit}")
    try:
        r = subprocess.run(cmd, cwd=root / "sycophancy_phase0", capture_output=True, text=True, timeout=3600)
        out, code = r.stdout, r.returncode
    except subprocess.TimeoutExpired:
        out, code = "timeout after 3600 s", -1
    tail = next((ln.strip() for ln in reversed(out.splitlines()) if SUMMARY.search(ln)), "")
    def num(w):
        m = re.search(rf"(\d+) {w}\b", tail)
        return int(m.group(1)) if m else 0
    res = {"passed": num("passed"), "failed": num("failed"), "errors": num("errors?"), "exit": code,
           "tail": (tail or (out.strip().splitlines() or [""])[-1])[-300:], "summary_found": bool(tail), "source": "stdout"}
    if junit is not None:                 # pytest's own report: nothing the tests print can change these counts
        try:
            node = ET.parse(junit).getroot()
            suites = [node] if node.tag == "testsuite" else list(node.iter("testsuite"))
            tot = lambda a: sum(int(s.get(a, 0)) for s in suites)  # noqa: E731
            res.update(passed=tot("tests") - tot("failures") - tot("errors") - tot("skipped"), failed=tot("failures"),
                       errors=tot("errors"), source="junit")
        except (OSError, ET.ParseError, ValueError):
            res.update(summary_found=False, source="junit missing")
        finally:
            try:
                junit.unlink()
            except OSError:
                pass
    return res


def _evd_copy(review_dir, led: dict, root: Path):
    scratch, evd_rel = led.get("scratch_round_dir", ""), led.get("evidence_dir", "")
    if not scratch or not isinstance(review_dir, str) or not under(review_dir, scratch) or review_dir == scratch:
        return None
    return root / evd_rel / review_dir[len(scratch) + 1:] / "verdict.json"


def part_assemble(root: Path, evd_rel: str, parts: dict) -> dict:
    """Build review-verdicts/ledger.json from review-verdicts/ledger.parts/<key>.json in the order of the manifest.
    Parts '<key>.<i>' form the list <key> at the position of the first of them (versions, not_reviewed); an empty list
    comes as the single part '<key>'."""
    pdir = root / evd_rel / "review-verdicts" / "ledger.parts"
    led, missing, bad = {}, [], []
    for key in parts:
        f = pdir / f"{key}.json"
        try:
            val = json.loads(f.read_text(encoding="utf-8"))
        except FileNotFoundError:
            missing.append(key)
            continue
        except ValueError:
            bad.append(key)
            continue
        head, dot, idx = key.partition(".")
        if dot and idx.isdigit():
            led.setdefault(head, []).append(val)
        else:
            led[key] = val
    out = root / evd_rel / "review-verdicts" / "ledger.json"
    text = json.dumps(led, ensure_ascii=False, indent=1)
    text = re.sub("[\ud800-\udfff]", lambda m: "\\u%04x" % ord(m.group()), text)   # lone surrogates escaped: valid UTF-8, lossless
    out.write_text(text, encoding="utf-8")
    return {"parts": len(parts), "missing": missing, "unreadable": bad}


def part_ledger(root: Path, evd_rel: str, expect: dict | None, ledger_sha: str | None, parts: dict | None = None) -> dict:
    path = root / evd_rel / "review-verdicts" / "ledger.json"
    problems, warnings, differing = [], [], []
    try:
        led = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"versions": -1, "mismatches": 1, "warnings": 0, "problems": [f"ledger unreadable: {type(exc).__name__}: {exc}"],
                "differing_parts": list(parts or [])}
    if ledger_sha is not None and canonical_sha(led) != ledger_sha:
        diff = []
        for k, want in (parts or {}).items():
            node = led
            try:
                for step in k.split("."):
                    node = node[int(step)] if isinstance(node, list) else node[step]
            except (KeyError, IndexError, ValueError, TypeError):
                diff.append(f"{k} (missing)")
                continue
            if canonical_sha(node)[:len(want)] != want:
                diff.append(k)
        split = {k.partition(".")[0] for k in (parts or {}) if k.partition(".")[2].isdigit()}
        extra = [k for k in led if parts is not None and k not in parts and k not in split]
        for key in split:
            if isinstance(led.get(key), list) and len(led[key]) != sum(1 for k in parts if k.partition(".")[0] == key and k.partition(".")[2].isdigit()):
                diff.append(f"{key} (count {len(led[key])})")
        differing = diff + [k + " (unexpected)" for k in extra]
        problems.append("ledger.json differs from the ledger the workflow built (canonical sha256)"
                        + (f"; differing parts: {differing}" if parts is not None else ""))
    try:
        iso, versions, final = led["isolation"], led["versions"], led["final"]
    except (KeyError, TypeError) as exc:
        return {"versions": -1, "mismatches": len(problems) + 1, "warnings": 0,
                "problems": (problems + [f"ledger incomplete: {type(exc).__name__}: {exc}"])[:10], "differing_parts": differing}
    seen = {}
    for v in versions:
        key = (v.get("id"), v.get("version"), v.get("attempt"))
        if key in seen:
            problems.append(f"duplicate version {key}")
        seen[key] = v
        got = decide(v.get("verdicts", {}), iso)
        for k, want in got.items():
            if v.get(k) != want:
                problems.append(f"{key}: stored {k}={v.get(k)!r}, recomputed {want!r}")
        for lens in LENSES:
            lv = v.get("verdicts", {}).get(lens)
            if lv is None:
                continue
            cp = _evd_copy(lv.get("review_dir"), led, root)
            if cp is None or not cp.is_file():
                warnings.append(f"{key} {lens}: reviewer's verdict.json copy missing")
                continue
            try:
                own = json.loads(cp.read_text(encoding="utf-8"))
            except ValueError:
                warnings.append(f"{key} {lens}: reviewer's verdict.json unreadable")
                continue
            fields = ("severity", "consequence_follows") if lens == "applicability" else ("refuted", "severity", "reproduced_numbers")
            diff = [f for f in fields if own.get(f) != lv.get(f)]
            if lens != "applicability" and sorted(map(str, own.get("files_read") or [])) != sorted(map(str, lv.get("files_read") or [])):
                diff.append("files_read")
            if diff:
                warnings.append(f"{key} {lens}: reviewer's verdict.json differs in {diff}")
    for f in final:
        key = (f.get("id"), f.get("version"), f.get("attempt"))
        v = seen.get(key)
        if v is None:
            problems.append(f"final {key} has no version entry")
        elif any(v.get(k) != f.get(k) for k in ("truth_label", "v4_label", "blind_status")):
            problems.append(f"final {key} labels differ from its version entry")
    if expect is not None:
        exp_v = {(e["id"], e["version"], e["attempt"]): e for e in expect.get("versions", [])}
        if set(exp_v) != set(seen):
            problems.append(f"version set differs from the workflow's: missing {sorted(set(exp_v) - set(seen))[:5]}, extra {sorted(set(seen) - set(exp_v))[:5]}")
        for key, e in exp_v.items():
            v = seen.get(key)
            if v is not None and any(v.get(k) != e.get(k) for k in ("truth_label", "v4_label", "blind_status")):
                problems.append(f"{key}: labels differ from the workflow's {e}")
        exp_f = [(e["id"], e["version"], e["attempt"], e["truth_label"]) for e in expect.get("final", [])]
        got_f = [(f.get("id"), f.get("version"), f.get("attempt"), f.get("truth_label")) for f in final]
        if exp_f != got_f:
            problems.append("final labels differ from the workflow's")
    return {"versions": len(versions), "mismatches": len(problems), "warnings": len(warnings),
            "problems": problems[:10], "warning_list": warnings[:10], "differing_parts": differing}


def part_record(root: Path, rnd: str, evd_rel: str) -> dict:
    text = (root / ARCHIVE_REL).read_text(encoding="utf-8")
    heads = [m.start() for m in re.finditer(rf"(?m)^### {re.escape(rnd)}(?=[\s（(:：]|$)", text)]
    if not heads:
        return {"headings": 0, "chars": 0, "tags": 0, "bad_tags": [], "bad_tag_count": 0}
    s = heads[0]
    nxt = re.compile(r"(?m)^(## |### r\d)").search(text, s + 1)        # the next round heading or the next section
    sub = text[s:nxt.start() if nxt else len(text)]
    inner = len(re.findall(r"(?m)^#{2,3} ", sub)) - 1                     # sub-structure must use #### or deeper
    try:
        entries = {e["id"]: e["printed"] for e in json.loads((root / evd_rel / "evidence.json").read_text(encoding="utf-8"))["entries"]}
    except (OSError, ValueError, KeyError, TypeError):
        entries = {}
    tags, bad, prev_end = 0, [], 0
    for m in re.finditer(r"\[E:([^\]]+)\]", sub):
        if sub[m.start() - 1:m.start()] == "`" and sub[m.end():m.end() + 1] == "`":   # a tag in a code span is a mention
            continue
        before = sub[max(prev_end, m.start() - 120):m.start()].replace("−", "-")   # after the previous tag, at most 120 chars
        prev_end = m.end()
        for tid in (t.strip() for t in m.group(1).split(",")):
            tags += 1
            pr = entries.get(tid)
            if tid not in entries:
                bad.append(f"{tid}: no evidence entry")
            elif not isinstance(pr, str):
                bad.append(f"{tid}: printed value is not a string")
            elif not _number_token(pr.replace("−", "-"), before):
                bad.append(f"{tid}: printed value {pr} not (as a whole number) between the previous tag and this one")
    return {"headings": len(heads), "chars": len(sub), "inner_headings": inner, "tags": tags, "bad_tags": bad[:10], "bad_tag_count": len(bad)}


def _number_token(printed: str, text: str) -> bool:
    """printed occurs in text as a complete number: no digit, '.' or ',' before it; no sign before it unless printed has one
    (a minus after a digit, letter or bracket is an operator, e.g. 1-0.52); no digit, decimal or thousands continuation,
    exponent or ×10 after it."""
    signed = printed[:1] in "+-"
    pre = r"(?<![\d.,])" + ("" if signed else r"(?:(?<![+\-])|(?<=[\d)}\]A-Za-z$][+\-]))")
    post = r"(?!\d|[.,]\d|\s*(?:[eE][+\-]?\d|[×x]\s*10))"
    return re.search(pre + re.escape(printed) + post, text) is not None


def _frozen_entries(evd: Path, top: re.Pattern = FROZEN_TOP):
    """(relative path, kind, payload) for everything under the frozen top-level directories, without following symlinks.
    kind 'f' = regular file (payload: content sha256), 'l' = symlink (payload: link target); __pycache__ is skipped."""
    out = []
    if not evd.is_dir():
        return out
    for name in sorted(os.listdir(evd)):
        d = evd / name
        if not top.match(name):
            continue
        if d.is_symlink():
            out.append((name, "l", os.readlink(d)))
            continue
        if not d.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(d, followlinks=False):
            dirnames[:] = sorted(x for x in dirnames if x != "__pycache__")
            base_ = Path(dirpath)
            for x in sorted(filenames) + sorted(y for y in os.listdir(base_) if (base_ / y).is_symlink() and (base_ / y).is_dir()):
                q = base_ / x
                rel = q.relative_to(evd).as_posix()
                if q.is_symlink():
                    out.append((rel, "l", os.readlink(q)))
                elif q.is_file():
                    out.append((rel, "f", hashlib.sha256(q.read_bytes()).hexdigest()))
    return sorted(set(out))


def part_frozen(evd: Path, state_dir: Path | None = None, freeze: bool = False, ledger_ok: bool | None = None) -> dict:
    """Hash of the frozen material.  With freeze, record it as the reference in <state-dir>/frozen.json, but only when the
    ledger check of the same run passed, and never over a different earlier reference (the first freeze is final);
    otherwise report whether it is unchanged against that reference (None if there is none)."""
    h, n = hashlib.sha256(), 0
    for rel, kind, payload in _frozen_entries(evd):
        h.update(rel.encode("utf-8", "surrogateescape") + b"\0" + kind.encode() + b"\0" + payload.encode("utf-8", "surrogateescape") + b"\n")
        n += 1
    res = {"hash": h.hexdigest(), "files": n}
    if state_dir is not None:
        ref = state_dir / "frozen.json"
        if freeze:
            try:
                old = json.loads(ref.read_text(encoding="ascii"))["hash"]
            except (OSError, ValueError, KeyError):
                old = None
            exp = _expect(state_dir)
            snap = evd / "code" / "module_after_review.py"
            if old is not None:
                res["frozen"] = old == res["hash"]
                if not res["frozen"]:
                    res["reason"] = "the frozen material differs from the reference recorded by the first freeze"
            elif ledger_ok is False:
                res["frozen"] = False
                res["reason"] = "not recorded: the ledger check of this run failed"
            elif not exp or not snap.is_file() or _sha(snap) != exp.get("module_sha"):
                res["frozen"] = False
                res["reason"] = "not recorded: the module snapshot is missing or differs from expect.json"
            else:
                _write_json(ref, res)
                res["frozen"] = True
        else:
            try:
                res["unchanged"] = json.loads(ref.read_text(encoding="ascii"))["hash"] == res["hash"]
            except (OSError, ValueError, KeyError):
                res["unchanged"] = None
    return res


_PLAIN_NEW = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _bound_names(node) -> set[str]:
    names = set()
    if isinstance(node, _PLAIN_NEW):
        names.add(node.name)
    for sub in ast.walk(node) if not isinstance(node, _PLAIN_NEW) else []:
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
            names.add(sub.id)
        elif isinstance(sub, ast.alias):
            names.add((sub.asname or sub.name).split(".")[0])
        elif isinstance(sub, (ast.Global, ast.Nonlocal)):
            names.update(sub.names)
    return names


_DYNAMIC = {"globals", "vars", "setattr", "delattr", "exec", "eval", "__import__", "locals"}
_DYNAMIC_ALWAYS = {"globals", "exec", "eval", "__import__"}          # in function bodies; vars/setattr/delattr only on globals


def _dataclass_decorator(d) -> bool:
    """@dataclass, @dataclasses.dataclass, or either called with literal keyword arguments, e.g. @dataclass(frozen=True)."""
    if isinstance(d, ast.Call):
        return not d.args and all(isinstance(k.value, ast.Constant) for k in d.keywords) and _dataclass_decorator(d.func)
    return isinstance(d, (ast.Name, ast.Attribute)) and (getattr(d, "id", None) or getattr(d, "attr", None)) == "dataclass"


def _protected_names(src: str, tree) -> set[str]:
    """Names whose rebinding changes reviewed behaviour: module-level bindings and reads, and every name a snapshot
    function or class resolves globally (builtins included), from the symbol tables.  Function locals are not included."""
    names = set().union(*(_bound_names(n) for n in tree.body)) if tree.body else set()
    for n in tree.body:                                       # module-level reads outside function and class bodies
        if not isinstance(n, _PLAIN_NEW):
            names |= {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}

    def walk(t):
        if t.get_type() != "module":
            names.update(sym.get_name() for sym in t.get_symbols() if sym.is_global() or sym.is_declared_global())
        for c in t.get_children():
            walk(c)
    walk(symtable.symtable(src, "<snapshot>", "exec"))
    return names


def _store_root(x):
    while isinstance(x, (ast.Attribute, ast.Subscript)):
        x = x.value
    return x.id if isinstance(x, ast.Name) else None


def _expr_effects(nodes, protected: set[str]) -> list[str]:
    out = []
    for node in nodes:
        for x in ast.walk(node):
            if isinstance(x, ast.Name) and x.id in _DYNAMIC:
                out.append(f"uses {x.id}()")
            elif isinstance(x, (ast.Attribute, ast.Subscript)) and isinstance(x.ctx, (ast.Store, ast.Del)) and _store_root(x) in protected:
                out.append(f"assigns into {_store_root(x)}")
            elif isinstance(x, (ast.Global, ast.Nonlocal)) and set(x.names) & protected:
                out.append(f"declares {sorted(set(x.names) & protected)} global")
    return out


def _child_table(table, node):
    if table is None:
        return None
    return next((c for c in table.get_children() if c.get_name() == node.name and c.get_lineno() == node.lineno), None)


def _import_time_effects(node, protected: set[str], table=None) -> list[str]:
    """Hardening for new functions and classes (round-protocol v5.1 §9.5, §9.12; not a sandbox).  Positions evaluated at
    import (decorators, defaults, annotations, bases, class bodies) may not use dynamic namespace access or store into a
    protected name; function bodies may not declare protected names global, use dynamic namespace access, or store into
    a protected name the body resolves globally (the symbol table tells a body's own locals apart)."""
    out = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = node.args
        heads = list(node.decorator_list) + list(a.defaults) + [d for d in a.kw_defaults if d is not None]
        heads += [x.annotation for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg] if x is not None and x.annotation is not None]
        heads += [node.returns] if node.returns is not None else []
        out += _expr_effects(heads, protected)
        sub = _child_table(table, node)
        glob = ({sym.get_name() for sym in sub.get_symbols() if sym.is_global() or sym.is_declared_global()} if sub is not None
                else set(protected))
        for st in node.body:
            for x in ast.walk(st):
                if isinstance(x, (ast.Global, ast.Nonlocal)) and set(x.names) & protected:
                    out.append(f"declares {sorted(set(x.names) & protected)} global")
                elif isinstance(x, ast.Name) and x.id in _DYNAMIC_ALWAYS:
                    out.append(f"uses {x.id}()")
                elif (isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in ("vars", "setattr", "delattr")
                      and (not x.args or not isinstance(x.args[0], ast.Name) or (x.args[0].id in protected and x.args[0].id in glob))):
                    out.append(f"uses {x.func.id}() on a module-level object")
                elif isinstance(x, (ast.Attribute, ast.Subscript)) and isinstance(x.ctx, (ast.Store, ast.Del)):
                    r = _store_root(x)
                    if r in protected and r in glob:
                        out.append(f"assigns into {r}")
    elif isinstance(node, ast.ClassDef):
        out += _expr_effects(list(node.decorator_list) + list(node.bases) + [k.value for k in node.keywords], protected)
        sub = _child_table(table, node)
        for st in node.body:
            if isinstance(st, _PLAIN_NEW):
                out += _import_time_effects(st, protected, sub)
            else:
                out += _expr_effects([st], protected)
    return sorted(set(out))


def part_module(root: Path, module: str, evd: Path) -> dict:
    snap = evd / "code" / "module_after_review.py"
    if not snap.is_file():
        return {"violations": -1, "details": ["review-time snapshot missing"]}
    a_src, b_src = snap.read_text(encoding="utf-8"), (root / module).read_text(encoding="utf-8")
    try:
        a_tree, b_tree = ast.parse(a_src), ast.parse(b_src)
    except SyntaxError as exc:
        return {"violations": 1, "details": [f"module does not parse: {exc}"]}
    # statements are compared by their AST (decorators included; formatting and comments between statements ignored)
    a_segs = [ast.dump(n) for n in a_tree.body]
    b_segs = [ast.dump(n) for n in b_tree.body]
    pool, details = list(b_segs), []
    for n, s in zip(a_tree.body, a_segs):
        if s in pool:
            pool.remove(s)
        else:
            details.append(f"snapshot statement at line {n.lineno} is missing or changed")
    snap_names = _protected_names(a_src, a_tree)
    b_table = symtable.symtable(b_src, "<module>", "exec")
    remaining = list(a_segs)
    for n, s in zip(b_tree.body, b_segs):
        if s in remaining:
            remaining.remove(s)
            continue
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            if any(al.name == "*" for al in n.names):
                details.append(f"new star import at line {n.lineno} binds names that cannot be checked")
            elif _bound_names(n) & snap_names:
                details.append(f"new import at line {n.lineno} rebinds {sorted(_bound_names(n) & snap_names)}")
            continue
        if not isinstance(n, _PLAIN_NEW) or (n.decorator_list and not all(_dataclass_decorator(d) for d in n.decorator_list)):
            details.append(f"new top-level statement at line {n.lineno} is not a plain new function or class")
        elif _bound_names(n) & snap_names:
            details.append(f"new statement at line {n.lineno} rebinds {sorted(_bound_names(n) & snap_names)}")
        else:
            details.extend(f"new statement at line {n.lineno}: {w}" for w in _import_time_effects(n, snap_names, b_table))
    return {"violations": len(details), "details": details[:10]}


def part_scope(root: Path, allowed: list[str], baseline: dict) -> dict:
    base = {b["path"]: (b.get("sha256"), b.get("index")) for b in baseline["paths"]}
    allowed_p = lambda p: any(p == a or (a.endswith("/") and p.startswith(a)) for a in allowed)  # noqa: E731
    idx = _index_map(root)
    out = set()
    for p in _git_changed(root):
        if "__pycache__/" in p or p.endswith(".pyc") or allowed_p(p):
            continue
        if p in base and base[p] == (_sha(root / p), idx.get(p)):    # same working-tree content AND same staged content
            continue
        out.add(p)
    for p, (h, ix) in base.items():           # a baseline path reverted, committed, deleted or re-staged
        if not allowed_p(p) and (_sha(root / p), idx.get(p)) != (h, ix):
            out.add(p)
    head = _head(root)
    return {"out_of_scope": sorted(out)[:20], "count": len(out), "head_moved": head != baseline.get("head"), "head": head}


# ------------------------------------------------------------------------------------------------ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("round")
    ap.add_argument("--module", required=True)
    ap.add_argument("--tests", default=TESTS_REL)
    ap.add_argument("--only", default="verifier,pytest,ledger,record,frozen,module,scope")
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--baseline-sha", default=None)
    ap.add_argument("--copy-from", default=None)
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--expect", default=None)
    ap.add_argument("--ledger-sha", default=None)
    ap.add_argument("--ledger-parts", default=None)
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", a.round):
        ap.error("bad round name")
    for rel in (a.module, a.tests):
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            ap.error(f"{rel} must be repository-relative")

    def outside_dir(x, name):
        if not x or not Path(x).is_absolute():
            raise ValueError(f"{name} needs an absolute directory")
        p = Path(x).resolve()
        if p == root or root in p.parents:
            raise ValueError(f"{name} must be outside the repository")
        return p

    evd_rel = f"docs/research/goal-rounds/{a.round}"
    evd = root / evd_rel
    parts = [p.strip() for p in a.only.split(",") if p.strip()]
    res: dict = {}
    for part in parts:
        try:
            sd = outside_dir(a.state_dir, "--state-dir") if a.state_dir else None
            if part == "baseline":
                res[part] = part_baseline(root, outside_dir(a.state_dir, "--state-dir"), a.module, a.tests)
            elif part == "accept":
                res[part] = part_accept(root, a.module, a.tests, outside_dir(a.state_dir, "--state-dir"))
            elif part == "backup":
                res[part] = part_backup(root, a.module, a.tests, outside_dir(a.backup_dir, "--backup-dir"), sd)
            elif part == "restore":
                res[part] = part_restore(root, a.module, a.tests, outside_dir(a.backup_dir, "--backup-dir"), sd)
            elif part == "hashes":
                res[part] = part_hashes(root, a.module, a.tests, sd)
            elif part == "fresh":
                res[part] = part_fresh(outside_dir(a.copy_from, "--copy-from") if a.copy_from else None, evd)
            elif part == "copy":
                res[part] = part_copy(root, outside_dir(a.copy_from, "--copy-from"), evd)
            elif part == "snapshot":
                res[part] = part_snapshot(root, a.module, evd, sd)
            elif part == "assemble":
                if not a.ledger_parts:
                    raise ValueError("assemble needs --ledger-parts")
                res[part] = part_assemble(root, evd_rel, json.loads(a.ledger_parts))
            elif part == "verifier":
                res[part] = part_verifier(root, evd_rel)
            elif part == "pytest":
                res[part] = part_pytest(root, outside_dir(a.state_dir, "--state-dir") if a.state_dir else None)
            elif part == "ledger":
                res[part] = part_ledger(root, evd_rel, json.loads(a.expect) if a.expect else None, a.ledger_sha,
                                        json.loads(a.ledger_parts) if a.ledger_parts else None)
            elif part == "record":
                res[part] = part_record(root, a.round, evd_rel)
            elif part == "frozen":
                res[part] = part_frozen(evd, sd)
            elif part == "freeze":
                lp = res.get("ledger")
                res[part] = part_frozen(evd, outside_dir(a.state_dir, "--state-dir"), freeze=True,
                                        ledger_ok=None if lp is None else (isinstance(lp, dict) and lp.get("mismatches") == 0))
            elif part == "module":
                res[part] = part_module(root, a.module, evd)
            elif part == "scope":
                res[part] = part_scope(root, [ARCHIVE_REL, a.tests, a.module, evd_rel + "/"],
                                       _load_baseline(outside_dir(a.state_dir, "--state-dir"), a.baseline_sha))
            else:
                res[part] = {"error": f"unknown part {part}"}
        except Exception as exc:  # a part that cannot be measured is reported, never silently skipped
            res[part] = {"error": f"{type(exc).__name__}: {exc}"}
        print(f"{part}: {json.dumps(res[part], ensure_ascii=False)[:400]}")
    print("GATE " + json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
