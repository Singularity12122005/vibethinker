"""从 SFT 数学血缘确定性构建共享 Math500，并转换为 VERL schema。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from vibethinker_experiments.data.decontamination import BenchmarkDenyIndex
from vibethinker_experiments.qwen35.math_protocol import answer_candidates, grade_math_answer

MATH500_QUOTAS = {
    "algebra": {"warmup": 60, "main": 35, "challenge": 5},
    "applied_word": {"warmup": 50, "main": 29, "challenge": 1},
    "calculus_analysis": {"warmup": 30, "main": 18, "challenge": 2},
    "combinatorics": {"warmup": 27, "main": 16, "challenge": 2},
    "geometry": {"warmup": 42, "main": 25, "challenge": 3},
    "number_theory": {"warmup": 39, "main": 23, "challenge": 3},
    "other": {"warmup": 12, "main": 7, "challenge": 1},
    "probability_statistics": {"warmup": 42, "main": 24, "challenge": 4},
}

FORBIDDEN_PROMPT_FRAGMENTS = (
    "<think>",
    "</think>",
    "<answer>",
    "</answer>",
    "<|im_start|>",
    "<|im_end|>",
    "you must think",
    "output your answer in",
)


def _stable_key(row: Mapping[str, Any]) -> str:
    digest = str(row.get("problem_hash") or "")
    return hashlib.sha256(f"qwen25-math500:{digest}".encode()).hexdigest()


def _topic(row: Mapping[str, Any]) -> str:
    value = str(row.get("topic") or row.get("_topic") or "other")
    if value in {"calculus", "precalculus"}:
        return "calculus_analysis"
    if value == "probability":
        return "probability_statistics"
    return value if value in MATH500_QUOTAS else "other"


def _difficulty(row: Mapping[str, Any]) -> str:
    value = row.get("difficulty", row.get("_difficulty"))
    if value in {"warmup", "medium_low", "simple"}:
        return "warmup"
    if value in {"hard", "challenge"}:
        return "challenge"
    if value in {"main", None}:
        return "main"
    try:
        return "main" if float(value) <= 6.5 else "challenge"
    except (TypeError, ValueError):
        return "main"


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(" ".join(prompt.casefold().split()).encode()).hexdigest()


def candidates_from_sft(
    sft_rows: Iterable[dict[str, Any]],
    prompt_pool: Iterable[dict[str, Any]],
    *,
    deny_index: BenchmarkDenyIndex,
    excluded_prompt_hashes: set[str] | None = None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """恢复原始 gold；不把教师 reasoning 或教师答案当作 RL ground truth。"""
    prompt_lookup = {str(row.get("_prompt_hash")): row for row in prompt_pool}
    excluded_hashes = excluded_prompt_hashes or set()
    eligible: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    for row in sft_rows:
        if str(row.get("_domain") or row.get("_mix_domain")) != "math":
            continue
        messages = row.get("messages") or []
        prompt = str(messages[0].get("content") or "").strip() if messages else ""
        source = prompt_lookup.get(str(row.get("_prompt_hash")))
        gold = str((source or {}).get("_gold_answer") or "").strip()
        verification = row.get("_verification") or {}
        digest = prompt_hash(prompt)
        if not prompt or not gold:
            rejected["missing_original_gold"] += 1
            continue
        if verification.get("passed") is not True:
            rejected["sft_verification_failed"] += 1
            continue
        if digest in excluded_hashes:
            rejected["external_exact_deny"] += 1
            continue
        match = deny_index.match(prompt)
        if match.hard_deny:
            rejected["benchmark_exact"] += 1
            continue
        if match.near_deny:
            rejected["benchmark_near"] += 1
            continue
        teacher_answer = str((verification.get("detail") or {}).get("extracted") or "").strip()
        self_ok, _ = grade_math_answer(gold, gold)
        teacher_ok, _ = grade_math_answer(teacher_answer, gold)
        if not self_ok or not teacher_ok:
            rejected["gold_or_teacher_regrade_failed"] += 1
            continue
        eligible.append(
            {
                "id": f"math500-{digest[:20]}",
                "problem": prompt,
                "answer": gold,
                "problem_hash": digest,
                "topic": _topic(source or row),
                "difficulty": _difficulty(source or row),
                "source": row.get("_source"),
                "source_tranche": row.get("_source_tranche"),
                "overlaps_sft_training": True,
                "reasoning_trace_retained": False,
                "gold_self_grade_passed": True,
                "sft_teacher_answer_grade_passed": True,
            }
        )
    return eligible, rejected


def select_math500(
    candidates: Iterable[dict[str, Any]],
    quotas: Mapping[str, Mapping[str, int]] = MATH500_QUOTAS,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    rows = list(candidates)
    for topic, bands in quotas.items():
        for difficulty, quota in bands.items():
            pool = [
                row
                for row in rows
                if row.get("topic") == topic and row.get("difficulty") == difficulty
            ]
            pool.sort(key=_stable_key)
            if len(pool) < quota:
                raise ValueError(
                    f"insufficient {topic}/{difficulty}: need {quota}, found {len(pool)}"
                )
            selected.extend(pool[:quota])
    expected = sum(sum(bands.values()) for bands in quotas.values())
    hashes = {str(row["problem_hash"]) for row in selected}
    if len(selected) != expected or len(hashes) != expected:
        raise RuntimeError(f"selection must contain {expected} unique prompts")
    return sorted(selected, key=_stable_key)


def to_verl_records(rows: Iterable[dict[str, Any]], tokenizer=None) -> list[dict[str, Any]]:
    records, seen = [], set()
    for index, source in enumerate(rows):
        row = dict(source)
        problem, answer = str(row["problem"]).strip(), str(row["answer"]).strip()
        lowered = problem.casefold()
        dirty = [fragment for fragment in FORBIDDEN_PROMPT_FRAGMENTS if fragment in lowered]
        if dirty:
            raise ValueError(f"row {index}: prompt contains forbidden fragments {dirty}")
        normalized = " ".join(problem.casefold().split())
        if normalized in seen:
            raise ValueError(f"row {index}: duplicate prompt")
        seen.add(normalized)
        if not answer_candidates(answer):
            raise ValueError(f"row {index}: unparseable final answer")
        prompt_tokens = None
        if tokenizer is not None:
            messages = [{"role": "user", "content": problem}]
            rendered = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            prompt_tokens = len(tokenizer(rendered, add_special_tokens=False)["input_ids"])
            if prompt_tokens > 768:
                raise ValueError(f"row {index}: prompt exceeds 768 tokens")
        records.append(
            {
                "data_source": "vibethinker_math",
                "prompt": [{"role": "user", "content": problem}],
                "ability": "math",
                "reward_model": {"style": "rule", "ground_truth": answer},
                "extra_info": {
                    "index": index,
                    "source": row.get("source") or "unknown",
                    "category": row.get("topic") or "unknown",
                    "difficulty": row.get("difficulty") or "unknown",
                    "prompt_tokens": prompt_tokens,
                },
            }
        )
    return records


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--sft", type=Path, required=True)
    build.add_argument("--prompt-pool", type=Path, required=True)
    build.add_argument("--deny-index", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    prepare = subparsers.add_parser("prepare-verl")
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "build":
        eligible, rejected = candidates_from_sft(
            read_jsonl(args.sft),
            read_jsonl(args.prompt_pool),
            deny_index=BenchmarkDenyIndex.load(args.deny_index),
        )
        selected = select_math500(eligible)
        write_jsonl(args.output, selected)
        print(json.dumps({"rows": len(selected), "excluded": dict(rejected)}, indent=2))
        return

    from datasets import Dataset
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    records = to_verl_records(read_jsonl(args.input), tokenizer)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    Dataset.from_list(records).to_parquet(str(args.output_dir / "train.parquet"))
    Dataset.from_list(records[:8]).to_parquet(str(args.output_dir / "smoke.parquet"))
    print(json.dumps({"rows": len(records)}, indent=2))


if __name__ == "__main__":
    main()
