"""Dataset-role contracts for future process-observation pilots.

This module prepares source traces for later qualification work. It does not load
checkpoints, tokenize target-model inputs, create ARU candidates, or run branches.
"""

from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from vibethinker_experiments.evaluation.io import (
    canonical_json,
    read_jsonl,
    sha256_bytes,
    write_immutable,
)

from .identity import assert_sha256, canonical_json_bytes, canonical_jsonl_bytes, canonical_sha256

DatasetRole = Literal[
    "contract_toy",
    "transport_qualification_micro",
    "processbench_external_trace",
    "target_native_trace",
    "checkpoint_alignment_confirmation",
]
TraceProvenance = Literal[
    "synthetic_toy",
    "handcrafted_qualification",
    "external_benchmark_trace",
    "target_checkpoint_native",
]
DiscoveryOrConfirmation = Literal["discovery", "confirmation", "unassigned"]
MaterializationStatus = Literal[
    "materialized_private",
    "metadata_only",
    "not_materialized",
    "source_unavailable",
]
TraceClass = Literal["erroneous", "all_correct"]
TokenizationStatus = Literal["character_spans_only", "verified_tokenized"]

DATASET_ROLES: tuple[str, ...] = (
    "contract_toy",
    "transport_qualification_micro",
    "processbench_external_trace",
    "target_native_trace",
    "checkpoint_alignment_confirmation",
)
TRACE_PROVENANCE_VALUES: tuple[str, ...] = (
    "synthetic_toy",
    "handcrafted_qualification",
    "external_benchmark_trace",
    "target_checkpoint_native",
)
PROCESSBENCH_DATASET_ID = "Qwen/ProcessBench"
PROCESSBENCH_DATASET_REPO_TYPE = "dataset"
PROCESSBENCH_FORMAL_SOURCE_LOCK_PATH = (
    "configs/process_observation/processbench_source_lock.json"
)
PROCESSBENCH_OFFICIAL_SPLITS: tuple[str, ...] = (
    "gsm8k",
    "math",
    "olympiadbench",
    "omnimath",
)
PROCESSBENCH_EXPECTED_FIELDS: tuple[str, ...] = (
    "id",
    "generator",
    "problem",
    "steps",
    "final_answer_correct",
    "label",
)
PROCESSBENCH_LICENSE = "apache-2.0"
PROCESSBENCH_SELECTION_POLICY_ID = "processbench-balanced-32-v1"
PROCESSBENCH_SELECTION_SEED = 20260722
TRACE_RENDERING_POLICY_ID = "processbench-external-macro-text-v1"
CONFIRMATION_UNSEAL_TOKEN = "processbench-confirmation-policy-freeze-v1"
PROCESSBENCH_OFFICIAL_EVALUATION_REPOSITORY = "QwenLM/ProcessBench"
PROCESSBENCH_OFFICIAL_EVALUATION_REVISION = "e8024636bcabdf8bd514440551b531d3f90dd18b"
PROCESSBENCH_RUN_EVAL_SHA256 = (
    "66d09fc7a3d20d46f166d4bba4e04835f3d7473e1534b6908cd9045aefc7b704"
)
PROCESSBENCH_CRITIQUE_TEMPLATE_SHA256 = (
    "0e7dba24bfaa9dea379907e11b8dc701c6cd6e74453ab2ffc9b1d63237cc4434"
)
PROCESSBENCH_README_SHA256 = (
    "5c2dbd2264c1a73270929b888f2f45d671f4a771557db2ce4909b08daed97e67"
)
FUTURE_ALIGNMENT_SOURCES: tuple[str, ...] = (
    "MATH-500",
    "technical-report Health Panel",
)
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_SOURCE_REVISION_LABELS = {
    "latest",
    "main",
    "master",
    "refs/convert/parquet",
}
PROCESSBENCH_FORBIDDEN_OUTPUT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("complete problem field", re.compile(r'"problem"\s*:\s*"')),
    ("complete steps array", re.compile(r'"steps"\s*:\s*\[')),
    ("authorization header", re.compile(r"authorization\s*:", re.IGNORECASE)),
    ("bearer credential", re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)),
    ("secret-like key", re.compile(r'"(?:api[_-]?key|password|credential|secret|token)"\s*:')),
    ("windows absolute path", re.compile(r"[A-Za-z]:[\\/]")),
    ("unix cache path", re.compile(r'(?:"|\\s)/(?:home|tmp|var/tmp|root)/')),
)

PROCESSBENCH_OFFICIAL_LABEL_SEMANTICS = {
    "dataset": PROCESSBENCH_DATASET_ID,
    "step_indexing": "zero_based",
    "all_correct_sentinel": -1,
    "error_label_valid_range": "0 <= label < len(steps)",
    "raw_label_preserved": True,
    "final_answer_correct_distinct_from_step_correctness": True,
    "malformed_or_missing_labels": (
        "official evaluation code does not add protective validation; this importer "
        "fails closed before inventory or selection"
    ),
    "evidence": {
        "template": (
            "QwenLM/ProcessBench code/templates/critique_template.txt says solution "
            "paragraphs are indexed from 0 and no-error returns -1"
        ),
        "evaluation": (
            "QwenLM/ProcessBench code/run_eval.py compares pred == label and splits "
            "error_data by label != -1, correct_data by label == -1"
        ),
    },
}


class ProcessBenchSourceUnavailable(FileNotFoundError):
    pass


def _nonempty_str(value: Any, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} must be non-empty")
    return text


def _literal(value: Any, allowed: tuple[str, ...], field: str) -> str:
    text = str(value)
    if text not in allowed:
        raise ValueError(f"{field} must be one of {list(allowed)}")
    return text


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _source_split(value: Any) -> str:
    return _literal(value, PROCESSBENCH_OFFICIAL_SPLITS, "source_split")


def normalize_problem_text(problem: str) -> str:
    text = unicodedata.normalize("NFC", problem)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(text.split())


def normalized_problem_sha256(problem: str) -> str:
    return sha256_bytes(normalize_problem_text(problem).encode("utf-8"))


def conservative_normalized_problem_sha256(problem: str) -> str:
    return normalized_problem_sha256(problem)


def aggressive_duplicate_review_text(problem: str) -> str:
    text = normalize_problem_text(problem).casefold()
    text = re.sub(r"\\(?:left|right|quad|qquad)\b", "", text)
    text = re.sub(r"\\[,;!]", "", text)
    text = re.sub(r"[\s{}()\[\],.;:]+", "", text)
    return text


def aggressive_duplicate_review_sha256(problem: str) -> str:
    return sha256_bytes(aggressive_duplicate_review_text(problem).encode("utf-8"))


def raw_source_sha256(row: dict[str, Any]) -> str:
    return canonical_sha256(row)


def validate_processbench_dataset_revision_sha(value: str, field: str) -> str:
    revision = str(value).strip()
    lowered = revision.casefold()
    if lowered in FORBIDDEN_SOURCE_REVISION_LABELS or lowered.startswith("refs/"):
        raise ValueError(f"{field} must be an immutable 40-character Git SHA")
    if not GIT_SHA_RE.match(revision):
        raise ValueError(f"{field} must be an immutable 40-character Git SHA")
    return revision


def deterministic_tie_break(seed: int, *parts: object) -> str:
    return sha256_bytes(
        canonical_json({"parts": [str(part) for part in parts], "seed": seed}).encode("utf-8")
    )


def build_semantics_source_receipts(
    *,
    evaluation_code_revision: str,
    run_eval_sha256: str,
    critique_template_sha256: str,
    readme_or_datacard_sha256: str,
) -> dict[str, Any]:
    for field, value in {
        "critique_template_sha256": critique_template_sha256,
        "readme_or_datacard_sha256": readme_or_datacard_sha256,
        "run_eval_sha256": run_eval_sha256,
    }.items():
        assert_sha256(value, field)
    return {
        "critique_template_sha256": critique_template_sha256,
        "evaluation_code_revision": _nonempty_str(
            evaluation_code_revision, "evaluation_code_revision"
        ),
        "official_evaluation_repository": PROCESSBENCH_OFFICIAL_EVALUATION_REPOSITORY,
        "label_semantics": PROCESSBENCH_OFFICIAL_LABEL_SEMANTICS,
        "readme_or_datacard_sha256": readme_or_datacard_sha256,
        "run_eval_sha256": run_eval_sha256,
    }


