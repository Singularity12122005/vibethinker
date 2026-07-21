from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vibethinker_experiments.evaluation.artifacts import (
    FINALIZED,
    GENERATED,
    GENERATION_RESULTS,
    JUDGMENTS,
    SCORED_RESULTS,
    ArtifactError,
    finalize_run,
    mark_generated,
    seal_judgments,
)
from vibethinker_experiments.evaluation.io import canonical_json, read_json, read_jsonl
from vibethinker_experiments.evaluation.models import EvaluationProfile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rehash_generation(row: dict) -> None:
    identity = {
        key: row[key]
        for key in (
            "panel_id",
            "panel_sha256",
            "raw_completion",
            "prompt_tokens",
            "completion_tokens",
            "finish_reason",
            "profile_id",
        )
    }
    row["generation_sha256"] = hashlib.sha256(canonical_json(identity).encode()).hexdigest()


def test_generated_and_finalized_are_distinct_and_reentrant(
    tmp_path, toy_rows, toy_manifest, toy_profile, generation_results
):
    marker = mark_generated(
        tmp_path,
        toy_rows,
        generation_results,
        panel_manifest=toy_manifest,
        profile=toy_profile,
    )
    generation_hash = digest(tmp_path / GENERATION_RESULTS)
    assert marker["status"] == "GENERATED"
    assert (tmp_path / GENERATED).is_file()
    assert not (tmp_path / FINALIZED).exists()
    assert not (tmp_path / SCORED_RESULTS).exists()

    finalized_once = finalize_run(
        tmp_path,
        toy_rows,
        panel_manifest=toy_manifest,
        profile=toy_profile,
    )
    finalized_bytes = (tmp_path / FINALIZED).read_bytes()
    scored_bytes = (tmp_path / SCORED_RESULTS).read_bytes()
    finalized_twice = finalize_run(
        tmp_path,
        toy_rows,
        panel_manifest=toy_manifest,
        profile=toy_profile,
    )
    assert finalized_once == finalized_twice
    assert (tmp_path / FINALIZED).read_bytes() == finalized_bytes
    assert (tmp_path / SCORED_RESULTS).read_bytes() == scored_bytes
    assert digest(tmp_path / GENERATION_RESULTS) == generation_hash
    assert len(read_jsonl(tmp_path / SCORED_RESULTS)) == len(toy_rows)


def test_generation_artifact_cannot_be_replaced(
    tmp_path, toy_rows, toy_manifest, toy_profile, generation_results
):
    mark_generated(
        tmp_path,
        toy_rows,
        generation_results,
        panel_manifest=toy_manifest,
        profile=toy_profile,
    )
    changed = [dict(row) for row in generation_results]
    changed[0]["raw_completion"] = "different synthetic output"
    rehash_generation(changed[0])
    with pytest.raises(ValueError, match="immutable artifact differs"):
        mark_generated(
            tmp_path,
            toy_rows,
            changed,
            panel_manifest=toy_manifest,
            profile=toy_profile,
        )


def test_generated_requires_exact_panel_ids_and_generation_cap(
    tmp_path, toy_rows, toy_manifest, toy_profile, generation_results
):
    wrong_ids = [dict(row) for row in generation_results]
    wrong_ids[0]["panel_id"] = "synthetic-extra-id"
    rehash_generation(wrong_ids[0])
    with pytest.raises(ArtifactError, match="exactly match"):
        mark_generated(
            tmp_path / "wrong-ids",
            toy_rows,
            wrong_ids,
            panel_manifest=toy_manifest,
            profile=toy_profile,
        )

    over_cap = [dict(row) for row in generation_results]
    over_cap[0]["prompt_tokens"] = 0
    over_cap[0]["completion_tokens"] = toy_profile.generation_cap_tokens + 1
    rehash_generation(over_cap[0])
    with pytest.raises(ValueError, match="generation cap"):
        mark_generated(
            tmp_path / "over-cap",
            toy_rows,
            over_cap,
            panel_manifest=toy_manifest,
            profile=toy_profile,
        )


def test_judgments_are_compacted_sealed_and_generation_bound(
    tmp_path, toy_rows, toy_manifest, toy_profile, generation_results
):
    judged_profile = EvaluationProfile.from_mapping(
        {
            **toy_profile.to_dict(),
            "profile_id": "synthetic-toy-judged",
            "require_judgments": True,
        }
    )
    generations = [dict(row, profile_id=judged_profile.profile_id) for row in generation_results]
    for row in generations:
        rehash_generation(row)
    mark_generated(
        tmp_path,
        toy_rows,
        generations,
        panel_manifest=toy_manifest,
        profile=judged_profile,
    )
    attempts = [
        {
            "panel_id": row["panel_id"],
            "domain": row["domain"],
            "panel_sha256": row["panel_sha256"],
            "generation_sha256": row["generation_sha256"],
            "judge_status": "correct",
            "true_correct": True,
            "confidence": 1.0,
            "brief_reason": "synthetic",
            "judge_signature": "a" * 64,
            "attempt": 1,
            "error_type": None,
        }
        for row in generations
    ]
    seal_judgments(
        tmp_path,
        attempts + attempts,
        panel_manifest=toy_manifest,
    )
    assert len(read_jsonl(tmp_path / JUDGMENTS)) == len(toy_rows)
    finalize_run(
        tmp_path,
        toy_rows,
        panel_manifest=toy_manifest,
        profile=judged_profile,
    )
    assert all(row["judgment_score"] == 1.0 for row in read_jsonl(tmp_path / SCORED_RESULTS))
    judge_summary = read_json(tmp_path / "report.json")["scores"]["overall"]["judge"]
    assert judge_summary == {
        "resolved": len(toy_rows),
        "unresolved_or_missing": 0,
        "coverage": 1.0,
        "accuracy": 1.0,
    }


def test_finalizer_detects_post_generation_tampering(
    tmp_path, toy_rows, toy_manifest, toy_profile, generation_results
):
    mark_generated(
        tmp_path,
        toy_rows,
        generation_results,
        panel_manifest=toy_manifest,
        profile=toy_profile,
    )
    with (tmp_path / GENERATION_RESULTS).open("a") as handle:
        handle.write("{}\n")
    with pytest.raises(ArtifactError, match="changed after sealing"):
        finalize_run(
            tmp_path,
            toy_rows,
            panel_manifest=toy_manifest,
            profile=toy_profile,
        )
