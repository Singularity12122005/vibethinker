"""F3 — synthetic Python program outputs (plan Appendix C).

Programs: 8–15 lines; integer variable initialisation, one ``for`` loop (<= 20 iterations) with an if/else,
list append / sum, optional string concatenation, optional second loop over the list, final ``print(expr)``.
No randomness, no imports, no I/O.  gold = stdout of a 5-second sandboxed run (``python -I -S -c``), stripped;
output length <= 12.  Script C changes one literal constant so that the output changes (re-draw otherwise).
``gold_type`` is ``integer`` when the output is an integer literal (compared as a number, §5.1) else ``string``.
"""
from __future__ import annotations

import random
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .common import BankRecord

SEED = 20261016
N_PROGRAMS = 120
FORBIDDEN = re.compile(r"\b(import|open|exec|eval|input|__|os\b|sys\b|random|while)\b")
INT_RE = re.compile(r"^-?\d+$")


@dataclass
class Slot:
    line: int
    old: int
    candidates: List[int]
    render: str          # line template with '{v}' for the literal


class Program:
    def __init__(self, lines: List[str], slots: List[Slot]):
        self.lines = lines
        self.slots = slots

    @property
    def code(self) -> str:
        return "\n".join(self.lines) + "\n"

    def with_slot(self, slot: Slot, v: int) -> "Program":
        lines = list(self.lines)
        lines[slot.line] = slot.render.format(v=v)
        return Program(lines, [s for s in self.slots if s is not slot])


def run_sandboxed(code: str, timeout: float = 5.0) -> Optional[str]:
    """stdout (stripped) of ``python -I -S -c code``; None on error/timeout/non-zero exit."""
    if FORBIDDEN.search(code):
        return None
    try:
        r = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True,
                           timeout=timeout, env={"PYTHONHASHSEED": "0"})
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0 or r.stderr:
        return None
    return r.stdout.strip()


def gen_program(rng: random.Random) -> Program:
    lines: List[str] = []
    slots: List[Slot] = []

    def add(tmpl: str, v: Optional[int] = None, cands: Optional[List[int]] = None):
        if v is None:
            lines.append(tmpl)
        else:
            lines.append(tmpl.format(v=v))
            slots.append(Slot(len(lines) - 1, v, [c for c in (cands or []) if c != v], tmpl))

    a, b = rng.randint(2, 9), rng.randint(2, 9)
    add("a = {v}", a, list(range(2, 10)))
    add("b = {v}", b, list(range(2, 10)))
    add("total = 0")
    add("items = []")
    use_str = rng.random() < 0.5
    if use_str:
        add('s = ""')
    n = rng.randint(5, 20)
    start = rng.choice([0, 1])
    add(f"for i in range({start}, {{v}}):", n + start, [k for k in range(start + 4, start + 21)])
    k = rng.randint(2, 5)
    cond_kind = rng.choice(["mod", "gt", "modshift"])
    if cond_kind == "mod":
        add("    if i % {v} == 0:", k, [2, 3, 4, 5])
    elif cond_kind == "gt":
        add("    if i > {v}:", rng.randint(2, max(3, n // 2 + 1)), list(range(1, n)))
    else:
        add("    if (i + a) % {v} == 1:", k, [2, 3, 4, 5])
    add("        total += " + rng.choice(["a * i", "i", "a + b", "b * i", "i * i"]))
    add("    else:")
    add("        total -= " + rng.choice(["b", "a", "1", "i % 3", "2"]))
    m = rng.randint(3, 9)
    add("    items.append(total % {v})", m, list(range(3, 10)))
    if use_str:
        add("    s += " + rng.choice(['str(i % 10)', '"x"', 'str(total % 10)', '"ab"[i % 2]']))
    if rng.random() < 0.6:
        thr = rng.randint(1, m - 1)
        add("for v in items:")
        add("    if v > {v}:", thr, list(range(0, m)))
        add("        total += " + rng.choice(["v", "1", "v * 2", "v - 1"]))
    choices = ["print(total)", "print(sum(items))", "print(items[-1] + total)", "print(total % 97)", "print(sum(items) - total)"]
    if use_str:
        choices += ["print(s[-6:])", "print(s[:5] + str(total % 10))", "print(len(s) + total)"]
    add(rng.choice(choices))
    return Program(lines, slots)


def _valid_output(out: Optional[str]) -> bool:
    return out is not None and 0 < len(out) <= 12 and "\n" not in out


def modify(prog: Program, rng: random.Random, gold: str, max_slots: int = 6) -> Optional[Tuple[Program, Slot, int, str]]:
    """Change one literal so the output changes; returns (new_program, slot, new_value, new_output) or None."""
    slots = [s for s in prog.slots if s.candidates]
    rng.shuffle(slots)
    for slot in slots[:max_slots]:
        cands = list(slot.candidates)
        rng.shuffle(cands)
        for v in cands[:4]:
            p2 = prog.with_slot(slot, v)
            out = run_sandboxed(p2.code)
            if _valid_output(out) and out != gold:
                return p2, slot, v, out
    return None


def statement_for(code: str) -> str:
    return f"下面是一段 Python 程序：\n```python\n{code.rstrip()}\n```\n运行后标准输出的内容是什么？（只写输出本身，不含引号）"


def build_f3(seed: int = SEED, n_programs: int = N_PROGRAMS, max_tries: int = 20000) -> List[BankRecord]:
    rng = random.Random(seed)
    out: List[BankRecord] = []
    seen = set()
    tries = 0
    while len(out) < n_programs:
        tries += 1
        if tries > max_tries:
            raise RuntimeError("F3: too many rejections")
        prog = gen_program(rng)
        if not (8 <= len(prog.lines) <= 15) or prog.code in seen:
            continue
        gold = run_sandboxed(prog.code)
        if not _valid_output(gold):
            continue
        mod = modify(prog, rng, gold)
        if mod is None:
            continue
        p2, slot, v, gold2 = mod
        seen.add(prog.code)
        idx = len(out)
        gt = "integer" if INT_RE.match(gold) else "string"
        note = f"将程序第 {slot.line + 1} 行中的 {slot.old} 改为 {v}（该行改为 `{p2.lines[slot.line].strip()}`）"
        out.append(BankRecord(problem_id=f"F3-prog-{idx:03d}", family="F3", statement_zh=statement_for(prog.code),
                              gold=gold, gold_type=gt, template="program", params=dict(code=prog.code, n_lines=len(prog.lines)),
                              modified_statement_zh=statement_for(p2.code), modified_gold=gold2, modification_note=note,
                              meta=dict(modified_code=p2.code, modified_line=slot.line + 1, modified_gold_type="integer" if INT_RE.match(gold2) else "string")))
    return out
