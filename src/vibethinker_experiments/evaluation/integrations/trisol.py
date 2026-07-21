"""Sanitized optional TriSol result import contract.

This adapter contains no internal team, endpoint, credential, candidate ID, or
job naming convention. Authentication remains the responsibility of an
operator-provided client implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..io import read_json, sha256_file


class ResultDownloader(Protocol):
    def download_result(self, opaque_job_reference: str, destination: Path) -> None: ...


def import_generated_result(
    client: ResultDownloader,
    *,
    opaque_job_reference: str,
    destination: str | Path,
    expected_panel_sha256: str,
) -> Path:
    """Download and verify a platform-neutral generated-result directory."""

    if not opaque_job_reference or any(char.isspace() for char in opaque_job_reference):
        raise ValueError("job reference must be a non-empty opaque token")
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    client.download_result(opaque_job_reference, root)
    manifest_path = root / "generation_manifest.json"
    results_path = root / "generation_results.jsonl"
    generated_path = root / "GENERATED.json"
    if not all(path.is_file() for path in (manifest_path, results_path, generated_path)):
        raise ValueError("download does not satisfy the GENERATED artifact contract")
    manifest: dict[str, Any] = read_json(manifest_path)
    marker = read_json(generated_path)
    if manifest.get("panel", {}).get("panel_sha256") != expected_panel_sha256:
        raise ValueError("download used a different panel")
    if marker.get("generation_results_sha256") != sha256_file(results_path):
        raise ValueError("downloaded generation checksum mismatch")
    return root
