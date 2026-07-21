"""Pure scoring and reporting functions with no network or file-system access."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from typing import Any

STRICT_PROTOCOL_RE = re.compile(r"^\s*<think>(?P<think>[\s\S]*?)</think>(?P<visible>[\s\S]+?)\s*$")
PROTOCOL_TAG_RE = re.compile(r"</?(?:think|answer)>", re.IGNORECASE)
CodeGrader = Callable[[str, dict[str, Any]], tuple[float, dict[str, Any]]]


def visible_after_think(text: str) -> str:
    return text.split("</think>", 1)[1].strip() if "</think>" in text else ""


def best_effort_answer(text: str) -> str:
    if "</think>" in text:
        return visible_after_think(text)
    return re.sub(r"^\s*<think>\s*", "", text, count=1, flags=re.IGNORECASE).strip()


def score_format(text: str) -> tuple[float, dict[str, Any]]:
    reasons: list[str] = []
    match = STRICT_PROTOCOL_RE.match(text)
    if not match:
        reasons.append("protocol_shape")
    else:
        if not match.group("think").strip():
            reasons.append("empty_think")
        if not match.group("visible").strip():
            reasons.append("empty_visible")
        if PROTOCOL_TAG_RE.search(match.group("think")) or PROTOCOL_TAG_RE.search(
            match.group("visible")
        ):
            reasons.append("extra_protocol_tag")
    if text.count("<think>") != 1 or text.count("</think>") != 1:
        reasons.append("think_tag_count")
    if "<answer>" in text.lower() or "</answer>" in text.lower():
        reasons.append("answer_tag")
    reasons = list(dict.fromkeys(reasons))
    return float(not reasons), {"format_reasons": reasons}


def context_limit_hit_score(
    prompt_tokens: int, completion_tokens: int, *, context_tokens: int
) -> float:
    """Return context exhaustion using the explicit profile value."""

    if min(prompt_tokens, completion_tokens) < 0 or context_tokens < 1:
        raise ValueError("invalid token counts or context")
    return float(prompt_tokens + completion_tokens >= context_tokens)


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", value).rstrip(".。")


def _word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value, flags=re.UNICODE))


def _score_ifc(answer: str, grading: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    failures: list[str] = []
    for constraint in grading.get("constraints", []):
        kind = constraint.get("type")
        value = constraint.get("value")
        if kind == "max_words":
            passed = 0 < _word_count(answer) <= int(value)
        elif kind == "exact_lines":
            passed = len([line for line in answer.splitlines() if line.strip()]) == int(value)
        elif kind == "must_include":
            passed = str(value).casefold() in answer.casefold()
        elif kind == "forbidden_word":
            passed = not re.search(rf"\b{re.escape(str(value))}\b", answer, flags=re.IGNORECASE)
        elif kind == "valid_json_keys":
            try:
                parsed = json.loads(answer)
                passed = isinstance(parsed, dict) and set(parsed) == set(value)
            except (TypeError, json.JSONDecodeError):
                passed = False
        else:
            passed = False
        if not passed:
            failures.append(str(kind))
    return float(not failures), {"failed_constraints": failures}


def score_answer(
    row: dict[str, Any],
    answer: str,
    *,
    code_grader: CodeGrader | None = None,
) -> tuple[float, dict[str, Any]]:
    grading = row["grading"]
    kind = str(grading.get("type", row["domain"]))
    if not answer:
        return 0.0, {"reason": "empty_answer"}
    if kind in {"exact", "math"}:
        expected = grading.get("answers") or [grading.get("answer")]
        matches = [_normalize(answer) == _normalize(str(value)) for value in expected]
        return float(any(matches)), {"reason": "ok" if any(matches) else "wrong"}
    if kind == "mcq":
        match = re.search(r"(?:^|\b)([A-Z])(?:\b|$)", answer.upper())
        extracted = match.group(1) if match else ""
        passed = extracted == str(grading["answer"]).upper()
        return float(passed), {"extracted": extracted}
    if kind in {"required_strings", "knowledge"}:
        required = [str(value) for value in grading.get("required_strings", [])]
        forbidden = [str(value) for value in grading.get("forbidden_strings", [])]
        required_hits = [value.casefold() in answer.casefold() for value in required]
        passed = (
            bool(required_hits)
            and all(required_hits)
            and not any(value.casefold() in answer.casefold() for value in forbidden)
        )
        return float(passed), {"required_hits": required_hits}
    if kind == "ifc":
        return _score_ifc(answer, grading)
    if kind.startswith("code"):
        if code_grader is None:
            return 0.0, {"reason": "code_grader_not_configured"}
        return code_grader(answer, grading)
    return 0.0, {"reason": f"unknown_grader:{kind}"}


def score_completion(
    panel_row: dict[str, Any],
    generation_result: dict[str, Any],
    *,
    context_tokens: int,
    code_grader: CodeGrader | None = None,
) -> dict[str, Any]:
    text = str(generation_result["raw_completion"])
    capability_score, capability_detail = score_answer(
        panel_row, best_effort_answer(text), code_grader=code_grader
    )
    visible_score, visible_detail = score_answer(
        panel_row, visible_after_think(text), code_grader=code_grader
    )
    format_score, format_detail = score_format(text)
    return {
        "panel_id": generation_result["panel_id"],
        "domain": panel_row["domain"],
        "panel_sha256": generation_result["panel_sha256"],
        "generation_sha256": generation_result["generation_sha256"],
        "capability_score": capability_score,
        "visible_capability_score": visible_score,
        "format_score": format_score,
        "end_to_end_score": float(format_score == 1.0 and visible_score == 1.0),
        "context_limit_hit_score": context_limit_hit_score(
            int(generation_result["prompt_tokens"]),
            int(generation_result["completion_tokens"]),
            context_tokens=context_tokens,
        ),
        "capability_detail": capability_detail,
        "visible_capability_detail": visible_detail,
        **format_detail,
    }


def summarize_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = (
        "capability_score",
        "visible_capability_score",
        "format_score",
        "end_to_end_score",
        "context_limit_hit_score",
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["domain"])].append(row)

    def summarize(group: list[dict[str, Any]]) -> dict[str, Any]:
        judgments = [
            float(row["judgment_score"]) for row in group if row.get("judgment_score") is not None
        ]
        return {
            "n": len(group),
            **{metric: sum(float(row[metric]) for row in group) / len(group) for metric in metrics},
            "judge": {
                "resolved": len(judgments),
                "unresolved_or_missing": len(group) - len(judgments),
                "coverage": len(judgments) / len(group),
                "accuracy": sum(judgments) / len(judgments) if judgments else None,
            },
        }

    return {
        "overall": summarize(rows) if rows else {"n": 0},
        "domains": {domain: summarize(group) for domain, group in sorted(grouped.items())},
    }
