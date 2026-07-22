"""Intervention construction with exact shared-prefix semantics."""

from __future__ import annotations

from collections.abc import Iterable

from .identity import canonical_sha256
from .models import ARUCandidate, CandidateRegion, InterventionKind, InterventionSpec


def make_intervention(
    *,
    intervention_id: str,
    aru_id: str,
    kind: InterventionKind,
    prompt_token_ids: tuple[int, ...],
    completion_prefix_token_ids: tuple[int, ...],
    original_unit_token_ids: tuple[int, ...],
    replacement_unit_token_ids: tuple[int, ...],
    replacement_text: str,
    semantic_intent: str,
    annotation_provenance: str,
    paired_control_id: str | None = None,
    semantic_validation_status: str = "claimed",
) -> InterventionSpec:
    value = {
        "annotation_provenance": annotation_provenance,
        "aru_id": aru_id,
        "completion_prefix_token_ids": list(completion_prefix_token_ids),
        "intervention_id": intervention_id,
        "kind": kind,
        "original_unit_token_ids": list(original_unit_token_ids),
        "paired_control_id": paired_control_id,
        "prompt_token_ids": list(prompt_token_ids),
        "replacement_text": replacement_text,
        "replacement_unit_token_ids": list(replacement_unit_token_ids),
        "semantic_intent": semantic_intent,
        "semantic_validation_status": semantic_validation_status,
    }
    value["canonical_sha256"] = canonical_sha256(value)
    return InterventionSpec.from_mapping(value)


def validate_intervention_family(
    region: CandidateRegion,
    interventions: Iterable[InterventionSpec],
) -> None:
    materialized = list(interventions)
    if not materialized:
        raise ValueError("at least one intervention is required")
    expected_prefix_length = region.span_start_token
    first_prefix = materialized[0].shared_prefix_token_ids
    first_aru_id = materialized[0].aru_id
    if len(first_prefix) != expected_prefix_length:
        raise ValueError("shared prefix must end exactly at the candidate unit boundary")
    for item in materialized:
        if item.aru_id != first_aru_id:
            raise ValueError("one intervention family cannot mix ARUs or rollouts")
        if item.shared_prefix_token_ids != first_prefix:
            raise ValueError("all interventions for one ARU must share the exact prefix")
        if item.kind == "delete" and item.replacement_unit_token_ids != ():
            raise ValueError("delete intervention must use an explicitly empty replacement")
        if item.kind != "delete" and item.replacement_unit_token_ids == ():
            raise ValueError("only delete interventions may have an empty replacement")
        if (
            item.kind == "no_op_control"
            and item.replacement_unit_token_ids != item.original_unit_token_ids
        ):
            raise ValueError("no-op control must be token-identical to the original")
        if item.kind == "unrelated_unit_control" and (
            item.paired_control_id is None
            or not item.paired_control_id.startswith(f"{item.aru_id}-")
        ):
            raise ValueError("unrelated-unit control requires explicit same-ARU provenance")


def prepare_toy_interventions(
    region: CandidateRegion,
    aru: ARUCandidate,
    *,
    prompt_token_ids: tuple[int, ...],
    completion_prefix_token_ids: tuple[int, ...],
    original_unit_token_ids: tuple[int, ...],
    annotation_provenance: str = "synthetic-toy",
) -> list[InterventionSpec]:
    """Build the minimal synthetic branch set used by CPU tests."""

    variants = [
        ("original", original_unit_token_ids, aru.source_span_text, "keep original unit", None),
        ("paraphrase", (105,), "four is the total", "claim equivalent paraphrase", "original"),
        ("repair", (104,), "therefore the total is 4", "claim minimal repair", "original"),
        ("corrupt", (999,), "five is the total", "claim minimal corruption", "original"),
        ("delete", (), "", "remove the candidate unit", "original"),
        (
            "no_op_control",
            original_unit_token_ids,
            aru.source_span_text,
            "no-op control",
            "original",
        ),
        (
            "unrelated_unit_control",
            (202,),
            "unrelated color detail",
            "control unrelated unit",
            "original",
        ),
    ]
    interventions = [
        make_intervention(
            intervention_id=f"{aru.aru_id}-{kind}",
            aru_id=aru.aru_id,
            kind=kind,  # type: ignore[arg-type]
            prompt_token_ids=prompt_token_ids,
            completion_prefix_token_ids=completion_prefix_token_ids,
            original_unit_token_ids=original_unit_token_ids,
            replacement_unit_token_ids=tuple(tokens),
            replacement_text=text,
            semantic_intent=intent,
            paired_control_id=None if paired is None else f"{aru.aru_id}-{paired}",
            annotation_provenance=annotation_provenance,
            semantic_validation_status="claimed",
        )
        for kind, tokens, text, intent, paired in variants
    ]
    validate_intervention_family(region, interventions)
    return interventions
