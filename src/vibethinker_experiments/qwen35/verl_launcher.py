"""Validate frozen Qwen3.5 VERL YAML and invoke the v0.8.0 PPO entry point."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ..common.hashing import file_sha256
from .runtime_model import validate_runtime

REQUIRED_RUNTIME_FEATURES = {
    "release-backward-cache-before-rollout-wakeup",
    "cuda-hybrid-sleep-level-two",
    "text-only-position-ids-and-chat-stop-token",
    "ulysses-global-shift-labels",
    "chunked-fused-linear-label-alignment",
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text())
    if isinstance(config, dict) and config.get("extends"):
        parent = load_config((path.parent / str(config["extends"])).resolve())
        overrides = {key: value for key, value in config.items() if key != "extends"}
        config = _deep_merge(parent, overrides)
    if (
        not isinstance(config, dict)
        or config.get("schema_version") != 1
        or config.get("verl", {}).get("baseline") != "v0.8.0"
    ):
        raise ValueError("expected schema_version=1 with VERL baseline v0.8.0")
    return config


def validate_config(config: dict[str, Any]) -> None:
    data, rollout, actor, cluster = (
        config["data"],
        config["rollout"],
        config["actor"],
        config["cluster"],
    )
    context = int(data["max_prompt_length"]) + int(data["max_response_length"])
    if context != 131072:
        raise ValueError("prompt + response budget must equal 131072")
    if config["training"]["mode"] != "full_parameter":
        raise ValueError("Qwen3.5 RL requires a full-parameter actor")
    total_gpus = int(cluster["nodes"]) * int(cluster["gpus_per_node"])
    sequence_parallel = int(actor["sequence_parallel_size"])
    if sequence_parallel < 1 or sequence_parallel > 8 or total_gpus % sequence_parallel:
        raise ValueError("sequence parallel size must divide total GPUs and be <= 8")
    if int(rollout["max_model_len"]) != context:
        raise ValueError("rollout max_model_len must match the context budget")
    if int(actor["ppo_mini_batch_size"]) != int(data["train_batch_size"]):
        raise ValueError("PPO mini batch must equal the global train batch")


def validate_formal_run_inputs(
    config: dict[str, Any],
    *,
    model_path: Path,
    train_file: Path,
    model_receipt_path: Path,
    data_receipt_path: Path,
    runtime_receipt_path: Path,
) -> None:
    model_receipt = json.loads(model_receipt_path.read_text())
    data_receipt = json.loads(data_receipt_path.read_text())
    runtime_receipt = json.loads(runtime_receipt_path.read_text())
    if model_receipt.get("schema_version") != 1 or model_receipt.get("sft_epoch") != 9:
        raise ValueError("Qwen3.5 formal RL requires the selected SFT epoch 9 receipt")
    adapter_sha256 = str(model_receipt.get("adapter_sha256", ""))
    if len(adapter_sha256) != 64:
        raise ValueError("model receipt must contain the selected adapter SHA-256")
    expected_rows = 500 if config["data"]["variant"] == "Math500" else 1000
    if (
        data_receipt.get("schema_version") != 1
        or data_receipt.get("variant") != config["data"]["variant"]
        or data_receipt.get("rows") != expected_rows
        or data_receipt.get("train_sha256") != file_sha256(train_file)
    ):
        raise ValueError("RL data receipt does not match the configured variant and train file")
    if (
        runtime_receipt.get("schema_version") != 1
        or runtime_receipt.get("verl_baseline") != "v0.8.0"
        or runtime_receipt.get("apply_checked") is not True
        or not REQUIRED_RUNTIME_FEATURES.issubset(set(runtime_receipt.get("features", [])))
    ):
        raise ValueError("formal Qwen3.5 runtime receipt is incomplete")
    validate_runtime(model_path, 131072, adapter_sha256)


def build_command(
    config: dict[str, Any],
    *,
    model_path: str,
    train_file: str,
    output_dir: str,
    extra_overrides: list[str] | None = None,
) -> list[str]:
    validate_config(config)
    root = Path(__file__).resolve().parent
    values = {
        "model_path": model_path,
        "train_file": train_file,
        "output_dir": output_dir,
        "reward_path": str(root / "verl_reward.py"),
        "reward_manager_path": str(root / "reward_manager_math.py"),
    }
    overrides = []
    for key, value in config["hydra_overrides"].items():
        if isinstance(value, str):
            value = value.format(**values)
        if isinstance(value, bool):
            value = str(value)
        overrides.append(f"{key}={value}")
    return ["python3", "-m", "verl.trainer.main_ppo", *overrides, *(extra_overrides or [])]


def runtime_environment(
    config: dict[str, Any], *, model_path: str, output_dir: str
) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "PYTHONUNBUFFERED": "1",
            "VT_TOKENIZER_PATH": model_path,
            "VT_MAX_COMPLETION_TOKENS": str(config["data"]["max_response_length"]),
            "VT_LENGTH_SOFT_START_TOKENS": str(config["reward"]["length_soft_start_tokens"]),
            "VT_REWARD_AUDIT_DIR": str(Path(output_dir) / "logs" / "reward_audit"),
        }
    )
    return environment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-receipt", type=Path)
    parser.add_argument("--data-receipt", type=Path)
    parser.add_argument("--runtime-receipt", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("overrides", nargs="*")
    args = parser.parse_args()
    config = load_config(args.config)
    command = build_command(
        config,
        model_path=args.model_path,
        train_file=args.train_file,
        output_dir=args.output_dir,
        extra_overrides=args.overrides,
    )
    if args.dry_run:
        print("\n".join(command))
        return
    if not all((args.model_receipt, args.data_receipt, args.runtime_receipt)):
        parser.error("formal execution requires model, data, and runtime receipts")
    validate_formal_run_inputs(
        config,
        model_path=Path(args.model_path),
        train_file=Path(args.train_file),
        model_receipt_path=args.model_receipt,
        data_receipt_path=args.data_receipt,
        runtime_receipt_path=args.runtime_receipt,
    )
    subprocess.run(
        command,
        check=True,
        env=runtime_environment(config, model_path=args.model_path, output_dir=args.output_dir),
    )


if __name__ == "__main__":
    main()
