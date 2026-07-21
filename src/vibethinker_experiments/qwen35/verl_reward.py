"""VERL custom reward entry point for Qwen3.5 math RL.

The unique filename is intentional: older sources had two unrelated modules
named ``reward_math.py`` and could silently import the wrong implementation.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from vibethinker_experiments.qwen35.math_protocol import (
    grade_math_answer,
    parse_protocol,
    protocol_progress_reward,
)


@lru_cache(maxsize=1)
def _tokenizer():
    from transformers import AutoTokenizer

    path = os.environ.get("VT_TOKENIZER_PATH")
    if not path:
        raise RuntimeError("VT_TOKENIZER_PATH must point to the runtime model")
    return AutoTokenizer.from_pretrained(path, local_files_only=True)


def score_math_completion(
    solution_str: str,
    ground_truth: str,
    *,
    completion_tokens: int,
    max_completion_tokens: int,
    length_soft_start_tokens: int,
    truncated: bool | None = None,
) -> dict[str, Any]:
    if not 0 <= length_soft_start_tokens < max_completion_tokens:
        raise ValueError("length_soft_start_tokens must be in [0, max_completion_tokens)")
    parsed = parse_protocol(solution_str)
    progress = protocol_progress_reward(solution_str)
    truncated = completion_tokens >= max_completion_tokens if truncated is None else bool(truncated)
    if completion_tokens <= length_soft_start_tokens and not truncated:
        length_score = 1.0
    elif truncated or completion_tokens >= max_completion_tokens:
        length_score = 0.0
    else:
        span = max_completion_tokens - length_soft_start_tokens
        length_score = 1 - (completion_tokens - length_soft_start_tokens) / span

    correct, reason = False, "bad_protocol"
    if parsed["format_ok"]:
        correct, detail = grade_math_answer(parsed["visible_text"], str(ground_truth))
        reason = str(detail.get("reason", "wrong"))
    success = bool(parsed["format_ok"] and correct)
    score = 0.5 + 0.5 * length_score if success else progress
    return {
        "score": float(score),
        "binary_success": float(success),
        "answer_correct": float(correct),
        "format_ok": float(parsed["format_ok"]),
        "format_progress": float(progress),
        "length_score": float(length_score),
        "completion_tokens": int(completion_tokens),
        "truncated": float(truncated),
        "reason": reason,
    }


def compute_score(
    data_source: str,
    solution_str: str,
    ground_truth: str,
    extra_info: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    if data_source != "vibethinker_math":
        raise ValueError(f"unsupported data_source={data_source!r}")
    extra_info = extra_info or {}
    tokens = extra_info.get("completion_tokens")
    if tokens is None:
        tokens = len(_tokenizer()(solution_str, add_special_tokens=False)["input_ids"])
    result = score_math_completion(
        solution_str,
        ground_truth,
        completion_tokens=int(tokens),
        max_completion_tokens=int(os.environ.get("VT_MAX_COMPLETION_TOKENS", "130048")),
        length_soft_start_tokens=int(os.environ.get("VT_LENGTH_SOFT_START_TOKENS", "65536")),
        truncated=extra_info.get("hard_truncated"),
    )
    audit_dir = os.environ.get("VT_REWARD_AUDIT_DIR")
    if audit_dir:
        directory = Path(audit_dir)
        directory.mkdir(parents=True, exist_ok=True)
        record = {
            "data_source": data_source,
            "ground_truth": str(ground_truth),
            "rl_component": extra_info.get("rl_component"),
            **result,
            "solution_prefix": solution_str[:1000],
            "solution_suffix": solution_str[-1000:],
        }
        with (directory / f"reward-{os.getpid()}.jsonl").open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return result
