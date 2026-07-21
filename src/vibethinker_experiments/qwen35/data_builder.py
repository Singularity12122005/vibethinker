"""Deterministic builders for Math500 and Math500+GSM500 VERL data."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from vibethinker_experiments.data.decontamination import BenchmarkDenyIndex

from .math_protocol import answer_candidates, grade_math_answer

FORBIDDEN = (
    "<think>",
    "</think>",
    "<answer>",
    "</answer>",
    "<|im_start|>",
    "<|im_end|>",
    "you must think",
    "output your answer in",
)
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_verified_deny_index(
    index_dir: Path,
    receipt_path: Path,
) -> tuple[BenchmarkDenyIndex, str]:
    receipt = json.loads(receipt_path.read_text())
    expected_files = receipt.get("files") if receipt.get("schema_version") == 1 else None
    names = ("exact.json", "ngram10_index.json", "ngram10_counts.json")
    if not isinstance(expected_files, dict) or set(expected_files) != set(names):
        raise ValueError("deny receipt must freeze all three index file hashes")
    for name in names:
        actual = sha256(index_dir / name)
        if expected_files[name] != actual:
            raise ValueError(f"deny index hash mismatch: {name}")
    return BenchmarkDenyIndex.load(index_dir), sha256(receipt_path)


def _problem(row: dict[str, Any]) -> str:
    for key in ("problem", "question", "prompt", "question_text"):
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            if len(value) != 1 or value[0].get("role") != "user":
                raise ValueError("prompt must contain exactly one user message")
            value = value[0].get("content")
        return str(value).strip()
    raise KeyError("row has no problem field")


def _answer(row: dict[str, Any]) -> str:
    for key in ("answer", "final_answer", "ground_truth", "gt_answer"):
        if row.get(key) is not None:
            return str(row[key]).strip()
    reward = row.get("reward_model")
    if isinstance(reward, dict) and reward.get("ground_truth") is not None:
        return str(reward["ground_truth"]).strip()
    raise KeyError("row has no explicit final answer")


def _problem_hash(row: dict[str, Any]) -> str:
    return str(
        row.get("problem_hash")
        or hashlib.sha256(" ".join(_problem(row).split()).casefold().encode()).hexdigest()
    )


def audit_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    audited, seen = [], set()
    for index, source in enumerate(rows):
        row = dict(source)
        problem, answer = _problem(row), _answer(row)
        lowered = problem.lower()
        found = [fragment for fragment in FORBIDDEN if fragment in lowered]
        if found:
            raise ValueError(f"row {index}: dirty prompt fragments {found}")
        key = " ".join(problem.split()).casefold()
        if key in seen:
            raise ValueError(f"row {index}: duplicate problem")
        seen.add(key)
        if not answer_candidates(answer):
            raise ValueError(f"row {index}: unparseable answer")
        passed, detail = grade_math_answer(answer, answer)
        if not passed:
            raise ValueError(f"row {index}: gold self-grade failed: {detail}")
        row.update(problem=problem, answer=answer, problem_hash=_problem_hash(row))
        row["reasoning_trace_retained"] = False
        row["gold_self_grade_passed"] = True
        audited.append(row)
    return audited


def select_math500(
    candidates: Iterable[dict[str, Any]],
    *,
    deny_index: BenchmarkDenyIndex,
    deny_receipt_sha256: str,
    quotas: dict[str, dict[str, int]] = MATH500_QUOTAS,
) -> list[dict[str, Any]]:
    """Select quotas only after enforcing a frozen benchmark/panel deny receipt."""
    if len(deny_receipt_sha256) != 64:
        raise ValueError("deny receipt SHA-256 is required")
    rows = audit_rows(candidates)
    for row in rows:
        match = deny_index.match(row["problem"])
        if match.hard_deny or match.near_deny:
            raise ValueError(f"benchmark/panel deny hit: {row['problem_hash']}")
        row["benchmark_deny_receipt_sha256"] = deny_receipt_sha256
    selected: list[dict[str, Any]] = []
    for topic, bands in quotas.items():
        for difficulty, quota in bands.items():
            pool = [
                row
                for row in rows
                if row.get("topic") == topic and row.get("difficulty") == difficulty
            ]
            pool.sort(
                key=lambda row: hashlib.sha256(
                    f"math-rl-sft30k-500-v1:{row['problem_hash']}".encode()
                ).hexdigest()
            )
            if len(pool) < quota:
                raise ValueError(
                    f"insufficient {topic}/{difficulty}: need {quota}, found {len(pool)}"
                )
            selected.extend(pool[:quota])
    expected_total = sum(sum(bands.values()) for bands in quotas.values())
    if (
        len(selected) != expected_total
        or len({_problem_hash(row) for row in selected}) != expected_total
    ):
        raise RuntimeError("Math500 selection must satisfy all unique quota slots")
    return selected


def combine_math500_gsm500(
    math_rows: Iterable[dict[str, Any]], gsm_rows: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    math, gsm = audit_rows(math_rows), audit_rows(gsm_rows)
    if len(math) != 500 or len(gsm) != 500:
        raise ValueError(f"expected 500+500 rows, got {len(math)}+{len(gsm)}")
    combined, hashes = [], set()
    for component, rows in (("math500", math), ("gsm8k500", gsm)):
        for row in rows:
            digest = _problem_hash(row)
            if digest in hashes:
                raise ValueError("duplicate across Math500 and GSM500")
            hashes.add(digest)
            combined.append({**row, "rl_component": component})
    random.Random(20260718).shuffle(combined)
    return combined


def to_verl_records(rows: Iterable[dict[str, Any]], tokenizer=None) -> list[dict[str, Any]]:
    records = []
    for index, row in enumerate(audit_rows(rows)):
        problem, answer = row["problem"], row["answer"]
        prompt_tokens = None
        if tokenizer is not None:
            prompt = [{"role": "user", "content": problem}]
            rendered = tokenizer.apply_chat_template(
                prompt, tokenize=False, add_generation_prompt=True
            )
            prompt_tokens = len(tokenizer(rendered, add_special_tokens=False)["input_ids"])
            if prompt_tokens > 1024:
                raise ValueError(f"row {index}: prompt exceeds 1024 tokens")
        records.append(
            {
                "data_source": "vibethinker_math",
                "prompt": [{"role": "user", "content": problem}],
                "ability": "math",
                "reward_model": {"style": "rule", "ground_truth": answer},
                "extra_info": {
                    "index": index,
                    "source": row.get("source") or row.get("_source") or "unknown",
                    "category": row.get("category") or row.get("topic") or "unknown",
                    "difficulty": row.get("difficulty") or "unknown",
                    "rl_component": row.get("rl_component") or "math500",
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


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    select = subparsers.add_parser("select-math500")
    select.add_argument("--candidates", type=Path, required=True)
    select.add_argument("--deny-index", type=Path, required=True)
    select.add_argument("--deny-receipt", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    combine = subparsers.add_parser("combine")
    combine.add_argument("--math", type=Path, required=True)
    combine.add_argument("--gsm", type=Path, required=True)
    combine.add_argument("--output", type=Path, required=True)
    prepare = subparsers.add_parser("prepare-verl")
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--model", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "select-math500":
        deny_index, receipt_sha256 = load_verified_deny_index(
            args.deny_index,
            args.deny_receipt,
        )
        rows = select_math500(
            read_jsonl(args.candidates),
            deny_index=deny_index,
            deny_receipt_sha256=receipt_sha256,
        )
        write_jsonl(args.output, rows)
    elif args.command == "combine":
        rows = combine_math500_gsm500(read_jsonl(args.math), read_jsonl(args.gsm))
        write_jsonl(args.output, rows)
    else:
        from datasets import Dataset
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
        records = to_verl_records(read_jsonl(args.input), tokenizer)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        Dataset.from_list(records).to_parquet(str(args.output_dir / "train.parquet"))
        Dataset.from_list(records[:8]).to_parquet(str(args.output_dir / "smoke.parquet"))
        print(
            json.dumps(
                {
                    "rows": len(records),
                    "components": dict(
                        Counter(row["extra_info"]["rl_component"] for row in records)
                    ),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