def pinned_processbench_semantics_source_receipts() -> dict[str, Any]:
    return build_semantics_source_receipts(
        evaluation_code_revision=PROCESSBENCH_OFFICIAL_EVALUATION_REVISION,
        run_eval_sha256=PROCESSBENCH_RUN_EVAL_SHA256,
        critique_template_sha256=PROCESSBENCH_CRITIQUE_TEMPLATE_SHA256,
        readme_or_datacard_sha256=PROCESSBENCH_README_SHA256,
    )


def build_snapshot_manifest(
    *,
    dataset_revision: str,
    retrieval_method: str,
    retrieval_timestamp: str,
    source_license: str,
    source_file_inventory: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    raw_split_row_counts: dict[str, int],
    semantics_source_receipts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dataset_id": PROCESSBENCH_DATASET_ID,
        "exact_revision": _nonempty_str(dataset_revision, "dataset_revision"),
        "license": _nonempty_str(source_license, "source_license"),
        "raw_row_counts": dict(sorted(raw_split_row_counts.items())),
        "raw_split_names": list(PROCESSBENCH_OFFICIAL_SPLITS),
        "relative_file_inventory": list(source_file_inventory),
        "retrieval_method": _nonempty_str(retrieval_method, "retrieval_method"),
        "retrieval_timestamp": _nonempty_str(retrieval_timestamp, "retrieval_timestamp"),
        "schema_version": 1,
        "semantics_source_receipts": semantics_source_receipts,
    }


def write_snapshot_manifest(path: Path, manifest: dict[str, Any]) -> str:
    return write_immutable(path, canonical_json_bytes(manifest))


@dataclass(frozen=True)
class ProcessBenchSourceLock:
    schema_version: int
    dataset_id: str
    dataset_repo_type: str
    dataset_revision_sha: str
    source_license: str
    expected_split_names: tuple[str, ...]
    expected_public_row_count: int | None
    official_evaluation_repository: str
    official_evaluation_revision: str
    run_eval_sha256: str
    critique_template_sha256: str
    readme_sha256: str
    resolution_receipt_sha256: str
    created_at_utc: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ProcessBenchSourceLock:
        if _int(value.get("schema_version"), "schema_version") != 1:
            raise ValueError("ProcessBenchSourceLock schema_version must be 1")
        dataset_id = _nonempty_str(value.get("dataset_id"), "dataset_id")
        if dataset_id != PROCESSBENCH_DATASET_ID:
            raise ValueError("ProcessBench source lock must use Qwen/ProcessBench")
        repo_type = _nonempty_str(value.get("dataset_repo_type"), "dataset_repo_type")
        if repo_type != PROCESSBENCH_DATASET_REPO_TYPE:
            raise ValueError("ProcessBench source lock dataset_repo_type must be dataset")
        revision = validate_processbench_dataset_revision_sha(
            str(value.get("dataset_revision_sha", "")), "dataset_revision_sha"
        )
        expected_split_names = tuple(str(item) for item in value.get("expected_split_names", ()))
        if expected_split_names != PROCESSBENCH_OFFICIAL_SPLITS:
            raise ValueError("expected_split_names must match the official ProcessBench splits")
        expected_count = value.get("expected_public_row_count")
        if expected_count is not None:
            expected_count = _int(expected_count, "expected_public_row_count")
            if expected_count <= 0:
                raise ValueError("expected_public_row_count must be positive or null")
        eval_repo = _nonempty_str(
            value.get("official_evaluation_repository"), "official_evaluation_repository"
        )
        if eval_repo != PROCESSBENCH_OFFICIAL_EVALUATION_REPOSITORY:
            raise ValueError("official evaluation repository must remain separate and pinned")
        eval_revision = validate_processbench_dataset_revision_sha(
            str(value.get("official_evaluation_revision", "")),
            "official_evaluation_revision",
        )
        if eval_revision == revision:
            raise ValueError("dataset-source and semantics-source revisions must be distinct")
        for field in (
            "critique_template_sha256",
            "readme_sha256",
            "resolution_receipt_sha256",
            "run_eval_sha256",
        ):
            assert_sha256(value.get(field), field)
        return cls(
            schema_version=1,
            dataset_id=dataset_id,
            dataset_repo_type=repo_type,
            dataset_revision_sha=revision,
            source_license=_nonempty_str(value.get("source_license"), "source_license"),
            expected_split_names=expected_split_names,
            expected_public_row_count=expected_count,
            official_evaluation_repository=eval_repo,
            official_evaluation_revision=eval_revision,
            run_eval_sha256=str(value["run_eval_sha256"]),
            critique_template_sha256=str(value["critique_template_sha256"]),
            readme_sha256=str(value["readme_sha256"]),
            resolution_receipt_sha256=str(value["resolution_receipt_sha256"]),
            created_at_utc=_nonempty_str(value.get("created_at_utc"), "created_at_utc"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at_utc": self.created_at_utc,
            "critique_template_sha256": self.critique_template_sha256,
            "dataset_id": self.dataset_id,
            "dataset_repo_type": self.dataset_repo_type,
            "dataset_revision_sha": self.dataset_revision_sha,
            "expected_public_row_count": self.expected_public_row_count,
            "expected_split_names": list(self.expected_split_names),
            "official_evaluation_repository": self.official_evaluation_repository,
            "official_evaluation_revision": self.official_evaluation_revision,
            "readme_sha256": self.readme_sha256,
            "resolution_receipt_sha256": self.resolution_receipt_sha256,
            "run_eval_sha256": self.run_eval_sha256,
            "schema_version": self.schema_version,
            "source_license": self.source_license,
        }

    def to_stable_identity(self) -> dict[str, Any]:
        identity = self.to_dict()
        identity.pop("created_at_utc", None)
        return identity

    @property
    def stable_source_identity_sha256(self) -> str:
        return canonical_sha256(self.to_stable_identity())


def load_formal_processbench_source_lock(path: Path) -> ProcessBenchSourceLock:
    if not path.is_file():
        raise ProcessBenchSourceUnavailable("formal ProcessBench inventory requires source lock")
    return ProcessBenchSourceLock.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def source_lock_from_resolution(
    resolution: dict[str, Any],
    *,
    created_at_utc: str,
    expected_public_row_count: int | None = None,
) -> ProcessBenchSourceLock:
    return ProcessBenchSourceLock.from_mapping(
        {
            "created_at_utc": created_at_utc,
            "critique_template_sha256": PROCESSBENCH_CRITIQUE_TEMPLATE_SHA256,
            "dataset_id": PROCESSBENCH_DATASET_ID,
            "dataset_repo_type": PROCESSBENCH_DATASET_REPO_TYPE,
            "dataset_revision_sha": resolution["resolved_revision_sha"],
            "expected_public_row_count": expected_public_row_count,
            "expected_split_names": list(PROCESSBENCH_OFFICIAL_SPLITS),
            "official_evaluation_repository": PROCESSBENCH_OFFICIAL_EVALUATION_REPOSITORY,
            "official_evaluation_revision": PROCESSBENCH_OFFICIAL_EVALUATION_REVISION,
            "readme_sha256": PROCESSBENCH_README_SHA256,
            "resolution_receipt_sha256": resolution["stable_resolution_receipt_sha256"],
            "run_eval_sha256": PROCESSBENCH_RUN_EVAL_SHA256,
            "schema_version": 1,
            "source_license": resolution["source_license"],
        }
    )


def processbench_metadata_client_versions() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "resolver": "urllib.request",
        "vibethinker_processbench_resolver": "processbench-source-resolve-v1",
    }


