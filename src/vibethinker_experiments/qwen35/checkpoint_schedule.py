"""Qwen3.5 adapter for the shared checkpoint contract."""

from __future__ import annotations

from pathlib import Path

from ..checkpoints.core import (
    checkpoint_save_decision,
    commit_checkpoint_tree,
    validate_committed_checkpoint,
)

__all__ = [
    "mark_checkpoint_committed",
    "should_save_training_checkpoint",
    "validate_committed_checkpoint",
]


def should_save_training_checkpoint(
    *,
    global_steps: int,
    save_freq: int,
    steps_per_epoch: int,
    is_last_step: bool,
    esi_close_to_expiration: bool,
) -> bool:
    if save_freq <= 0:
        return False
    return checkpoint_save_decision(
        global_step=global_steps,
        save_frequency=save_freq,
        steps_per_epoch=steps_per_epoch,
        is_last_step=is_last_step,
        close_to_expiration=esi_close_to_expiration,
    ).should_save


def mark_checkpoint_committed(checkpoint_dir: str | Path, global_step: int) -> Path:
    return commit_checkpoint_tree(
        checkpoint_dir,
        global_step=global_step,
        metadata={"family": "qwen35", "framework": "verl-v0.8.0"},
    )
