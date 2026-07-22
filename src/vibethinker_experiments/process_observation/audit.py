"""Optimization-signal provenance records and pure aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from .models import GradientProvenanceRecord, TriState


def tri_from_qwen25(value: object) -> TriState:
    if value is None:
        return "unknown"
    numeric = float(value)
    if numeric == 1.0:
        return "true"
    if numeric == 0.0:
        return "false"
    return "unknown"


def gradient_record_from_qwen25_reward(
    row: dict[str, Any],
    *,
    checkpoint_id: str,
    training_step: int,
    prompt_id: str,
    group_id: str,
    rollout_id: str,
    source_artifact_sha256: str,
    accepted_for_update: TriState = "unknown",
    sampling_attempt: int | None = None,
    resolved_config_sha256: str | None = None,
) -> GradientProvenanceRecord:
    value = {
        "accepted_for_update": accepted_for_update,
        "answer_correct": tri_from_qwen25(row.get("answer_correct")),
        "base_reward": row.get("base_reward"),
        "binary_success": tri_from_qwen25(row.get("binary_success")),
        "checkpoint_id": checkpoint_id,
        "completion_tokens": int(row.get("completion_tokens", 0)),
        "format_ok": tri_from_qwen25(row.get("format_ok")),
        "format_progress": row.get("format_progress"),
        "group_id": group_id,
        "overlong_multiplier": row.get("overlong_multiplier"),
        "prompt_id": prompt_id,
        "resolved_config_sha256": resolved_config_sha256,
        "rollout_id": rollout_id,
        "sampling_attempt": sampling_attempt,
        "schema_version": 1,
        "source_artifact_sha256": source_artifact_sha256,
        "total_score": row.get("score"),
        "training_step": training_step,
        "truncated": bool(float(row.get("truncated", 0.0))),
    }
    return GradientProvenanceRecord.from_mapping(value)


def _mean(values: Iterable[float | None]) -> float | None:
    materialized = [float(value) for value in values if value is not None]
    return sum(materialized) / len(materialized) if materialized else None


def aggregate_gradient_groups(
    records: list[GradientProvenanceRecord],
    *,
    accepted_only: bool = False,
) -> dict[str, Any]:
    selected = [
        record
        for record in records
        if not accepted_only or record.accepted_for_update == "true"
    ]
    groups: dict[tuple[str, int, str], list[GradientProvenanceRecord]] = defaultdict(list)
    for record in selected:
        groups[(record.checkpoint_id, record.training_step, record.group_id)].append(record)
    class_counts: Counter[str] = Counter()
    for rows in groups.values():
        correctness = {row.binary_success for row in rows}
        if "unknown" in correctness:
            class_counts["unknown"] += 1
        elif correctness == {"true"}:
            class_counts["M1"] += 1
        elif correctness == {"false"}:
            class_counts["M0"] += 1
        else:
            class_counts["Mmix"] += 1
    total_groups = len(groups)
    accepted_values = [row.accepted_for_update for row in records]
    acceptance_known = all(value in {"true", "false"} for value in accepted_values)
    attempts = [row.sampling_attempt for row in records if row.sampling_attempt is not None]
    prompt_counts = Counter(row.prompt_id for row in selected)
    return {
        "M0": class_counts["M0"] / total_groups if total_groups else None,
        "M1": class_counts["M1"] / total_groups if total_groups else None,
        "Mmix": class_counts["Mmix"] / total_groups if total_groups else None,
        "acceptance_rate": (
            sum(value == "true" for value in accepted_values) / len(accepted_values)
            if acceptance_known and accepted_values
            else None
        ),
        "accepted_only": accepted_only,
        "effective_sample_size": len(selected) if acceptance_known else None,
        "group_count": total_groups,
        "mean_reward_components": {
            "base_reward": _mean(row.base_reward for row in selected),
            "format_progress": _mean(row.format_progress for row in selected),
            "overlong_multiplier": _mean(row.overlong_multiplier for row in selected),
            "total_score": _mean(row.total_score for row in selected),
        },
        "record_count": len(selected),
        "repeated_prompt_count": sum(count - 1 for count in prompt_counts.values() if count > 1),
        "resampling_factor": max(attempts) if attempts and len(attempts) == len(records) else None,
        "unique_prompt_count": len(prompt_counts),
        "unknown_dynamic_sampling": not attempts or len(attempts) != len(records),
        "unknown_group_fraction": (
            class_counts["unknown"] / total_groups if total_groups else None
        ),
    }


def aggregate_raw_and_accepted(records: list[GradientProvenanceRecord]) -> dict[str, Any]:
    return {
        "accepted": aggregate_gradient_groups(records, accepted_only=True),
        "raw": aggregate_gradient_groups(records, accepted_only=False),
    }
