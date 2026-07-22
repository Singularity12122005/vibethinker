"""Sparse deterministic localization for candidate process regions."""

from __future__ import annotations

from .identity import canonical_sha256
from .models import CandidateRegion, NaturalRolloutReference, RegionSplit


def selection_policy_identity(config: dict[str, object]) -> str:
    return canonical_sha256({"selector": "deterministic-sparse-token-region", **config})


def deterministic_candidate_regions(
    rollouts: list[NaturalRolloutReference],
    *,
    selection_policy_id: str,
    split: RegionSplit,
    max_width_tokens: int = 3,
    source_artifact_sha256: str | None = None,
) -> list[CandidateRegion]:
    if max_width_tokens < 1:
        raise ValueError("max_width_tokens must be positive")
    rows: list[CandidateRegion] = []
    for rollout in rollouts:
        if rollout.completion_tokens < 1:
            continue
        start = rollout.prompt_tokens
        end = start + min(max_width_tokens, rollout.completion_tokens)
        value = {
            "annotation_provenance": "deterministic-cpu-selector",
            "checkpoint_id": rollout.checkpoint_id,
            "prompt_id": rollout.prompt_id,
            "region_id": f"{rollout.rollout_id}-region0",
            "rollout_id": rollout.rollout_id,
            "selection_policy_id": selection_policy_id,
            "selection_reason": "first completion transition with non-empty continuation",
            "shared_prefix_end_token": start,
            "source": "deterministic_rule",
            "source_artifact_sha256": source_artifact_sha256 or rollout.source_artifact_sha256,
            "span_end_token": end,
            "span_start_token": start,
            "split": split,
        }
        rows.append(CandidateRegion.from_mapping(value))
    return rows
