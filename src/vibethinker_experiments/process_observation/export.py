"""Export counterfactual-response rows for future granularity comparison."""

from __future__ import annotations

from typing import Any

from .identity import canonical_sha256
from .models import Granularity

GRANULARITIES = {"token_window", "sentence", "macro_step", "aru"}


def comparison_row(
    *,
    granularity: Granularity,
    branch_id: str,
    prompt_id: str,
    checkpoint_id: str,
    intervention_family: str,
    semantic_problem_family: str,
    surface_paraphrase_family: str,
    split: str,
    features: dict[str, Any],
    target: dict[str, Any],
    annotation_cost: float | None = None,
) -> dict[str, Any]:
    if granularity not in GRANULARITIES:
        raise ValueError("unsupported granularity")
    if split not in {"train", "heldout"}:
        raise ValueError("split must be train or heldout")
    identity = {
        "annotation_cost": annotation_cost,
        "branch_id": branch_id,
        "checkpoint_id": checkpoint_id,
        "features": features,
        "granularity": granularity,
        "intervention_family": intervention_family,
        "prompt_id": prompt_id,
        "semantic_problem_family": semantic_problem_family,
        "split": split,
        "surface_paraphrase_family": surface_paraphrase_family,
        "target": target,
    }
    return {**identity, "schema_version": 1, "row_sha256": canonical_sha256(identity)}


def validate_split_leakage(rows: list[dict[str, Any]]) -> None:
    for key in (
        "prompt_id",
        "semantic_problem_family",
        "surface_paraphrase_family",
        "checkpoint_id",
        "intervention_family",
    ):
        splits: dict[str, set[str]] = {}
        for row in rows:
            splits.setdefault(str(row[key]), set()).add(str(row["split"]))
        leaked = sorted(identity for identity, seen in splits.items() if len(seen) > 1)
        if leaked:
            raise ValueError(f"split leakage by {key}: {leaked[:5]}")
