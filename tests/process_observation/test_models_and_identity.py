from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vibethinker_experiments.checkpoints.core import commit_checkpoint
from vibethinker_experiments.process_observation.branching import make_branch_request
from vibethinker_experiments.process_observation.identity import (
    canonical_jsonl_bytes,
    canonical_sha256,
    checkpoint_manifest_hash_if_committed,
)
from vibethinker_experiments.process_observation.interventions import (
    make_intervention,
    prepare_toy_interventions,
)
from vibethinker_experiments.process_observation.localization import deterministic_candidate_regions
from vibethinker_experiments.process_observation.models import (
    CheckpointReference,
    InterventionSpec,
    NaturalRolloutReference,
    PrefixBranchResponse,
    ProcessRunProfile,
)


def test_profile_requires_explicit_token_limits_and_mode_isolation(process_profile):
    assert process_profile.context_tokens == 64
    values = process_profile.to_dict()
    values.pop("context_tokens")
    with pytest.raises(ValueError, match="context_tokens"):
        ProcessRunProfile.from_mapping(values)
    with pytest.raises(ValueError, match="formal/toy isolation"):
        ProcessRunProfile.from_mapping({**process_profile.to_dict(), "mode": "formal"})


def test_formal_rollout_requires_exact_tokens_and_receipt(natural_rollout):
    values = natural_rollout.to_dict()
    values.update(
        {
            "completion_token_ids": None,
            "prompt_token_ids": None,
            "source_mode": "formal",
            "tokenization_receipt": None,
        }
    )
    with pytest.raises(ValueError, match="exact prompt and completion token IDs"):
        NaturalRolloutReference.from_mapping(values)
    values.update(
        {
            "completion_token_ids": [101, 102, 103],
            "prompt_token_ids": [11, 12, 13],
            "tokenization_receipt": None,
        }
    )
    with pytest.raises(ValueError, match="tokenizer verification receipt"):
        NaturalRolloutReference.from_mapping(values)


def test_canonical_jsonl_bytes_are_lf_and_windows_independent():
    rows = [{"b": "two", "a": "one"}, {"a": "line\ninside"}]
    content = canonical_jsonl_bytes(rows)
    assert b"\r\n" not in content
    assert content.endswith(b"\n")
    assert hashlib.sha256(content).hexdigest() == hashlib.sha256(
        b'{"a":"one","b":"two"}\n{"a":"line\\ninside"}\n'
    ).hexdigest()


def test_checkpoint_validation_uses_committed_contract(tmp_path: Path):
    checkpoint = tmp_path / "ckpt"
    (checkpoint / "model").mkdir(parents=True)
    (checkpoint / "model" / "weights.bin").write_bytes(b"weights")
    commit_checkpoint(
        checkpoint,
        global_step=31,
        required_files=["model/weights.bin"],
        metadata={"lineage": "qwen25-15k"},
    )
    digest = checkpoint_manifest_hash_if_committed(str(checkpoint))
    assert digest is not None and len(digest) == 64


def test_intervention_family_requires_exact_prefix_boundary(natural_rollout, aru_candidate):
    region = deterministic_candidate_regions(
        [natural_rollout],
        selection_policy_id="deterministic-sparse-token-region-v1",
        split="discovery",
    )[0]
    interventions = prepare_toy_interventions(
        region,
        aru_candidate,
        prompt_token_ids=tuple(natural_rollout.prompt_token_ids or ()),
        completion_prefix_token_ids=(),
        original_unit_token_ids=tuple(natural_rollout.completion_token_ids or ()),
    )
    delete = next(item for item in interventions if item.kind == "delete")
    original = next(item for item in interventions if item.kind == "original")
    no_op = next(item for item in interventions if item.kind == "no_op_control")
    assert {item.kind for item in interventions} == {
        "corrupt",
        "delete",
        "no_op_control",
        "original",
        "paraphrase",
        "repair",
        "unrelated_unit_control",
    }
    assert {
        item.prompt_token_ids + item.completion_prefix_token_ids for item in interventions
    } == {tuple(natural_rollout.prompt_token_ids or ())}
    assert delete.replacement_unit_token_ids == ()
    assert no_op.replacement_unit_token_ids == original.replacement_unit_token_ids
    assert no_op.replacement_unit_token_ids == no_op.original_unit_token_ids
    assert all(
        item.semantic_validation_status == "claimed"
        for item in interventions
        if item.kind in {"paraphrase", "repair"}
    )
    bad = make_intervention(
        intervention_id="bad",
        aru_id=aru_candidate.aru_id,
        kind="delete",
        prompt_token_ids=(1,),
        completion_prefix_token_ids=(),
        original_unit_token_ids=(2,),
        replacement_unit_token_ids=(),
        replacement_text="",
        semantic_intent="bad boundary",
        annotation_provenance="test",
    )
    with pytest.raises(ValueError, match="candidate unit boundary"):
        from vibethinker_experiments.process_observation.interventions import (
            validate_intervention_family,
        )

        validate_intervention_family(region, [bad])


