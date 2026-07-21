"""共享 Qwen2.5 LoRA SFT：无 packing、无截断、仅 assistant loss。"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from vibethinker_experiments.common.jsonl import read_jsonl


def expected_optimizer_steps(rows: int, epochs: int, effective_batch: int) -> int:
    if rows <= 0 or epochs <= 0 or effective_batch <= 0:
        raise ValueError("rows, epochs, and effective_batch must be positive")
    return math.ceil(rows / effective_batch) * epochs


class ChatDataset:
    def __init__(self, path: Path, *, limit: int | None = None, longest_first: bool = False):
        rows = read_jsonl(path, strict=True)
        if longest_first:
            rows.sort(key=lambda row: int(row.get("_chat_tokens", 0)), reverse=True)
        self.rows = rows[:limit] if limit else rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.rows[index]


class AssistantOnlyCollator:
    """以 assistant header 的 token 前缀确定 mask 边界，避免字符串反查歧义。"""

    def __init__(self, tokenizer, max_length: int):
        self.tokenizer = tokenizer
        self.max_length = int(max_length)

    def _encode_one(self, row: dict[str, Any]) -> dict[str, list[int]]:
        messages = row.get("messages")
        if (
            not isinstance(messages, list)
            or len(messages) != 2
            or [message.get("role") for message in messages] != ["user", "assistant"]
        ):
            raise ValueError("expected exactly [user, assistant] messages")
        full_text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        prompt_text = self.tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=True
        )
        full_ids = self.tokenizer(full_text, add_special_tokens=False)["input_ids"]
        prompt_ids = self.tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        if full_ids[: len(prompt_ids)] != prompt_ids:
            raise ValueError("chat template prompt is not a token prefix of the training sample")
        if len(full_ids) > self.max_length:
            domain = row.get("_domain") or row.get("_mix_domain") or "unknown"
            raise ValueError(
                f"sample exceeds max_seq_length without truncation: "
                f"tokens={len(full_ids)} max={self.max_length} domain={domain}"
            )
        if len(full_ids) == len(prompt_ids):
            raise ValueError("assistant target is empty")
        return {
            "input_ids": full_ids,
            "attention_mask": [1] * len(full_ids),
            "labels": [-100] * len(prompt_ids) + full_ids[len(prompt_ids) :],
        }

    def __call__(self, features: list[dict[str, Any]]):
        import torch

        encoded = [self._encode_one(row) for row in features]
        padded_length = max(len(item["input_ids"]) for item in encoded)
        batch: dict[str, list[list[int]]] = {
            "input_ids": [],
            "attention_mask": [],
            "labels": [],
        }
        for item in encoded:
            padding = padded_length - len(item["input_ids"])
            batch["input_ids"].append(item["input_ids"] + [self.tokenizer.pad_token_id] * padding)
            batch["attention_mask"].append(item["attention_mask"] + [0] * padding)
            batch["labels"].append(item["labels"] + [-100] * padding)
        return {name: torch.tensor(values, dtype=torch.long) for name, values in batch.items()}


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("SFT config must be a schema_version=1 mapping")
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    data, training, lora = config["data"], config["training"], config["lora"]
    if data.get("packing") is not False or data.get("truncation") != "error":
        raise ValueError("Qwen2.5 SFT requires packing=false and truncation=error")
    if training.get("assistant_only_loss") is not True:
        raise ValueError("assistant_only_loss must be true")
    if int(training["epochs"]) != 10:
        raise ValueError("formal Qwen2.5 SFT uses 10 epochs")
    expected_steps = int(training["steps_per_epoch"]) * int(training["epochs"])
    if int(training["planned_optimizer_steps"]) != expected_steps:
        raise ValueError("planned_optimizer_steps must equal epochs * steps_per_epoch")
    if int(lora["rank"]) != 16 or int(lora["alpha"]) != 32:
        raise ValueError("formal SFT adapter must be LoRA r16/alpha32")


def resolve_train_file(path: Path) -> Path:
    if path.is_file():
        return path
    preferred = path / "train.jsonl"
    if preferred.is_file():
        return preferred
    candidates = sorted(path.glob("*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"no JSONL training file under {path}")
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--longest-first", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    training, data, lora = config["training"], config["data"], config["lora"]

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    set_seed(int(training["seed"]))
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    dataset = ChatDataset(
        resolve_train_file(args.data),
        limit=args.limit,
        longest_first=args.longest_first,
    )
    domains = Counter(
        row.get("_domain") or row.get("_mix_domain") or "unknown" for row in dataset.rows
    )
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    effective_batch = (
        world_size
        * int(training["per_device_batch_size"])
        * int(training["gradient_accumulation_steps"])
    )
    computed_steps = expected_optimizer_steps(
        len(dataset),
        int(training["epochs"]),
        effective_batch,
    )
    if args.max_steps < 0 and computed_steps != int(training["planned_optimizer_steps"]):
        raise ValueError(
            f"runtime topology implies {computed_steps} steps, "
            f"manifest freezes {training['planned_optimizer_steps']}"
        )
    print(
        json.dumps(
            {
                "rows": len(dataset),
                "domains": dict(domains),
                "effective_global_batch": effective_batch,
                "planned_optimizer_steps": computed_steps,
            }
        ),
        flush=True,
    )

    base = AutoModelForCausalLM.from_pretrained(
        args.model,
        local_files_only=True,
        torch_dtype=torch.bfloat16,
        attn_implementation=config["model"]["attention_implementation"],
    )
    base.config.use_cache = False
    model = get_peft_model(
        base,
        LoraConfig(
            r=int(lora["rank"]),
            lora_alpha=int(lora["alpha"]),
            lora_dropout=float(lora["dropout"]),
            target_modules=lora["target_modules"],
            task_type="CAUSAL_LM",
        ),
    )
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(args.output_dir),
            num_train_epochs=float(training["epochs"]),
            max_steps=args.max_steps,
            per_device_train_batch_size=int(training["per_device_batch_size"]),
            gradient_accumulation_steps=int(training["gradient_accumulation_steps"]),
            learning_rate=float(training["learning_rate"]),
            lr_scheduler_type="cosine_with_min_lr",
            lr_scheduler_kwargs={"min_lr": float(training["min_learning_rate"])},
            warmup_ratio=float(training["warmup_ratio"]),
            logging_steps=int(training["logging_steps"]),
            save_strategy="epoch",
            save_total_limit=int(training["save_total_limit"]),
            bf16=True,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            report_to="none",
            remove_unused_columns=False,
            dataloader_num_workers=int(training["dataloader_num_workers"]),
            ddp_find_unused_parameters=False,
        ),
        train_dataset=dataset,
        data_collator=AssistantOnlyCollator(tokenizer, int(data["max_seq_length"])),
    )
    trainer.train()
    final_dir = args.output_dir / "final"
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)


if __name__ == "__main__":
    main()
