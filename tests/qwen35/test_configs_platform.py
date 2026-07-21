from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from vibethinker_experiments.qwen35.platform_submitter import (
    build_submit_command,
    render_launch_script,
)
from vibethinker_experiments.qwen35.verl_launcher import (
    build_command,
    load_config,
    validate_config,
    validate_formal_run_inputs,
)

ROOT = Path(__file__).resolve().parents[2]


def test_verl_configs_are_valid_and_reward_import_is_unambiguous():
    for name in ("verl_128k_math500.yaml", "verl_128k_mix1k.yaml"):
        config = load_config(ROOT / "configs" / "qwen35" / name)
        validate_config(config)
        assert config["runtime"]["sft_start_checkpoint"] == "epoch_9"
        assert config["cluster"] == {"nodes": 2, "gpus_per_node": 8}
        assert config["training"]["total_epochs"] == 5
        command = build_command(
            config,
            model_path="/model",
            train_file="/data/train.parquet",
            output_dir="/output",
        )
        joined = " ".join(command)
        assert "verl_reward.py" in joined
        assert "/reward_math.py" not in joined
        assert "reward_manager_math.py" in joined


def test_verl_variants_only_override_data_identity_and_experiment_name():
    config_dir = ROOT / "configs" / "qwen35"
    math500 = load_config(config_dir / "verl_128k_math500.yaml")
    mix1k = load_config(config_dir / "verl_128k_mix1k.yaml")
    assert math500["data"]["variant"] == "Math500"
    assert mix1k["data"]["variant"] == "Mix1K"
    assert mix1k["data"]["components"] == {"Math500": 500, "GSM8K": 500}
    for section in ("verl", "runtime", "training", "actor", "rollout", "reward", "cluster"):
        assert math500[section] == mix1k[section]


def test_submitter_never_serializes_token(monkeypatch):
    monkeypatch.setenv("TRISOL_TOKEN", "secret-token-must-not-leak")
    config = {
        "schema_version": 1,
        "kind": "sft",
        "platform": {
            "cli": "trisol",
            "job_name": "example",
            "base_model": "model:1",
            "dataset": "data:1",
            "cluster": "cluster",
            "image": "example/image:tag",
        },
        "resources": {"nodes": 1, "gpus_per_node": 8, "gpu_model": "A100"},
        "paths": {
            "experiment_config": "/workspace/sft.yaml",
            "model": "/input/model",
            "data": "/input/data",
            "output": "/output",
        },
    }
    script = render_launch_script(config)
    command = build_submit_command(config)
    assert "secret-token-must-not-leak" not in script
    assert "TRISOL_TOKEN" not in script
    assert all("secret-token-must-not-leak" not in argument for argument in command)
    encoded = command[command.index("--args") + 1].split("echo ", 1)[1].split(" ", 1)[0]
    assert base64.b64decode(encoded).decode() == script


def test_platform_examples_are_sanitized_templates():
    for name in ("platform_sft.example.yaml", "platform_verl.example.yaml"):
        config = yaml.safe_load((ROOT / "configs" / "qwen35" / name).read_text())
        serialized = str(config)
        assert config["platform"]["cluster"] == "<cluster-name>"
        assert config["platform"]["image"] == "<public-or-authorized-image>"
        assert "TRISOL_TOKEN" not in serialized


def test_formal_launcher_rejects_unproven_private_runtime(tmp_path: Path) -> None:
    train_file = tmp_path / "train.parquet"
    train_file.write_bytes(b"synthetic")
    model_receipt = tmp_path / "model.json"
    model_receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sft_epoch": 9,
                "adapter_sha256": "a" * 64,
            }
        )
    )
    data_receipt = tmp_path / "data.json"
    data_receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "variant": "Math500",
                "rows": 500,
                "train_sha256": hashlib.sha256(b"synthetic").hexdigest(),
            }
        )
    )
    runtime_receipt = tmp_path / "runtime.json"
    runtime_receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "verl_baseline": "v0.8.0",
                "apply_checked": True,
                "features": [],
            }
        )
    )
    config = load_config(ROOT / "configs/qwen35/verl_128k_math500.yaml")
    with pytest.raises(ValueError, match="runtime receipt"):
        validate_formal_run_inputs(
            config,
            model_path=tmp_path / "model",
            train_file=train_file,
            model_receipt_path=model_receipt,
            data_receipt_path=data_receipt,
            runtime_receipt_path=runtime_receipt,
        )
