"""Checkpoint scheduling and compact pure-data-parallel restore contracts."""

from __future__ import annotations

import json
from pathlib import Path

from ..checkpoints.core import (
    checkpoint_save_decision,
    commit_checkpoint_tree,
    validate_committed_checkpoint,
)

ENTROPY_STATE_KEYS = {
    "value",
    "target_entropy",
    "min_value",
    "max_value",
    "delta",
    "loss_enabled",
}


def should_save_checkpoint(
    *,
    global_step: int,
    save_freq: int,
    steps_per_epoch: int,
    is_last_step: bool,
    esi_close_to_expiration: bool,
) -> bool:
    if save_freq <= 0:
        return False
    return checkpoint_save_decision(
        global_step=global_step,
        save_frequency=save_freq,
        steps_per_epoch=steps_per_epoch,
        is_last_step=is_last_step,
        close_to_expiration=esi_close_to_expiration,
    ).should_save


def mark_checkpoint_committed(path: str | Path, global_step: int, epoch: int | None) -> Path:
    metadata = Path(path) / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    manifest = metadata / "training_state.json"
    manifest.write_text(
        json.dumps({"global_step": global_step, "completed_epoch": epoch}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return commit_checkpoint_tree(
        path,
        global_step=global_step,
        metadata={
            "completed_epoch": epoch,
            "family": "openthinker3",
            "framework": "verl",
        },
    )


def validate_replicated_actor_checkpoint(path: str | Path, world_size: int) -> None:
    """Validate one model/optimizer copy plus per-rank RNG state."""

    if world_size < 1:
        raise ValueError("world_size must be positive")
    actor = Path(path) / "actor"
    required = [
        actor / "replicated_data_parallel.json",
        actor / f"model_world_size_{world_size}_rank_0.pt",
        actor / f"optim_world_size_{world_size}_rank_0.pt",
    ]
    required.extend(
        actor / f"extra_state_world_size_{world_size}_rank_{rank}.pt" for rank in range(world_size)
    )
    missing = [str(item) for item in required if not item.is_file() or item.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"replicated actor checkpoint is incomplete: {missing[:8]}")

    duplicates = [
        item.name
        for item in actor.glob("*_world_size_*_rank_*.pt")
        if item.name.startswith(("model_", "optim_")) and not item.name.endswith("_rank_0.pt")
    ]
    if duplicates:
        raise RuntimeError(
            "replicated actor checkpoint contains duplicate model/optimizer states: "
            f"{duplicates[:8]}"
        )

    manifest = json.loads((actor / "replicated_data_parallel.json").read_text(encoding="utf-8"))
    expected = {"world_size": world_size, "model_optimizer_rank": 0}
    if manifest != expected:
        raise RuntimeError(f"replicated actor manifest mismatch: {manifest} != {expected}")


def validate_replicated_resume_checkpoint(path: str | Path, world_size: int) -> int:
    """Validate an archived checkpoint before distributed restore."""

    root = Path(path)
    try:
        validate_committed_checkpoint(root)
    except ValueError as exc:
        raise RuntimeError(f"checkpoint commit validation failed: {exc}") from exc
    required = [
        root / "metadata" / "COMMITTED",
        root / "metadata" / "training_state.json",
        root / "data.pt",
        root / "adaptive_entropy.json",
    ]
    missing = [str(item) for item in required if not item.is_file() or item.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"resume checkpoint is incomplete: {missing}")

    state = json.loads(required[1].read_text(encoding="utf-8"))
    global_step = state.get("global_step")
    if not isinstance(global_step, int) or global_step < 1:
        raise RuntimeError(f"invalid resume global_step: {global_step!r}")
    entropy_state = json.loads(required[3].read_text(encoding="utf-8"))
    if set(entropy_state) != ENTROPY_STATE_KEYS:
        raise RuntimeError(
            f"adaptive entropy state keys mismatch: {set(entropy_state)} != {ENTROPY_STATE_KEYS}"
        )
    validate_replicated_actor_checkpoint(root, world_size)
    return global_step
