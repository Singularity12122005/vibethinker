"""Benchmark 精确匹配与 10-gram 近重复去污染。

本模块只保留可复用索引/审计算法；benchmark 下载、站点抓取和固定本机缓存遍历
不迁移。
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..common.hashing import sha256_text
from ..common.io import write_json
from ..common.jsonl import read_jsonl


def paper_normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def ten_grams(value: str) -> set[str]:
    tokens = paper_normalize(value).split()
    return {sha256_text(" ".join(tokens[index : index + 10])) for index in range(len(tokens) - 9)}


def is_high_confidence_near(shared: int, containment: float) -> bool:
    return (
        (shared >= 3 and containment >= 0.99)
        or (shared >= 8 and containment >= 0.80)
        or (shared >= 15 and containment >= 0.50)
        or (shared >= 20 and containment >= 0.35)
    )


def extract_prompt(row: dict[str, Any]) -> str:
    for key in ("problem", "prompt", "question", "input", "question_text"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    messages = row.get("messages")
    if isinstance(messages, list):
        return "\n".join(
            str(message.get("content") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "user"
        )
    return ""


@dataclass(frozen=True)
class MatchResult:
    hard_deny: bool
    near_deny: bool
    exact_labels: tuple[str, ...] = ()
    near_labels: tuple[str, ...] = ()
    max_shared_10grams: int = 0
    max_containment: float = 0.0


@dataclass
class BenchmarkDenyIndex:
    exact: dict[str, list[str]]
    ngram_labels: dict[str, list[str]]
    ngram_counts: dict[str, int]

    @classmethod
    def build(cls, prompts: Iterable[tuple[str, str]]) -> BenchmarkDenyIndex:
        exact: dict[str, list[str]] = defaultdict(list)
        ngram_labels: dict[str, list[str]] = defaultdict(list)
        ngram_counts: dict[str, int] = {}
        for label, prompt in prompts:
            normalized = paper_normalize(prompt)
            if not normalized:
                continue
            exact[sha256_text(normalized)].append(label)
            grams = ten_grams(prompt)
            ngram_counts[label] = len(grams)
            for gram in grams:
                ngram_labels[gram].append(label)
        return cls(
            {key: sorted(set(value)) for key, value in exact.items()},
            {key: sorted(set(value)) for key, value in ngram_labels.items()},
            ngram_counts,
        )

    def match(self, prompt: str) -> MatchResult:
        exact_labels = tuple(self.exact.get(sha256_text(paper_normalize(prompt)), ()))
        grams = ten_grams(prompt)
        shared: Counter[str] = Counter()
        for gram in grams:
            shared.update(self.ngram_labels.get(gram, ()))
        near: list[str] = []
        max_shared = 0
        max_containment = 0.0
        for label, count in shared.items():
            denominator = min(len(grams), self.ngram_counts.get(label, 0))
            containment = count / denominator if denominator else 0.0
            max_shared = max(max_shared, count)
            max_containment = max(max_containment, containment)
            if is_high_confidence_near(count, containment):
                near.append(label)
        return MatchResult(
            bool(exact_labels),
            bool(near),
            exact_labels,
            tuple(sorted(near)),
            max_shared,
            round(max_containment, 6),
        )

    def save(self, directory: str | Path) -> None:
        root = Path(directory)
        write_json(root / "exact.json", self.exact)
        write_json(root / "ngram10_index.json", self.ngram_labels)
        write_json(root / "ngram10_counts.json", self.ngram_counts)

    @classmethod
    def load(cls, directory: str | Path) -> BenchmarkDenyIndex:
        root = Path(directory)
        return cls(
            json.loads((root / "exact.json").read_text()),
            json.loads((root / "ngram10_index.json").read_text()),
            json.loads((root / "ngram10_counts.json").read_text()),
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--benchmarks", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--index-dir", type=Path, required=True)
    audit.add_argument("--data", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        rows = read_jsonl(args.benchmarks, strict=True)
        prompts = [
            (str(row.get("label") or row.get("id") or index), extract_prompt(row))
            for index, row in enumerate(rows)
        ]
        BenchmarkDenyIndex.build(prompts).save(args.output_dir)
        return
    index = BenchmarkDenyIndex.load(args.index_dir)
    findings = []
    for row_number, row in enumerate(read_jsonl(args.data)):
        result = index.match(extract_prompt(row))
        if result.hard_deny or result.near_deny:
            findings.append({"row": row_number, **asdict(result)})
    write_json(args.output, {"rows": len(read_jsonl(args.data)), "findings": findings})


if __name__ == "__main__":
    main()