def test_intervention_missing_data_and_cross_aru_unrelated_controls_are_rejected(
    natural_rollout, aru_candidate
):
    with pytest.raises(ValueError, match="missing required fields"):
        InterventionSpec.from_mapping(
            {
                "intervention_id": "missing",
                "aru_id": aru_candidate.aru_id,
                "kind": "delete",
            }
        )
    region = deterministic_candidate_regions(
        [natural_rollout],
        selection_policy_id="deterministic-sparse-token-region-v1",
        split="discovery",
    )[0]
    unrelated = make_intervention(
        intervention_id="bad-unrelated",
        aru_id=aru_candidate.aru_id,
        kind="unrelated_unit_control",
        prompt_token_ids=tuple(natural_rollout.prompt_token_ids or ()),
        completion_prefix_token_ids=(),
        original_unit_token_ids=(101,),
        replacement_unit_token_ids=(202,),
        replacement_text="unrelated",
        semantic_intent="control unrelated unit",
        paired_control_id="other-rollout-original",
        annotation_provenance="test",
    )
    with pytest.raises(ValueError, match="same-ARU provenance"):
        from vibethinker_experiments.process_observation.interventions import (
            validate_intervention_family,
        )

        validate_intervention_family(region, [unrelated])


def test_request_identity_excludes_runtime_locator(
    process_profile, checkpoint_reference, natural_rollout, aru_candidate
):
    region = deterministic_candidate_regions(
        [natural_rollout],
        selection_policy_id="deterministic-sparse-token-region-v1",
        split="confirmation",
    )[0]
    intervention = prepare_toy_interventions(
        region,
        aru_candidate,
        prompt_token_ids=tuple(natural_rollout.prompt_token_ids or ()),
        completion_prefix_token_ids=(),
        original_unit_token_ids=(101,),
    )[0]
    left = make_branch_request(
        intervention=intervention,
        checkpoint_reference=checkpoint_reference,
        prompt_id=natural_rollout.prompt_id,
        profile=process_profile,
        seed=process_profile.seeds[0],
        continuation_mode="short",
        transport_config_id="toy-transport-v1",
    )
    moved_checkpoint = checkpoint_reference.__class__.from_mapping(
        {**checkpoint_reference.to_dict(), "runtime_locator": "C:/private/local/checkpoint"}
    )
    right = make_branch_request(
        intervention=intervention,
        checkpoint_reference=moved_checkpoint,
        prompt_id=natural_rollout.prompt_id,
        profile=process_profile,
        seed=process_profile.seeds[0],
        continuation_mode="short",
        transport_config_id="toy-transport-v1",
    )
    assert left.request_sha256 == right.request_sha256


def test_response_identity_rejects_runtime_timestamps():
    value = {
        "branch_id": "b1",
        "completion_tokens": 1,
        "continuation_text": "x",
        "continuation_token_ids": [1],
        "finish_reason": "eos",
        "prompt_tokens": 3,
        "request_sha256": "a" * 64,
        "runtime_receipt": {"timestamp": "2026-07-22T00:00:00Z"},
        "transport_signature": "toy",
        "truncated": False,
    }
    value["response_sha256"] = canonical_sha256(
        {**value, "runtime_receipt": {"receipt_id": "deterministic"}}
    )
    with pytest.raises(ValueError, match="runtime timestamps"):
        PrefixBranchResponse.from_mapping(value)


