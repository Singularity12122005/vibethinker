"""Immutable artifact pipeline for process-observation runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibethinker_experiments.evaluation.io import (
    index_unique,
    read_json,
    read_jsonl,
    sha256_file,
    write_immutable,
)

from .audit import aggregate_raw_and_accepted
from .identity import canonical_json_bytes, canonical_jsonl_bytes, canonical_sha256
from .models import (
    ARUCandidate,
    CandidateRegion,
    GradientProvenanceRecord,
    InterventionSpec,
    NaturalRolloutReference,
    PrefixBranchRequest,
    PrefixBranchResponse,
    ProcessOutcome,
    ProcessRunProfile,
)

RUN_MANIFEST = "run_manifest.json"
NATURAL_ROLLOUTS = "natural_rollouts.jsonl"
CANDIDATE_REGIONS = "candidate_regions.jsonl"
ARU_CANDIDATES = "aru_candidates.jsonl"
INTERVENTIONS = "interventions.jsonl"
BRANCH_REQUESTS = "branch_requests.jsonl"
BRANCH_RESULTS = "branch_results.jsonl"
PROCESS_OUTCOMES = "process_outcomes.jsonl"
GRADIENT_PROVENANCE = "gradient_provenance.jsonl"
REPORT = "report.json"
FINALIZED = "FINALIZED.json"


class ProcessArtifactError(ValueError):
    pass


def load_profile(path: str | Path) -> ProcessRunProfile:
    import yaml

    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("process profile must be a YAML object")
    return ProcessRunProfile.from_mapping(value)


def _rows(records: list[Any]) -> list[dict[str, Any]]:
    return [record.to_dict() for record in records]


def _index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    try:
        return index_unique(rows, key)
    except ValueError as exc:
        raise ProcessArtifactError(str(exc)) from exc


def _write_json(root: Path, filename: str, value: dict[str, Any]) -> str:
    return write_immutable(root / filename, canonical_json_bytes(value))


def _write_jsonl(root: Path, filename: str, rows: list[dict[str, Any]], key: str) -> str:
    ordered = sorted(rows, key=lambda row: str(row[key]))
    return write_immutable(root / filename, canonical_jsonl_bytes(ordered))


def _verify_marker(root: Path) -> dict[str, Any]:
    marker = read_json(root / FINALIZED)
    if marker.get("status") != "FINALIZED":
        raise ProcessArtifactError("invalid FINALIZED status")
    hashes = marker.get("artifact_sha256")
    if not isinstance(hashes, dict):
        raise ProcessArtifactError("FINALIZED marker missing artifact hashes")
    for filename, expected in hashes.items():
        path = root / filename
        if not path.is_file() or sha256_file(path) != expected:
            raise ProcessArtifactError(f"finalized artifact changed: {filename}")
    identity = {
        "artifact_sha256": hashes,
        "profile_id": marker.get("profile_id"),
        "schema_version": marker.get("schema_version"),
        "status": marker.get("status"),
    }
    if marker.get("finalization_sha256") != canonical_sha256(identity):
        raise ProcessArtifactError("FINALIZED identity hash mismatch")
    return marker


def _validate_graph(
    *,
    profile: ProcessRunProfile,
    natural_rollouts: list[NaturalRolloutReference],
    candidate_regions: list[CandidateRegion],
    aru_candidates: list[ARUCandidate],
    interventions: list[InterventionSpec],
    branch_requests: list[PrefixBranchRequest],
    branch_responses: list[PrefixBranchResponse],
    process_outcomes: list[ProcessOutcome],
    expected_branch_count: int | None,
) -> None:
    if expected_branch_count is not None and expected_branch_count != len(branch_requests):
        raise ProcessArtifactError("declared branch count does not match branch requests")
    rollouts = _index(_rows(natural_rollouts), "rollout_id")
    regions = _index(_rows(candidate_regions), "region_id")
    arus = _index(_rows(aru_candidates), "aru_id")
    intervention_index = _index(_rows(interventions), "intervention_id")
    requests = _index(_rows(branch_requests), "branch_id")
    responses = _index(_rows(branch_responses), "branch_id")
    outcomes = _index(_rows(process_outcomes), "branch_id")
    if {row.source_mode for row in natural_rollouts} != {profile.mode}:
        raise ProcessArtifactError("formal/toy isolation violation in natural rollouts")
    for rollout in natural_rollouts:
        if rollout.checkpoint_id not in profile.checkpoint_ids:
            raise ProcessArtifactError(
                f"rollout uses undeclared checkpoint: {rollout.checkpoint_id}"
            )
    for region in candidate_regions:
        if region.rollout_id not in rollouts:
            raise ProcessArtifactError(f"region references missing rollout: {region.rollout_id}")
    for aru in aru_candidates:
        if aru.region_id not in regions:
            raise ProcessArtifactError(f"ARU references missing region: {aru.region_id}")
    for intervention in interventions:
        if intervention.aru_id not in arus:
            raise ProcessArtifactError(
                f"intervention references missing ARU: {intervention.aru_id}"
            )
    if set(responses) != set(requests):
        raise ProcessArtifactError("every declared branch must have exactly one response")
    if set(outcomes) != set(requests):
        raise ProcessArtifactError("every declared branch must have exactly one outcome")
    for branch_id, response in responses.items():
        request = requests[branch_id]
        if response["request_sha256"] != request["request_sha256"]:
            raise ProcessArtifactError(f"{branch_id}: response targets a different request")
    for branch_id, outcome in outcomes.items():
        response = responses[branch_id]
        if outcome["source_response_sha256"] != response["response_sha256"]:
            raise ProcessArtifactError(f"{branch_id}: outcome targets a different response")
        if outcome["intervention_id"] not in intervention_index:
            raise ProcessArtifactError(f"{branch_id}: outcome references missing intervention")


def finalize_process_run(
    run_dir: str | Path,
    *,
    profile: ProcessRunProfile,
    natural_rollouts: list[NaturalRolloutReference],
    candidate_regions: list[CandidateRegion],
    aru_candidates: list[ARUCandidate],
    interventions: list[InterventionSpec],
    branch_requests: list[PrefixBranchRequest],
    branch_responses: list[PrefixBranchResponse],
    process_outcomes: list[ProcessOutcome],
    gradient_provenance: list[GradientProvenanceRecord] | None = None,
    expected_branch_count: int | None = None,
) -> dict[str, Any]:
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    if (root / FINALIZED).is_file():
        return _verify_marker(root)
    _validate_graph(
        profile=profile,
        natural_rollouts=natural_rollouts,
        candidate_regions=candidate_regions,
        aru_candidates=aru_candidates,
        interventions=interventions,
        branch_requests=branch_requests,
        branch_responses=branch_responses,
        process_outcomes=process_outcomes,
        expected_branch_count=expected_branch_count,
    )
    artifact_hashes: dict[str, str] = {}
    manifest = {
        "artifact_format_version": profile.artifact_format_version,
        "mode": profile.mode,
        "profile": profile.to_dict(),
        "schema_version": 1,
    }
    artifact_hashes[RUN_MANIFEST] = _write_json(root, RUN_MANIFEST, manifest)
    artifact_hashes[NATURAL_ROLLOUTS] = _write_jsonl(
        root, NATURAL_ROLLOUTS, _rows(natural_rollouts), "rollout_id"
    )
    artifact_hashes[CANDIDATE_REGIONS] = _write_jsonl(
        root, CANDIDATE_REGIONS, _rows(candidate_regions), "region_id"
    )
    artifact_hashes[ARU_CANDIDATES] = _write_jsonl(
        root, ARU_CANDIDATES, _rows(aru_candidates), "aru_id"
    )
    artifact_hashes[INTERVENTIONS] = _write_jsonl(
        root, INTERVENTIONS, _rows(interventions), "intervention_id"
    )
    artifact_hashes[BRANCH_REQUESTS] = _write_jsonl(
        root, BRANCH_REQUESTS, _rows(branch_requests), "branch_id"
    )
    artifact_hashes[BRANCH_RESULTS] = _write_jsonl(
        root, BRANCH_RESULTS, _rows(branch_responses), "branch_id"
    )
    artifact_hashes[PROCESS_OUTCOMES] = _write_jsonl(
        root, PROCESS_OUTCOMES, _rows(process_outcomes), "branch_id"
    )
    reward_summary = None
    if gradient_provenance is not None:
        artifact_hashes[GRADIENT_PROVENANCE] = _write_jsonl(
            root, GRADIENT_PROVENANCE, _rows(gradient_provenance), "rollout_id"
        )
        reward_summary = aggregate_raw_and_accepted(gradient_provenance)
    outcome_rows = _rows(process_outcomes)
    report = {
        "artifact_sha256": dict(sorted(artifact_hashes.items())),
        "branch_count": len(branch_requests),
        "candidate_region_count": len(candidate_regions),
        "gradient_summary": reward_summary,
        "mode": profile.mode,
        "outcomes": {
            "final_correctness": _counts(outcome_rows, "final_correctness"),
            "local_validity": _counts(outcome_rows, "local_validity"),
        },
        "profile_id": profile.profile_id,
        "schema_version": 1,
        "synthetic_toy": profile.mode == "toy",
    }
    artifact_hashes[REPORT] = _write_json(root, REPORT, report)
    marker_identity = {
        "artifact_sha256": dict(sorted(artifact_hashes.items())),
        "profile_id": profile.profile_id,
        "schema_version": 1,
        "status": "FINALIZED",
    }
    marker = {**marker_identity, "finalization_sha256": canonical_sha256(marker_identity)}
    _write_json(root, FINALIZED, marker)
    return marker


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key))
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def load_records(path: str | Path, kind: str) -> list[Any]:
    factories = {
        "aru": ARUCandidate.from_mapping,
        "branch_request": PrefixBranchRequest.from_mapping,
        "branch_response": PrefixBranchResponse.from_mapping,
        "candidate_region": CandidateRegion.from_mapping,
        "gradient": GradientProvenanceRecord.from_mapping,
        "intervention": InterventionSpec.from_mapping,
        "natural_rollout": NaturalRolloutReference.from_mapping,
        "outcome": ProcessOutcome.from_mapping,
    }
    if kind not in factories:
        raise ValueError(f"unknown record kind: {kind}")
    return [factories[kind](row) for row in read_jsonl(path)]
