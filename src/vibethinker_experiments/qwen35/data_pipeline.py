"""Pure assembly logic for the audited Qwen3.5 30K SFT dataset.

Teacher transport, retries, and concurrent execution deliberately live outside
this module.  The functions here join immutable prompt pools to completed
teacher responses, invoke caller-supplied verifiers, fill domain quotas in
prompt-pool order, and perform the final cross-domain audit.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .math_protocol import grade_math_answer

DOMAINS = ("math", "code", "general")
EXPECTED_VERIFIERS = {
    "math": "math_verifier",
    "code": "code_tests",
    "general": "general_judge",
}
FINAL_SEED = 20260714
PROTOCOL = re.compile(r"^\s*<think>\s*(?P<think>[\s\S]+?)\s*</think>\s*(?P<visible>[\s\S]+?)\s*$")
PROTOCOL_TAG = re.compile(r"</?(?:think|answer)>", re.IGNORECASE)

Verifier = Callable[[Mapping[str, Any], str], tuple[bool, Mapping[str, Any]]]


def canonical_prompt_hash(prompt: str) -> str:
    """Return the stable identity used to join every pipeline stage."""
    return hashlib.sha256(" ".join(prompt.casefold().split()).encode()).hexdigest()


def _prompt(row: Mapping[str, Any]) -> str:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) != 1:
        raise ValueError("prompt row must contain exactly one message")
    message = messages[0]
    if not isinstance(message, Mapping) or message.get("role") != "user":
        raise ValueError("prompt row must contain exactly one user message")
    prompt = str(message.get("content") or "").strip()
    if not prompt or PROTOCOL_TAG.search(prompt):
        raise ValueError("prompt is empty or contains protocol tags")
    return prompt


def normalize_prompt_pool(rows: Iterable[Mapping[str, Any]], domain: str) -> list[dict[str, Any]]:
    """Validate a domain pool while preserving its primary/reserve order."""
    if domain not in DOMAINS:
        raise ValueError(f"unsupported domain: {domain}")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, source in enumerate(rows):
        row = dict(source)
        prompt = _prompt(row)
        row_domain = str(row.get("_domain") or row.get("_mix_domain") or "")
        if row_domain != domain:
            raise ValueError(f"row {index}: expected domain {domain}, found {row_domain!r}")
        prompt_hash = str(row.get("_prompt_hash") or "")
        if prompt_hash != canonical_prompt_hash(prompt):
            raise ValueError(f"row {index}: prompt hash mismatch")
        if prompt_hash in seen:
            raise ValueError(f"row {index}: duplicate prompt hash")
        seen.add(prompt_hash)
        row["_domain"] = domain
        row["_mix_domain"] = domain
        normalized.append(row)
    return normalized


def math_verifier(row: Mapping[str, Any], visible: str) -> tuple[bool, Mapping[str, Any]]:
    """Verify a math completion against the prompt-pool gold answer."""
    gold = str(row.get("_gold_answer") or "").strip()
    if not gold:
        return False, {"reason": "missing_gold"}
    return grade_math_answer(visible, gold)


def _teacher_value(result: Mapping[str, Any], *names: str) -> str:
    for name in names:
        if result.get(name) is not None:
            return str(result[name]).strip()
    return ""


def _token_count(result: Mapping[str, Any], name: str) -> int:
    aliases = (name, f"_{name}")
    value = next((result[key] for key in aliases if result.get(key) is not None), None)
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"teacher result is missing integer {name}") from exc
    if count < 0:
        raise ValueError(f"{name} must be non-negative")
    return count


def assemble_verified_row(
    prompt_row: Mapping[str, Any],
    teacher_result: Mapping[str, Any],
    domain: str,
    verifier: Verifier,
) -> dict[str, Any]:
    """Turn one completed teacher response into one verifier-backed SFT row."""
    if domain not in DOMAINS:
        raise ValueError(f"unsupported domain: {domain}")
    prompt = _prompt(prompt_row)
    prompt_hash = str(prompt_row.get("_prompt_hash") or "")
    result_hash = str(teacher_result.get("_prompt_hash") or teacher_result.get("prompt_hash") or "")
    if result_hash != prompt_hash:
        raise ValueError("teacher result does not match prompt row")
    if _teacher_value(teacher_result, "finish_reason", "_api_finish_reason") != "stop":
        raise ValueError("teacher result did not finish with stop")

    reasoning = _teacher_value(teacher_result, "reasoning", "reasoning_content")
    visible = _teacher_value(teacher_result, "content", "visible")
    if (
        not reasoning
        or not visible
        or PROTOCOL_TAG.search(reasoning)
        or PROTOCOL_TAG.search(visible)
    ):
        raise ValueError("teacher result has invalid native reasoning/content channels")
    target = f"<think>\n{reasoning}\n</think>\n{visible}"
    match = PROTOCOL.match(target)
    if not match:
        raise ValueError("assembled teacher result violates the target protocol")

    think_tokens = _token_count(teacher_result, "think_tokens")
    visible_tokens = _token_count(teacher_result, "visible_tokens")
    chat_tokens = _token_count(teacher_result, "chat_tokens")
    if think_tokens >= 15_000 or visible_tokens >= 15_000 or chat_tokens > 30_000:
        raise ValueError("teacher result violates token limits")

    passed, detail = verifier(prompt_row, visible)
    if passed is not True:
        raise ValueError("teacher result failed verifier")
    verifier_name = EXPECTED_VERIFIERS[domain]
    if not isinstance(detail, Mapping):
        raise ValueError("verifier detail must be a mapping")

    excluded = {"_gold_answer", "_reference_answer", "_reference_solution", "_tests"}
    output = {key: value for key, value in prompt_row.items() if key not in excluded}
    output["messages"] = [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": target},
    ]
    output.update(
        {
            "_api_finish_reason": "stop",
            "_think_tokens": think_tokens,
            "_visible_tokens": visible_tokens,
            "_chat_tokens": chat_tokens,
            "_verification": {
                "type": verifier_name,
                "passed": True,
                "detail": dict(detail),
            },
        }
    )
    for source, destination in (
        ("model", "_distilled_model"),
        ("provider", "_distilled_provider"),
        ("attempt", "_distill_round"),
    ):
        if teacher_result.get(source) is not None:
            output[destination] = teacher_result[source]
    return output


def _result_order(result: Mapping[str, Any]) -> tuple[int, str]:
    raw_attempt = result.get("attempt", result.get("_distill_round", 1))
    try:
        attempt = int(raw_attempt)
    except (TypeError, ValueError):
        attempt = 1
    serialized = json.dumps(dict(result), ensure_ascii=False, sort_keys=True, default=str)
    return attempt, hashlib.sha256(serialized.encode()).hexdigest()


def join_and_verify_domain(
    prompt_pool: Iterable[Mapping[str, Any]],
    teacher_results: Iterable[Mapping[str, Any]],
    domain: str,
    verifier: Verifier,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join asynchronous results deterministically and retain verifier passes."""
    pool = normalize_prompt_pool(prompt_pool, domain)
    by_hash: dict[str, list[Mapping[str, Any]]] = {}
    unknown_results = 0
    known_hashes = {str(row["_prompt_hash"]) for row in pool}
    for result in teacher_results:
        prompt_hash = str(result.get("_prompt_hash") or result.get("prompt_hash") or "")
        if prompt_hash not in known_hashes:
            unknown_results += 1
            continue
        by_hash.setdefault(prompt_hash, []).append(result)

    verified: list[dict[str, Any]] = []
    rejection_reasons: Counter[str] = Counter()
    attempted_prompts = 0
    for row in pool:
        candidates = sorted(by_hash.get(str(row["_prompt_hash"]), []), key=_result_order)
        if candidates:
            attempted_prompts += 1
        for result in candidates:
            try:
                verified.append(assemble_verified_row(row, result, domain, verifier))
                break
            except ValueError as exc:
                rejection_reasons[str(exc)] += 1

    audit = {
        "domain": domain,
        "pool_rows": len(pool),
        "teacher_results": sum(len(values) for values in by_hash.values()),
        "attempted_prompts": attempted_prompts,
        "verified_prompts": len(verified),
        "unknown_results": unknown_results,
        "rejections": dict(sorted(rejection_reasons.items())),
    }
    return verified, audit


