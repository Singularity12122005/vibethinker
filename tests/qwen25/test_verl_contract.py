from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibethinker_experiments.checkpoints import validate_committed_checkpoint
from vibethinker_experiments.qwen25.checkpoint_schedule import (
    epoch_boundaries,
    mark_checkpoint_committed,
    should_save_training_checkpoint,
)
from vibethinker_experiments.qwen25.sft import expected_optimizer_steps
from vibethinker_experiments.qwen25.verl_launcher import (
    build_command,
    load_config,
    validate_formal_run_inputs,
)

ROOT = Path(__file__).resolve().parents[2]


def test_sft_steps_round_each_epoch_after_distributed_sharding() -> None:
    assert expected_optimizer_steps(15_000, 10, 128) == 1_180
    assert expected_optimizer_steps(30_000, 10, 128) == 2_350


def test_formal_launcher_rejects_wrong_sft_lineage_before_execution(tmp_path: Path) -> None:
    receipt = tmp_path / "model.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "lineage": "qwen25-15k",
                "sft_epoch": 5,
                "adapter_sha256": "a" * 64,
            }
        )
    )
    empty = tmp_path / "empty.json"
    empty.write_text("{}")
    with pytest.raises(ValueError, match="lineage"):
        validate_formal_run_inputs(
            lineage="qwen25-15k",
            model_path=tmp_path / "model",
            train_file=tmp_path / "train.parquet",
            model_receipt_path=receipt,
            data_receipt_path=empty,
            runtime_receipt_path=empty,
        )


def test_frozen_rl_config_has_shared_formal_contract():
    config = load_config(ROOT / "configs" / "qwen25" / "verl_math500_64k.yaml")
    assert config["data"]["prompt_rows"] == 500
    assert config["data"]["max_prompt_length"] == 768
    assert config["data"]["max_response_length"] == 64768
    assert config["cluster"] == {
        "nodes": 2,
        "gpus_per_node": 8,
        "gpu_class": "A100-80GB",
    }
    assert config["rollout"]["group_size"] == 8
    assert config["training"]["formal_completed_boundary"] == "epoch_1"
    assert config["training"]["full_five_epoch_completion_claim"] is False


def test_launcher_builds_public_verl_command():
    config = load_config(ROOT / "configs" / "qwen25" / "verl_math500_64k.yaml")
    command = build_command(
        config,
        model_path="MODEL",
        train_file="TRAIN",
        output_dir="OUTPUT",
    )
    joined = " ".join(command)
    assert command[:3] == ["python3", "-m", "verl.trainer.main_ppo"]
    assert "data.train_batch_size=16" in joined
    assert "actor_rollout_ref.rollout.n=8" in joined
    assert "actor_rollout_ref.actor.kl_loss_coef=0.01" in joined
    assert "trainer.nnodes=2" in joined


def test_epoch_checkpoint_schedule_and_atomic_marker(tmp_path):
    assert epoch_boundaries() == (31, 62, 93, 124, 155)
    assert should_save_training_checkpoint(
        global_steps=31,
        save_freq=50,
        steps_per_epoch=31,
        is_last_step=False,
        esi_close_to_expiration=False,
    )
    (tmp_path / "state.bin").write_bytes(b"state")
    marker = mark_checkpoint_committed(tmp_path, 31)
    manifest = validate_committed_checkpoint(tmp_path)
    assert manifest["global_step"] == 31
    assert manifest["metadata"]["family"] == "qwen25"
    assert [item["path"] for item in manifest["files"]] == ["state.bin"]
    assert not (marker.parent / ".COMMITTED.tmp").exists()
