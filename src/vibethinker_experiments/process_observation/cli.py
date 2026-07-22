"""Explicit CLI for the process-observation pilot contracts."""

from __future__ import annotations

import argparse
from pathlib import Path

from vibethinker_experiments.evaluation.io import read_jsonl, write_immutable, write_json

from .artifacts import finalize_process_run, load_profile, load_records
from .audit import aggregate_raw_and_accepted, gradient_record_from_qwen25_reward
from .branching import (
    DeterministicToyPrefixBranchTransport,
    NetworkDisabledPrefixBranchTransport,
    branch_all,
    make_branch_request,
)
from .export import comparison_row, validate_split_leakage
from .identity import canonical_jsonl_bytes
from .interventions import prepare_toy_interventions
from .localization import deterministic_candidate_regions
from .models import CheckpointReference, NaturalRolloutReference
from .outcomes import DeterministicToyOutcomeEvaluator


def _write_rows(path: Path, rows: list[object]) -> None:
    write_immutable(path, canonical_jsonl_bytes([row.to_dict() for row in rows]))  # type: ignore[attr-defined]


def cmd_validate_profile(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    print(profile.to_dict())


def cmd_localize(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    rollouts = [
        NaturalRolloutReference.from_mapping(row) for row in read_jsonl(args.natural_rollouts)
    ]
    if {row.source_mode for row in rollouts} != {profile.mode}:
        raise SystemExit("formal/toy isolation violation in localize inputs")
    rows = deterministic_candidate_regions(
        rollouts,
        selection_policy_id=args.selection_policy_id,
        split=args.split,
        max_width_tokens=args.max_width_tokens,
    )
    _write_rows(args.output, rows)


def cmd_prepare_interventions(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    if profile.mode != "toy":
        raise SystemExit("formal intervention preparation requires a private reviewed adapter")
    rollouts = {
        row.rollout_id: row
        for row in (
            NaturalRolloutReference.from_mapping(item) for item in read_jsonl(args.natural_rollouts)
        )
    }
    regions = [row for row in load_records(args.candidate_regions, "candidate_region")]
    arus = [row for row in load_records(args.aru_candidates, "aru")]
    aru_by_region = {aru.region_id: aru for aru in arus}
    output = []
    for region in regions:
        rollout = rollouts[region.rollout_id]
        aru = aru_by_region[region.region_id]
        if rollout.prompt_token_ids is None or rollout.completion_token_ids is None:
            raise SystemExit("toy intervention preparation requires explicit fixture token IDs")
        start = region.span_start_token - rollout.prompt_tokens
        end = region.span_end_token - rollout.prompt_tokens
        if start < 0 or end < start:
            raise SystemExit("candidate region is outside the completion token range")
        completion_prefix = tuple(rollout.completion_token_ids[:start])
        original = tuple(rollout.completion_token_ids[start:end])
        if aru.source_span_token_ids is not None and tuple(aru.source_span_token_ids) != original:
            raise SystemExit("ARU source span token IDs do not match the rollout tokenization")
        output.extend(
            prepare_toy_interventions(
                region,
                aru,
                prompt_token_ids=tuple(rollout.prompt_token_ids),
                completion_prefix_token_ids=completion_prefix,
                original_unit_token_ids=original,
            )
        )
    _write_rows(args.output, output)


def cmd_branch(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    checkpoint = CheckpointReference.from_mapping(read_jsonl(args.checkpoint_reference)[0])
    interventions = [row for row in load_records(args.interventions, "intervention")]
    if args.transport == "toy":
        if profile.mode != "toy":
            raise SystemExit("formal mode cannot use toy transport")
        transport = DeterministicToyPrefixBranchTransport()
    else:
        transport = NetworkDisabledPrefixBranchTransport()
    requests = [
        make_branch_request(
            intervention=intervention,
            checkpoint_reference=checkpoint,
            prompt_id=args.prompt_id,
            profile=profile,
            seed=seed,
            continuation_mode=args.continuation_mode,
            transport_config_id=args.transport_config_id,
        )
        for seed in profile.seeds
        for intervention in interventions
    ]
    if args.requests_output:
        _write_rows(args.requests_output, requests)
    responses = branch_all(requests, transport=transport)
    _write_rows(args.output, responses)


def cmd_evaluate(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    if profile.mode != "toy" or args.evaluator != "toy":
        raise SystemExit("formal outcome evaluation requires an injected private evaluator")
    responses = {row.branch_id: row for row in load_records(args.branch_results, "branch_response")}
    interventions = {
        row.intervention_id: row for row in load_records(args.interventions, "intervention")
    }
    arus = {row.aru_id: row for row in load_records(args.aru_candidates, "aru")}
    evaluator = DeterministicToyOutcomeEvaluator()
    outcomes = []
    for response in responses.values():
        intervention_id = str(response.branch_id).rsplit("-short-seed", 1)[0].rsplit(
            "-full-seed", 1
        )[0]
        intervention = interventions[intervention_id]
        outcomes.append(
            evaluator.evaluate(
                prompt_record={"prompt_id": args.prompt_id},
                aru_candidate=arus[intervention.aru_id],
                intervention=intervention,
                branch_response=response,
            )
        )
    _write_rows(args.output, outcomes)


def cmd_audit_rewards(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.input)
    if args.qwen25_reward_fields:
        records = [
            gradient_record_from_qwen25_reward(
                row,
                checkpoint_id=args.checkpoint_id,
                training_step=int(row.get("training_step", args.training_step)),
                prompt_id=str(row.get("prompt_id", f"prompt-{index}")),
                group_id=str(row.get("group_id", "group-0")),
                rollout_id=str(row.get("rollout_id", f"rollout-{index}")),
                source_artifact_sha256=args.source_artifact_sha256,
            )
            for index, row in enumerate(rows)
        ]
    else:
        records = [row for row in load_records(args.input, "gradient")]
    _write_rows(args.output, records)
    write_json(args.report, aggregate_raw_and_accepted(records))


def cmd_finalize(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    marker = finalize_process_run(
        args.run_dir,
        profile=profile,
        natural_rollouts=load_records(args.natural_rollouts, "natural_rollout"),
        candidate_regions=load_records(args.candidate_regions, "candidate_region"),
        aru_candidates=load_records(args.aru_candidates, "aru"),
        interventions=load_records(args.interventions, "intervention"),
        branch_requests=load_records(args.branch_requests, "branch_request"),
        branch_responses=load_records(args.branch_results, "branch_response"),
        process_outcomes=load_records(args.process_outcomes, "outcome"),
        gradient_provenance=(
            None
            if args.gradient_provenance is None
            else load_records(args.gradient_provenance, "gradient")
        ),
        expected_branch_count=args.expected_branch_count,
    )
    print(marker)


def cmd_export_comparison(args: argparse.Namespace) -> None:
    outcomes = read_jsonl(args.process_outcomes)
    rows = [
        comparison_row(
            granularity=args.granularity,
            branch_id=row["branch_id"],
            prompt_id=args.prompt_id,
            checkpoint_id=args.checkpoint_id,
            intervention_family=str(row["intervention_id"]).split("-")[0],
            semantic_problem_family=args.semantic_problem_family,
            surface_paraphrase_family=args.surface_paraphrase_family,
            split=args.split,
            features={"intervention_id": row["intervention_id"]},
            target={"final_correctness": row["final_correctness"]},
            annotation_cost=None,
        )
        for row in outcomes
    ]
    validate_split_leakage(rows)
    write_immutable(args.output, canonical_jsonl_bytes(rows))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-profile")
    validate.add_argument("--profile", type=Path, required=True)
    validate.set_defaults(func=cmd_validate_profile)

    localize = sub.add_parser("localize")
    localize.add_argument("--profile", type=Path, required=True)
    localize.add_argument("--natural-rollouts", type=Path, required=True)
    localize.add_argument("--output", type=Path, required=True)
    localize.add_argument("--selection-policy-id", required=True)
    localize.add_argument("--split", choices=["discovery", "confirmation"], required=True)
    localize.add_argument("--max-width-tokens", type=int, default=3)
    localize.set_defaults(func=cmd_localize)

    prep = sub.add_parser("prepare-interventions")
    prep.add_argument("--profile", type=Path, required=True)
    prep.add_argument("--natural-rollouts", type=Path, required=True)
    prep.add_argument("--candidate-regions", type=Path, required=True)
    prep.add_argument("--aru-candidates", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.set_defaults(func=cmd_prepare_interventions)

    branch = sub.add_parser("branch")
    branch.add_argument("--profile", type=Path, required=True)
    branch.add_argument("--checkpoint-reference", type=Path, required=True)
    branch.add_argument("--interventions", type=Path, required=True)
    branch.add_argument("--prompt-id", required=True)
    branch.add_argument("--requests-output", type=Path)
    branch.add_argument("--output", type=Path, required=True)
    branch.add_argument("--transport", choices=["disabled", "toy"], default="disabled")
    branch.add_argument("--transport-config-id", required=True)
    branch.add_argument("--continuation-mode", choices=["short", "full"], required=True)
    branch.set_defaults(func=cmd_branch)

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--profile", type=Path, required=True)
    evaluate.add_argument("--branch-results", type=Path, required=True)
    evaluate.add_argument("--interventions", type=Path, required=True)
    evaluate.add_argument("--aru-candidates", type=Path, required=True)
    evaluate.add_argument("--prompt-id", required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--evaluator", choices=["toy"], required=True)
    evaluate.set_defaults(func=cmd_evaluate)

    audit = sub.add_parser("audit-rewards")
    audit.add_argument("--input", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    audit.add_argument("--report", type=Path, required=True)
    audit.add_argument("--qwen25-reward-fields", action="store_true")
    audit.add_argument("--checkpoint-id", default="qwen25-15k-sft-epoch1")
    audit.add_argument("--training-step", type=int, default=0)
    audit.add_argument("--source-artifact-sha256", default="0" * 64)
    audit.set_defaults(func=cmd_audit_rewards)

    finalize = sub.add_parser("finalize")
    finalize.add_argument("--profile", type=Path, required=True)
    finalize.add_argument("--run-dir", type=Path, required=True)
    finalize.add_argument("--natural-rollouts", type=Path, required=True)
    finalize.add_argument("--candidate-regions", type=Path, required=True)
    finalize.add_argument("--aru-candidates", type=Path, required=True)
    finalize.add_argument("--interventions", type=Path, required=True)
    finalize.add_argument("--branch-requests", type=Path, required=True)
    finalize.add_argument("--branch-results", type=Path, required=True)
    finalize.add_argument("--process-outcomes", type=Path, required=True)
    finalize.add_argument("--gradient-provenance", type=Path)
    finalize.add_argument("--expected-branch-count", type=int)
    finalize.set_defaults(func=cmd_finalize)

    export = sub.add_parser("export-comparison")
    export.add_argument("--process-outcomes", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument(
        "--granularity",
        choices=["token_window", "sentence", "macro_step", "aru"],
        required=True,
    )
    export.add_argument("--prompt-id", required=True)
    export.add_argument("--checkpoint-id", required=True)
    export.add_argument("--semantic-problem-family", required=True)
    export.add_argument("--surface-paraphrase-family", required=True)
    export.add_argument("--split", choices=["train", "heldout"], required=True)
    export.set_defaults(func=cmd_export_comparison)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
