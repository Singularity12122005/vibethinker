"""Outcome evaluation with explicit unknown semantics."""

from __future__ import annotations

from typing import Any, Protocol

from vibethinker_experiments.evaluation.core import best_effort_answer, score_format

from .models import ARUCandidate, InterventionSpec, PrefixBranchResponse, ProcessOutcome


class ProcessOutcomeEvaluator(Protocol):
    def evaluate(
        self,
        *,
        prompt_record: dict[str, Any],
        aru_candidate: ARUCandidate,
        intervention: InterventionSpec,
        branch_response: PrefixBranchResponse,
    ) -> ProcessOutcome: ...


class DeterministicToyOutcomeEvaluator:
    """Synthetic evaluator; it makes no claim about real model reasoning."""

    signature = "deterministic-toy-process-outcome-v1"

    def evaluate(
        self,
        *,
        prompt_record: dict[str, Any],
        aru_candidate: ARUCandidate,
        intervention: InterventionSpec,
        branch_response: PrefixBranchResponse,
    ) -> ProcessOutcome:
        answer = best_effort_answer(branch_response.continuation_text)
        format_score, format_detail = score_format(branch_response.continuation_text)
        kind = intervention.kind
        correctness = "false" if kind in {"corrupt", "delete"} else "true"
        local_validity = "false" if kind == "corrupt" else "true"
        if kind == "unrelated_unit_control":
            local_validity = "unknown"
        return ProcessOutcome.from_mapping(
            {
                "branch_id": branch_response.branch_id,
                "candidate_answer": answer,
                "detail": {
                    "aru_id": aru_candidate.aru_id,
                    "format_detail": format_detail,
                    "prompt_id": prompt_record.get("prompt_id"),
                    "synthetic": True,
                },
                "evaluator_provenance": "synthetic-toy",
                "evaluator_signature": self.signature,
                "final_correctness": correctness,
                "intervention_id": intervention.intervention_id,
                "local_validity": local_validity,
                "protocol_valid": bool(format_score),
                "self_repair": "unknown",
                "source_response_sha256": branch_response.response_sha256,
                "terminated_normally": branch_response.finish_reason in {"eos", "stop"},
                "truncated": branch_response.truncated,
            }
        )
