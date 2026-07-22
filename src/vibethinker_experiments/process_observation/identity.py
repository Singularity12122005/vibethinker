"""Stable identities and canonical bytes for process-observation artifacts."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from vibethinker_experiments.evaluation.io import (
    canonical_json,
    index_unique,
    jsonl_bytes,
    sha256_bytes,
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_KEY_PARTS = ("api_key", "apikey", "secret", "credential", "password")
SECRET_TOKEN_KEYS = {"token", "access_token", "bearer_token", "refresh_token"}
PRIVATE_LOCATION_KEYS = ("endpoint", "url", "locator", "cache", "path")
RUNTIME_ONLY_KEY_PARTS = ("created_at", "timestamp", "updated_at", "wall_clock")


def canonical_json_bytes(value: Any) -> bytes:
    """Return UTF-8, no-BOM, LF-terminated canonical JSON bytes."""

    return (canonical_json(value) + "\n").encode("utf-8")


def canonical_jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Return deterministic JSONL bytes with exactly one LF after every row."""

    return jsonl_bytes(rows)


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def assert_sha256(value: str | None, field: str) -> None:
    if value is not None and not SHA256_RE.match(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest or null")


def is_absolute_locator(value: str) -> bool:
    text = str(value)
    if PurePosixPath(text).is_absolute() or PureWindowsPath(text).is_absolute():
        return True
    return bool(re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("\\\\"))


def assert_public_identity(value: Any, *, path: str = "identity") -> None:
    """Reject secrets, endpoints, and local absolute paths from stable identities."""

    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).casefold()
            if any(part in lowered for part in SECRET_KEY_PARTS) or lowered in SECRET_TOKEN_KEYS:
                raise ValueError(f"{path}.{key}: secret-like keys cannot enter public identity")
            if any(part in lowered for part in RUNTIME_ONLY_KEY_PARTS):
                raise ValueError(f"{path}.{key}: runtime timestamps cannot enter public identity")
            if any(part in lowered for part in PRIVATE_LOCATION_KEYS):
                text = str(item)
                if "://" in text or is_absolute_locator(text):
                    raise ValueError(
                        f"{path}.{key}: runtime locations cannot enter public identity"
                    )
            assert_public_identity(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_public_identity(item, path=f"{path}[{index}]")
    elif isinstance(value, str):
        if "://" in value or is_absolute_locator(value):
            raise ValueError(f"{path}: endpoints and absolute paths are runtime-only")


def validate_no_duplicate_ids(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return index_unique(rows, key)


def checkpoint_manifest_hash_if_committed(runtime_locator: str | None) -> str | None:
    """Validate an existing committed checkpoint and return its manifest hash.

    Missing runtime locators are evidence gaps, not failures: callers should record an
    unverified checkpoint reference instead of manufacturing a receipt.
    """

    if runtime_locator is None:
        return None
    from vibethinker_experiments.checkpoints.core import validate_committed_checkpoint

    root = Path(runtime_locator)
    manifest_path = root / "metadata" / "checkpoint.json"
    if not manifest_path.is_file() or not (root / "metadata" / "COMMITTED").is_file():
        return None
    validate_committed_checkpoint(root)
    return sha256_bytes(manifest_path.read_bytes())
