"""Immutable GENERATED and FINALIZED artifact lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import CodeGrader, score_completion, summarize_scores
from .io import (
    canonical_json,
    index_unique,
    jsonl_bytes,
    read_json,
    read_jsonl,
    sha256_bytes,
    sha256_file,
    write_immutable,
)
from .judge import compact_judgments
from .models import EvaluationProfile, PanelManifest
from .validation import validate_generation_result, validate_judgment, validate_panel_rows

GENERATION_RESULTS = "generation_results.jsonl"
JUDGMENTS = "judgments.jsonl"
SCORED_RESULTS = "scored_results.jsonl"
GENERATION_MANIFEST = "generation_manifest.json"
GENERATED = "GENERATED.json"
FINALIZED = "FINALIZED.json"
REPORT = "report.json"


class ArtifactError(ValueError):
    pass


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def mark_generated(
    run_dir: str | Path,
    panel_rows: list[dict[str, Any]],
    generation_results: list[dict[str, Any]],
    *,
    panel_manifest: PanelManifest,
    profile: EvaluationProfile,
) -> dict[str, Any]:
    """Seal complete generation output without claiming scoring is finalized."""

    panel_manifest.assert_compatible(profile)
    panel_by_id = validate_panel_rows(panel_rows, panel_manifest)
    indexed = index_unique(generation_results, "panel_id")
    if set(indexed) != set(panel_by_id):
        raise ArtifactError("generation IDs do not exactly match the frozen panel")
    ordered = [indexed[panel_id] for panel_id in sorted(panel_by_id)]
    for row in ordered:
        validate_generation_result(
            row,
            panel_sha256=panel_manifest.panel_sha256,
            profile_id=profile.profile_id,
            context_tokens=profile.context_tokens,
            generation_cap_tokens=profile.generation_cap_tokens,
        )
    root = Path(run_dir)
    generation_hash = write_immutable(root / GENERATION_RESULTS, jsonl_bytes(ordered))
    generation_manifest = {
        "schema_version": 1,
        "status": "GENERATED",
        "panel": panel_manifest.to_dict(),
        "profile": profile.to_dict(),
        "generation_results_sha256": generation_hash,
        "row_count": len(ordered),
    }
    manifest_hash = write_immutable(root / GENERATION_MANIFEST, _json_bytes(generation_manifest))
    marker = {
        "schema_version": 1,
        "status": "GENERATED",
        "generation_manifest_sha256": manifest_hash,
        "generation_results_sha256": generation_hash,
        "panel_sha256": panel_manifest.panel_sha256,
        "profile_id": profile.profile_id,
    }
    write_immutable(root / GENERATED, _json_bytes(marker))
    return marker


def seal_judgments(
    run_dir: str | Path,
    attempts: list[dict[str, Any]],
    *,
    panel_manifest: PanelManifest,
    require_resolved: bool = True,
) -> list[dict[str, Any]]:
    """Compact retry attempts by panel_id, then seal one immutable judgment file."""

    root = Path(run_dir)
    if not (root / GENERATED).is_file():
        raise ArtifactError("judgments cannot be sealed before GENERATED")
    generated_marker = read_json(root / GENERATED)
    if generated_marker.get("panel_sha256") != panel_manifest.panel_sha256:
        raise ArtifactError("judgments target a different generated panel")
    if generated_marker.get("generation_results_sha256") != sha256_file(root / GENERATION_RESULTS):
        raise ArtifactError("generation results changed before judgment sealing")
    generation_by_id = index_unique(read_jsonl(root / GENERATION_RESULTS), "panel_id")
    compact = compact_judgments(attempts)
    indexed = index_unique(compact, "panel_id")
    if len(indexed) != panel_manifest.row_count:
        raise ArtifactError(
            f"judgment coverage mismatch: expected {panel_manifest.row_count}, got {len(indexed)}"
        )
    for row in compact:
        validate_judgment(row, panel_sha256=panel_manifest.panel_sha256)
        generation = generation_by_id.get(str(row["panel_id"]))
        if generation is None or row["generation_sha256"] != generation.get("generation_sha256"):
            raise ArtifactError(f"{row['panel_id']}: judgment targets a different generation")
    signatures = {str(row["judge_signature"]) for row in compact}
    if len(signatures) != 1:
        raise ArtifactError("sealed judgments must use one judge signature")
    unresolved = [row["panel_id"] for row in compact if row["judge_status"] == "unresolved"]
    if require_resolved and unresolved:
        raise ArtifactError(f"unresolved judgments remain: {unresolved}")
    write_immutable(root / JUDGMENTS, jsonl_bytes(compact))
    return compact


def _verify_generated(
    root: Path, panel_manifest: PanelManifest, profile: EvaluationProfile
) -> list[dict[str, Any]]:
    if not (root / GENERATED).is_file():
        raise ArtifactError("run has not reached GENERATED")
    marker = read_json(root / GENERATED)
    manifest = read_json(root / GENERATION_MANIFEST)
    if marker.get("status") != "GENERATED" or manifest.get("status") != "GENERATED":
        raise ArtifactError("invalid GENERATED status")
    if sha256_file(root / GENERATION_MANIFEST) != marker["generation_manifest_sha256"]:
        raise ArtifactError("generation manifest changed after sealing")
    if sha256_file(root / GENERATION_RESULTS) != marker["generation_results_sha256"]:
        raise ArtifactError("generation results changed after sealing")
    if manifest.get("panel") != panel_manifest.to_dict():
        raise ArtifactError("panel manifest differs from generated run")
    if manifest.get("profile") != profile.to_dict():
        raise ArtifactError("evaluation profile differs from generated run")
    rows = read_jsonl(root / GENERATION_RESULTS)
    for row in rows:
        validate_generation_result(
            row,
            panel_sha256=panel_manifest.panel_sha256,
            profile_id=profile.profile_id,
            context_tokens=profile.context_tokens,
            generation_cap_tokens=profile.generation_cap_tokens,
        )
    return rows


def _verify_finalized(root: Path) -> dict[str, Any]:
    marker = read_json(root / FINALIZED)
    if marker.get("status") != "FINALIZED":
        raise ArtifactError("invalid FINALIZED marker")
    for field, filename in (
        ("generated_marker_sha256", GENERATED),
        ("generation_manifest_sha256", GENERATION_MANIFEST),
        ("generation_results_sha256", GENERATION_RESULTS),
        ("judgments_sha256", JUDGMENTS),
        ("scored_results_sha256", SCORED_RESULTS),
        ("report_sha256", REPORT),
    ):
        expected = marker.get(field)
        path = root / filename
        if expected is None:
            if field == "judgments_sha256" and not path.exists():
                continue
            raise ArtifactError(f"FINALIZED marker missing {field}")
        if not path.is_file() or sha256_file(path) != expected:
            raise ArtifactError(f"finalized artifact changed: {filename}")
    identity = {
        key: marker.get(key)
        for key in (
            "panel_sha256",
            "profile_id",
            "generated_marker_sha256",
            "generation_manifest_sha256",
            "generation_results_sha256",
            "judgments_sha256",
            "scored_results_sha256",
            "report_sha256",
        )
    }
    if marker.get("finalization_sha256") != sha256_bytes(canonical_json(identity).encode()):
        raise ArtifactError("FINALIZED identity hash mismatch")
    return marker


def finalize_run(
    run_dir: str | Path,
    panel_rows: list[dict[str, Any]],
    *,
    panel_manifest: PanelManifest,
    profile: EvaluationProfile,
    code_grader: CodeGrader | None = None,
) -> dict[str, Any]:
    """Join immutable inputs into immutable scored results; safe to run twice."""

    root = Path(run_dir)
    panel_manifest.assert_compatible(profile)
    panel_by_id = validate_panel_rows(panel_rows, panel_manifest)
    generations = _verify_generated(root, panel_manifest, profile)
    if (root / FINALIZED).is_file():
        marker = _verify_finalized(root)
        if (
            marker.get("panel_sha256") != panel_manifest.panel_sha256
            or marker.get("profile_id") != profile.profile_id
        ):
            raise ArtifactError("finalized run does not match panel or profile")
        return marker
    generation_by_id = index_unique(generations, "panel_id")
    if set(generation_by_id) != set(panel_by_id):
        raise ArtifactError("generation IDs do not match panel IDs")

    judgments: list[dict[str, Any]] = []
    if (root / JUDGMENTS).is_file():
        judgments = read_jsonl(root / JUDGMENTS)
    elif profile.require_judgments:
        raise ArtifactError("profile requires sealed judgments before finalization")
    judgment_by_id = index_unique(judgments, "panel_id") if judgments else {}
    if judgments and set(judgment_by_id) != set(panel_by_id):
        raise ArtifactError("judgment IDs do not match panel IDs")
    for panel_id, judgment in judgment_by_id.items():
        validate_judgment(judgment, panel_sha256=panel_manifest.panel_sha256)
        if judgment.get("generation_sha256") != generation_by_id[panel_id].get("generation_sha256"):
            raise ArtifactError(f"{panel_id}: judgment targets a different generation")
        if profile.require_judgments and judgment["judge_status"] == "unresolved":
            raise ArtifactError(f"{panel_id}: required judgment is unresolved")

    scored: list[dict[str, Any]] = []
    for panel_id in sorted(panel_by_id):
        generation = generation_by_id[panel_id]
        row = score_completion(
            panel_by_id[panel_id],
            generation,
            context_tokens=profile.context_tokens,
            code_grader=code_grader,
        )
        judgment = judgment_by_id.get(panel_id)
        row["judgment_score"] = (
            float(judgment["judge_status"] == "correct")
            if judgment and judgment["judge_status"] != "unresolved"
            else None
        )
        row["judge_signature"] = judgment.get("judge_signature") if judgment else None
        scored.append(row)

    scored_hash = write_immutable(root / SCORED_RESULTS, jsonl_bytes(scored))
    report = {
        "schema_version": 1,
        "panel_sha256": panel_manifest.panel_sha256,
        "profile_id": profile.profile_id,
        "scores": summarize_scores(scored),
    }
    report_hash = write_immutable(root / REPORT, _json_bytes(report))
    marker = {
        "schema_version": 1,
        "status": "FINALIZED",
        "panel_sha256": panel_manifest.panel_sha256,
        "profile_id": profile.profile_id,
        "generated_marker_sha256": sha256_file(root / GENERATED),
        "generation_manifest_sha256": sha256_file(root / GENERATION_MANIFEST),
        "generation_results_sha256": sha256_file(root / GENERATION_RESULTS),
        "judgments_sha256": sha256_file(root / JUDGMENTS) if judgments else None,
        "scored_results_sha256": scored_hash,
        "report_sha256": report_hash,
        "finalization_sha256": sha256_bytes(
            canonical_json(
                {
                    "panel_sha256": panel_manifest.panel_sha256,
                    "profile_id": profile.profile_id,
                    "generated_marker_sha256": sha256_file(root / GENERATED),
                    "generation_manifest_sha256": sha256_file(root / GENERATION_MANIFEST),
                    "generation_results_sha256": sha256_file(root / GENERATION_RESULTS),
                    "judgments_sha256": sha256_file(root / JUDGMENTS) if judgments else None,
                    "scored_results_sha256": scored_hash,
                    "report_sha256": report_hash,
                }
            ).encode()
        ),
    }
    write_immutable(root / FINALIZED, _json_bytes(marker))
    return marker
