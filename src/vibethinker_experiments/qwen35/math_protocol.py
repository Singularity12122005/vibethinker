"""Qwen3.5 math-RL protocol and final-answer verifier."""

from __future__ import annotations

import re
from typing import Any

from ..common.timeout import call_with_timeout
from .math_grading import extract_answer, grade_answer_mathd, grade_answer_sympy

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
STRICT_PROTOCOL_RE = re.compile(r"^\s*<think>(?P<think>[\s\S]*?)</think>(?P<visible>[\s\S]*)$")
PROTOCOL_TAG_RE = re.compile(r"</?(?:think|answer)>")
ANSWER_CUE_RE = re.compile(
    r"(?is)(?:final\s+answer|the\s+answer|answer)\s*(?:is\s*|[:=]\s*)(?P<answer>[^\n]+)"
)
BOLD_RE = re.compile(r"\*\*(?P<answer>.+?)\*\*")
INLINE_MATH_RE = re.compile(r"(?<!\\)\$(?!\$)(?P<answer>[^$\n]+?)(?<!\\)\$")
NUMBER_RE = re.compile(
    r"[-+]?(?:\\?\$\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:\s*/\s*\d+)?(?:\\?%)?"
)
CURRENCY_RE = re.compile(r"(?:\\?\$\s*)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
DURATION_RE = re.compile(
    r"(?i)(?P<hours>\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b"
    r"(?:\s*(?:and|,)?\s*(?P<minutes>\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m)\b)?"
)


def parse_protocol(text: str) -> dict[str, Any]:
    match = STRICT_PROTOCOL_RE.match(text)
    if not match:
        visible = text.split(THINK_CLOSE, 1)[1].strip() if THINK_CLOSE in text else ""
        return {
            "format_ok": False,
            "has_think_close": THINK_CLOSE in text,
            "has_visible_output": bool(visible),
            "visible_text": visible,
        }
    think, visible = match.group("think"), match.group("visible").strip()
    invalid_tags = PROTOCOL_TAG_RE.search(think) or PROTOCOL_TAG_RE.search(visible)
    format_ok = bool(think.strip() and visible and not invalid_tags)
    return {
        "format_ok": format_ok,
        "has_think_close": True,
        "has_visible_output": bool(visible),
        "visible_text": visible if format_ok else "",
    }


def protocol_progress_reward(text: str) -> float:
    open_count, close_count = text.count(THINK_OPEN), text.count(THINK_CLOSE)
    reward = 0.1 * (open_count == 1) + 0.1 * (close_count == 1)
    if open_count == close_count == 1 and text.index(THINK_OPEN) < text.index(THINK_CLOSE):
        reward += 0.1
    return round(float(reward), 10)


def _dedupe(values: list[str]) -> list[str]:
    result, seen = [], set()
    for value in values:
        candidate = str(value).strip().strip("`*_ $").rstrip(".。;,，").strip()
        if not candidate or len(candidate) > 2000:
            continue
        key = " ".join(candidate.split())
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _expand_conclusion(value: str) -> list[str]:
    candidates: list[str] = []
    boxed = extract_answer(value)
    if boxed:
        candidates.append(boxed)
    bold = [match.group("answer") for match in BOLD_RE.finditer(value)]
    candidates.extend(bold)
    candidates.extend(match.group("answer") for match in INLINE_MATH_RE.finditer(value))
    duration = DURATION_RE.search(value)
    if duration:
        total = float(duration.group("hours")) * 60 + float(duration.group("minutes") or 0)
        candidates.append(str(int(total)) if total.is_integer() else str(total))
    plain = re.sub(r"[*_`#>]", "", value)
    numbers = NUMBER_RE.findall(plain)
    currencies = CURRENCY_RE.findall(plain)
    if len(currencies) == 1:
        candidates.append(currencies[0])
    if numbers:
        correction = re.search(r"(?i)\bnot\b.+?\b(?:but|rather)\b", plain)
        starts_with_number = re.match(rf"^\s*{NUMBER_RE.pattern}", plain)
        candidates.append(numbers[-1] if correction or not starts_with_number else numbers[0])
    candidates.append(value)
    return _dedupe(candidates)


def final_answer_candidate_groups(answer_text: str) -> list[tuple[str, list[str]]]:
    """Order candidates by confidence and preserve explicit-conclusion precedence."""
    text = str(answer_text).strip()
    if not text:
        return []
    groups: list[tuple[str, list[str]]] = []
    boxed = extract_answer(text)
    boxed_position = max(text.rfind("\\boxed"), text.rfind("\\fbox"))
    cues = list(ANSWER_CUE_RE.finditer(text))
    cue_position = cues[-1].start() if cues else -1
    high = []
    if boxed:
        high.append((boxed_position, "boxed", _dedupe([boxed])))
    if cues:
        high.append((cue_position, "answer_cue", _expand_conclusion(cues[-1].group("answer"))))
    groups.extend((name, candidates) for _, name, candidates in sorted(high, reverse=True))

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    tail = "\n".join(lines[-4:])
    emphasis = [match.group("answer") for match in BOLD_RE.finditer(tail)]
    if emphasis:
        groups.append(("final_emphasis", _expand_conclusion(emphasis[-1])))
    math_spans = [match.group("answer") for match in INLINE_MATH_RE.finditer(tail)]
    if math_spans:
        groups.append(("final_math", _expand_conclusion(math_spans[-1])))
    if lines:
        groups.append(("final_line", _expand_conclusion(lines[-1])))
    return [(name, values) for name, values in groups if values]


def answer_candidates(answer_text: str) -> list[str]:
    return [
        candidate
        for _, candidates in final_answer_candidate_groups(answer_text)
        for candidate in candidates
    ]


def grade_math_answer(answer_text: str, ground_truth: str) -> tuple[bool, dict[str, Any]]:
    groups = final_answer_candidate_groups(answer_text)
    reference = extract_answer(str(ground_truth)) or str(ground_truth).strip().strip("$")
    if not groups or not reference:
        return False, {"reason": "missing_final_answer", "reference": reference or None}
    tried: list[dict[str, str]] = []
    for source, candidates in groups:
        for candidate in candidates:
            tried.append({"source": source, "candidate": candidate})
            if call_with_timeout(grade_answer_mathd, candidate, reference) or call_with_timeout(
                grade_answer_sympy, candidate, reference
            ):
                return True, {
                    "reason": "correct",
                    "matched": candidate,
                    "matched_source": source,
                    "reference": reference,
                }
        if source in {"boxed", "answer_cue"}:
            break
    return False, {
        "reason": "wrong",
        "candidate": tried[0]["candidate"] if tried else None,
        "reference": reference,
        "tried": tried,
    }
