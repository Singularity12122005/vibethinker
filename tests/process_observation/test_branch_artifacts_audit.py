from __future__ import annotations

import pytest

from vibethinker_experiments.evaluation.io import read_json
from vibethinker_experiments.process_observation.artifacts import (
    FINALIZED,
    ProcessArtifactError,
    finalize_process_run,
)
from vibethinker_experiments.process_observation.audit import (
    aggregate_raw_and_accepted,
    gradient_record_from_qwen25_reward,
)
from vibethinker_experiments.process_observation.branching import (
    DeterministicToyPrefixBranchTransport,
    NetworkDisabledPrefixBranchTransport,
    branch_all,
    make_branch_request,
)
from vibethinker_experiments.process_observation.interventions import prepare_toy_interventions
from vibethinker_experiments.process_observation.localization import deterministic_candidate_regions
from vibethinker_experiments.process_observation.outcomes import DeterministicToyOutcomeEvaluator


def _toy_pipeline(process_profile, checkpoint_reference, natural_rollout, aru_candidate):
    region = deterministic_candidate_regions(
        [natural_rollout],
        selection_policy_id=process_profile.candidate_selection_policy_id,
        split="discovery",
    )[0]
    interventions = prepare_toy_interventions(
        region,
        aru_candidate,
        prompt_token_ids=tuple(natural_rollout.prompt_token_ids or ()),
        completion_prefix_token_ids=(),
        original_unit_token_ids=tuple(natural_rollout.completion_token_ids or ()),
    )
    requests = [
        make_branch_request(
            intervention=intervention,
            checkpoint_reference=checkpoint_reference,
            prompt_id=natural_rollout.prompt_id,
            profile=process_profile,
            seed=process_profile.seeds[0],
            continuation_mode="short",
            transport_config_id="deterministic-toy-prefix-branch-v1",
        )
        for intervention in interventions
    ]
    responses = branch_all(requests, transport=DeterministicToyPrefixBranchTransport())
    evaluator = DeterministicToyOutcomeEvaluator()
    arus = {aru_candidate.aru_id: aru_candidate}
    outcomes = [
        evaluator.evaluate(
            prompt_record={"prompt_id": natural_rollout.prompt_id},
            aru_candidate=arus[str(response.branch_id).split("-original", 1)[0]]
            if "-original" in response.branch_id
            else aru_candidate,
            intervention=next(
                item
                for item in interventions
                if response.branch_id.startswith(item.intervention_id)
            ),
            branch_response=response,
        )
        for response in responses
    ]
    return [region], interventions, requests, responses, outcomes


def test_network_disabled_default(
    process_profile, checkpoint_reference, natural_rollout, aru_candidate
):
    region = deterministic_candidate_regions(
        [natural_rollout],
        selection_policy_id=process_profile.candidate_selection_policy_id,
        split="discovery",
    )[0]
    intervention = prepare_toy_interventions(
        region,
        aru_candidate,
        prompt_token_ids=tuple(natural_rollout.prompt_token_ids or ()),
        completion_prefix_token_ids=(),
        original_unit_token_ids=(101,),
    )[0]
    request = make_branch_request(
        intervention=intervention,
        checkpoint_reference=checkpoint_reference,
        prompt_id=natural_rollout.prompt_id,
        profile=process_profile,
        seed=process_profile.seeds[0],
        continuation_mode="short",
        transport_config_id="disabled",
    )
    with pytest.raises(RuntimeError, match="not configured"):
        NetworkDisabledPrefixBranchTransport().branch(request)


def test_toy_branch_request_and_response_hashes_are_distinct(
    process_profile, checkpoint_reference, natural_rollout, aru_candidate
):
    region, interventions, requests, responses, _ = _toy_pipeline(
        process_profile, checkpoint_reference, natural_rollout, aru_candidate
    )
    assert region[0].split == "discovery"
    assert requests[0].request_sha256 != responses[0].response_sha256
    assert branch_all(requests, transport=DeterministicToyPrefixBranchTransport()) == responses
    too_small = process_profile.__class__.from_mapping(
        {
            **process_profile.to_dict(),
            "context_tokens": 4,
            "full_continuation_tokens": 4,
            "short_continuation_tokens": 4,
        }
    )
    with pytest.raises(ValueError, match="context_tokens must cover"):
        make_branch_request(
            intervention=interventions[0],
            checkpoint_reference=checkpoint_reference,
            prompt_id=natural_rollout.prompt_id,
            profile=too_small,
            seed=too_small.seeds[0],
            continuation_mode="short",
            transport_config_id="deterministic-toy-prefix-branch-v1",
        )


