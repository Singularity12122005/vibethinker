"""Validated records for the causal process-observation pilot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .identity import assert_public_identity, assert_sha256, canonical_sha256

Mode = Literal["toy", "formal"]
CheckpointStage = Literal["base", "sft", "rl"]
CheckpointStatus = Literal["validated", "unverified"]
RegionSplit = Literal["discovery", "confirmation"]
RegionSource = Literal["deterministic_rule", "external_annotation", "human_review"]
RelationType = Literal["derive", "assume", "eliminate", "contradict", "update", "unknown"]
ARUStatus = Literal["proposed", "accepted", "split", "merged", "rejected"]
InterventionKind = Literal[
    "original",
    "paraphrase",
    "repair",
    "corrupt",
    "delete",
    "no_op_control",
    "unrelated_unit_control",
]
SemanticValidationStatus = Literal["claimed", "verifier_validated", "human_validated", "unknown"]
ContinuationMode = Literal["natural", "short", "full"]
TriState = Literal["true", "false", "unknown"]
Granularity = Literal["token_window", "sentence", "macro_step", "aru"]


def _required(value: dict[str, Any], fields: set[str]) -> None:
    missing = sorted(fields - value.keys())
    if missing:
        raise ValueError(f"missing required fields: {missing}")


def _nonempty_str(value: Any, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} must be non-empty")
    return text


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    return float(value)


def _tuple_ints(value: Any, field: str, *, allow_none: bool = False) -> tuple[int, ...] | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of token IDs")
    result = tuple(_nonnegative_int(item, field) for item in value)
    return result


def _tuple_strs(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of strings")
    result = tuple(_nonempty_str(item, field) for item in value)
    return result


def _mode(value: Any) -> Mode:
    mode = str(value)
    if mode not in {"toy", "formal"}:
        raise ValueError("mode must be toy or formal")
    return mode  # type: ignore[return-value]


def _tri(value: Any, field: str) -> TriState:
    text = str(value)
    if text not in {"true", "false", "unknown"}:
        raise ValueError(f"{field} must be true, false, or unknown")
    return text  # type: ignore[return-value]


def _literal(value: Any, allowed: set[str], field: str) -> str:
    text = str(value)
    if text not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return text


def _messages(value: Any) -> tuple[dict[str, str], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("prompt_messages must be a non-empty list")
    messages: list[dict[str, str]] = []
    for message in value:
        if not isinstance(message, dict) or "role" not in message or "content" not in message:
            raise ValueError("each message must contain role and content")
        messages.append({"role": str(message["role"]), "content": str(message["content"])})
    return tuple(messages)


def _mode_isolation(mode: Mode, values: list[str]) -> None:
    joined = " ".join(values).casefold()
    if mode == "formal" and ("synthetic" in joined or "toy" in joined):
        raise ValueError("formal/toy isolation violation: formal identity references toy data")
    if mode == "toy" and "formal" in joined:
        raise ValueError("formal/toy isolation violation: toy identity references formal data")


@dataclass(frozen=True)
class ProcessRunProfile:
    profile_id: str
    schema_version: int
    mode: Mode
    context_tokens: int
    short_continuation_tokens: int
    full_continuation_tokens: int
    temperature: float
    top_p: float
    seeds: tuple[int, ...]
    checkpoint_ids: tuple[str, ...]
    outcome_evaluator_id: str
    candidate_selection_policy_id: str
    intervention_policy_id: str
    artifact_format_version: int

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ProcessRunProfile:
        _required(
            value,
            {
                "profile_id",
                "schema_version",
                "mode",
                "context_tokens",
                "short_continuation_tokens",
                "full_continuation_tokens",
                "temperature",
                "top_p",
                "seeds",
                "checkpoint_ids",
                "outcome_evaluator_id",
                "candidate_selection_policy_id",
                "intervention_policy_id",
                "artifact_format_version",
            },
        )
        mode = _mode(value["mode"])
        context_tokens = _positive_int(value["context_tokens"], "context_tokens")
        short_tokens = _positive_int(
            value["short_continuation_tokens"], "short_continuation_tokens"
        )
        full_tokens = _positive_int(value["full_continuation_tokens"], "full_continuation_tokens")
        if max(short_tokens, full_tokens) > context_tokens:
            raise ValueError("continuation limits cannot exceed context_tokens")
        temperature = _float(value["temperature"], "temperature")
        top_p = _float(value["top_p"], "top_p")
        if temperature < 0 or not 0 < top_p <= 1:
            raise ValueError("temperature must be non-negative and top_p must be in (0, 1]")
        seeds = tuple(_positive_int(item, "seeds") for item in value["seeds"])
        if not seeds:
            raise ValueError("seeds must be explicit and non-empty")
        checkpoint_ids = _tuple_strs(value["checkpoint_ids"], "checkpoint_ids")
        profile = cls(
            profile_id=_nonempty_str(value["profile_id"], "profile_id"),
            schema_version=_positive_int(value["schema_version"], "schema_version"),
            mode=mode,
            context_tokens=context_tokens,
            short_continuation_tokens=short_tokens,
            full_continuation_tokens=full_tokens,
            temperature=temperature,
            top_p=top_p,
            seeds=seeds,
            checkpoint_ids=checkpoint_ids,
            outcome_evaluator_id=_nonempty_str(
                value["outcome_evaluator_id"], "outcome_evaluator_id"
            ),
            candidate_selection_policy_id=_nonempty_str(
                value["candidate_selection_policy_id"], "candidate_selection_policy_id"
            ),
            intervention_policy_id=_nonempty_str(
                value["intervention_policy_id"], "intervention_policy_id"
            ),
            artifact_format_version=_positive_int(
                value["artifact_format_version"], "artifact_format_version"
            ),
        )
        _mode_isolation(
            mode,
            [
                profile.profile_id,
                *profile.checkpoint_ids,
                profile.outcome_evaluator_id,
                profile.candidate_selection_policy_id,
                profile.intervention_policy_id,
            ],
        )
        return profile

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_format_version": self.artifact_format_version,
            "candidate_selection_policy_id": self.candidate_selection_policy_id,
            "checkpoint_ids": list(self.checkpoint_ids),
            "context_tokens": self.context_tokens,
            "full_continuation_tokens": self.full_continuation_tokens,
            "intervention_policy_id": self.intervention_policy_id,
            "mode": self.mode,
            "outcome_evaluator_id": self.outcome_evaluator_id,
            "profile_id": self.profile_id,
            "schema_version": self.schema_version,
            "seeds": list(self.seeds),
            "short_continuation_tokens": self.short_continuation_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }


@dataclass(frozen=True)
class CheckpointReference:
    checkpoint_id: str
    lineage: str
    stage: CheckpointStage
    manifest_sha256: str | None
    tokenizer_reference: str
    tokenizer_sha256: str | None
    checkpoint_receipt_reference: str | None
    status: CheckpointStatus
    runtime_locator: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> CheckpointReference:
        _required(
            value,
            {
                "checkpoint_id",
                "lineage",
                "stage",
                "manifest_sha256",
                "tokenizer_reference",
                "tokenizer_sha256",
                "checkpoint_receipt_reference",
                "status",
            },
        )
        manifest_sha256 = value.get("manifest_sha256")
        tokenizer_sha256 = value.get("tokenizer_sha256")
        assert_sha256(manifest_sha256, "manifest_sha256")
        assert_sha256(tokenizer_sha256, "tokenizer_sha256")
        stage = _literal(str(value["stage"]), {"base", "sft", "rl"}, "stage")
        status = _literal(str(value["status"]), {"validated", "unverified"}, "status")
        reference = cls(
            checkpoint_id=_nonempty_str(value["checkpoint_id"], "checkpoint_id"),
            lineage=_nonempty_str(value["lineage"], "lineage"),
            stage=stage,  # type: ignore[arg-type]
            manifest_sha256=manifest_sha256,
            tokenizer_reference=_nonempty_str(value["tokenizer_reference"], "tokenizer_reference"),
            tokenizer_sha256=tokenizer_sha256,
            checkpoint_receipt_reference=(
                None
                if value.get("checkpoint_receipt_reference") is None
                else _nonempty_str(
                    value["checkpoint_receipt_reference"], "checkpoint_receipt_reference"
                )
            ),
            status=status,  # type: ignore[arg-type]
            runtime_locator=value.get("runtime_locator"),
        )
        assert_public_identity(reference.to_identity_dict())
        return reference

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_receipt_reference": self.checkpoint_receipt_reference,
            "lineage": self.lineage,
            "manifest_sha256": self.manifest_sha256,
            "stage": self.stage,
            "status": self.status,
            "tokenizer_reference": self.tokenizer_reference,
            "tokenizer_sha256": self.tokenizer_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.to_identity_dict(), "runtime_locator": self.runtime_locator}


@dataclass(frozen=True)
class NaturalRolloutReference:
    rollout_id: str
    prompt_id: str
    checkpoint_id: str
    generation_sha256: str
    prompt_messages: tuple[dict[str, str], ...]
    raw_completion: str | None
    prompt_token_ids: tuple[int, ...] | None
    completion_token_ids: tuple[int, ...] | None
    tokenization_receipt: str | None
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str
    truncated: bool
    source_artifact_sha256: str
    source_mode: Mode
    sealed_artifact_reference: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> NaturalRolloutReference:
        _required(
            value,
            {
                "rollout_id",
                "prompt_id",
                "checkpoint_id",
                "generation_sha256",
                "prompt_messages",
                "raw_completion",
                "prompt_token_ids",
                "completion_token_ids",
                "tokenization_receipt",
                "prompt_tokens",
                "completion_tokens",
                "finish_reason",
                "truncated",
                "source_artifact_sha256",
                "source_mode",
            },
        )
        source_mode = _mode(value["source_mode"])
        generation_sha256 = _nonempty_str(value["generation_sha256"], "generation_sha256")
        source_artifact_sha256 = _nonempty_str(
            value["source_artifact_sha256"], "source_artifact_sha256"
        )
        assert_sha256(generation_sha256, "generation_sha256")
        assert_sha256(source_artifact_sha256, "source_artifact_sha256")
        prompt_token_ids = _tuple_ints(
            value["prompt_token_ids"], "prompt_token_ids", allow_none=True
        )
        completion_token_ids = _tuple_ints(
            value["completion_token_ids"], "completion_token_ids", allow_none=True
        )
        tokenization_receipt = value.get("tokenization_receipt")
        prompt_tokens = _nonnegative_int(value["prompt_tokens"], "prompt_tokens")
        completion_tokens = _nonnegative_int(value["completion_tokens"], "completion_tokens")
        if prompt_token_ids is not None and len(prompt_token_ids) != prompt_tokens:
            raise ValueError("prompt_tokens must match prompt_token_ids length")
        if completion_token_ids is not None and len(completion_token_ids) != completion_tokens:
            raise ValueError("completion_tokens must match completion_token_ids length")
        if source_mode == "formal":
            if prompt_token_ids is None or completion_token_ids is None:
                raise ValueError("formal rollouts require exact prompt and completion token IDs")
            if not tokenization_receipt:
                raise ValueError("formal rollouts require a tokenizer verification receipt")
        raw_completion = value.get("raw_completion")
        sealed = value.get("sealed_artifact_reference")
        if raw_completion is None and sealed is None:
            raise ValueError("rollout requires raw_completion or sealed_artifact_reference")
        if not isinstance(value["truncated"], bool):
            raise ValueError("truncated must be boolean")
        return cls(
            rollout_id=_nonempty_str(value["rollout_id"], "rollout_id"),
            prompt_id=_nonempty_str(value["prompt_id"], "prompt_id"),
            checkpoint_id=_nonempty_str(value["checkpoint_id"], "checkpoint_id"),
            generation_sha256=generation_sha256,
            prompt_messages=_messages(value["prompt_messages"]),
            raw_completion=None if raw_completion is None else str(raw_completion),
            prompt_token_ids=prompt_token_ids,
            completion_token_ids=completion_token_ids,
            tokenization_receipt=(
                None if tokenization_receipt is None else str(tokenization_receipt)
            ),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason=_nonempty_str(value["finish_reason"], "finish_reason"),
            truncated=value["truncated"],
            source_artifact_sha256=source_artifact_sha256,
            source_mode=source_mode,
            sealed_artifact_reference=None if sealed is None else str(sealed),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "completion_token_ids": (
                None if self.completion_token_ids is None else list(self.completion_token_ids)
            ),
            "completion_tokens": self.completion_tokens,
            "finish_reason": self.finish_reason,
            "generation_sha256": self.generation_sha256,
            "prompt_id": self.prompt_id,
            "prompt_messages": list(self.prompt_messages),
            "prompt_token_ids": (
                None if self.prompt_token_ids is None else list(self.prompt_token_ids)
            ),
            "prompt_tokens": self.prompt_tokens,
            "raw_completion": self.raw_completion,
            "rollout_id": self.rollout_id,
            "sealed_artifact_reference": self.sealed_artifact_reference,
            "source_artifact_sha256": self.source_artifact_sha256,
            "source_mode": self.source_mode,
            "tokenization_receipt": self.tokenization_receipt,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class CandidateRegion:
    region_id: str
    rollout_id: str
    checkpoint_id: str
    prompt_id: str
    span_start_token: int
    span_end_token: int
    shared_prefix_end_token: int
    selection_reason: str
    selection_policy_id: str
    split: RegionSplit
    source: RegionSource
    annotation_provenance: str
    source_artifact_sha256: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> CandidateRegion:
        _required(
            value,
            {
                "region_id",
                "rollout_id",
                "checkpoint_id",
                "prompt_id",
                "span_start_token",
                "span_end_token",
                "shared_prefix_end_token",
                "selection_reason",
                "selection_policy_id",
                "split",
                "source",
                "annotation_provenance",
                "source_artifact_sha256",
            },
        )
        span_start = _nonnegative_int(value["span_start_token"], "span_start_token")
        span_end = _nonnegative_int(value["span_end_token"], "span_end_token")
        prefix_end = _nonnegative_int(value["shared_prefix_end_token"], "shared_prefix_end_token")
        if not 0 <= prefix_end <= span_start < span_end:
            raise ValueError(
                "candidate region requires 0 <= shared_prefix_end <= span_start < span_end"
            )
        source_artifact_sha256 = _nonempty_str(
            value["source_artifact_sha256"], "source_artifact_sha256"
        )
        assert_sha256(source_artifact_sha256, "source_artifact_sha256")
        return cls(
            region_id=_nonempty_str(value["region_id"], "region_id"),
            rollout_id=_nonempty_str(value["rollout_id"], "rollout_id"),
            checkpoint_id=_nonempty_str(value["checkpoint_id"], "checkpoint_id"),
            prompt_id=_nonempty_str(value["prompt_id"], "prompt_id"),
            span_start_token=span_start,
            span_end_token=span_end,
            shared_prefix_end_token=prefix_end,
            selection_reason=_nonempty_str(value["selection_reason"], "selection_reason"),
            selection_policy_id=_nonempty_str(value["selection_policy_id"], "selection_policy_id"),
            split=_literal(str(value["split"]), {"discovery", "confirmation"}, "split"),  # type: ignore[arg-type]
            source=_literal(
                str(value["source"]),
                {"deterministic_rule", "external_annotation", "human_review"},
                "source",
            ),  # type: ignore[arg-type]
            annotation_provenance=_nonempty_str(
                value["annotation_provenance"], "annotation_provenance"
            ),
            source_artifact_sha256=source_artifact_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ARUCandidate:
    aru_id: str
    region_id: str
    premises: tuple[str, ...]
    state_update: str
    relation_type: RelationType
    source_span_text: str
    source_span_token_ids: tuple[int, ...] | None
    annotation_provenance: str
    status: ARUStatus
    parent_aru_ids: tuple[str, ...]
    child_aru_ids: tuple[str, ...]
    schema_version: int

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ARUCandidate:
        _required(
            value,
            {
                "aru_id",
                "region_id",
                "premises",
                "state_update",
                "relation_type",
                "source_span_text",
                "source_span_token_ids",
                "annotation_provenance",
                "status",
                "parent_aru_ids",
                "child_aru_ids",
                "schema_version",
            },
        )
        return cls(
            aru_id=_nonempty_str(value["aru_id"], "aru_id"),
            region_id=_nonempty_str(value["region_id"], "region_id"),
            premises=_tuple_strs(value["premises"], "premises"),
            state_update=_nonempty_str(value["state_update"], "state_update"),
            relation_type=_literal(
                str(value["relation_type"]),
                {"derive", "assume", "eliminate", "contradict", "update", "unknown"},
                "relation_type",
            ),  # type: ignore[arg-type]
            source_span_text=_nonempty_str(value["source_span_text"], "source_span_text"),
            source_span_token_ids=_tuple_ints(
                value["source_span_token_ids"], "source_span_token_ids", allow_none=True
            ),
            annotation_provenance=_nonempty_str(
                value["annotation_provenance"], "annotation_provenance"
            ),
            status=_literal(
                str(value["status"]),
                {"proposed", "accepted", "split", "merged", "rejected"},
                "status",
            ),  # type: ignore[arg-type]
            parent_aru_ids=_tuple_strs(value["parent_aru_ids"], "parent_aru_ids"),
            child_aru_ids=_tuple_strs(value["child_aru_ids"], "child_aru_ids"),
            schema_version=_positive_int(value["schema_version"], "schema_version"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "annotation_provenance": self.annotation_provenance,
            "aru_id": self.aru_id,
            "child_aru_ids": list(self.child_aru_ids),
            "parent_aru_ids": list(self.parent_aru_ids),
            "premises": list(self.premises),
            "region_id": self.region_id,
            "relation_type": self.relation_type,
            "schema_version": self.schema_version,
            "source_span_text": self.source_span_text,
            "source_span_token_ids": (
                None if self.source_span_token_ids is None else list(self.source_span_token_ids)
            ),
            "state_update": self.state_update,
            "status": self.status,
        }


@dataclass(frozen=True)
class InterventionSpec:
    intervention_id: str
    aru_id: str
    kind: InterventionKind
    prompt_token_ids: tuple[int, ...]
    completion_prefix_token_ids: tuple[int, ...]
    original_unit_token_ids: tuple[int, ...]
    replacement_unit_token_ids: tuple[int, ...]
    replacement_text: str
    semantic_intent: str
    paired_control_id: str | None
    annotation_provenance: str
    semantic_validation_status: SemanticValidationStatus
    canonical_sha256: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> InterventionSpec:
        _required(
            value,
            {
                "intervention_id",
                "aru_id",
                "kind",
                "prompt_token_ids",
                "completion_prefix_token_ids",
                "original_unit_token_ids",
                "replacement_unit_token_ids",
                "replacement_text",
                "semantic_intent",
                "paired_control_id",
                "annotation_provenance",
                "semantic_validation_status",
                "canonical_sha256",
            },
        )
        item = cls(
            intervention_id=_nonempty_str(value["intervention_id"], "intervention_id"),
            aru_id=_nonempty_str(value["aru_id"], "aru_id"),
            kind=_literal(
                str(value["kind"]),
                {
                    "original",
                    "paraphrase",
                    "repair",
                    "corrupt",
                    "delete",
                    "no_op_control",
                    "unrelated_unit_control",
                },
                "kind",
            ),  # type: ignore[arg-type]
            prompt_token_ids=_tuple_ints(value["prompt_token_ids"], "prompt_token_ids")
            or (),
            completion_prefix_token_ids=_tuple_ints(
                value["completion_prefix_token_ids"], "completion_prefix_token_ids"
            )
            or (),
            original_unit_token_ids=_tuple_ints(
                value["original_unit_token_ids"], "original_unit_token_ids"
            )
            or (),
            replacement_unit_token_ids=_tuple_ints(
                value["replacement_unit_token_ids"], "replacement_unit_token_ids"
            )
            or (),
            replacement_text=str(value["replacement_text"]),
            semantic_intent=_nonempty_str(value["semantic_intent"], "semantic_intent"),
            paired_control_id=(
                None
                if value.get("paired_control_id") is None
                else _nonempty_str(value["paired_control_id"], "paired_control_id")
            ),
            annotation_provenance=_nonempty_str(
                value["annotation_provenance"], "annotation_provenance"
            ),
            semantic_validation_status=_literal(
                str(value["semantic_validation_status"]),
                {"claimed", "verifier_validated", "human_validated", "unknown"},
                "semantic_validation_status",
            ),  # type: ignore[arg-type]
            canonical_sha256=_nonempty_str(value["canonical_sha256"], "canonical_sha256"),
        )
        expected = canonical_sha256(item.to_identity_dict())
        if item.canonical_sha256 != expected:
            raise ValueError("intervention canonical_sha256 mismatch")
        return item

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "annotation_provenance": self.annotation_provenance,
            "aru_id": self.aru_id,
            "completion_prefix_token_ids": list(self.completion_prefix_token_ids),
            "intervention_id": self.intervention_id,
            "kind": self.kind,
            "original_unit_token_ids": list(self.original_unit_token_ids),
            "paired_control_id": self.paired_control_id,
            "prompt_token_ids": list(self.prompt_token_ids),
            "replacement_text": self.replacement_text,
            "replacement_unit_token_ids": list(self.replacement_unit_token_ids),
            "semantic_intent": self.semantic_intent,
            "semantic_validation_status": self.semantic_validation_status,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.to_identity_dict(), "canonical_sha256": self.canonical_sha256}

    @property
    def shared_prefix_token_ids(self) -> tuple[int, ...]:
        return self.prompt_token_ids + self.completion_prefix_token_ids


@dataclass(frozen=True)
class PrefixBranchRequest:
    branch_id: str
    request_sha256: str
    checkpoint_reference: CheckpointReference
    prompt_id: str
    prompt_token_ids: tuple[int, ...]
    completion_prefix_token_ids: tuple[int, ...]
    intervention_token_ids: tuple[int, ...]
    context_tokens: int
    max_new_tokens: int
    temperature: float
    top_p: float
    seed: int
    continuation_mode: ContinuationMode
    profile_id: str
    transport_config_id: str
    metadata: dict[str, Any]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> PrefixBranchRequest:
        _required(
            value,
            {
                "branch_id",
                "request_sha256",
                "checkpoint_reference",
                "prompt_id",
                "prompt_token_ids",
                "completion_prefix_token_ids",
                "intervention_token_ids",
                "context_tokens",
                "max_new_tokens",
                "temperature",
                "top_p",
                "seed",
                "continuation_mode",
                "profile_id",
                "transport_config_id",
                "metadata",
            },
        )
        checkpoint_reference = CheckpointReference.from_mapping(value["checkpoint_reference"])
        metadata = dict(value["metadata"])
        item = cls(
            branch_id=_nonempty_str(value["branch_id"], "branch_id"),
            request_sha256=_nonempty_str(value["request_sha256"], "request_sha256"),
            checkpoint_reference=checkpoint_reference,
            prompt_id=_nonempty_str(value["prompt_id"], "prompt_id"),
            prompt_token_ids=_tuple_ints(value["prompt_token_ids"], "prompt_token_ids")
            or (),
            completion_prefix_token_ids=_tuple_ints(
                value["completion_prefix_token_ids"], "completion_prefix_token_ids"
            )
            or (),
            intervention_token_ids=_tuple_ints(
                value["intervention_token_ids"], "intervention_token_ids"
            )
            or (),
            context_tokens=_positive_int(value["context_tokens"], "context_tokens"),
            max_new_tokens=_positive_int(value["max_new_tokens"], "max_new_tokens"),
            temperature=_float(value["temperature"], "temperature"),
            top_p=_float(value["top_p"], "top_p"),
            seed=_positive_int(value["seed"], "seed"),
            continuation_mode=_literal(
                str(value["continuation_mode"]), {"natural", "short", "full"}, "continuation_mode"
            ),  # type: ignore[arg-type]
            profile_id=_nonempty_str(value["profile_id"], "profile_id"),
            transport_config_id=_nonempty_str(
                value["transport_config_id"], "transport_config_id"
            ),
            metadata=metadata,
        )
        if item.max_new_tokens > item.context_tokens:
            raise ValueError("max_new_tokens cannot exceed context_tokens")
        if item.input_token_count + item.max_new_tokens > item.context_tokens:
            raise ValueError(
                "context_tokens must cover prompt, completion prefix, "
                "intervention, and max_new_tokens"
            )
        if item.temperature < 0 or not 0 < item.top_p <= 1:
            raise ValueError("temperature must be non-negative and top_p must be in (0, 1]")
        expected = canonical_sha256(item.to_identity_dict())
        if item.request_sha256 != expected:
            raise ValueError("request_sha256 mismatch")
        return item

    def to_identity_dict(self) -> dict[str, Any]:
        value = {
            "branch_id": self.branch_id,
            "checkpoint_reference": self.checkpoint_reference.to_identity_dict(),
            "completion_prefix_token_ids": list(self.completion_prefix_token_ids),
            "context_tokens": self.context_tokens,
            "continuation_mode": self.continuation_mode,
            "intervention_token_ids": list(self.intervention_token_ids),
            "max_new_tokens": self.max_new_tokens,
            "metadata": self.metadata,
            "profile_id": self.profile_id,
            "prompt_id": self.prompt_id,
            "prompt_token_ids": list(self.prompt_token_ids),
            "seed": self.seed,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "transport_config_id": self.transport_config_id,
        }
        assert_public_identity(value)
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_identity_dict(),
            "checkpoint_reference": self.checkpoint_reference.to_dict(),
            "request_sha256": self.request_sha256,
        }

    @property
    def shared_prefix_token_ids(self) -> tuple[int, ...]:
        return self.prompt_token_ids + self.completion_prefix_token_ids

    @property
    def input_token_ids(self) -> tuple[int, ...]:
        return self.shared_prefix_token_ids + self.intervention_token_ids

    @property
    def input_token_count(self) -> int:
        return len(self.input_token_ids)


@dataclass(frozen=True)
class PrefixBranchResponse:
    branch_id: str
    request_sha256: str
    continuation_text: str
    continuation_token_ids: tuple[int, ...] | None
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str
    truncated: bool
    transport_signature: str
    response_sha256: str
    runtime_receipt: dict[str, Any] | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> PrefixBranchResponse:
        _required(
            value,
            {
                "branch_id",
                "request_sha256",
                "continuation_text",
                "continuation_token_ids",
                "prompt_tokens",
                "completion_tokens",
                "finish_reason",
                "truncated",
                "transport_signature",
                "response_sha256",
                "runtime_receipt",
            },
        )
        if not isinstance(value["truncated"], bool):
            raise ValueError("truncated must be boolean")
        item = cls(
            branch_id=_nonempty_str(value["branch_id"], "branch_id"),
            request_sha256=_nonempty_str(value["request_sha256"], "request_sha256"),
            continuation_text=str(value["continuation_text"]),
            continuation_token_ids=_tuple_ints(
                value["continuation_token_ids"], "continuation_token_ids", allow_none=True
            ),
            prompt_tokens=_nonnegative_int(value["prompt_tokens"], "prompt_tokens"),
            completion_tokens=_nonnegative_int(value["completion_tokens"], "completion_tokens"),
            finish_reason=_nonempty_str(value["finish_reason"], "finish_reason"),
            truncated=value["truncated"],
            transport_signature=_nonempty_str(value["transport_signature"], "transport_signature"),
            response_sha256=_nonempty_str(value["response_sha256"], "response_sha256"),
            runtime_receipt=value.get("runtime_receipt"),
        )
        expected = canonical_sha256(item.to_identity_dict())
        if item.response_sha256 != expected:
            raise ValueError("response_sha256 mismatch")
        return item

    def to_identity_dict(self) -> dict[str, Any]:
        value = {
            "branch_id": self.branch_id,
            "completion_tokens": self.completion_tokens,
            "continuation_text": self.continuation_text,
            "continuation_token_ids": (
                None
                if self.continuation_token_ids is None
                else list(self.continuation_token_ids)
            ),
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "request_sha256": self.request_sha256,
            "runtime_receipt": self.runtime_receipt,
            "transport_signature": self.transport_signature,
            "truncated": self.truncated,
        }
        assert_public_identity(value)
        return value

    def to_dict(self) -> dict[str, Any]:
        return {**self.to_identity_dict(), "response_sha256": self.response_sha256}


@dataclass(frozen=True)
class ProcessOutcome:
    branch_id: str
    intervention_id: str
    local_validity: TriState
    candidate_answer: str | None
    final_correctness: TriState
    self_repair: TriState
    terminated_normally: bool
    protocol_valid: bool
    truncated: bool
    detail: dict[str, Any]
    evaluator_signature: str
    evaluator_provenance: str
    source_response_sha256: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ProcessOutcome:
        _required(
            value,
            {
                "branch_id",
                "intervention_id",
                "local_validity",
                "candidate_answer",
                "final_correctness",
                "self_repair",
                "terminated_normally",
                "protocol_valid",
                "truncated",
                "detail",
                "evaluator_signature",
                "evaluator_provenance",
                "source_response_sha256",
            },
        )
        source_response_sha256 = _nonempty_str(
            value["source_response_sha256"], "source_response_sha256"
        )
        assert_sha256(source_response_sha256, "source_response_sha256")
        for field in ("terminated_normally", "protocol_valid", "truncated"):
            if not isinstance(value[field], bool):
                raise ValueError(f"{field} must be boolean")
        if not isinstance(value["detail"], dict):
            raise ValueError("detail must be an object")
        return cls(
            branch_id=_nonempty_str(value["branch_id"], "branch_id"),
            intervention_id=_nonempty_str(value["intervention_id"], "intervention_id"),
            local_validity=_tri(value["local_validity"], "local_validity"),
            candidate_answer=(
                None if value.get("candidate_answer") is None else str(value["candidate_answer"])
            ),
            final_correctness=_tri(value["final_correctness"], "final_correctness"),
            self_repair=_tri(value["self_repair"], "self_repair"),
            terminated_normally=value["terminated_normally"],
            protocol_valid=value["protocol_valid"],
            truncated=value["truncated"],
            detail=dict(value["detail"]),
            evaluator_signature=_nonempty_str(value["evaluator_signature"], "evaluator_signature"),
            evaluator_provenance=_nonempty_str(
                value["evaluator_provenance"], "evaluator_provenance"
            ),
            source_response_sha256=source_response_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class GradientProvenanceRecord:
    checkpoint_id: str
    training_step: int
    prompt_id: str
    group_id: str
    rollout_id: str
    total_score: float | None
    binary_success: TriState
    answer_correct: TriState
    format_ok: TriState
    format_progress: float | None
    base_reward: float | None
    overlong_multiplier: float | None
    completion_tokens: int
    truncated: bool
    accepted_for_update: TriState
    sampling_attempt: int | None
    resolved_config_sha256: str | None
    source_artifact_sha256: str
    schema_version: int

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> GradientProvenanceRecord:
        _required(
            value,
            {
                "checkpoint_id",
                "training_step",
                "prompt_id",
                "group_id",
                "rollout_id",
                "total_score",
                "binary_success",
                "answer_correct",
                "format_ok",
                "format_progress",
                "base_reward",
                "overlong_multiplier",
                "completion_tokens",
                "truncated",
                "accepted_for_update",
                "sampling_attempt",
                "resolved_config_sha256",
                "source_artifact_sha256",
                "schema_version",
            },
        )
        resolved = value.get("resolved_config_sha256")
        source = _nonempty_str(value["source_artifact_sha256"], "source_artifact_sha256")
        assert_sha256(resolved, "resolved_config_sha256")
        assert_sha256(source, "source_artifact_sha256")
        if not isinstance(value["truncated"], bool):
            raise ValueError("truncated must be boolean")
        sampling_attempt = value.get("sampling_attempt")
        return cls(
            checkpoint_id=_nonempty_str(value["checkpoint_id"], "checkpoint_id"),
            training_step=_nonnegative_int(value["training_step"], "training_step"),
            prompt_id=_nonempty_str(value["prompt_id"], "prompt_id"),
            group_id=_nonempty_str(value["group_id"], "group_id"),
            rollout_id=_nonempty_str(value["rollout_id"], "rollout_id"),
            total_score=(
                None
                if value.get("total_score") is None
                else _float(value["total_score"], "total_score")
            ),
            binary_success=_tri(value["binary_success"], "binary_success"),
            answer_correct=_tri(value["answer_correct"], "answer_correct"),
            format_ok=_tri(value["format_ok"], "format_ok"),
            format_progress=(
                None
                if value.get("format_progress") is None
                else _float(value["format_progress"], "format_progress")
            ),
            base_reward=(
                None
                if value.get("base_reward") is None
                else _float(value["base_reward"], "base_reward")
            ),
            overlong_multiplier=(
                None
                if value.get("overlong_multiplier") is None
                else _float(value["overlong_multiplier"], "overlong_multiplier")
            ),
            completion_tokens=_nonnegative_int(value["completion_tokens"], "completion_tokens"),
            truncated=value["truncated"],
            accepted_for_update=_tri(value["accepted_for_update"], "accepted_for_update"),
            sampling_attempt=(
                None
                if sampling_attempt is None
                else _positive_int(sampling_attempt, "sampling_attempt")
            ),
            resolved_config_sha256=resolved,
            source_artifact_sha256=source,
            schema_version=_positive_int(value["schema_version"], "schema_version"),
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()
