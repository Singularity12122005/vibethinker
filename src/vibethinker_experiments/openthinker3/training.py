"""Render the frozen experiment contract into a VERL command."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml


def load_training_contract(path: str | Path) -> dict[str, Any]:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("unsupported OpenThinker3 training contract")
    validate_training_contract(config)
    return config


def validate_training_contract(config: dict[str, Any]) -> None:
    data = config["data"]
    rollout = config["rollout"]
    actor = config["actor"]
    resources = config["resources"]
    algorithm = config["algorithm"]
    if data["max_prompt_length"] + rollout["max_response_length"] != rollout["max_model_length"]:
        raise ValueError("prompt and response limits must exactly fill max_model_length")
    if actor["max_tokens_per_gpu"] != rollout["max_model_length"]:
        raise ValueError("actor token budget must hold the longest allowed sequence")
    if data["rows_per_epoch"] % data["batch_size"] == 0:
        expected_steps = data["rows_per_epoch"] // data["batch_size"]
    else:
        expected_steps = data["rows_per_epoch"] // data["batch_size"] + 1
    if expected_steps != 263 or data["drop_last"] is not False:
        raise ValueError("frozen epoch scheduling contract changed")
    if resources["nodes"] * resources["gpus_per_node"] != 32:
        raise ValueError("formal topology must contain 32 GPUs")
    if actor["fsdp_size"] != 1 or rollout["group_size"] != 16:
        raise ValueError("pure-DP/group-size contract changed")
    if algorithm["use_kl_reward"] or algorithm["use_kl_loss"]:
        raise ValueError("formal recipe disables both KL paths")
    if config["formal_runtime_id"] != "REQUIRED_FROM_RUN_MANIFEST":
        raise ValueError("public training config must not select a runtime artifact")


def build_verl_overrides(
    config: dict[str, Any],
    *,
    model_path: str,
    train_file: str,
    output_dir: str,
    ray_address: str | None = None,
    resume_path: str | None = None,
) -> list[str]:
    data = config["data"]
    rollout = config["rollout"]
    actor = config["actor"]
    algorithm = config["algorithm"]
    resources = config["resources"]
    reward = config["reward"]
    checkpoint = config["checkpoint"]
    values: dict[str, object] = {
        "algorithm.adv_estimator": algorithm["advantage_estimator"],
        "algorithm.use_kl_in_reward": algorithm["use_kl_reward"],
        "algorithm.norm_adv_by_std_in_grpo": algorithm["normalize_advantage_by_std"],
        "data.train_files": train_file,
        "data.val_files": train_file,
        "data.train_batch_size": data["batch_size"],
        "data.seed": data["seed"],
        "data.shuffle": True,
        "data.max_prompt_length": data["max_prompt_length"],
        "data.max_response_length": rollout["max_response_length"],
        "data.filter_overlong_prompts": False,
        "data.truncation": data["truncation"],
        "actor_rollout_ref.model.path": model_path,
        "actor_rollout_ref.model.lora_rank": 0,
        "actor_rollout_ref.model.use_remove_padding": actor["remove_padding"],
        "actor_rollout_ref.model.enable_gradient_checkpointing": actor["gradient_checkpointing"],
        "actor_rollout_ref.actor.strategy": actor["strategy"],
        "actor_rollout_ref.actor.optim.lr": actor["learning_rate"],
        "actor_rollout_ref.actor.optim.lr_warmup_steps": actor["warmup_steps"],
        "actor_rollout_ref.actor.optim.weight_decay": actor["weight_decay"],
        "actor_rollout_ref.actor.ppo_mini_batch_size": data["batch_size"],
        "actor_rollout_ref.actor.ppo_epochs": actor["ppo_epochs"],
        "actor_rollout_ref.actor.shuffle": False,
        "actor_rollout_ref.actor.loss_agg_mode": algorithm["loss_aggregation"],
        "actor_rollout_ref.actor.clip_ratio_low": algorithm["clip_ratio_low"],
        "actor_rollout_ref.actor.clip_ratio_high": algorithm["clip_ratio_high"],
        "actor_rollout_ref.actor.clip_ratio_c": algorithm["dual_clip_c"],
        "actor_rollout_ref.actor.calculate_entropy": True,
        "actor_rollout_ref.actor.entropy_coeff": 0.0,
        "actor_rollout_ref.actor.use_dynamic_bsz": actor["dynamic_batching"],
        "actor_rollout_ref.actor.ppo_max_token_len_per_gpu": actor["max_tokens_per_gpu"],
        "actor_rollout_ref.actor.use_kl_loss": algorithm["use_kl_loss"],
        "actor_rollout_ref.actor.fsdp_config.fsdp_size": actor["fsdp_size"],
        "actor_rollout_ref.actor.fsdp_config.param_offload": False,
        "actor_rollout_ref.actor.fsdp_config.optimizer_offload": False,
        "actor_rollout_ref.rollout.name": "vllm",
        "actor_rollout_ref.rollout.mode": "async",
        "actor_rollout_ref.rollout.tensor_model_parallel_size": rollout["tensor_parallel_size"],
        "actor_rollout_ref.rollout.data_parallel_size": rollout["data_parallel_size"],
        "actor_rollout_ref.rollout.gpu_memory_utilization": rollout["gpu_memory_utilization"],
        "actor_rollout_ref.rollout.n": rollout["group_size"],
        "actor_rollout_ref.rollout.temperature": rollout["temperature"],
        "actor_rollout_ref.rollout.top_p": rollout["top_p"],
        "actor_rollout_ref.rollout.top_k": rollout["top_k"],
        "actor_rollout_ref.rollout.max_model_len": rollout["max_model_length"],
        "actor_rollout_ref.rollout.max_num_batched_tokens": rollout["max_num_batched_tokens"],
        "actor_rollout_ref.rollout.max_num_seqs": rollout["max_num_seqs"],
        "actor_rollout_ref.rollout.enable_chunked_prefill": True,
        "actor_rollout_ref.rollout.enable_prefix_caching": True,
        "actor_rollout_ref.rollout.free_cache_engine": True,
        "reward.num_workers": reward["ray_workers"],
        "reward.custom_reward_function.path": ("pkg://vibethinker_experiments.openthinker3.reward"),
        "reward.custom_reward_function.name": "compute_score",
        "reward.reward_manager.source": "register",
        "reward.reward_manager.name": reward["manager"],
        "trainer.balance_batch": True,
        "trainer.logger": '["console"]',
        "trainer.default_local_dir": output_dir,
        "trainer.resume_mode": "auto",
        "trainer.max_actor_ckpt_to_keep": 64,
        "trainer.n_gpus_per_node": resources["gpus_per_node"],
        "trainer.nnodes": resources["nodes"],
        "trainer.val_before_train": False,
        "trainer.test_freq": -1,
        "trainer.save_freq": checkpoint["save_frequency"],
        "trainer.total_epochs": data["epochs"],
    }
    overrides = [f"{key}={_hydra_value(value)}" for key, value in values.items()]
    if ray_address:
        overrides.append(f"+ray_kwargs.ray_init.address={ray_address}")
    if resume_path:
        if Path(resume_path).name.rsplit("_", 1)[0] != "global_step":
            raise ValueError("resume path must end in global_step_N")
        overrides.extend(
            ["trainer.resume_mode=resume_path", f"trainer.resume_from_path={resume_path}"]
        )
    return overrides


def _hydra_value(value: object) -> str:
    if value is True:
        return "True"
    if value is False:
        return "False"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--ray-address")
    parser.add_argument("--resume-path")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = load_training_contract(args.config)
    command = [
        "python3",
        "-m",
        "verl.trainer.main_ppo",
        *build_verl_overrides(
            config,
            model_path=args.model_path,
            train_file=args.train_file,
            output_dir=args.output_dir,
            ray_address=args.ray_address,
            resume_path=args.resume_path,
        ),
    ]
    if args.execute:
        environment = os.environ.copy()
        environment.update(
            {key: str(value) for key, value in config["runtime_environment"].items()}
        )
        subprocess.run(command, check=True, env=environment)
    else:
        print("\n".join(command))


if __name__ == "__main__":
    main()