def resolve_processbench_source_metadata(
    *,
    dataset_id: str = PROCESSBENCH_DATASET_ID,
    allow_network: bool = False,
    metadata_bytes: bytes | None = None,
    resolution_time: str,
    client_version: dict[str, str] | None = None,
) -> dict[str, Any]:
    if dataset_id != PROCESSBENCH_DATASET_ID:
        raise ValueError("ProcessBench resolver only allows the official Qwen/ProcessBench source")
    if metadata_bytes is None:
        if not allow_network:
            raise ProcessBenchSourceUnavailable(
                "ProcessBench source resolution is network-disabled by default"
            )
        metadata_bytes = _fetch_processbench_metadata_bytes(dataset_id)
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    if str(metadata.get("id", dataset_id)) != PROCESSBENCH_DATASET_ID:
        raise ValueError("metadata response does not describe Qwen/ProcessBench")
    resolved = validate_processbench_dataset_revision_sha(
        str(metadata.get("sha", "")), "resolved_revision_sha"
    )
    source_license = _extract_source_license(metadata)
    file_inventory = _metadata_file_inventory(metadata)
    semantics_receipts = pinned_processbench_semantics_source_receipts()
    stable_payload = {
        "dataset_id": PROCESSBENCH_DATASET_ID,
        "metadata_response_digest": sha256_bytes(metadata_bytes),
        "raw_dataset_content_downloaded": False,
        "repository_file_inventory": file_inventory,
        "resolved_revision_sha": resolved,
        "semantics_source_receipts": semantics_receipts,
        "source_license": source_license,
    }
    return {
        **stable_payload,
        "client_version": client_version or processbench_metadata_client_versions(),
        "dataset_repo_type": PROCESSBENCH_DATASET_REPO_TYPE,
        "resolution_time": _nonempty_str(resolution_time, "resolution_time"),
        "schema_version": 1,
        "stable_resolution_receipt_sha256": canonical_sha256(stable_payload),
    }


