"""SFT 样本协议校验、去重与 Stage-2 长思维筛选。"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common.hashing import stable_text_hash
from ..common.io import write_jsonl
from ..common.jsonl import read_jsonl

PROTOCOL_RE = re.compile(
    r"^\s*<think>\s*(?P<think>[\s\S]*?)\s*</think>\s*(?P<visible>[\s\S]+?)\s*$"
)
TAG_RE = re.compile(r"</?(?:think|answer)>", re.I)


@dataclass(frozen=True)
class SFTValidation:
    valid: bool
    reason: str | None = None
    prompt_hash: str | None = None
    think_chars: int = 0


def validate_sft_row(row: dict[str, Any]) -> SFTValidation:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return SFTValidation(False, "messages_missing")
    user = next((m for m in messages if m.get("role") == "user"), None)
    assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), None)
    if not isinstance(user, dict) or not isinstance(assistant, dict):
        return SFTValidation(False, "required_roles_missing")
    prompt = str(user.get("content") or "").strip()
    answer = str(assistant.get("content") or "").strip()
    if not prompt or not answer:
        return SFTValidation(False, "empty_content")
    if TAG_RE.search(prompt):
        return SFTValidation(False, "protocol_tag_in_prompt")
    match = PROTOCOL_RE.match(answer)
    if not match or not match.group("think").strip() or not match.group("visible").strip():
        return SFTValidation(False, "bad_assistant_protocol")
    if TAG_RE.search(match.group("think")) or TAG_RE.search(match.group("visible")):
        return SFTValidation(False, "nested_protocol_tag")
    return SFTValidation(
        True,
        prompt_hash=stable_text_hash(prompt),
        think_chars=len(match.group("think")),
    )


def filter_sft_rows(
    rows: Iterable[dict[str, Any]],
    *,
    min_think_tokens: float = 0,
    chars_per_token: float = 3.5,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if chars_per_token <= 0:
        raise ValueError("chars_per_token 必须大于 0")
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats = {"input": 0, "invalid": 0, "duplicate": 0, "too_short": 0, "kept": 0}
    for row in rows:
        stats["input"] += 1
        result = validate_sft_row(row)
        if not result.valid:
            stats["invalid"] += 1
            continue
        assert result.prompt_hash is not None
        if result.prompt_hash in seen:
            stats["duplicate"] += 1
            continue
        estimated = result.think_chars / chars_per_token
        if estimated < min_think_tokens:
            stats["too_short"] += 1
            continue
        seen.add(result.prompt_hash)
        output = dict(row)
        output["_prompt_hash"] = result.prompt_hash
        output["_est_think_tokens"] = round(estimated)
        kept.append(output)
        stats["kept"] += 1
    return kept, stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-think-tokens", type=float, default=0)
    parser.add_argument("--chars-per-token", type=float, default=3.5)
    args = parser.parse_args()
    rows, stats = filter_sft_rows(
        read_jsonl(args.input),
        min_think_tokens=args.min_think_tokens,
        chars_per_token=args.chars_per_token,
    )
    write_jsonl(args.output, rows)
    print(stats)


if __name__ == "__main__":
    main()
