"""平台无关的 checkpoint 保存、提交标记和 guardian 决策。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from ..common.hashing import file_sha256
from ..common.io import atomic_write_text, write_json


@dataclass(frozen=True)
class SaveDecision:
    should_save: bool
    reasons: tuple[str, ...] = ()


def checkpoint_save_decision(
    *,
    global_step: int,
    save_frequency: int,
    steps_per_epoch: int = 0,
    is_last_step: bool = False,
    close_to_expiration: bool = False,
) -> SaveDecision:
    """最终步和临近回收优先；save_frequency<=0 仅关闭周期保存。"""
    if global_step < 0:
        raise ValueError("global_step cannot be negative")
    reasons: list[str] = []
    if is_last_step:
        reasons.append("last_step")
    if close_to_expiration:
        reasons.append("close_to_expiration")
    if save_frequency > 0 and global_step > 0 and global_step % save_frequency == 0:
        reasons.append("periodic")
    if steps_per_epoch > 0 and global_step > 0 and global_step % steps_per_epoch == 0:
        reasons.append("epoch_boundary")
    return SaveDecision(bool(reasons), tuple(reasons))


class CheckpointStoreAdapter(Protocol):
    """训练框架负责把状态写到给定目录。"""

    def save(self, checkpoint_dir: Path, global_step: int) -> None: ...


class CheckpointPublisher(Protocol):
    """平台上传、对象存储或复制逻辑由调用方注入。"""

    def publish(
        self, checkpoint_dir: Path, global_step: int, metadata: Mapping[str, Any]
    ) -> Mapping[str, Any] | None: ...


def save_checkpoint_if_due(
    store: CheckpointStoreAdapter,
    checkpoint_dir: str | Path,
    *,
    global_step: int,
    save_frequency: int,
    steps_per_epoch: int = 0,
    is_last_step: bool = False,
    close_to_expiration: bool = False,
    required_files: Sequence[str | Path] = (),
    metadata: Mapping[str, Any] | None = None,
) -> SaveDecision:
    """执行纯决策、adapter 保存和最终提交，未到期时不产生目录。"""
    decision = checkpoint_save_decision(
        global_step=global_step,
        save_frequency=save_frequency,
        steps_per_epoch=steps_per_epoch,
        is_last_step=is_last_step,
        close_to_expiration=close_to_expiration,
    )
    if not decision.should_save:
        return decision
    path = Path(checkpoint_dir)
    (path / "metadata" / "COMMITTED").unlink(missing_ok=True)
    store.save(path, global_step)
    commit_checkpoint(
        path,
        global_step=global_step,
        required_files=required_files,
        metadata={"save_reasons": list(decision.reasons), **dict(metadata or {})},
    )
    return decision


def _safe_relative(value: str | Path) -> str:
    path = PurePosixPath(Path(value).as_posix())
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise ValueError(f"checkpoint file must be a safe relative path: {value}")
    return path.as_posix()


def _resolve_checkpoint_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"checkpoint file escapes root: {relative}") from exc
    return path


def commit_checkpoint(
    checkpoint_dir: str | Path,
    *,
    global_step: int,
    required_files: Sequence[str | Path] = (),
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """验证文件后原子写 manifest，最后写 COMMITTED marker。"""
    if global_step < 0:
        raise ValueError("global_step cannot be negative")
    root = Path(checkpoint_dir)
    root.mkdir(parents=True, exist_ok=True)
    metadata_dir = root / "metadata"
    marker = metadata_dir / "COMMITTED"
    marker.unlink(missing_ok=True)
    files: list[dict[str, Any]] = []
    for value in sorted({_safe_relative(item) for item in required_files}):
        path = _resolve_checkpoint_file(root, value)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"checkpoint file is missing or empty: {value}")
        files.append({"path": value, "size": path.stat().st_size, "sha256": file_sha256(path)})
    manifest = {
        "format_version": 1,
        "global_step": global_step,
        "files": files,
        "metadata": dict(metadata or {}),
    }
    manifest_path = metadata_dir / "checkpoint.json"
    write_json(manifest_path, manifest)
    atomic_write_text(marker, file_sha256(manifest_path) + "\n")
    return marker


def commit_checkpoint_tree(
    checkpoint_dir: str | Path,
    *,
    global_step: int,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Hash every checkpoint artifact, then atomically publish the shared marker."""
    root = Path(checkpoint_dir)
    excluded = {
        "metadata/.COMMITTED.tmp",
        "metadata/COMMITTED",
        "metadata/checkpoint.json",
    }
    required_files = [
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in excluded
    ]
    return commit_checkpoint(
        root,
        global_step=global_step,
        required_files=required_files,
        metadata=metadata,
    )


def validate_committed_checkpoint(checkpoint_dir: str | Path) -> dict[str, Any]:
    root = Path(checkpoint_dir)
    manifest_path = root / "metadata" / "checkpoint.json"
    marker = root / "metadata" / "COMMITTED"
    if not manifest_path.is_file() or not marker.is_file():
        raise ValueError("checkpoint is not committed")
    expected_manifest_hash = marker.read_text(encoding="utf-8").strip()
    if expected_manifest_hash != file_sha256(manifest_path):
        raise ValueError("checkpoint manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1 or not isinstance(manifest.get("global_step"), int):
        raise ValueError("invalid checkpoint manifest")
    files = manifest.get("files")
    if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
        raise ValueError("invalid checkpoint file manifest")
    for item in files:
        relative = _safe_relative(str(item.get("path", "")))
        path = _resolve_checkpoint_file(root, relative)
        if (
            not path.is_file()
            or path.stat().st_size != item.get("size")
            or file_sha256(path) != item.get("sha256")
        ):
            raise ValueError(f"committed checkpoint file mismatch: {relative}")
    return manifest


@dataclass(frozen=True)
class GuardianConfig:
    every_n_steps: int = 100
    require_committed: bool = True

    def __post_init__(self) -> None:
        if self.every_n_steps < 1:
            raise ValueError("every_n_steps must be positive")


@dataclass(frozen=True)
class GuardianDecision:
    should_publish: bool
    reason: str
    global_step: int
    checkpoint_dir: Path


@dataclass
class CheckpointGuardian:
    publisher: CheckpointPublisher
    config: GuardianConfig = field(default_factory=GuardianConfig)
    last_published_step: int = 0

    def decide(
        self,
        checkpoint_dir: str | Path,
        *,
        global_step: int,
        is_primary: bool = True,
    ) -> GuardianDecision:
        path = Path(checkpoint_dir)
        if not is_primary:
            return GuardianDecision(False, "not_primary", global_step, path)
        if global_step <= 0:
            return GuardianDecision(False, "invalid_step", global_step, path)
        if global_step - self.last_published_step < self.config.every_n_steps:
            return GuardianDecision(False, "interval_not_reached", global_step, path)
        if not path.is_dir():
            return GuardianDecision(False, "checkpoint_missing", global_step, path)
        if self.config.require_committed:
            try:
                validate_committed_checkpoint(path)
            except ValueError:
                return GuardianDecision(False, "checkpoint_not_committed", global_step, path)
        return GuardianDecision(True, "periodic_snapshot", global_step, path)

    def publish_if_due(
        self,
        checkpoint_dir: str | Path,
        *,
        global_step: int,
        is_primary: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> GuardianDecision:
        decision = self.decide(
            checkpoint_dir,
            global_step=global_step,
            is_primary=is_primary,
        )
        if not decision.should_publish:
            return decision
        self.publisher.publish(decision.checkpoint_dir, global_step, dict(metadata or {}))
        self.last_published_step = global_step
        return decision
