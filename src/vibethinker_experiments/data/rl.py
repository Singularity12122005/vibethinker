"""RLVR 样本的 verifier 数据清洗和确定性分层抽样核心。"""

from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..common.hashing import stable_text_hash
from ..common.io import write_jsonl
from ..common.jsonl import read_jsonl
from .decontamination import BenchmarkDenyIndex, extract_prompt


def _case_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def prepare_stdin_stdout_tests(
    raw: dict[str, Any], *, min_tests: int = 1, max_tests: int = 64
) -> tuple[dict[str, list[str]] | None, str | None]:
    """规范化 stdin/stdout tests，拒绝错位、冲突和超大 payload。"""
    if raw.get("fn_name"):
        return None, "call_based_not_stdin_stdout"
    inputs = list(raw.get("inputs") or raw.get("input") or ())
    outputs = list(raw.get("outputs") or raw.get("output") or ())
    if len(inputs) != len(outputs) or len(inputs) < min_tests:
        return None, "insufficient_or_misaligned_tests"
    pairs: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    for input_value, output_value in zip(inputs, outputs):  # noqa: B905
        stdin, stdout = _case_text(input_value), _case_text(output_value)
        if len(stdin) > 1_000_000 or len(stdout) > 1_000_000:
            continue
        if stdin in seen and seen[stdin].strip() != stdout.strip():
            return None, "conflicting_test_outputs"
        if stdin not in seen:
            seen[stdin] = stdout
            pairs.append((stdin, stdout))
    if len(pairs) < min_tests:
        return None, "insufficient_unique_tests"
    pairs.sort(key=lambda pair: stable_text_hash(pair[0] + "\0" + pair[1]))
    pairs = pairs[:max_tests]
    if sum(len(stdin) + len(stdout) for stdin, stdout in pairs) > 8_000_000:
        return None, "test_payload_too_large"
    return {
        "inputs": [stdin for stdin, _ in pairs],
        "outputs": [stdout for _, stdout in pairs],
    }, None


def select_weighted_topics(
    rows: Iterable[dict[str, Any]],
    *,
    quota: int,
    topic_weights: dict[str, float],
    salt: str,
) -> list[dict[str, Any]]:
    """按目标 topic 比例轮询选择，hash 排序保证跨机器复现。"""
    materialized = list(rows)
    queues: dict[str, deque[dict[str, Any]]] = {}
    for topic in topic_weights:
        topic_rows = [row for row in materialized if row.get("topic") == topic]
        topic_rows.sort(key=lambda row: stable_text_hash(salt + extract_prompt(row)))
        queues[topic] = deque(topic_rows)
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    while len(selected) < quota:
        available = [topic for topic, queue in queues.items() if queue]
        if not available:
            raise ValueError(f"无法填满 quota={quota}，仅选择 {len(selected)} 条")
        topic = min(
            available,
            key=lambda name: counts[name] / max(topic_weights[name], 1e-12),
        )
        selected.append(queues[topic].popleft())
        counts[topic] += 1
    return selected


def clean_rl_rows(
    rows: Iterable[dict[str, Any]], deny_index: BenchmarkDenyIndex | None = None
) -> tuple[list[dict[str, Any]], Counter[str]]:
    kept: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    seen: set[str] = set()
    for row in rows:
        problem = extract_prompt(row).strip()
        domain = str(row.get("domain") or "")
        answer = row.get("answer")
        if not problem or domain not in {"math", "code", "stem"} or answer is None:
            rejected["bad_contract"] += 1
            continue
        prompt_hash = stable_text_hash(problem)
        if prompt_hash in seen:
            rejected["duplicate"] += 1
            continue
        if deny_index is not None:
            match = deny_index.match(problem)
            if match.hard_deny or match.near_deny:
                rejected["benchmark_overlap"] += 1
                continue
        output = dict(row)
        output["problem"] = problem
        output["problem_hash"] = prompt_hash
        if domain == "code":
            raw_tests = row.get("tests")
            if raw_tests is None and isinstance(answer, str):
                try:
                    raw_tests = json.loads(answer)
                except json.JSONDecodeError:
                    raw_tests = {}
            tests, reason = prepare_stdin_stdout_tests(raw_tests or {})
            if reason:
                rejected[f"code_{reason}"] += 1
                continue
            output["tests"] = tests
            output["answer"] = json.dumps(tests, ensure_ascii=False, separators=(",", ":"))
            output["verifier"] = "python_stdin_stdout_not_hardened_sandbox"
        seen.add(prompt_hash)
        kept.append(output)
    return kept, rejected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deny-index", type=Path)
    args = parser.parse_args()
    index = BenchmarkDenyIndex.load(args.deny_index) if args.deny_index else None
    rows, rejected = clean_rl_rows(read_jsonl(args.input), index)
    write_jsonl(args.output, rows)
    print({"kept": len(rows), "rejected": dict(rejected)})


if __name__ == "__main__":
    main()
