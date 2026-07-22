"""Prefix-branch request construction and injected transports."""

from __future__ import annotations

from typing import Protocol

from .identity import canonical_sha256
from .models import (
    CheckpointReference,
    ContinuationMode,
    InterventionSpec,
    PrefixBranchRequest,
    PrefixBranchResponse,
    ProcessRunProfile,
)


class PrefixBranchTransport(Protocol):
    def branch(self, request: PrefixBranchRequest) -> PrefixBranchResponse: ...


class NetworkDisabledPrefixBranchTransport:
    """Safe default transport that cannot perform network or model I/O."""

    def branch(self, request: PrefixBranchRequest) -> PrefixBranchResponse:
        raise RuntimeError(
            "prefix-branch transport is not configured; inject a private adapter or toy transport"
        )


class DeterministicToyPrefixBranchTransport:
    """Deterministic synthetic transport for CPU-only contract tests."""

    signature = "deterministic-toy-prefix-branch-v1"

    def branch(self, request: PrefixBranchRequest) -> PrefixBranchResponse:
        kind = str(request.metadata.get("intervention_kind", "unknown"))
        if kind in {"corrupt", "delete"}:
            text = "<think>synthetic branch follows the edited unit</think>5"
            token_ids = (5005,)
        else:
            text = "<think>synthetic branch follows the edited unit</think>4"
            token_ids = (5004,)
        prompt_tokens = request.input_token_count
        completion_tokens = len(token_ids)
        if completion_tokens > request.max_new_tokens:
            raise ValueError("toy branch exceeds explicit generation cap")
        if prompt_tokens + completion_tokens > request.context_tokens:
            raise ValueError("toy branch exceeds explicit context cap")
        value = {
            "branch_id": request.branch_id,
            "completion_tokens": completion_tokens,
            "continuation_text": text,
            "continuation_token_ids": list(token_ids),
            "finish_reason": "eos",
            "prompt_tokens": prompt_tokens,
            "request_sha256": request.request_sha256,
            "runtime_receipt": {"mode": "toy", "transport": self.signature},
            "transport_signature": self.signature,
            "truncated": False,
        }
        value["response_sha256"] = canonical_sha256(value)
        return PrefixBranchResponse.from_mapping(value)


def make_branch_request(
    *,
    intervention: InterventionSpec,
    checkpoint_reference: CheckpointReference,
    prompt_id: str,
    profile: ProcessRunProfile,
    seed: int,
    continuation_mode: ContinuationMode,
    transport_config_id: str,
    metadata: dict[str, object] | None = None,
) -> PrefixBranchRequest:
    if profile.mode == "formal":
        if not intervention.prompt_token_ids:
            raise ValueError("formal branching requires exact prompt_token_ids")
        if intervention.completion_prefix_token_ids and not intervention.prompt_token_ids:
            raise ValueError("formal branching cannot use only a completion prefix")
        if checkpoint_reference.status != "validated":
            raise ValueError("formal branching requires a validated checkpoint receipt")
        if checkpoint_reference.checkpoint_receipt_reference is None:
            raise ValueError("formal branching requires checkpoint_receipt_reference")
        if checkpoint_reference.tokenizer_sha256 is None:
            raise ValueError("formal branching requires tokenizer_sha256")
    max_new_tokens = (
        profile.short_continuation_tokens
        if continuation_mode == "short"
        else profile.full_continuation_tokens
    )
    value = {
        "branch_id": f"{intervention.intervention_id}-{continuation_mode}-seed{seed}",
        "checkpoint_reference": checkpoint_reference.to_dict(),
        "completion_prefix_token_ids": list(intervention.completion_prefix_token_ids),
        "context_tokens": profile.context_tokens,
        "continuation_mode": continuation_mode,
        "intervention_token_ids": list(intervention.replacement_unit_token_ids),
        "max_new_tokens": max_new_tokens,
        "metadata": {
            "aru_id": intervention.aru_id,
            "intervention_id": intervention.intervention_id,
            "intervention_kind": intervention.kind,
            **dict(metadata or {}),
        },
        "profile_id": profile.profile_id,
        "prompt_id": prompt_id,
        "prompt_token_ids": list(intervention.prompt_token_ids),
        "seed": seed,
        "temperature": profile.temperature,
        "top_p": profile.top_p,
        "transport_config_id": transport_config_id,
    }
    value["request_sha256"] = canonical_sha256(
        {key: item for key, item in value.items() if key != "request_sha256"}
        | {"checkpoint_reference": checkpoint_reference.to_identity_dict()}
    )
    return PrefixBranchRequest.from_mapping(value)


def branch_all(
    requests: list[PrefixBranchRequest],
    *,
    transport: PrefixBranchTransport | None = None,
) -> list[PrefixBranchResponse]:
    active = transport or NetworkDisabledPrefixBranchTransport()
    return [active.branch(request) for request in requests]
