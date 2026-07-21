from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibethinker_experiments.checkpoints import validate_committed_checkpoint
from vibethinker_experiments.openthinker3.algorithm import (
    AdaptiveEntropyController,
    select_nonconstant_group_indices,
)
from vibethinker_experiments.openthinker3.checkpoint import (
    mark_checkpoint_committed,
    should_save_checkpoint,
    validate_replicated_actor_checkpoint,
    validate_replicated_resume_checkpoint,
)


def _write_replicated_actor(root: Path, world_size: int) -> None:
    actor = root / "actor"
    actor.mkdir()
    (actor / "replicated_data_parallel.json").write_text(
        json.dumps({"model_optimizer_rank": 0, "world_size": world_size}) + "\n"
    )
    (actor / f"model_world_size_{world_size}_rank_0.pt").write_bytes(b"model")
    (actor / f"optim_world_size_{world_size}_rank_0.pt").write_bytes(b"optim")
    for rank in range(world_size):
        (actor / f"extra_state_world_size_{world_size}_rank_{rank}.pt").write_bytes(b"rng")


def test_group_filter_keeps_complete_dispatchable_groups() -> None:
    uids = ["a"] * 16 + ["b"] * 16 + ["c"] * 16 + ["d"] * 16
    scores = [0] * 16 + [0, 1] * 8 + [1, 0] * 8 + [1] * 16
    selected, stats = select_nonconstant_group_indices(uids, scores, group_size=16, world_size=32)
    assert len(selected) == 32
    assert {uids[index] for index in selected} == {"b", "c"}
    assert stats["group_filter/all_zero"] == 1
    assert stats["group_filter/all_one"] == 1


def test_group_filter_enforces_binary_complete_groups() -> None:
    with pytest.raises(ValueError, match="binary reward"):
        select_nonconstant_group_indices(["x"] * 16, [0.5] * 16, group_size=16, world_size=32)
    with pytest.raises(ValueError, match="incomplete"):
        select_nonconstant_group_indices(["x"] * 15, [0] * 15, group_size=16, world_size=32)


def test_adaptive_entropy_round_trip_and_bounds() -> None:
    controller = AdaptiveEntropyController()
    controller.update(0.1)
    assert controller.realized_value == pytest.approx(0.0001)
    state = controller.state_dict()
    restored = AdaptiveEntropyController()
    restored.load_state_dict(state)
    assert restored.state_dict() == state
    restored.update(0.3)
    assert restored.value == 0.0
    assert restored.realized_value == 0.0


def test_checkpoint_schedule_includes_frequency_epoch_and_last_step() -> None:
    assert should_save_checkpoint(
        global_step=50,
        save_freq=50,
        steps_per_epoch=263,
        is_last_step=False,
        esi_close_to_expiration=False,
    )
    assert should_save_checkpoint(
        global_step=263,
        save_freq=50,
        steps_per_epoch=263,
        is_last_step=False,
        esi_close_to_expiration=False,
    )
    assert not should_save_checkpoint(
        global_step=51,
        save_freq=50,
        steps_per_epoch=263,
        is_last_step=False,
        esi_close_to_expiration=False,
    )


def test_replicated_resume_contract(tmp_path: Path) -> None:
    _write_replicated_actor(tmp_path, 2)
    (tmp_path / "data.pt").write_bytes(b"loader")
    (tmp_path / "adaptive_entropy.json").write_text(
        json.dumps(AdaptiveEntropyController().state_dict()) + "\n"
    )
    mark_checkpoint_committed(tmp_path, 50, None)
    manifest = validate_committed_checkpoint(tmp_path)
    assert manifest["global_step"] == 50
    assert manifest["metadata"]["family"] == "openthinker3"
    assert len(manifest["files"]) == 8
    validate_replicated_actor_checkpoint(tmp_path, 2)
    assert validate_replicated_resume_checkpoint(tmp_path, 2) == 50


def test_replicated_checkpoint_rejects_duplicate_model_state(tmp_path: Path) -> None:
    _write_replicated_actor(tmp_path, 2)
    (tmp_path / "actor" / "model_world_size_2_rank_1.pt").write_bytes(b"duplicate")
    with pytest.raises(RuntimeError, match="duplicate"):
        validate_replicated_actor_checkpoint(tmp_path, 2)
