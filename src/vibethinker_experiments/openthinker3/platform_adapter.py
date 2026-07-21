"""Sanitized platform adapter for the frozen four-node training contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .checkpoint import validate_replicated_resume_checkpoint
from .data_contract import sha256
from .training import load_training_contract

_ARCHIVE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Topology:
    node_rank: int
    node_count: int
    head_address: str
    head_port: int


def load_platform_config(path: str | Path) -> dict[str, Any]:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("unsupported platform adapter config")
    return config


def load_runtime_manifest(path: str | Path) -> dict[str, Any]:
    manifest = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported external runtime manifest")
    return manifest


def runtime_archive_identity(
    training: Mapping[str, Any], runtime_manifest: Mapping[str, Any]
) -> tuple[str, str]:
    resolved_config = str(training["resolved_config"])
    if runtime_manifest.get("resolved_config") != resolved_config:
        raise ValueError("runtime manifest resolved_config does not match training contract")
    archive_sha256 = str(runtime_manifest.get("runtime_archive_sha256", ""))
    if not _ARCHIVE_SHA256.fullmatch(archive_sha256):
        raise ValueError("runtime manifest must provide a lowercase 64-hex archive SHA-256")
    return archive_sha256, resolved_config


def _first_environment(
    environment: Mapping[str, str], names: list[str], *, default: str | None = None
) -> str:
    for name in names:
        if environment.get(name):
            return environment[name]
    if default is not None:
        return default
    raise RuntimeError(f"none of the required environment variables are set: {names}")


def resolve_topology(
    platform: Mapping[str, Any], environment: Mapping[str, str] | None = None
) -> Topology:
    values = os.environ if environment is None else environment
    rendezvous = platform["rendezvous"]
    return Topology(
        node_rank=int(_first_environment(values, rendezvous["node_rank_envs"])),
        node_count=int(_first_environment(values, rendezvous["node_count_envs"])),
        head_address=_first_environment(values, rendezvous["head_address_envs"]),
        head_port=int(
            _first_environment(
                values,
                rendezvous["head_port_envs"],
                default=str(rendezvous["default_head_port"]),
            )
        ),
    )


def validate_topology(topology: Topology, training: Mapping[str, Any]) -> None:
    expected_nodes = int(training["resources"]["nodes"])
    if topology.node_count != expected_nodes:
        raise RuntimeError(f"expected {expected_nodes} nodes, got {topology.node_count}")
    if topology.node_rank not in range(expected_nodes):
        raise RuntimeError(f"node rank is outside 0..{expected_nodes - 1}: {topology.node_rank}")
    if not topology.head_address or not 1 <= topology.head_port <= 65535:
        raise RuntimeError("invalid rendezvous address or port")


def validate_artifacts(
    *,
    runtime_archive: str | Path,
    train_data: str | Path,
    training: Mapping[str, Any],
    runtime_manifest: Mapping[str, Any],
) -> None:
    expected_runtime_sha, _resolved_config = runtime_archive_identity(training, runtime_manifest)
    actual_runtime_sha = sha256(runtime_archive)
    if actual_runtime_sha != expected_runtime_sha:
        raise RuntimeError(
            f"runtime archive SHA mismatch: {actual_runtime_sha} != {expected_runtime_sha}"
        )
    actual_data_sha = sha256(train_data)
    expected_data_sha = str(training["data"]["archive_sha256"])
    if actual_data_sha != expected_data_sha:
        raise RuntimeError(f"training data SHA mismatch: {actual_data_sha} != {expected_data_sha}")


def prepare_resume_link(
    checkpoint: str | Path,
    *,
    scratch_dir: str | Path,
    world_size: int,
) -> Path:
    """Create the same explicit global-step path on every node."""

    checkpoint = Path(checkpoint).resolve()
    global_step = validate_replicated_resume_checkpoint(checkpoint, world_size)
    namespace = hashlib.sha256(str(checkpoint).encode("utf-8")).hexdigest()[:12]
    parent = Path(scratch_dir).resolve() / f"resume-{namespace}"
    parent.mkdir(parents=True, exist_ok=True)
    link = parent / f"global_step_{global_step}"
    if link.is_symlink():
        if link.resolve() == checkpoint:
            return link
        link.unlink()
    elif link.exists():
        raise RuntimeError(f"refusing to replace non-symlink resume path: {link}")
    link.symlink_to(checkpoint, target_is_directory=True)
    return link


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-config", type=Path, required=True)
    parser.add_argument("--platform-config", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--runtime-archive", type=Path, required=True)
    parser.add_argument("--train-data", type=Path, required=True)
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--scratch-dir", type=Path)
    args = parser.parse_args()

    training = load_training_contract(args.training_config)
    platform = load_platform_config(args.platform_config)
    runtime_manifest = load_runtime_manifest(args.runtime_manifest)
    topology = resolve_topology(platform)
    validate_topology(topology, training)
    validate_artifacts(
        runtime_archive=args.runtime_archive,
        train_data=args.train_data,
        training=training,
        runtime_manifest=runtime_manifest,
    )
    archive_sha256, resolved_config = runtime_archive_identity(training, runtime_manifest)
    result: dict[str, object] = {
        "topology": topology.__dict__,
        "runtime_identity": f"sha256:{archive_sha256}+config:{resolved_config}",
        "status": "PASS",
    }
    if args.resume_checkpoint:
        if not args.scratch_dir:
            parser.error("--scratch-dir is required with --resume-checkpoint")
        result["resume_path"] = str(
            prepare_resume_link(
                args.resume_checkpoint,
                scratch_dir=args.scratch_dir,
                world_size=training["resources"]["nodes"] * training["resources"]["gpus_per_node"],
            )
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