def _fetch_processbench_metadata_bytes(dataset_id: str) -> bytes:
    request = urllib.request.Request(
        f"https://huggingface.co/api/datasets/{dataset_id}?blobs=true",
        headers={"User-Agent": "vibethinker-processbench-source-resolve-v1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise ProcessBenchSourceUnavailable(str(exc)) from exc


def _extract_source_license(metadata: dict[str, Any]) -> str:
    card = metadata.get("cardData")
    if isinstance(card, dict):
        license_value = card.get("license")
        if isinstance(license_value, str) and license_value.strip():
            return license_value.strip()
        if isinstance(license_value, list) and license_value:
            return str(license_value[0]).strip()
    for tag in metadata.get("tags", ()):
        text = str(tag)
        if text.startswith("license:"):
            return text.split(":", 1)[1]
    return PROCESSBENCH_LICENSE


def _metadata_file_inventory(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for sibling in metadata.get("siblings", ()):
        if not isinstance(sibling, dict):
            continue
        lfs = sibling.get("lfs") if isinstance(sibling.get("lfs"), dict) else {}
        files.append(
            {
                "blob_id": sibling.get("blobId"),
                "lfs_oid": lfs.get("oid"),
                "lfs_size_bytes": lfs.get("size"),
                "path": _nonempty_str(sibling.get("rfilename"), "rfilename"),
                "size_bytes": sibling.get("size"),
            }
        )
    return sorted(files, key=lambda item: str(item["path"]))


@dataclass(frozen=True)
class DatasetRoleRecord:
    dataset_role: DatasetRole
    source_dataset: str
    source_split: str
    source_record_id: str
    problem_id: str
    normalized_problem_sha256: str
    trace_provenance: TraceProvenance
    discovery_or_confirmation: DiscoveryOrConfirmation
    source_revision: str
    source_license: str
    selection_policy_id: str
    annotation_provenance: str
    materialization_status: MaterializationStatus
    raw_source_sha256: str | None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> DatasetRoleRecord:
        required = {
            "dataset_role",
            "source_dataset",
            "source_split",
            "source_record_id",
            "problem_id",
            "normalized_problem_sha256",
            "trace_provenance",
            "discovery_or_confirmation",
            "source_revision",
            "source_license",
            "selection_policy_id",
            "annotation_provenance",
            "materialization_status",
            "raw_source_sha256",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise ValueError(f"missing required dataset role fields: {missing}")
        digest = value.get("raw_source_sha256")
        assert_sha256(digest, "raw_source_sha256")
        assert_sha256(value["normalized_problem_sha256"], "normalized_problem_sha256")
        return cls(
            dataset_role=_literal(value["dataset_role"], DATASET_ROLES, "dataset_role"),  # type: ignore[arg-type]
            source_dataset=_nonempty_str(value["source_dataset"], "source_dataset"),
            source_split=_nonempty_str(value["source_split"], "source_split"),
            source_record_id=_nonempty_str(value["source_record_id"], "source_record_id"),
            problem_id=_nonempty_str(value["problem_id"], "problem_id"),
            normalized_problem_sha256=str(value["normalized_problem_sha256"]),
            trace_provenance=_literal(
                value["trace_provenance"], TRACE_PROVENANCE_VALUES, "trace_provenance"
            ),  # type: ignore[arg-type]
            discovery_or_confirmation=_literal(
                value["discovery_or_confirmation"],
                ("discovery", "confirmation", "unassigned"),
                "discovery_or_confirmation",
            ),  # type: ignore[arg-type]
            source_revision=_nonempty_str(value["source_revision"], "source_revision"),
            source_license=_nonempty_str(value["source_license"], "source_license"),
            selection_policy_id=_nonempty_str(
                value["selection_policy_id"], "selection_policy_id"
            ),
            annotation_provenance=_nonempty_str(
                value["annotation_provenance"], "annotation_provenance"
            ),
            materialization_status=_literal(
                value["materialization_status"],
                ("materialized_private", "metadata_only", "not_materialized", "source_unavailable"),
                "materialization_status",
            ),  # type: ignore[arg-type]
            raw_source_sha256=digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ProcessBenchExample:
    role_record: DatasetRoleRecord
    generator: str
    problem: str
    steps: tuple[str, ...]
    final_answer_correct: bool
    raw_label: int

    @classmethod
    def from_raw(
        cls,
        row: dict[str, Any],
        *,
        source_split: str,
        source_revision: str,
        source_license: str = PROCESSBENCH_LICENSE,
        selection_policy_id: str = "unselected",
        annotation_provenance: str = "official_processbench",
    ) -> ProcessBenchExample:
        split = _source_split(source_split)
        missing = sorted(set(PROCESSBENCH_EXPECTED_FIELDS) - row.keys())
        if missing:
            raise ValueError(f"missing ProcessBench fields: {missing}")
        source_record_id = _nonempty_str(row["id"], "id")
        generator = _nonempty_str(row["generator"], "generator")
        problem = _nonempty_str(row["problem"], "problem")
        steps_raw = row["steps"]
        if not isinstance(steps_raw, list) or not steps_raw:
            raise ValueError("steps must be a non-empty list")
        steps = tuple(_nonempty_str(step, "steps") for step in steps_raw)
        final_answer_correct = _bool(row["final_answer_correct"], "final_answer_correct")
        label = _int(row["label"], "label")
        if label != -1 and not 0 <= label < len(steps):
            raise ValueError("label must be -1 or a zero-based step index within steps")
        digest = normalized_problem_sha256(problem)
        role_record = DatasetRoleRecord(
            dataset_role="processbench_external_trace",
            source_dataset=PROCESSBENCH_DATASET_ID,
            source_split=split,
            source_record_id=source_record_id,
            problem_id=f"processbench:{split}:{source_record_id}",
            normalized_problem_sha256=digest,
            trace_provenance="external_benchmark_trace",
            discovery_or_confirmation="unassigned",
            source_revision=_nonempty_str(source_revision, "source_revision"),
            source_license=_nonempty_str(source_license, "source_license"),
            selection_policy_id=selection_policy_id,
            annotation_provenance=annotation_provenance,
            materialization_status="materialized_private",
            raw_source_sha256=raw_source_sha256(row),
        )
        return cls(
            role_record=role_record,
            generator=generator,
            problem=problem,
            steps=steps,
            final_answer_correct=final_answer_correct,
            raw_label=label,
        )

    @property
    def source_split(self) -> str:
        return self.role_record.source_split

    @property
    def source_record_id(self) -> str:
        return self.role_record.source_record_id

    @property
    def problem_id(self) -> str:
        return self.role_record.problem_id

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def is_all_correct(self) -> bool:
        return self.raw_label == -1

    @property
    def trace_class(self) -> TraceClass:
        return "all_correct" if self.is_all_correct else "erroneous"

    @property
    def earliest_error_step_index(self) -> int | None:
        return None if self.is_all_correct else self.raw_label

    @property
    def normalized_error_position(self) -> float | None:
        if self.is_all_correct:
            return None
        return (self.raw_label + 0.5) / self.step_count

    @property
    def conservative_normalized_problem_sha256(self) -> str:
        return self.role_record.normalized_problem_sha256

    @property
    def aggressive_duplicate_review_sha256(self) -> str:
        return aggressive_duplicate_review_sha256(self.problem)

    def with_assignment(
        self,
        split: DiscoveryOrConfirmation,
        *,
        selection_policy_id: str,
    ) -> ProcessBenchExample:
        return ProcessBenchExample(
            role_record=DatasetRoleRecord(
                **{
                    **self.role_record.to_dict(),
                    "discovery_or_confirmation": split,
                    "selection_policy_id": selection_policy_id,
                    "materialization_status": "metadata_only",
                }
            ),
            generator=self.generator,
            problem=self.problem,
            steps=self.steps,
            final_answer_correct=self.final_answer_correct,
            raw_label=self.raw_label,
        )

    def to_private_dict(self) -> dict[str, Any]:
        return {
            **self.role_record.to_dict(),
            "final_answer_correct": self.final_answer_correct,
            "generator": self.generator,
            "label": self.raw_label,
            "problem": self.problem,
            "steps": list(self.steps),
            "trace_class": self.trace_class,
        }

    def to_public_stub(self) -> dict[str, Any]:
        return {
            **self.role_record.to_dict(),
            "aggressive_duplicate_review_sha256": self.aggressive_duplicate_review_sha256,
            "conservative_normalized_problem_sha256": (
                self.conservative_normalized_problem_sha256
            ),
            "final_answer_correct": self.final_answer_correct,
            "generator": self.generator,
            "label": self.raw_label,
            "number_of_steps": self.step_count,
            "trace_class": self.trace_class,
        }


@dataclass(frozen=True)
class ProcessBenchSourceBundle:
    records: tuple[ProcessBenchExample, ...]
    source_revision: str
    source_license: str
    snapshot_sha256: str | None
    source_file_inventory: tuple[dict[str, Any], ...]
    raw_split_row_counts: dict[str, int]


@dataclass(frozen=True)
class TraceRenderingPolicy:
    policy_id: str = TRACE_RENDERING_POLICY_ID
    step_prefix_format: str = "Step {step_index}: "
    step_delimiter: str = "\n"
    newline_convention: str = "lf"
    reasoning_channel_wrapper: str = "none_external_steps_only"
    include_think_tags: bool = False
    include_final_answer_text: bool = False
    source_text_normalization_rules: tuple[str, ...] = (
        "unicode_nfc",
        "crlf_to_lf",
        "strip_step_text",
    )
    unicode_normalization_policy: str = "NFC"
    tokenization_status: TokenizationStatus = "character_spans_only"
    tokenizer_receipt_requirement: str = "required_before_formal_trace_materialization"

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "include_final_answer_text": self.include_final_answer_text,
            "include_think_tags": self.include_think_tags,
            "newline_convention": self.newline_convention,
            "policy_id": self.policy_id,
            "reasoning_channel_wrapper": self.reasoning_channel_wrapper,
            "source_text_normalization_rules": list(self.source_text_normalization_rules),
            "step_delimiter": self.step_delimiter,
            "step_prefix_format": self.step_prefix_format,
            "tokenization_status": self.tokenization_status,
            "tokenizer_receipt_requirement": self.tokenizer_receipt_requirement,
            "unicode_normalization_policy": self.unicode_normalization_policy,
        }

    @property
    def policy_sha256(self) -> str:
        return canonical_sha256(self.to_identity_dict())


@dataclass(frozen=True)
class ExternalMacroRegion:
    region_kind: Literal["external_macro_region"]
    source_record_id: str
    step_index: int
    char_start: int | None
    char_end: int | None
    trace_provenance: Literal["external_benchmark_trace"]
    processbench_label_role: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def import_processbench_split(
    rows: list[dict[str, Any]],
    *,
    source_split: str,
    source_revision: str,
    source_license: str = PROCESSBENCH_LICENSE,
) -> list[ProcessBenchExample]:
    examples: list[ProcessBenchExample] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        try:
            example = ProcessBenchExample.from_raw(
                row,
                source_split=source_split,
                source_revision=source_revision,
                source_license=source_license,
            )
        except ValueError as exc:
            raise ValueError(f"{source_split}:{index}: {exc}") from exc
        if example.source_record_id in seen:
            raise ValueError(
                f"duplicate ProcessBench id in {source_split}: {example.source_record_id}"
            )
        seen.add(example.source_record_id)
        examples.append(example)
    return examples


def snapshot_tree_sha256(root: Path) -> str:
    if not root.is_dir():
        raise ProcessBenchSourceUnavailable(f"snapshot directory not found: {root}")
    return canonical_sha256({"files": snapshot_file_inventory(root)})


def snapshot_file_inventory(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        raise ProcessBenchSourceUnavailable(f"snapshot directory not found: {root}")
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
                "size_bytes": path.stat().st_size,
            }
        )
    return entries


def load_processbench_source(
    *,
    snapshot_dir: Path | None = None,
    allow_network: bool = False,
    cache_dir: Path | None = None,
    source_revision: str | None = None,
    source_license: str = PROCESSBENCH_LICENSE,
) -> ProcessBenchSourceBundle:
    if snapshot_dir is None and not allow_network:
        raise ProcessBenchSourceUnavailable(
            "ProcessBench loading is network-disabled by default; provide a local "
            "snapshot_dir or pass allow_network=True with an explicit cache_dir and revision"
        )
    if allow_network:
        if source_revision is None:
            raise ValueError("allow_network requires an explicit source_revision")
        if cache_dir is None:
            raise ValueError("allow_network requires an explicit download/cache path")
        return _load_processbench_from_network(
            cache_dir=cache_dir,
            source_revision=source_revision,
            source_license=source_license,
        )
    if snapshot_dir is None:
        raise AssertionError("unreachable")
    file_inventory = snapshot_file_inventory(snapshot_dir)
    snapshot_hash = canonical_sha256({"files": file_inventory})
    revision = source_revision or f"local-snapshot-sha256:{snapshot_hash}"
    records: list[ProcessBenchExample] = []
    raw_split_row_counts: dict[str, int] = {}
    for split in PROCESSBENCH_OFFICIAL_SPLITS:
        split_rows = _load_snapshot_split(snapshot_dir, split)
        raw_split_row_counts[split] = len(split_rows)
        records.extend(
            import_processbench_split(
                split_rows,
                source_split=split,
                source_revision=revision,
                source_license=source_license,
            )
        )
    return ProcessBenchSourceBundle(
        records=tuple(records),
        source_revision=revision,
        source_license=source_license,
        snapshot_sha256=snapshot_hash,
        source_file_inventory=tuple(file_inventory),
        raw_split_row_counts=raw_split_row_counts,
    )


def _load_processbench_from_network(
    *,
    cache_dir: Path,
    source_revision: str,
    source_license: str,
) -> ProcessBenchSourceBundle:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ProcessBenchSourceUnavailable(
            "network loading requires the optional datasets dependency"
        ) from exc
    records: list[ProcessBenchExample] = []
    raw_split_row_counts: dict[str, int] = {}
    for split in PROCESSBENCH_OFFICIAL_SPLITS:
        dataset = load_dataset(
            PROCESSBENCH_DATASET_ID,
            split=split,
            revision=source_revision,
            cache_dir=str(cache_dir),
        )
        rows = [dict(row) for row in dataset]
        raw_split_row_counts[split] = len(rows)
        records.extend(
            import_processbench_split(
                rows,
                source_split=split,
                source_revision=source_revision,
                source_license=source_license,
            )
        )
    return ProcessBenchSourceBundle(
        records=tuple(records),
        source_revision=source_revision,
        source_license=source_license,
        snapshot_sha256=None,
        source_file_inventory=(),
        raw_split_row_counts=raw_split_row_counts,
    )


def build_source_lock_validation_report(lock: ProcessBenchSourceLock) -> dict[str, Any]:
    return {
        "dataset_id": lock.dataset_id,
        "dataset_revision_sha": lock.dataset_revision_sha,
        "expected_public_row_count": lock.expected_public_row_count,
        "expected_split_names": list(lock.expected_split_names),
        "official_evaluation_repository": lock.official_evaluation_repository,
        "official_evaluation_revision": lock.official_evaluation_revision,
        "schema_version": 1,
        "source_license": lock.source_license,
        "stable_source_identity_sha256": lock.stable_source_identity_sha256,
        "valid": True,
    }


def write_source_lock_validation_report(lock: ProcessBenchSourceLock, output: Path) -> str:
    return write_immutable(output, canonical_json_bytes(build_source_lock_validation_report(lock)))


def build_snapshot_manifest_from_source_lock(
    *,
    lock: ProcessBenchSourceLock,
    snapshot_dir: Path,
    retrieval_method: str,
    retrieval_timestamp: str,
) -> dict[str, Any]:
    bundle = load_processbench_source(
        snapshot_dir=snapshot_dir,
        source_revision=lock.dataset_revision_sha,
        source_license=lock.source_license,
    )
    return build_snapshot_manifest(
        dataset_revision=lock.dataset_revision_sha,
        retrieval_method=retrieval_method,
        retrieval_timestamp=retrieval_timestamp,
        source_license=lock.source_license,
        source_file_inventory=bundle.source_file_inventory,
        raw_split_row_counts=bundle.raw_split_row_counts,
        semantics_source_receipts={
            "critique_template_sha256": lock.critique_template_sha256,
            "evaluation_code_revision": lock.official_evaluation_revision,
            "official_evaluation_repository": lock.official_evaluation_repository,
            "readme_or_datacard_sha256": lock.readme_sha256,
            "run_eval_sha256": lock.run_eval_sha256,
        },
    )


def total_inventory_row_count(inventory: dict[str, Any]) -> int:
    return sum(int(split_data["row_count"]) for split_data in inventory["splits"].values())


def validate_expected_public_row_count(
    inventory: dict[str, Any], lock: ProcessBenchSourceLock
) -> None:
    if lock.expected_public_row_count is None:
        return
    observed = total_inventory_row_count(inventory)
    if observed != lock.expected_public_row_count:
        raise ValueError(
            "observed ProcessBench row count does not match expected_public_row_count"
        )


def _load_snapshot_split(snapshot_dir: Path, split: str) -> list[dict[str, Any]]:
    candidates = [
        snapshot_dir / f"{split}.jsonl",
        snapshot_dir / f"{split}.json",
        snapshot_dir / "data" / f"{split}.jsonl",
        snapshot_dir / "data" / f"{split}.json",
    ]
    candidates.extend(sorted(snapshot_dir.rglob(f"*{split}*.jsonl")))
    candidates.extend(sorted(snapshot_dir.rglob(f"*{split}*.json")))
    candidates.extend(sorted(snapshot_dir.rglob(f"*{split}*.parquet")))
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return _load_rows_file(candidate)
    raise ProcessBenchSourceUnavailable(f"no local ProcessBench file found for split: {split}")


def _load_rows_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return read_jsonl(path)
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise ValueError(f"{path}: expected a JSON list of objects")
        return list(value)
    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ProcessBenchSourceUnavailable(
                "local parquet snapshots require the optional pyarrow dependency"
            ) from exc
        table = pq.read_table(path)
        return [dict(row) for row in table.to_pylist()]
    raise ValueError(f"unsupported ProcessBench file type: {path}")


def build_processbench_inventory(
    records: list[ProcessBenchExample],
    *,
    source_revision: str,
    source_license: str,
    source_file_inventory: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    semantics_source_receipts: dict[str, Any] | None = None,
    malformed_field_counts: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    duplicate_ids = _duplicate_record_ids(records)
    if duplicate_ids:
        raise ValueError(f"duplicate ProcessBench source IDs: {duplicate_ids}")
    by_split: dict[str, list[ProcessBenchExample]] = {
        split: [row for row in records if row.source_split == split]
        for split in PROCESSBENCH_OFFICIAL_SPLITS
    }
    split_inventory: dict[str, Any] = {}
    for split, rows in by_split.items():
        errors = [row for row in rows if not row.is_all_correct]
        correct = [row for row in rows if row.is_all_correct]
        split_inventory[split] = {
            "all_correct_count": len(correct),
            "all_correct_but_final_wrong_count": sum(
                row.is_all_correct and not row.final_answer_correct for row in rows
            ),
            "earliest_error_position_distribution": dict(
                sorted(Counter(row.raw_label for row in errors).items())
            ),
            "error_but_final_correct_count": sum(
                (not row.is_all_correct) and row.final_answer_correct for row in rows
            ),
            "error_count": len(errors),
            "generator_distribution": dict(
                sorted(Counter(row.generator for row in rows).items())
            ),
            "label_final_answer_crosstab": _label_final_answer_crosstab(rows),
            "malformed_field_counts": (malformed_field_counts or {}).get(split, {}),
            "normalized_error_position_distribution": _normalized_position_distribution(errors),
            "normalized_error_position_quantiles": _normalized_position_quantiles(errors),
            "number_of_steps_distribution": dict(
                sorted(Counter(row.step_count for row in rows).items())
            ),
            "step_count_quantiles": _step_count_quantiles(rows),
            "row_count": len(rows),
            "split_generator_trace_status": _split_generator_trace_status(rows),
        }
    return {
        "schema_version": 1,
        "complete": True,
        "dataset": PROCESSBENCH_DATASET_ID,
        "aggressive_duplicate_review_clusters": _aggressive_duplicate_review_clusters(records),
        "conservative_duplicate_hashes_across_splits": _duplicate_hashes_across_splits(records),
        "conservative_duplicate_hashes_within_splits": _duplicate_hashes_within_splits(records),
        "duplicate_normalized_problem_hashes_across_splits": _duplicate_hashes_across_splits(
            records
        ),
        "observed_total_row_count": sum(data["row_count"] for data in split_inventory.values()),
        "official_label_semantics": PROCESSBENCH_OFFICIAL_LABEL_SEMANTICS,
        "semantics_source_receipts": semantics_source_receipts or {},
        "source_file_inventory": list(source_file_inventory),
        "source_license": source_license,
        "source_revision": source_revision,
        "split_generator_distribution": {
            split: data["generator_distribution"] for split, data in split_inventory.items()
        },
        "splits": split_inventory,
    }


def _duplicate_record_ids(records: list[ProcessBenchExample]) -> list[str]:
    seen: set[tuple[str, str]] = set()
    duplicate: list[str] = []
    for row in records:
        key = (row.source_split, row.source_record_id)
        if key in seen:
            duplicate.append(f"{row.source_split}:{row.source_record_id}")
        seen.add(key)
    return duplicate


def _duplicate_hashes_across_splits(records: list[ProcessBenchExample]) -> dict[str, list[str]]:
    locations: dict[str, set[str]] = defaultdict(set)
    ids: dict[str, list[str]] = defaultdict(list)
    for row in records:
        digest = row.role_record.normalized_problem_sha256
        locations[digest].add(row.source_split)
        ids[digest].append(f"{row.source_split}:{row.source_record_id}")
    return {
        digest: sorted(ids[digest])
        for digest, splits in sorted(locations.items())
        if len(splits) > 1
    }


def _duplicate_hashes_within_splits(records: list[ProcessBenchExample]) -> dict[str, list[str]]:
    ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in records:
        ids[(row.source_split, row.conservative_normalized_problem_sha256)].append(
            f"{row.source_split}:{row.source_record_id}"
        )
    return {
        f"{split}:{digest}": sorted(locations)
        for (split, digest), locations in sorted(ids.items())
        if len(locations) > 1
    }


def _aggressive_duplicate_review_clusters(
    records: list[ProcessBenchExample],
) -> dict[str, list[str]]:
    ids: dict[str, list[str]] = defaultdict(list)
    conservative_by_aggressive: dict[str, set[str]] = defaultdict(set)
    for row in records:
        digest = row.aggressive_duplicate_review_sha256
        ids[digest].append(f"{row.source_split}:{row.source_record_id}")
        conservative_by_aggressive[digest].add(row.conservative_normalized_problem_sha256)
    return {
        digest: sorted(locations)
        for digest, locations in sorted(ids.items())
        if len(locations) > 1 and len(conservative_by_aggressive[digest]) > 1
    }


def _label_final_answer_crosstab(rows: list[ProcessBenchExample]) -> dict[str, int]:
    return {
        "label_all_correct__final_answer_correct_false": sum(
            row.is_all_correct and not row.final_answer_correct for row in rows
        ),
        "label_all_correct__final_answer_correct_true": sum(
            row.is_all_correct and row.final_answer_correct for row in rows
        ),
        "label_error__final_answer_correct_false": sum(
            (not row.is_all_correct) and not row.final_answer_correct for row in rows
        ),
        "label_error__final_answer_correct_true": sum(
            (not row.is_all_correct) and row.final_answer_correct for row in rows
        ),
    }


def _split_generator_trace_status(rows: list[ProcessBenchExample]) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        status = "label_all_correct" if row.is_all_correct else "label_error"
        final = "final_correct" if row.final_answer_correct else "final_wrong"
        grouped[row.generator][f"{status}__{final}"] += 1
    return {
        generator: dict(sorted(counts.items()))
        for generator, counts in sorted(grouped.items())
    }


def _step_count_quantiles(rows: list[ProcessBenchExample]) -> dict[str, float | None]:
    values = sorted(row.step_count for row in rows)
    if not values:
        return {"min": None, "p25": None, "median": None, "p75": None, "max": None}
    return {
        "max": float(values[-1]),
        "median": _quantile(values, 0.5),
        "min": float(values[0]),
        "p25": _quantile(values, 0.25),
        "p75": _quantile(values, 0.75),
    }


def _quantile(values: list[float | int], q: float) -> float:
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _normalized_position_quantiles(rows: list[ProcessBenchExample]) -> dict[str, float | None]:
    values = sorted(
        position for row in rows if (position := row.normalized_error_position) is not None
    )
    if not values:
        return {"min": None, "p25": None, "median": None, "p75": None, "max": None}
    return {
        "max": float(values[-1]),
        "median": _quantile(values, 0.5),
        "min": float(values[0]),
        "p25": _quantile(values, 0.25),
        "p75": _quantile(values, 0.75),
    }


def _normalized_position_distribution(rows: list[ProcessBenchExample]) -> dict[str, int]:
    bins = {"[0,0.25)": 0, "[0.25,0.5)": 0, "[0.5,0.75)": 0, "[0.75,1]": 0}
    for row in rows:
        position = row.normalized_error_position
        if position is None:
            continue
        if position < 0.25:
            bins["[0,0.25)"] += 1
        elif position < 0.5:
            bins["[0.25,0.5)"] += 1
        elif position < 0.75:
            bins["[0.5,0.75)"] += 1
        else:
            bins["[0.75,1]"] += 1
    return bins


def select_processbench_pilot(
    records: list[ProcessBenchExample],
    *,
    inventory: dict[str, Any],
    seed: int = PROCESSBENCH_SELECTION_SEED,
    policy_id: str = PROCESSBENCH_SELECTION_POLICY_ID,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not inventory.get("complete"):
        raise ValueError("ProcessBench inventory must be complete before selection")
    selected_rows: list[dict[str, Any]] = []
    sampling_pair_rows: list[dict[str, Any]] = []
    shortfalls: dict[str, list[str]] = {}
    used_problem_hashes: set[str] = set()
    for split in PROCESSBENCH_OFFICIAL_SPLITS:
        split_records = [row for row in records if row.source_split == split]
        errors = [row for row in split_records if not row.is_all_correct]
        correct = [row for row in split_records if row.is_all_correct]
        selected_errors = _select_error_examples(
            errors,
            split=split,
            used_problem_hashes=used_problem_hashes,
            seed=seed,
        )
        if len(selected_errors) < 4:
            shortfalls.setdefault(split, []).append(f"erroneous selected {len(selected_errors)}/4")
        selected_correct: list[ProcessBenchExample] = []
        selected_error_hashes = {
            row.role_record.normalized_problem_sha256 for row in selected_errors
        }
        active_problem_hashes = set(used_problem_hashes) | selected_error_hashes
        for pair_index, error in enumerate(selected_errors):
            correct_match, score, tie = _select_correct_match(
                correct,
                error=error,
                selected_correct=selected_correct,
                used_problem_hashes=active_problem_hashes,
                seed=seed,
                split=split,
            )
            if correct_match is None:
                shortfalls.setdefault(split, []).append(
                    f"missing all-correct pair for {error.source_record_id}"
                )
                continue
            selected_correct.append(correct_match)
            assignment: DiscoveryOrConfirmation = "discovery" if pair_index < 2 else "confirmation"
            pair_id = f"processbench-{split}-pair-{pair_index:02d}"
            p_error = error.normalized_error_position
            if p_error is None:
                raise AssertionError("selected error cannot be all-correct")
            matched_step = matched_correct_step(p_error, correct_match.step_count)
            sampling_pair_rows.append(
                {
                    "correct_generator": correct_match.generator,
                    "correct_record_id": correct_match.source_record_id,
                    "correct_role": "position_matched_control",
                    "discovery_or_confirmation": assignment,
                    "error_generator": error.generator,
                    "error_record_id": error.source_record_id,
                    "error_role": "error_labelled_source_trace",
                    "matched_correct_step": matched_step,
                    "normalized_position": p_error,
                    "pair_kind": "position_matched_sampling_control",
                    "sampling_pair_id": pair_id,
                    "deterministic_pairing_score": score,
                    "source_split": split,
                    "tie_break_key": tie,
                }
            )
            selected_rows.extend(
                [
                    _selection_entry(
                        error.with_assignment(assignment, selection_policy_id=policy_id),
                        sampling_pair_id=pair_id,
                        sampling_pair_role="error_labelled_source_trace",
                        external_macro_step=error.raw_label,
                        matched_correct_step=None,
                        pairing_metadata=None,
                        policy_id=policy_id,
                    ),
                    _selection_entry(
                        correct_match.with_assignment(assignment, selection_policy_id=policy_id),
                        sampling_pair_id=pair_id,
                        sampling_pair_role="position_matched_control",
                        external_macro_step=matched_step,
                        matched_correct_step=matched_step,
                        pairing_metadata=score,
                        policy_id=policy_id,
                    ),
                ]
            )
            active_problem_hashes.add(correct_match.role_record.normalized_problem_sha256)
        used_problem_hashes.update(active_problem_hashes)
        if len(selected_correct) < len(selected_errors):
            shortfalls.setdefault(split, []).append(
                f"all-correct selected {len(selected_correct)}/{len(selected_errors)}"
            )
    validate_unique_selected_problem_hashes(selected_rows)
    validate_discovery_confirmation_no_leakage(selected_rows)
    report = {
        "schema_version": 1,
        "dataset": PROCESSBENCH_DATASET_ID,
        "sampling_pair_count": len(sampling_pair_rows),
        "policy_id": policy_id,
        "seed": seed,
        "selected_problem_count": len(selected_rows),
        "shortfalls": shortfalls,
        "source_revision": inventory.get("source_revision"),
        "split_composition": _selection_composition(selected_rows),
        "sampling_pairs": sampling_pair_rows,
    }
    return selected_rows, report


def matched_correct_step(normalized_error_position: float, correct_step_count: int) -> int:
    if correct_step_count < 1:
        raise ValueError("correct_step_count must be positive")
    return min(correct_step_count - 1, math.floor(normalized_error_position * correct_step_count))


def validate_discovery_confirmation_no_leakage(rows: list[dict[str, Any]]) -> None:
    buckets: dict[str, set[str]] = {"discovery": set(), "confirmation": set()}
    hashes: dict[str, set[str]] = {"discovery": set(), "confirmation": set()}
    for row in rows:
        split = row["discovery_or_confirmation"]
        if split not in buckets:
            continue
        buckets[split].add(str(row["problem_id"]))
        hashes[split].add(str(row["normalized_problem_sha256"]))
    if buckets["discovery"] & buckets["confirmation"]:
        raise ValueError("discovery/confirmation problem_id leakage")
    if hashes["discovery"] & hashes["confirmation"]:
        raise ValueError("discovery/confirmation normalized-problem leakage")


def validate_unique_selected_problem_hashes(rows: list[dict[str, Any]]) -> None:
    seen: dict[str, str] = {}
    for row in rows:
        digest = str(row["normalized_problem_sha256"])
        identity = str(row["problem_id"])
        previous = seen.get(digest)
        if previous is not None:
            raise ValueError("duplicate normalized-problem hash in selected manifest")
        seen[digest] = identity


def _select_error_examples(
    errors: list[ProcessBenchExample],
    *,
    split: str,
    used_problem_hashes: set[str],
    seed: int,
) -> list[ProcessBenchExample]:
    targets = (0.125, 0.375, 0.625, 0.875)
    selected: list[ProcessBenchExample] = []
    selected_hashes: set[str] = set()
    generator_counts: Counter[str] = Counter()
    for target in targets:
        candidates = [
            row
            for row in errors
            if row not in selected
            and row.role_record.normalized_problem_sha256 not in used_problem_hashes
            and row.role_record.normalized_problem_sha256 not in selected_hashes
        ]
        if not candidates:
            break
        best = min(
            candidates,
            key=lambda row: (
                abs((row.normalized_error_position or 0.0) - target),
                generator_counts[row.generator],
                deterministic_tie_break(seed, split, "error", target, row.source_record_id),
            ),
        )
        selected.append(best)
        selected_hashes.add(best.role_record.normalized_problem_sha256)
        generator_counts[best.generator] += 1
    return selected


def _select_correct_match(
    correct: list[ProcessBenchExample],
    *,
    error: ProcessBenchExample,
    selected_correct: list[ProcessBenchExample],
    used_problem_hashes: set[str],
    seed: int,
    split: str,
) -> tuple[ProcessBenchExample | None, dict[str, Any] | None, str | None]:
    used_correct_ids = {row.source_record_id for row in selected_correct}
    candidates = [
        row
        for row in correct
        if row.source_record_id not in used_correct_ids
        and row.role_record.normalized_problem_sha256 not in used_problem_hashes
    ]
    if not candidates:
        return None, None, None
    generator_counts = Counter(row.generator for row in selected_correct)
    p_error = error.normalized_error_position
    if p_error is None:
        raise AssertionError("error match cannot be all-correct")
    scored: list[tuple[tuple[float, float, float, int, str], ProcessBenchExample, str]] = []
    for row in candidates:
        tie = deterministic_tie_break(
            seed, split, "correct", error.source_record_id, row.source_record_id
        )
        matched_step = matched_correct_step(p_error, row.step_count)
        control_position = (matched_step + 0.5) / row.step_count
        position_distance = abs(control_position - p_error)
        log_step_count_distance = abs(math.log(row.step_count) - math.log(error.step_count))
        generator_mismatch_penalty = 0 if row.generator == error.generator else 1
        score_tuple = (
            generator_mismatch_penalty,
            position_distance,
            log_step_count_distance,
            generator_counts[row.generator],
            tie,
        )
        scored.append((score_tuple, row, tie))
    score_tuple, best, tie = min(scored, key=lambda item: item[0])
    score = {
        "deterministic_pairing_score": [
            score_tuple[0],
            score_tuple[1],
            score_tuple[2],
            score_tuple[3],
            score_tuple[4],
        ],
        "generator_matched": best.generator == error.generator,
        "generator_reuse_count": score_tuple[3],
        "log_step_count_distance": score_tuple[2],
        "position_distance": score_tuple[1],
        "tie_break_key": tie,
    }
    return best, score, tie


def _selection_entry(
    example: ProcessBenchExample,
    *,
    sampling_pair_id: str,
    sampling_pair_role: Literal["error_labelled_source_trace", "position_matched_control"],
    external_macro_step: int,
    matched_correct_step: int | None,
    pairing_metadata: dict[str, Any] | None,
    policy_id: str,
) -> dict[str, Any]:
    row = {
        **example.to_public_stub(),
        "external_macro_region": {
            "region_kind": "external_macro_region",
            "step_index": external_macro_step,
            "trace_provenance": "external_benchmark_trace",
        },
        "matched_correct_step": matched_correct_step,
        "native_trace_arm": {
            "candidate_region_policy": "future_behavioral_localization_policy",
            "materialization_status": "not_materialized",
            "processbench_label_used_for_region_selection": False,
            "trace_provenance": "target_checkpoint_native",
        },
        "pairing_metadata": pairing_metadata,
        "sampling_pair_id": sampling_pair_id,
        "sampling_pair_kind": "position_matched_sampling_control",
        "sampling_pair_role": sampling_pair_role,
    }
    row["dataset_role"] = "processbench_external_trace"
    row["selection_policy_id"] = policy_id
    return row


def _selection_composition(rows: list[dict[str, Any]]) -> dict[str, Any]:
    composition: dict[str, Any] = {}
    for split in PROCESSBENCH_OFFICIAL_SPLITS:
        split_rows = [row for row in rows if row["source_split"] == split]
        composition[split] = {
            "all_correct": sum(row["trace_class"] == "all_correct" for row in split_rows),
            "confirmation": sum(
                row["discovery_or_confirmation"] == "confirmation" for row in split_rows
            ),
            "discovery": sum(row["discovery_or_confirmation"] == "discovery" for row in split_rows),
            "erroneous": sum(row["trace_class"] == "erroneous" for row in split_rows),
            "generators": dict(sorted(Counter(row["generator"] for row in split_rows).items())),
            "row_count": len(split_rows),
        }
    return composition


def external_macro_region_for_example(
    example: ProcessBenchExample, *, matched_all_correct_step: int | None = None
) -> ExternalMacroRegion:
    if example.is_all_correct:
        if matched_all_correct_step is None:
            raise ValueError("all-correct external traces require a matched macro-step")
        step_index = matched_all_correct_step
        role = "matched_all_correct_macro_step"
    else:
        step_index = example.raw_label
        role = "gold_earliest_error_macro_step"
    if not 0 <= step_index < example.step_count:
        raise ValueError("external macro-region step index out of range")
    return ExternalMacroRegion(
        region_kind="external_macro_region",
        source_record_id=example.source_record_id,
        step_index=step_index,
        char_start=None,
        char_end=None,
        trace_provenance="external_benchmark_trace",
        processbench_label_role=role,
    )


def render_external_trace(
    example: ProcessBenchExample,
    *,
    policy: TraceRenderingPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or TraceRenderingPolicy()
    if policy.newline_convention != "lf":
        raise ValueError("only LF newline rendering is supported")
    if policy.tokenization_status != "character_spans_only":
        raise ValueError("tokenized rendering requires an explicit tokenizer materializer")
    prefix = "<think>\n" if policy.include_think_tags else ""
    suffix = "\n</think>" if policy.include_think_tags else ""
    pieces: list[str] = [prefix]
    spans: list[dict[str, Any]] = []
    offset = len(prefix)
    for index, step in enumerate(example.steps):
        normalized = unicodedata.normalize(policy.unicode_normalization_policy, step).strip()
        step_prefix = policy.step_prefix_format.format(step_index=index, step_number=index + 1)
        if index > 0:
            pieces.append(policy.step_delimiter)
            offset += len(policy.step_delimiter)
        pieces.append(step_prefix)
        offset += len(step_prefix)
        start = offset
        pieces.append(normalized)
        offset += len(normalized)
        spans.append(
            {
                "char_end": offset,
                "char_start": start,
                "region_kind": "external_macro_region",
                "step_index": index,
                "trace_provenance": "external_benchmark_trace",
            }
        )
    pieces.append(suffix)
    text = "".join(pieces)
    if "\r" in text:
        raise ValueError("rendered trace contains non-LF newline")
    identity = {
        "canonical_text": text,
        "policy": policy.to_identity_dict(),
        "source_record_id": example.source_record_id,
        "source_split": example.source_split,
    }
    return {
        "assistant_reasoning_boundary": None,
        "canonical_text": text,
        "chat_template_sha256": None,
        "prompt_token_ids": None,
        "rendering_sha256": canonical_sha256(identity),
        "source_record_id": example.source_record_id,
        "step_spans": spans,
        "tokenizer_sha256": None,
        "trace_provenance": "external_benchmark_trace",
        "trace_rendering_policy_id": policy.policy_id,
        "trace_rendering_policy_sha256": policy.policy_sha256,
    }


def validate_processbench_real_schema_integration(
    *,
    source_lock: ProcessBenchSourceLock,
    snapshot_dir: Path,
) -> dict[str, Any]:
    bundle = load_processbench_source(
        snapshot_dir=snapshot_dir,
        source_revision=source_lock.dataset_revision_sha,
        source_license=source_lock.source_license,
    )
    rows: list[dict[str, Any]] = []
    for split in PROCESSBENCH_OFFICIAL_SPLITS:
        split_records = [row for row in bundle.records if row.source_split == split]
        if not split_records:
            raise ValueError(f"materialized ProcessBench snapshot has no rows for {split}")
        example = split_records[0]
        rows.append(
            {
                "field_presence": {
                    "final_answer_correct": True,
                    "generator": True,
                    "id": True,
                    "label": True,
                    "problem": True,
                    "steps": True,
                },
                "field_types": {
                    "final_answer_correct": "bool",
                    "generator": "str",
                    "id": "str",
                    "label": "int",
                    "problem": "str",
                    "steps": "list[str]",
                },
                "label_valid": (
                    example.raw_label == -1 or 0 <= example.raw_label < example.step_count
                ),
                "normalized_problem_sha256": example.conservative_normalized_problem_sha256,
                "number_of_steps": example.step_count,
                "row_source_sha256": example.role_record.raw_source_sha256,
                "source_id": example.source_record_id,
                "split": split,
            }
        )
    return {
        "dataset_revision_sha": source_lock.dataset_revision_sha,
        "row_count_checked": len(rows),
        "schema_version": 1,
        "skipped": False,
        "validated_rows": rows,
    }


def processbench_integration_skip_report(
    *, source_lock_path: Path | None, snapshot_dir: Path | None
) -> dict[str, Any]:
    if source_lock_path is None or not source_lock_path.is_file():
        return {
            "reason": "formal ProcessBench source lock is not available",
            "schema_version": 1,
            "skipped": True,
            "synthetic_substitute_used": False,
        }
    if snapshot_dir is None or not snapshot_dir.is_dir():
        return {
            "reason": "materialized pinned ProcessBench snapshot is not available",
            "schema_version": 1,
            "skipped": True,
            "synthetic_substitute_used": False,
        }
    return validate_processbench_real_schema_integration(
        source_lock=load_formal_processbench_source_lock(source_lock_path),
        snapshot_dir=snapshot_dir,
    )


def scan_processbench_safe_artifact_paths(paths: list[Path]) -> dict[str, Any]:
    scanned: list[dict[str, Any]] = []
    violations: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            raise ValueError("ProcessBench safety scan requires explicit existing files")
        text = path.read_text(encoding="utf-8", errors="replace")
        scanned.append(
            {
                "path": path.name,
                "sha256": sha256_bytes(path.read_bytes()),
                "size_bytes": path.stat().st_size,
            }
        )
        for label, pattern in PROCESSBENCH_FORBIDDEN_OUTPUT_PATTERNS:
            if pattern.search(text):
                violations.append({"path": path.name, "violation": label})
    if violations:
        raise ValueError(f"unsafe ProcessBench output artifact: {violations}")
    return {"safe": True, "schema_version": 1, "scanned_files": scanned}


def write_inventory_files(
    inventory: dict[str, Any], *, output_json: Path, output_report: Path
) -> tuple[str, str]:
    inventory_hash = write_immutable(output_json, canonical_json_bytes(inventory))
    report = processbench_inventory_report(inventory)
    report_hash = write_immutable(output_report, (report + "\n").encode("utf-8"))
    return inventory_hash, report_hash


def split_selection_by_gate(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    discovery: list[dict[str, Any]] = []
    confirmation: list[dict[str, Any]] = []
    for row in rows:
        split = row["discovery_or_confirmation"]
        if split == "discovery":
            discovery.append(
                {
                    **row,
                    "confirmation_gate": {
                        "sealed": False,
                        "unseal_token_required": None,
                    },
                }
            )
        elif split == "confirmation":
            confirmation.append(
                {
                    **row,
                    "confirmation_gate": {
                        "required_policy_freezes": [
                            "selection_policy",
                            "rendering_policy",
                            "aru_segmentation_policy",
                            "intervention_policy",
                            "decision_thresholds",
                        ],
                        "sealed": True,
                        "unseal_token_required": CONFIRMATION_UNSEAL_TOKEN,
                    },
                }
            )
        else:
            raise ValueError("selection manifest rows must be discovery or confirmation")
    return discovery, confirmation


def write_split_selection_manifests(
    rows: list[dict[str, Any]],
    report: dict[str, Any],
    *,
    discovery_jsonl: Path,
    confirmation_jsonl: Path,
    output_report: Path,
) -> dict[str, str]:
    discovery, confirmation = split_selection_by_gate(rows)
    return {
        "confirmation_manifest_sha256": write_immutable(
            confirmation_jsonl, canonical_jsonl_bytes(confirmation)
        ),
        "discovery_manifest_sha256": write_immutable(
            discovery_jsonl, canonical_jsonl_bytes(discovery)
        ),
        "selection_report_sha256": write_immutable(
            output_report,
            (processbench_selection_report(report) + "\n").encode("utf-8"),
        ),
    }


def load_selection_manifest(
    path: Path,
    *,
    intended_split: DiscoveryOrConfirmation,
    unseal_confirmation: bool = False,
) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    for row in rows:
        if row.get("discovery_or_confirmation") != intended_split:
            raise ValueError("selection manifest split does not match intended analysis split")
        gate = row.get("confirmation_gate", {})
        if (
            intended_split == "confirmation"
            and gate.get("sealed") is True
            and not unseal_confirmation
        ):
            raise ValueError("confirmation manifest is sealed until explicit confirmation unseal")
    return rows


def processbench_inventory_report(inventory: dict[str, Any]) -> str:
    lines = [
        "# ProcessBench Inventory",
        "",
        f"Source dataset: `{inventory['dataset']}`",
        f"Source revision: `{inventory['source_revision']}`",
        f"Source license: `{inventory['source_license']}`",
        f"Observed total rows: `{inventory['observed_total_row_count']}`",
        "",
        (
            "This report contains aggregate inventory only. It does not contain raw "
            "problems or traces."
        ),
        "",
        f"Semantics receipts: `{inventory.get('semantics_source_receipts', {})}`",
        "",
        "## Splits",
    ]
    for split in PROCESSBENCH_OFFICIAL_SPLITS:
        data = inventory["splits"][split]
        lines.extend(
            [
                "",
                f"### {split}",
                "",
                f"- rows: {data['row_count']}",
                f"- all-correct: {data['all_correct_count']}",
                f"- erroneous: {data['error_count']}",
                f"- label/final-answer crosstab: {data['label_final_answer_crosstab']}",
                f"- error but final correct: {data['error_but_final_correct_count']}",
                f"- all-correct label but final wrong: {data['all_correct_but_final_wrong_count']}",
                f"- generators: {data['generator_distribution']}",
                f"- split x generator x trace status: {data['split_generator_trace_status']}",
                f"- steps distribution: {data['number_of_steps_distribution']}",
                f"- step quantiles: {data['step_count_quantiles']}",
                f"- earliest-error positions: {data['earliest_error_position_distribution']}",
                f"- normalized-error bins: {data['normalized_error_position_distribution']}",
                f"- normalized-error quantiles: {data['normalized_error_position_quantiles']}",
                f"- malformed fields: {data['malformed_field_counts']}",
            ]
        )
    lines.extend(
        [
            "",
            "## Duplicate Normalized Problems",
            "",
            "Conservative within splits: "
            f"{inventory['conservative_duplicate_hashes_within_splits']}",
            "Conservative across splits: "
            f"{inventory['conservative_duplicate_hashes_across_splits']}",
            f"Aggressive review clusters: {inventory['aggressive_duplicate_review_clusters']}",
        ]
    )
    return "\n".join(lines)


def processbench_selection_report(report: dict[str, Any]) -> str:
    lines = [
        "# ProcessBench Pilot Selection",
        "",
        f"Policy: `{report['policy_id']}`",
        f"Seed: `{report['seed']}`",
        f"Source revision: `{report['source_revision']}`",
        f"Selected problems: {report['selected_problem_count']}",
        f"Sampling pairs: {report['sampling_pair_count']}",
        "",
        "This report lists source IDs and hashes only. It does not contain raw benchmark text.",
        "",
        "## Composition",
        "",
    ]
    for split, item in report["split_composition"].items():
        lines.append(f"- {split}: {item}")
    lines.extend(["", "## Shortfalls", "", str(report["shortfalls"]), "", "## Sampling Pairs", ""])
    for pair in report["sampling_pairs"]:
        lines.append(f"- {pair}")
    return "\n".join(lines)