def test_artifact_finalization_is_idempotent_and_detects_tampering(
    tmp_path, process_profile, checkpoint_reference, natural_rollout, aru_candidate
):
    regions, interventions, requests, responses, outcomes = _toy_pipeline(
        process_profile, checkpoint_reference, natural_rollout, aru_candidate
    )
    marker = finalize_process_run(
        tmp_path,
        profile=process_profile,
        natural_rollouts=[natural_rollout],
        candidate_regions=regions,
        aru_candidates=[aru_candidate],
        interventions=interventions,
        branch_requests=requests,
        branch_responses=responses,
        process_outcomes=outcomes,
        expected_branch_count=len(requests),
    )
    assert marker == finalize_process_run(
        tmp_path,
        profile=process_profile,
        natural_rollouts=[natural_rollout],
        candidate_regions=regions,
        aru_candidates=[aru_candidate],
        interventions=interventions,
        branch_requests=requests,
        branch_responses=responses,
        process_outcomes=outcomes,
        expected_branch_count=len(requests),
    )
    assert read_json(tmp_path / "report.json")["synthetic_toy"] is True
    with (tmp_path / "branch_results.jsonl").open("ab") as handle:
        handle.write(b"{}\n")
    with pytest.raises(ProcessArtifactError, match="changed"):
        finalize_process_run(
            tmp_path,
            profile=process_profile,
            natural_rollouts=[natural_rollout],
            candidate_regions=regions,
            aru_candidates=[aru_candidate],
            interventions=interventions,
            branch_requests=requests,
            branch_responses=responses,
            process_outcomes=outcomes,
        )
    assert (tmp_path / FINALIZED).is_file()


def test_missing_branch_or_outcome_blocks_finalization(
    tmp_path, process_profile, checkpoint_reference, natural_rollout, aru_candidate
):
    regions, interventions, requests, responses, outcomes = _toy_pipeline(
        process_profile, checkpoint_reference, natural_rollout, aru_candidate
    )
    with pytest.raises(ProcessArtifactError, match="response"):
        finalize_process_run(
            tmp_path / "missing-response",
            profile=process_profile,
            natural_rollouts=[natural_rollout],
            candidate_regions=regions,
            aru_candidates=[aru_candidate],
            interventions=interventions,
            branch_requests=requests,
            branch_responses=responses[:-1],
            process_outcomes=outcomes,
        )
    with pytest.raises(ProcessArtifactError, match="outcome"):
        finalize_process_run(
            tmp_path / "missing-outcome",
            profile=process_profile,
            natural_rollouts=[natural_rollout],
            candidate_regions=regions,
            aru_candidates=[aru_candidate],
            interventions=interventions,
            branch_requests=requests,
            branch_responses=responses,
            process_outcomes=outcomes[:-1],
        )


def test_reward_audit_preserves_unknown_groups_and_qwen25_fields():
    digest = "a" * 64
    good = gradient_record_from_qwen25_reward(
        {
            "answer_correct": 1.0,
            "base_reward": 1.0,
            "binary_success": 1.0,
            "completion_tokens": 10,
            "format_ok": 1.0,
            "format_progress": 0.3,
            "overlong_multiplier": 1.0,
            "score": 1.0,
            "truncated": 0.0,
        },
        checkpoint_id="qwen25-15k-sft-epoch1",
        training_step=31,
        prompt_id="p1",
        group_id="g1",
        rollout_id="r1",
        source_artifact_sha256=digest,
        accepted_for_update="true",
    )
    unknown = good.__class__.from_mapping(
        {
            **good.to_dict(),
            "accepted_for_update": "unknown",
            "binary_success": "unknown",
            "rollout_id": "r2",
        }
    )
    summary = aggregate_raw_and_accepted([good, unknown])
    assert summary["raw"]["unknown_group_fraction"] == 1.0
    assert summary["raw"]["acceptance_rate"] is None
    assert summary["accepted"]["record_count"] == 1
