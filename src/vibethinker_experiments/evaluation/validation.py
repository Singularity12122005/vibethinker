"""Panel, result, and mode-boundary validation."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .io import canonical_json, index_unique, read_jsonl, sha256_bytes, sha256_file
from .models import DOMAINS, EvaluationProfile, PanelManifest

PROTOCOL_HINT = re.compile(r"<\s*/?\s*(?:think|answer)\s*>", re.IGNORECASE)


def validate_panel_rows(
    rows: list[dict[str, Any]], manifest: PanelManifest
) -> dict[str, dict[str, Any]]:
    indexed = index_unique(rows, "panel_id")
    if len(rows) != manifest.row_count:
        raise ValueError(
            f"panel row count mismatch: expected {manifest.row_count}, got {len(rows)}"
        )
    counts = Counter()
    for row in rows:
        panel_id = str(row["panel_id"])
        domain = str(row.get("domain", ""))
        if domain not in DOMAINS or domain not in manifest.domains:
            raise ValueError(f"{panel_id}: unsupported domain {domain!r}")
        counts[domain] += 1
        messages = row.get("messages")
        if (
            not isinstance(messages, list)
            or not messages
            or messages[-1].get("role") != "user"
            or any(message.get("role") not in {"user", "assistant"} for message in messages)
        ):
            raise ValueError(f"{panel_id}: conversation must end with a user turn")
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        if PROTOCOL_HINT.search(prompt):
            raise ValueError(f"{panel_id}: prompt contains protocol hints")
        fixture = row.get("fixture")
        if manifest.mode == "toy" and fixture != "synthetic-toy":
            raise ValueError(f"{panel_id}: toy rows must declare fixture=synthetic-toy")
        if manifest.mode == "formal" and fixture is not None:
            raise ValueError(f"{panel_id}: formal rows cannot carry toy fixture markers")
        if not isinstance(row.get("grading"), dict):
            raise ValueError(f"{panel_id}: grading must be an object")
    missing_domains = sorted(set(manifest.domains) - counts.keys())
    if missing_domains:
        raise ValueError(f"panel has no rows for domains: {missing_domains}")
    return indexed


def load_and_validate_panel(
    panel_path: str | Path,
    manifest: PanelManifest,
    profile: EvaluationProfile,
) -> list[dict[str, Any]]:
    manifest.assert_compatible(profile)
    actual_hash = sha256_file(panel_path)
    if actual_hash != manifest.panel_sha256:
        raise ValueError(
            f"panel SHA-256 mismatch: expected {manifest.panel_sha256}, got {actual_hash}"
        )
    rows = read_jsonl(panel_path)
    validate_panel_rows(rows, manifest)
    return rows


def validate_generation_result(
    row: dict[str, Any],
    *,
    panel_sha256: str,
    profile_id: str,
    context_tokens: int,
    generation_cap_tokens: int,
) -> None:
    required = {
        "panel_id",
        "domain",
        "raw_completion",
        "prompt_tokens",
        "completion_tokens",
        "finish_reason",
        "profile_id",
        "panel_sha256",
        "generation_sha256",
    }
    missing = sorted(required - row.keys())
    if missing:
        raise ValueError(f"generation result missing fields: {missing}")
    if row["panel_sha256"] != panel_sha256:
        raise ValueError(f"{row['panel_id']}: generation panel hash mismatch")
    if row["profile_id"] != profile_id:
        raise ValueError(f"{row['panel_id']}: generation profile mismatch")
    prompt_tokens = int(row["prompt_tokens"])
    completion_tokens = int(row["completion_tokens"])
    if prompt_tokens < 0 or completion_tokens < 0:
        raise ValueError(f"{row['panel_id']}: token counts must be non-negative")
    if completion_tokens > generation_cap_tokens:
        raise ValueError(f"{row['panel_id']}: completion exceeds generation cap")
    if prompt_tokens + completion_tokens > context_tokens:
        raise ValueError(f"{row['panel_id']}: generation exceeds profile context")
    identity = {
        key: row[key]
        for key in (
            "panel_id",
            "panel_sha256",
            "raw_completion",
            "prompt_tokens",
            "completion_tokens",
            "finish_reason",
            "profile_id",
        )
    }
    expected_digest = sha256_bytes(canonical_json(identity).encode())
    if row["generation_sha256"] != expected_digest:
        raise ValueError(f"{row['panel_id']}: generation hash mismatch")


def validate_judgment(row: dict[str, Any], *, panel_sha256: str) -> None:
    required = {
        "panel_id",
        "generation_sha256",
        "judge_signature",
        "judge_status",
        "true_correct",
        "attempt",
    }
    missing = sorted(required - row.keys())
    if missing:
        raise ValueError(f"judgment missing fields: {missing}")
    if row.get("panel_sha256") != panel_sha256:
        raise ValueError(f"{row.get('panel_id')}: judgment panel hash mismatch")
    if row.get("judge_status") not in {"correct", "incorrect", "unresolved"}:
        raise ValueError(f"{row.get('panel_id')}: invalid judge_status")
    for field in ("generation_sha256", "judge_signature"):
        digest = str(row[field])
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"{row.get('panel_id')}: invalid {field}")
    if bool(row["true_correct"]) != (row["judge_status"] == "correct"):
        raise ValueError(f"{row.get('panel_id')}: inconsistent true_correct")
    if not isinstance(row.get("attempt"), int) or int(row["attempt"]) < 1:
        raise ValueError(f"{row.get('panel_id')}: attempt must be positive")