def fill_domain_quota(
    prompt_pool: Iterable[Mapping[str, Any]],
    verified_rows: Iterable[Mapping[str, Any]],
    domain: str,
    quota: int = 10_000,
) -> list[dict[str, Any]]:
    """Fill a quota in frozen pool order, naturally consuming reserves."""
    if quota < 1:
        raise ValueError("quota must be positive")
    pool = normalize_prompt_pool(prompt_pool, domain)
    verified_by_hash: dict[str, dict[str, Any]] = {}
    for source in verified_rows:
        row = dict(source)
        prompt_hash = str(row.get("_prompt_hash") or "")
        if prompt_hash in verified_by_hash:
            raise ValueError("duplicate verified prompt hash")
        verified_by_hash[prompt_hash] = row
    unknown = set(verified_by_hash) - {str(row["_prompt_hash"]) for row in pool}
    if unknown:
        raise ValueError("verified rows contain prompts outside the frozen pool")
    selected = [
        verified_by_hash[str(row["_prompt_hash"])]
        for row in pool
        if str(row["_prompt_hash"]) in verified_by_hash
    ][:quota]
    if len(selected) != quota:
        raise ValueError(
            f"insufficient verified {domain} rows: need {quota}, found {len(selected)}"
        )
    return selected


def _audit_row(row: Mapping[str, Any], domain: str, index: int) -> str:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) != 2:
        raise ValueError(f"{domain}:{index}: expected user/assistant messages")
    if [message.get("role") for message in messages] != ["user", "assistant"]:
        raise ValueError(f"{domain}:{index}: bad message roles")
    prompt = str(messages[0].get("content") or "").strip()
    target = str(messages[1].get("content") or "").strip()
    if not prompt or PROTOCOL_TAG.search(prompt):
        raise ValueError(f"{domain}:{index}: contaminated prompt")
    match = PROTOCOL.match(target)
    if (
        not match
        or PROTOCOL_TAG.search(match.group("think"))
        or PROTOCOL_TAG.search(match.group("visible"))
    ):
        raise ValueError(f"{domain}:{index}: bad assistant protocol")
    if str(row.get("_domain") or row.get("_mix_domain")) != domain:
        raise ValueError(f"{domain}:{index}: wrong domain")
    prompt_hash = str(row.get("_prompt_hash") or "")
    if prompt_hash != canonical_prompt_hash(prompt):
        raise ValueError(f"{domain}:{index}: prompt hash mismatch")
    verification = row.get("_verification")
    if (
        not isinstance(verification, Mapping)
        or verification.get("passed") is not True
        or verification.get("type") != EXPECTED_VERIFIERS[domain]
    ):
        raise ValueError(f"{domain}:{index}: invalid verification")
    if row.get("_api_finish_reason") != "stop":
        raise ValueError(f"{domain}:{index}: non-stop teacher finish")
    think_tokens = _token_count(row, "think_tokens")
    visible_tokens = _token_count(row, "visible_tokens")
    chat_tokens = _token_count(row, "chat_tokens")
    if think_tokens >= 15_000 or visible_tokens >= 15_000 or chat_tokens > 30_000:
        raise ValueError(f"{domain}:{index}: token limit violation")
    if domain == "code":
        detail = verification.get("detail")
        if row.get("_quality_grade") != "A":
            raise ValueError(f"{domain}:{index}: code quality is not A")
        if (
            not isinstance(detail, Mapping)
            or not detail.get("n_total")
            or detail.get("n_pass") != detail.get("n_total")
        ):
            raise ValueError(f"{domain}:{index}: incomplete code verification")
    return prompt_hash


