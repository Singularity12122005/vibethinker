"""Transparent ARU decision helper with insufficient-evidence bias."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .identity import canonical_sha256

ARUDecision = Literal[
    "accept",
    "split_review_required",
    "merge_review_required",
    "reject",
    "insufficient_evidence",
]


@dataclass(frozen=True)
class ARUDecisionThresholds:
    min_paired_units: int = 3
    min_harm_effect: float = 0.5
    min_paraphrase_agreement: float = 0.8
    max_control_effect: float = 0.2
    bootstrap_seed: int = 20260722

    def __post_init__(self) -> None:
        if self.min_paired_units < 1:
            raise ValueError("min_paired_units must be positive")
        for value in (
            self.min_harm_effect,
            self.min_paraphrase_agreement,
            self.max_control_effect,
        ):
            if not 0 <= value <= 1:
                raise ValueError("thresholds must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "bootstrap_seed": self.bootstrap_seed,
            "max_control_effect": self.max_control_effect,
            "min_harm_effect": self.min_harm_effect,
            "min_paired_units": self.min_paired_units,
            "min_paraphrase_agreement": self.min_paraphrase_agreement,
        }


def _is_true(value: str) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def decide_aru(
    observations: list[dict[str, Any]],
    *,
    thresholds: ARUDecisionThresholds | None = None,
) -> dict[str, Any]:
    active = thresholds or ARUDecisionThresholds()
    by_unit: dict[str, dict[str, bool]] = {}
    for row in observations:
        unit = str(row["paired_unit_id"])
        kind = str(row["kind"])
        correctness = _is_true(str(row["final_correctness"]))
        if correctness is not None:
            by_unit.setdefault(unit, {})[kind] = correctness
    complete = [
        row
        for row in by_unit.values()
        if {"original", "paraphrase", "corrupt", "delete", "no_op_control"} <= row.keys()
    ]
    if len(complete) < active.min_paired_units:
        decision: ARUDecision = "insufficient_evidence"
        return _decision(decision, active, len(complete), {})

    paraphrase_agreement = sum(
        row["original"] == row["paraphrase"] for row in complete
    ) / len(complete)
    corrupt_harm = sum(row["original"] and not row["corrupt"] for row in complete) / len(complete)
    delete_harm = sum(row["original"] and not row["delete"] for row in complete) / len(complete)
    no_op_effect = sum(row["original"] != row["no_op_control"] for row in complete) / len(complete)
    unrelated_rows = [row for row in complete if "unrelated_unit_control" in row]
    unrelated_effect = (
        sum(row["original"] != row["unrelated_unit_control"] for row in unrelated_rows)
        / len(unrelated_rows)
        if unrelated_rows
        else 0.0
    )
    metrics = {
        "corrupt_harm": corrupt_harm,
        "delete_harm": delete_harm,
        "no_op_effect": no_op_effect,
        "paired_units": len(complete),
        "paraphrase_agreement": paraphrase_agreement,
        "unrelated_effect": unrelated_effect,
    }
    if paraphrase_agreement < active.min_paraphrase_agreement:
        return _decision("split_review_required", active, len(complete), metrics)
    if max(no_op_effect, unrelated_effect) > active.max_control_effect:
        return _decision("merge_review_required", active, len(complete), metrics)
    if max(corrupt_harm, delete_harm) >= active.min_harm_effect:
        return _decision("accept", active, len(complete), metrics)
    return _decision("reject", active, len(complete), metrics)


def _decision(
    decision: ARUDecision,
    thresholds: ARUDecisionThresholds,
    paired_units: int,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    identity = {
        "decision": decision,
        "metrics": metrics,
        "paired_units": paired_units,
        "thresholds": thresholds.to_dict(),
    }
    return {**identity, "decision_sha256": canonical_sha256(identity)}
