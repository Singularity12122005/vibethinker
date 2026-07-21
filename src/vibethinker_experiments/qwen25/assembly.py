"""15K/30K 三域 SFT 的确定性组装与失败即停审计。"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from vibethinker_experiments.data.decontamination import BenchmarkDenyIndex
from vibethinker_experiments.data.sft import validate_sft_row

DOMAINS = ("math", "code", "general")
EXPECTED_VERIFIER = {
    "math": "math_verifier",
    "code": "code_tests",
    "general": "general_judge",
}


def canonical_prompt(row: Mapping[str, Any]) -> str:
    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        return ""
    return str(messages[0].get("content") or "").strip()


def canonical_prompt_hash(row: Mapping[str, Any]) -> str:
    prompt = " ".join(canonical_prompt(row).casefold().split())
    return hashlib.sha256(prompt.encode()).hexdigest()


def _rank(row: Mapping[str, Any], salt: str) -> str:
    return hashlib.sha256(f"{salt}:{canonical_prompt_hash(row)}".encode()).hexdigest()


@dataclass(frozen=True)
class AssemblyAudit:
    rows: int
    domains: dict[str, int]
    duplicate_prompts: int
    invalid_protocol: int
    unverified_native_rows: int
    prompt_protocol_tags: int
    max_chat_tokens: int | None
    over_max_chat_tokens: int
    benchmark_audit: str
    hard_deny_matches: int | None
    near_deny_matches: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assemble_domains(
    parts: Mapping[str, Iterable[dict[str, Any]]],
    *,
    rows_per_domain: int,
    seed: str,
) -> list[dict[str, Any]]:
    """组装已选定的各域数据；不补采、不截断，也不静默丢弃坏行。"""
    if rows_per_domain <= 0:
        raise ValueError("rows_per_domain must be positive")
    selected: list[dict[str, Any]] = []
    for domain in DOMAINS:
        rows = [dict(row) for row in parts.get(domain, ())]
        if len(rows) != rows_per_domain:
            raise ValueError(
                f"{domain} must contain exactly {rows_per_domain} rows, found {len(rows)}"
            )
        for index, row in enumerate(rows):
            actual = str(row.get("_domain") or row.get("_mix_domain") or "")
            if actual != domain:
                raise ValueError(f"{domain}:{index} has domain {actual!r}")
        selected.extend(rows)
    return sorted(selected, key=lambda row: _rank(row, seed))


def assemble_15k(parts: Mapping[str, Iterable[dict[str, Any]]]) -> list[dict[str, Any]]:
    return assemble_domains(parts, rows_per_domain=5000, seed="qwen25-three-domain-15k")


def assemble_native_30k(
    parts: Mapping[str, Iterable[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return assemble_domains(parts, rows_per_domain=10000, seed="qwen25-native-teacher-30k")


def _chat_tokens(tokenizer: Any, messages: list[dict[str, Any]]) -> int:
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return len(tokenizer(rendered, add_special_tokens=False)["input_ids"])


def audit_dataset(
    rows: Iterable[dict[str, Any]],
    *,
    rows_per_domain: int,
    tokenizer: Any | None = None,
    max_chat_tokens: int = 30000,
    require_native_verification: bool = False,
    deny_index: BenchmarkDenyIndex | None = None,
) -> AssemblyAudit:
    materialized = list(rows)
    domains: Counter[str] = Counter()
    hashes: set[str] = set()
    invalid = unverified = contaminated_prompts = over_limit = 0
    lengths: list[int] = []
    hard_matches = near_matches = 0

    for row in materialized:
        validation = validate_sft_row(row)
        if not validation.valid:
            invalid += 1
        domain = str(row.get("_domain") or row.get("_mix_domain") or "")
        domains[domain] += 1
        prompt = canonical_prompt(row)
        if any(tag in prompt.lower() for tag in ("<think>", "</think>", "<answer>", "</answer>")):
            contaminated_prompts += 1
        hashes.add(canonical_prompt_hash(row))

        if require_native_verification:
            verification = row.get("_verification") or {}
            if verification.get("passed") is not True or verification.get(
                "type"
            ) != EXPECTED_VERIFIER.get(domain):
                unverified += 1

        if tokenizer is not None:
            count = _chat_tokens(tokenizer, row["messages"])
            lengths.append(count)
            if count > max_chat_tokens:
                over_limit += 1

        if deny_index is not None:
            match = deny_index.match(prompt)
            hard_matches += int(match.hard_deny)
            near_matches += int(match.near_deny)

    expected = {domain: rows_per_domain for domain in DOMAINS}
    if dict(domains) != expected:
        raise ValueError(f"wrong domain mix: expected {expected}, found {dict(domains)}")
    duplicate_count = len(materialized) - len(hashes)
    if invalid or duplicate_count or contaminated_prompts or over_limit or unverified:
        raise ValueError(
            "SFT audit failed: "
            f"invalid={invalid} duplicates={duplicate_count} prompt_tags={contaminated_prompts} "
            f"over_limit={over_limit} unverified={unverified}"
        )

    return AssemblyAudit(
        rows=len(materialized),
        domains=dict(domains),
        duplicate_prompts=duplicate_count,
        invalid_protocol=invalid,
        unverified_native_rows=unverified,
        prompt_protocol_tags=contaminated_prompts,
        max_chat_tokens=max(lengths) if lengths else None,
        over_max_chat_tokens=over_limit,
        benchmark_audit="performed" if deny_index is not None else "not_provided",
        hard_deny_matches=hard_matches if deny_index is not None else None,
        near_deny_matches=near_matches if deny_index is not None else None,
    )


def audit_15k(
    rows: Iterable[dict[str, Any]],
    *,
    tokenizer: Any | None = None,
    deny_index: BenchmarkDenyIndex | None = None,
) -> AssemblyAudit:
    return audit_dataset(
        rows,
        rows_per_domain=5000,
        tokenizer=tokenizer,
        deny_index=deny_index,
    )


def audit_native_30k(
    rows: Iterable[dict[str, Any]],
    *,
    tokenizer: Any | None = None,
    deny_index: BenchmarkDenyIndex | None = None,
) -> AssemblyAudit:
    return audit_dataset(
        rows,
        rows_per_domain=10000,
        tokenizer=tokenizer,
        require_native_verification=True,
        deny_index=deny_index,
    )
