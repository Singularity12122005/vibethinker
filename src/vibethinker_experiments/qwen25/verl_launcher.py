"""校验共享 64K recipe，并调用上游 VERL v0.8.0 PPO 入口。"""

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

LINEAGE_EPOCHS = {"qwen25-15k": 1, "qwen25-30k": 5}


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text())
    if (
        not isinstance(config, dict)
        or config.get("schema_version") != 1
        or config.get("verl", {}).get("baseline") != "v0.8.0"
    ):
        raise ValueError("expected schema_version=1 and VERL baseline v0.8.0")
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    data = config["data"]
    cluster = config["cluster"]
    actor = config["actor"]
    rollout = config["rollout"]
    training = config["training"]
    model = config["model"]
    context = int(data["max_prompt_length"]) + int(data["max_response_length"])
    if context != 65536:
        raise ValueError("prompt + response budget must equal 65,536")
    if (
        int(data["prompt_rows"]) != 500
        or int(data["train_batch_size"]) != 16
        or int(rollout["group_size"]) != 8
    ):
        raise ValueError("formal data contract is 500 prompts, global batch 16, G=8")
    if int(cluster["nodes"]) != 2 or int(cluster["gpus_per_node"]) != 8:
        raise ValueError("formal cluster contract is 2 nodes × 8 GPUs")
    if cluster.get("gpu_class") != "A100-80GB":
        raise ValueError("formal hardware class is A100-80GB")
    if actor.get("strategy") != "fsdp2" or rollout.get("mode") != "async":
        raise ValueError("formal runtime requires FSDP2 and asynchronous rollout")
    if rollout.get("engine") != "vllm" or int(rollout["max_model_len"]) != context:
        raise ValueError("rollout must use vLLM at the full context budget")
    if float(actor["learning_rate"]) != 1e-6 or float(actor["kl_loss_coefficient"]) != 0.01:
        raise ValueError("actor LR/KL coefficient differ from the frozen recipe")
    if (
        model.get("rl_adapter") != "fresh_lora"
        or int(model["lora_rank"]) != 16
        or int(model["lora_alpha"]) != 32
    ):
        raise ValueError("RL must create a fresh r16/alpha32 LoRA")
    if (
        int(training["epochs"]) != 5
        or int(training["steps_per_epoch"]) != 31
        or int(training["planned_steps"]) != 155
    ):
        raise ValueError("formal schedule is 5 × 31 = 155 planned steps")
    if int(actor["ppo_mini_batch_size"]) != int(data["train_batch_size"]):
        raise ValueError("PPO mini batch must equal the global prompt batch")


def validate_formal_run_inputs(
    *,
    lineage: str,
    model_path: Path,
    train_file: Path,
    model_receipt_path: Path,
    data_receipt_path: Path,
    runtime_receipt_path: Path,
) -> None:
    if lineage not in LINEAGE_EPOCHS:
        raise ValueError(f"unknown Qwen2.5 lineage: {lineage}")
    model_receipt = json.loads(model_receipt_path.read_text())
    data_receipt = json.loads(data_receipt_path.read_text())
    runtime_receipt = json.loads(runtime_receipt_path.read_text())
    adapter_sha256 = str(model_receipt.get("adapter_sha256", ""))
    if (
        model_receipt.get("schema_version") != 1
        or model_receipt.get("lineage") != lineage
        or model_receipt.get("sft_epoch") != LINEAGE_EPOCHS[lineage]
        or len(adapter_sha256) != 64
    ):
        raise ValueError("model receipt does not match the selected Qwen2.5 lineage")
    if (
        data_receipt.get("schema_version") != 1
        or data_receipt.get("variant") != "Math500"
        or data_receipt.get("rows") != 500
        or data_receipt.get("train_sha256") != file_sha256(train_file)
    ):
        raise ValueError("data receipt does not match the shared Math500 train file")
    if (
        runtime_receipt.get("schema_version") != 1
        or runtime_receipt.get("verl_baseline") != "v0.8.0"
        or runtime_receipt.get("apply_checked") is not True
        or "checkpoint-manifest-validated-resume" not in set(runtime_receipt.get("features", []))
    ):
        raise ValueError("formal Qwen2.5 runtime receipt is incomplete")
    validate_runtime(model_path, expected_adapter_sha256=adapter_sha256)


def build_command(
    config: dict[str, Any],
    *,
    model_path: str,
    train_file: str,
    output_dir: str,
    extra_overrides: list[str] | None = None,
) -> list[str]:
    validate_config(config)
    package_root = Path(__file__).resolve().parent
    values = {
        "model_path": model_path,
        "train_file": train_file,
        "output_dir": output_dir,
        "reward_path": str(package_root / "verl_reward.py"),
        "reward_manager_path": str(package_root / "reward_manager_math.py"),
    }
    overrides: list[str] = []
    for key, value in config["hydra_overrides"].items():
        if isinstance(value, str):
            value = value.format(**values)
        elif isinstance(value, bool):
            value = str(value).lower()
        overrides.append(f"{key}={value}")
    return [
        "python3",
        "-m",
        "verl.trainer.main_ppo",
        *overrides,
        *(extra_overrides or []),
    ]


def runtime_environment(config: dict[str, Any], *, model_path: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "VLLM_USE_V1": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "PYTHONUNBUFFERED": "1",
            "VT_TOKENIZER_PATH": model_path,
            "VT_MAX_COMPLETION_TOKENS": str(config["data"]["max_response_length"]),
            "VT_OVERLONG_SOFT_START_TOKENS": str(config["reward"]["overlong_soft_start_tokens"]),
            "VT_OVERLONG_FLOOR": str(config["reward"]["overlong_floor"]),
        }
    )
    return environment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--lineage", choices=sorted(LINEAGE_EPOCHS))
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
    if not all(
        (
            args.lineage,
            args.model_receipt,
            args.data_receipt,
            args.runtime_receipt,
        )
    ):
        parser.error("formal execution requires lineage plus model, data, and runtime receipts")
    validate_formal_run_inputs(
        lineage=args.lineage,
        model_path=Path(args.model_path),
        train_file=Path(args.train_file),
        model_receipt_path=args.model_receipt,
        data_receipt_path=args.data_receipt,
        runtime_receipt_path=args.runtime_receipt,
    )
    subprocess.run(
        command,
        check=True,
        env=runtime_environment(config, model_path=args.model_path),
    )


if __name__ == "__main__":
    main()
