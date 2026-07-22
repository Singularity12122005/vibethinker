from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tests.process_observation.conftest import REPOSITORY
from vibethinker_experiments.evaluation.io import read_jsonl
from vibethinker_experiments.process_observation.decisions import (
    ARUDecisionThresholds,
    decide_aru,
)
from vibethinker_experiments.process_observation.export import (
    comparison_row,
    validate_split_leakage,
)
from vibethinker_experiments.process_observation.identity import canonical_jsonl_bytes
from vibethinker_experiments.process_observation.interventions import make_intervention


def test_decision_prefers_insufficient_evidence_for_small_samples():
    rows = [{"paired_unit_id": "u1", "kind": "original", "final_correctness": "true"}]
    decision = decide_aru(rows, thresholds=ARUDecisionThresholds(min_paired_units=2))
    assert decision["decision"] == "insufficient_evidence"


def test_decision_accepts_only_with_controls_and_paired_effects():
    observations = []
    for index in range(3):
        observations.extend(
            [
                {"paired_unit_id": f"u{index}", "kind": "original", "final_correctness": "true"},
                {"paired_unit_id": f"u{index}", "kind": "paraphrase", "final_correctness": "true"},
                {"paired_unit_id": f"u{index}", "kind": "corrupt", "final_correctness": "false"},
                {"paired_unit_id": f"u{index}", "kind": "delete", "final_correctness": "false"},
                {
                    "paired_unit_id": f"u{index}",
                    "kind": "no_op_control",
                    "final_correctness": "true",
                },
                {
                    "paired_unit_id": f"u{index}",
                    "kind": "unrelated_unit_control",
                    "final_correctness": "true",
                },
            ]
        )
    assert decide_aru(observations)["decision"] == "accept"


def test_export_rows_detect_split_leakage():
    row = comparison_row(
        granularity="aru",
        branch_id="b1",
        prompt_id="p1",
        checkpoint_id="c1",
        intervention_family="f1",
        semantic_problem_family="family",
        surface_paraphrase_family="surface",
        split="train",
        features={"x": 1},
        target={"final_correctness": "true"},
    )
    leaked = {**row, "branch_id": "b2", "split": "heldout"}
    with pytest.raises(ValueError, match="split leakage"):
        validate_split_leakage([row, leaked])


