"""Qwen2.5 64K Math RL 的 VERL 自定义 reward 入口。"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from vibethinker_experiments.qwen35.math_protocol import (
    grade_math_answer,
    parse_protocol,
    protocol_progress_reward,
)


def overlong_multiplier(
    *,
    completion_tokens: int,
    soft_start_tokens: int,
    hard_limit_tokens: int,
    floor: float,
    truncated: bool,
) -> float:
    if not 0 <= soft_start_tokens < hard_limit_tokens:
        raise ValueError("soft_start_tokens must be in [0, hard_limit_tokens)")
    if not 0 <= floor <= 1:
        raise ValueError("floor must be in [0, 1]")
    if truncated or completion_tokens >= hard_limit_tokens:
        return 0.0
    if completion_tokens <= soft_start_tokens:
        return 1.0
    fraction = (completion_tokens - soft_start_tokens) / (hard_limit_tokens - soft_start_tokens)
    return 1.0 - min(max(fraction, 0.0), 1.0) * (1.0 - floor)


def score_math_completion(
    solution_str: str,
    ground_truth: str,
    *,
    completion_tokens: int,
    max_completion_tokens: int = 64768,
    overlong_soft_start_tokens: int = 60000,
    overlong_floor: float = 0.7,
    truncated: bool | None = None,
) -> dict[str, Any]:
    parsed = parse_protocol(solution_str)
    format_progress = protocol_progress_reward(solution_str)
    truncated = completion_tokens >= max_completion_tokens if truncated is None else truncated
    multiplier = overlong_multiplier(
        completion_tokens=completion_tokens,
        soft_start_tokens=overlong_soft_start_tokens,
        hard_limit_tokens=max_completion_tokens,
        floor=overlong_floor,
        truncated=bool(truncated),
    )
    answer_correct, reason = False, "bad_protocol"
    if parsed["format_ok"]:
        answer_correct, detail = grade_math_answer(parsed["visible_text"], str(ground_truth))
        reason = str(detail.get("reason", "wrong"))
    binary_success = bool(parsed["format_ok"] and answer_correct and not truncated)
    base_reward = 1.0 if binary_success else format_progress
    return {
        "score": float(base_reward * multiplier),
        "binary_success": float(binary_success),
        "answer_correct": float(answer_correct),
        "format_ok": float(parsed["format_ok"]),
        "format_progress": float(format_progress),
        "base_reward": float(base_reward),
        "overlong_multiplier": float(multiplier),
        "completion_tokens": int(completion_tokens),
        "truncated": float(bool(truncated)),
        "reason": reason,
    }


@lru_cache(maxsize=1)
def _tokenizer():
    from transformers import AutoTokenizer

    path = os.environ.get("VT_TOKENIZER_PATH")
    if not path:
        raise RuntimeError("VT_TOKENIZER_PATH must point to the runtime model")
    return AutoTokenizer.from_pretrained(path, local_files_only=True)


def compute_score(
    data_source: str,
    solution_str: str,
    ground_truth: str,
    extra_info: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    if data_source != "vibethinker_math":
        raise ValueError(f"unsupported data_source={data_source!r}")
    extra = extra_info or {}
    completion_tokens = extra.get("completion_tokens")
    if completion_tokens is None:
        completion_tokens = len(_tokenizer()(solution_str, add_special_tokens=False)["input_ids"])
    return score_math_completion(
        solution_str,
        ground_truth,
        completion_tokens=int(completion_tokens),
        max_completion_tokens=int(os.environ.get("VT_MAX_COMPLETION_TOKENS", "64768")),
        overlong_soft_start_tokens=int(os.environ.get("VT_OVERLONG_SOFT_START_TOKENS", "60000")),
        overlong_floor=float(os.environ.get("VT_OVERLONG_FLOOR", "0.7")),
        truncated=extra.get("hard_truncated"),
    )