def test_branch_request_preserves_prompt_special_tokens_and_assistant_prefix(
    process_profile, checkpoint_reference, aru_candidate
):
    prompt_tokens = (151643, 8948, 198, 151644, 872, 198, 42, 151645, 151644, 77091, 198)
    assistant_prefix = (32001, 32002)
    original = (101,)
    intervention = make_intervention(
        intervention_id="special",
        aru_id=aru_candidate.aru_id,
        kind="repair",
        prompt_token_ids=prompt_tokens,
        completion_prefix_token_ids=assistant_prefix,
        original_unit_token_ids=original,
        replacement_unit_token_ids=(777,),
        replacement_text="repair",
        semantic_intent="synthetic repair claim",
        annotation_provenance="test",
    )
    request = make_branch_request(
        intervention=intervention,
        checkpoint_reference=checkpoint_reference,
        prompt_id="prompt-with-template",
        profile=process_profile,
        seed=process_profile.seeds[0],
        continuation_mode="short",
        transport_config_id="toy-transport-v1",
    )
    assert request.prompt_token_ids == prompt_tokens
    assert request.completion_prefix_token_ids == assistant_prefix
    assert request.shared_prefix_token_ids == prompt_tokens + assistant_prefix
    assert request.input_token_ids == prompt_tokens + assistant_prefix + (777,)


def test_branch_request_context_budget_includes_prefix_intervention_and_generation(
    process_profile, checkpoint_reference, aru_candidate
):
    small = ProcessRunProfile.from_mapping(
        {
            **process_profile.to_dict(),
            "context_tokens": 5,
            "short_continuation_tokens": 2,
            "full_continuation_tokens": 2,
        }
    )
    intervention = make_intervention(
        intervention_id="too-long",
        aru_id=aru_candidate.aru_id,
        kind="corrupt",
        prompt_token_ids=(1, 2),
        completion_prefix_token_ids=(3,),
        original_unit_token_ids=(4,),
        replacement_unit_token_ids=(5,),
        replacement_text="bad",
        semantic_intent="context test",
        annotation_provenance="test",
    )
    with pytest.raises(ValueError, match="context_tokens must cover"):
        make_branch_request(
            intervention=intervention,
            checkpoint_reference=checkpoint_reference,
            prompt_id="p",
            profile=small,
            seed=small.seeds[0],
            continuation_mode="short",
            transport_config_id="toy-transport-v1",
        )


def test_formal_request_rejects_only_completion_prefix(process_profile, checkpoint_reference):
    formal_profile = ProcessRunProfile.from_mapping(
        {
            **process_profile.to_dict(),
            "checkpoint_ids": ["qwen25-15k-sft-epoch1"],
            "mode": "formal",
            "intervention_policy_id": "reviewed-intervention-v1",
            "outcome_evaluator_id": "reviewed-evaluator-v1",
            "profile_id": "qwen25-15k-formal-profile-v1",
        }
    )
    validated_checkpoint = CheckpointReference.from_mapping(
        {
            **checkpoint_reference.to_dict(),
            "checkpoint_id": "qwen25-15k-sft-epoch1",
            "checkpoint_receipt_reference": "receipt-qwen25-15k-sft-epoch1",
            "manifest_sha256": "a" * 64,
            "status": "validated",
            "tokenizer_reference": "qwen25-tokenizer",
            "tokenizer_sha256": "b" * 64,
        }
    )
    intervention = make_intervention(
        intervention_id="completion-prefix-only",
        aru_id="formal-aru",
        kind="repair",
        prompt_token_ids=(),
        completion_prefix_token_ids=(1, 2),
        original_unit_token_ids=(3,),
        replacement_unit_token_ids=(4,),
        replacement_text="repair",
        semantic_intent="formal rejection",
        annotation_provenance="test",
    )
    with pytest.raises(ValueError, match="formal branching requires exact prompt_token_ids"):
        make_branch_request(
            intervention=intervention,
            checkpoint_reference=validated_checkpoint,
            prompt_id="formal-prompt",
            profile=formal_profile,
            seed=formal_profile.seeds[0],
            continuation_mode="short",
            transport_config_id="private-reviewed-v1",
        )