def audit_final_dataset(
    rows_by_domain: Mapping[str, Iterable[Mapping[str, Any]]],
    quota: int = 10_000,
) -> dict[str, Any]:
    """Hard-audit exact domain quotas and cross-domain prompt uniqueness."""
    if set(rows_by_domain) != set(DOMAINS):
        raise ValueError(f"final dataset must contain exactly these domains: {DOMAINS}")
    seen: set[str] = set()
    domain_counts: dict[str, int] = {}
    source_tranches: Counter[str] = Counter()
    for domain in DOMAINS:
        rows = list(rows_by_domain[domain])
        if len(rows) != quota:
            raise ValueError(f"{domain}: expected {quota} rows, found {len(rows)}")
        domain_counts[domain] = len(rows)
        for index, row in enumerate(rows):
            prompt_hash = _audit_row(row, domain, index)
            if prompt_hash in seen:
                raise ValueError(f"{domain}:{index}: duplicate prompt across domains")
            seen.add(prompt_hash)
            source_tranches[str(row.get("_source_tranche") or "unknown")] += 1
    return {
        "rows": len(seen),
        "domains": domain_counts,
        "unique_prompts": len(seen),
        "prompt_protocol_tags": 0,
        "source_tranches": dict(sorted(source_tranches.items())),
        "seed": FINAL_SEED,
    }


def finalize_sft_dataset(
    rows_by_domain: Mapping[str, Iterable[Mapping[str, Any]]],
    quota: int = 10_000,
    seed: int = FINAL_SEED,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit, combine, and deterministically shuffle the final SFT rows."""
    if set(rows_by_domain) != set(DOMAINS):
        raise ValueError(f"final dataset must contain exactly these domains: {DOMAINS}")
    materialized = {domain: [dict(row) for row in rows_by_domain[domain]] for domain in DOMAINS}
    audit = audit_final_dataset(materialized, quota=quota)
    rows = [row for domain in DOMAINS for row in materialized[domain]]
    random.Random(seed).shuffle(rows)
    audit["seed"] = seed
    return rows, audit