def run_cli(*args, cwd=REPOSITORY):
    return subprocess.run(
        [sys.executable, "-m", "vibethinker_experiments.process_observation.cli", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


def run_cli_fail(*args, cwd=REPOSITORY):
    return subprocess.run(
        [sys.executable, "-m", "vibethinker_experiments.process_observation.cli", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def _write_jsonl(path, rows):
    path.write_bytes(canonical_jsonl_bytes(rows))


def _formal_profile(path):
    path.write_text(
        "\n".join(
            [
                "profile_id: qwen25-15k-formal-profile-v1",
                "schema_version: 1",
                "mode: formal",
                "context_tokens: 64",
                "short_continuation_tokens: 8",
                "full_continuation_tokens: 16",
                "temperature: 0.0",
                "top_p: 1.0",
                "seeds:",
                "  - 20260722",
                "checkpoint_ids:",
                "  - qwen25-15k-sft-epoch1",
                "outcome_evaluator_id: reviewed-evaluator-v1",
                "candidate_selection_policy_id: deterministic-sparse-token-region-v1",
                "intervention_policy_id: reviewed-intervention-v1",
                "artifact_format_version: 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _formal_checkpoint(*, receipt=True, validated=True):
    return {
        "checkpoint_id": "qwen25-15k-sft-epoch1",
        "checkpoint_receipt_reference": "receipt-qwen25-15k-sft-epoch1" if receipt else None,
        "lineage": "qwen25-15k",
        "manifest_sha256": "a" * 64 if validated else None,
        "runtime_locator": None,
        "stage": "sft",
        "status": "validated" if validated else "unverified",
        "tokenizer_reference": "qwen25-tokenizer",
        "tokenizer_sha256": "b" * 64 if validated else None,
    }


def _formal_intervention(*, prompt_token_ids=(11, 12, 13)):
    return make_intervention(
        intervention_id="formal-aru-001-repair",
        aru_id="formal-aru-001",
        kind="repair",
        prompt_token_ids=tuple(prompt_token_ids),
        completion_prefix_token_ids=(101,),
        original_unit_token_ids=(102,),
        replacement_unit_token_ids=(103,),
        replacement_text="repair",
        semantic_intent="formal fail-closed test",
        annotation_provenance="unit-test",
    ).to_dict()


def test_cli_toy_end_to_end_pipeline(tmp_path):
    profile = REPOSITORY / "configs/process_observation/toy-qwen25-15k.yaml"
    natural = REPOSITORY / "data/process_observation/toy/natural_rollouts.jsonl"
    checkpoint = REPOSITORY / "data/process_observation/toy/checkpoint_reference.jsonl"
    arus = REPOSITORY / "data/process_observation/toy/aru_candidates.jsonl"
    regions = tmp_path / "candidate_regions.jsonl"
    interventions = tmp_path / "interventions.jsonl"
    requests = tmp_path / "branch_requests.jsonl"
    results = tmp_path / "branch_results.jsonl"
    outcomes = tmp_path / "process_outcomes.jsonl"
    run_dir = tmp_path / "finalized"

    run_cli(
        "localize",
        "--profile",
        str(profile),
        "--natural-rollouts",
        str(natural),
        "--output",
        str(regions),
        "--selection-policy-id",
        "deterministic-sparse-token-region-v1",
        "--split",
        "discovery",
    )
    run_cli(
        "prepare-interventions",
        "--profile",
        str(profile),
        "--natural-rollouts",
        str(natural),
        "--candidate-regions",
        str(regions),
        "--aru-candidates",
        str(arus),
        "--output",
        str(interventions),
    )
    run_cli(
        "branch",
        "--profile",
        str(profile),
        "--checkpoint-reference",
        str(checkpoint),
        "--interventions",
        str(interventions),
        "--prompt-id",
        "toy-aru-addition-001",
        "--requests-output",
        str(requests),
        "--output",
        str(results),
        "--transport",
        "toy",
        "--transport-config-id",
        "deterministic-toy-prefix-branch-v1",
        "--continuation-mode",
        "short",
    )
    run_cli(
        "evaluate",
        "--profile",
        str(profile),
        "--branch-results",
        str(results),
        "--interventions",
        str(interventions),
        "--aru-candidates",
        str(arus),
        "--prompt-id",
        "toy-aru-addition-001",
        "--output",
        str(outcomes),
        "--evaluator",
        "toy",
    )
    run_cli(
        "finalize",
        "--profile",
        str(profile),
        "--run-dir",
        str(run_dir),
        "--natural-rollouts",
        str(natural),
        "--candidate-regions",
        str(regions),
        "--aru-candidates",
        str(arus),
        "--interventions",
        str(interventions),
        "--branch-requests",
        str(requests),
        "--branch-results",
        str(results),
        "--process-outcomes",
        str(outcomes),
        "--expected-branch-count",
        "7",
    )
    assert len(read_jsonl(run_dir / "branch_results.jsonl")) == 7
    assert (run_dir / "FINALIZED.json").is_file()


def test_cli_formal_mode_rejects_toy_transport(tmp_path):
    profile = _formal_profile(tmp_path / "formal.yaml")
    checkpoint = tmp_path / "checkpoint.jsonl"
    interventions = tmp_path / "interventions.jsonl"
    _write_jsonl(checkpoint, [_formal_checkpoint()])
    _write_jsonl(interventions, [_formal_intervention()])
    result = run_cli_fail(
        "branch",
        "--profile",
        str(profile),
        "--checkpoint-reference",
        str(checkpoint),
        "--interventions",
        str(interventions),
        "--prompt-id",
        "formal-prompt",
        "--output",
        str(tmp_path / "branch_results.jsonl"),
        "--transport",
        "toy",
        "--transport-config-id",
        "deterministic-toy-prefix-branch-v1",
        "--continuation-mode",
        "short",
    )
    assert result.returncode != 0
    assert "formal mode cannot use toy transport" in result.stderr


def test_cli_formal_localize_rejects_toy_rollout(tmp_path):
    result = run_cli_fail(
        "localize",
        "--profile",
        str(_formal_profile(tmp_path / "formal.yaml")),
        "--natural-rollouts",
        str(REPOSITORY / "data/process_observation/toy/natural_rollouts.jsonl"),
        "--output",
        str(tmp_path / "candidate_regions.jsonl"),
        "--selection-policy-id",
        "deterministic-sparse-token-region-v1",
        "--split",
        "discovery",
    )
    assert result.returncode != 0
    assert "formal/toy isolation" in result.stderr


def test_cli_formal_localize_rejects_unverified_tokenization(tmp_path):
    natural = tmp_path / "formal_rollouts.jsonl"
    row = read_jsonl(REPOSITORY / "data/process_observation/toy/natural_rollouts.jsonl")[0]
    row.update(
        {
            "checkpoint_id": "qwen25-15k-sft-epoch1",
            "source_mode": "formal",
            "tokenization_receipt": None,
        }
    )
    natural.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    result = run_cli_fail(
        "localize",
        "--profile",
        str(_formal_profile(tmp_path / "formal.yaml")),
        "--natural-rollouts",
        str(natural),
        "--output",
        str(tmp_path / "candidate_regions.jsonl"),
        "--selection-policy-id",
        "deterministic-sparse-token-region-v1",
        "--split",
        "discovery",
    )
    assert result.returncode != 0
    assert "tokenizer verification receipt" in result.stderr


def test_cli_formal_branch_rejects_absent_exact_prompt_tokens(tmp_path):
    profile = _formal_profile(tmp_path / "formal.yaml")
    checkpoint = tmp_path / "checkpoint.jsonl"
    interventions = tmp_path / "interventions.jsonl"
    _write_jsonl(checkpoint, [_formal_checkpoint()])
    _write_jsonl(interventions, [_formal_intervention(prompt_token_ids=())])
    result = run_cli_fail(
        "branch",
        "--profile",
        str(profile),
        "--checkpoint-reference",
        str(checkpoint),
        "--interventions",
        str(interventions),
        "--prompt-id",
        "formal-prompt",
        "--output",
        str(tmp_path / "branch_results.jsonl"),
        "--transport",
        "disabled",
        "--transport-config-id",
        "private-reviewed-v1",
        "--continuation-mode",
        "short",
    )
    assert result.returncode != 0
    assert "formal branching requires exact prompt_token_ids" in result.stderr


def test_cli_formal_branch_rejects_missing_checkpoint_receipt(tmp_path):
    profile = _formal_profile(tmp_path / "formal.yaml")
    checkpoint = tmp_path / "checkpoint.jsonl"
    interventions = tmp_path / "interventions.jsonl"
    _write_jsonl(checkpoint, [_formal_checkpoint(receipt=False, validated=False)])
    _write_jsonl(interventions, [_formal_intervention()])
    result = run_cli_fail(
        "branch",
        "--profile",
        str(profile),
        "--checkpoint-reference",
        str(checkpoint),
        "--interventions",
        str(interventions),
        "--prompt-id",
        "formal-prompt",
        "--output",
        str(tmp_path / "branch_results.jsonl"),
        "--transport",
        "disabled",
        "--transport-config-id",
        "private-reviewed-v1",
        "--continuation-mode",
        "short",
    )
    assert result.returncode != 0
    assert "validated checkpoint receipt" in result.stderr


def test_cli_formal_evaluate_rejects_missing_evaluator_provenance(tmp_path):
    result = run_cli_fail(
        "evaluate",
        "--profile",
        str(_formal_profile(tmp_path / "formal.yaml")),
        "--branch-results",
        str(tmp_path / "branch_results.jsonl"),
        "--interventions",
        str(tmp_path / "interventions.jsonl"),
        "--aru-candidates",
        str(tmp_path / "arus.jsonl"),
        "--prompt-id",
        "formal-prompt",
        "--output",
        str(tmp_path / "process_outcomes.jsonl"),
        "--evaluator",
        "toy",
    )
    assert result.returncode != 0
    assert "formal outcome evaluation requires an injected private evaluator" in result.stderr


def test_cli_disabled_transport_cannot_be_used_as_generated_response(tmp_path):
    checkpoint = REPOSITORY / "data/process_observation/toy/checkpoint_reference.jsonl"
    profile = REPOSITORY / "configs/process_observation/toy-qwen25-15k.yaml"
    interventions = tmp_path / "interventions.jsonl"
    _write_jsonl(interventions, [_formal_intervention(prompt_token_ids=(11, 12, 13))])
    output = tmp_path / "branch_results.jsonl"
    result = run_cli_fail(
        "branch",
        "--profile",
        str(profile),
        "--checkpoint-reference",
        str(checkpoint),
        "--interventions",
        str(interventions),
        "--prompt-id",
        "toy-aru-addition-001",
        "--output",
        str(output),
        "--transport",
        "disabled",
        "--transport-config-id",
        "disabled",
        "--continuation-mode",
        "short",
    )
    assert result.returncode != 0
    assert "transport is not configured" in result.stderr
    assert not output.exists()
