"""原子 artifact manifest 与可注入的结果发布协议。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from ..common.hashing import file_sha256, sha256_text
from ..common.io import write_json


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _resolve_artifact(root: Path, value: str | Path) -> tuple[str, Path]:
    relative = PurePosixPath(Path(value).as_posix())
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in {"", "."}:
        raise ValueError(f"artifact path must be safe and relative: {value}")
    path = (root / relative.as_posix()).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"artifact escapes publication root: {value}") from exc
    if not path.is_file():
        raise ValueError(f"artifact does not exist: {relative.as_posix()}")
    return relative.as_posix(), path


def build_artifact_manifest(
    root: str | Path,
    artifacts: Sequence[str | Path],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = Path(root)
    if not artifacts:
        raise ValueError("at least one artifact is required")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in artifacts:
        relative, path = _resolve_artifact(base, value)
        if relative in seen:
            raise ValueError(f"duplicate artifact: {relative}")
        seen.add(relative)
        entries.append({"path": relative, "size": path.stat().st_size, "sha256": file_sha256(path)})
    entries.sort(key=lambda item: item["path"])
    identity = {"format_version": 1, "files": entries, "metadata": dict(metadata or {})}
    return {**identity, "content_sha256": sha256_text(canonical_json(identity))}


def write_artifact_manifest(
    path: str | Path,
    root: str | Path,
    artifacts: Sequence[str | Path],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = build_artifact_manifest(root, artifacts, metadata=metadata)
    write_json(path, manifest)
    return manifest


def verify_artifact_manifest(root: str | Path, manifest: Mapping[str, Any]) -> None:
    identity = {
        "format_version": manifest.get("format_version"),
        "files": manifest.get("files"),
        "metadata": manifest.get("metadata"),
    }
    if identity["format_version"] != 1:
        raise ValueError("unsupported artifact manifest")
    if manifest.get("content_sha256") != sha256_text(canonical_json(identity)):
        raise ValueError("artifact manifest identity hash mismatch")
    expected = list(identity["files"] or [])
    rebuilt = build_artifact_manifest(
        root,
        [str(item["path"]) for item in expected],
        metadata=identity["metadata"],
    )
    if rebuilt != dict(manifest):
        raise ValueError("artifact bytes no longer match manifest")


class PublishAdapter(Protocol):
    """对象存储、数据平台或复制操作的注入边界。"""

    def publish(
        self, root: Path, manifest_path: Path, manifest: Mapping[str, Any]
    ) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class CallbackPublisher:
    callback: Callable[[Path, Path, Mapping[str, Any]], Mapping[str, Any] | None]

    def publish(
        self, root: Path, manifest_path: Path, manifest: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        return self.callback(root, manifest_path, manifest)


@dataclass(frozen=True)
class PublicationResult:
    manifest: Mapping[str, Any]
    receipt: Mapping[str, Any]
    receipt_path: Path


def publish_results(
    root: str | Path,
    artifacts: Sequence[str | Path],
    publisher: PublishAdapter,
    *,
    manifest_name: str = "manifest.json",
    receipt_name: str = "PUBLISHED.json",
    metadata: Mapping[str, Any] | None = None,
) -> PublicationResult:
    """先冻结 manifest，再发布，成功后最后原子写 receipt。"""
    base = Path(root)
    manifest_relative, _ = _resolve_output_path(base, manifest_name)
    receipt_relative, receipt_path = _resolve_output_path(base, receipt_name)
    if manifest_relative == receipt_relative:
        raise ValueError("manifest and receipt paths must differ")
    manifest_path = base / manifest_relative
    manifest = write_artifact_manifest(
        manifest_path,
        base,
        artifacts,
        metadata=metadata,
    )
    manifest_hash = file_sha256(manifest_path)
    adapter_receipt = dict(publisher.publish(base, manifest_path, manifest) or {})
    verify_artifact_manifest(base, manifest)
    if file_sha256(manifest_path) != manifest_hash:
        raise ValueError("manifest changed during publication")
    receipt = {
        "format_version": 1,
        "manifest": manifest_relative,
        "manifest_sha256": manifest_hash,
        "publication": adapter_receipt,
    }
    write_json(receipt_path, receipt)
    return PublicationResult(manifest, receipt, receipt_path)


def _resolve_output_path(root: Path, value: str | Path) -> tuple[str, Path]:
    relative = PurePosixPath(Path(value).as_posix())
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in {"", "."}:
        raise ValueError(f"output path must be safe and relative: {value}")
    path = root / relative.as_posix()
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"output path escapes publication root: {value}") from exc
    return relative.as_posix(), path
