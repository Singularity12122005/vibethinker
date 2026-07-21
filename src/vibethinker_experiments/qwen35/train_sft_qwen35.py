"""Text-only Qwen3.5-2B 30K LoRA SFT with assistant-only targets."""

from __future__ import annotations

import argparse
import json
import math
import os
import types
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from ..common.jsonl import read_jsonl

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

TEXT_LINEAR_TARGETS = (
    "in_proj_qkv",
    "in_proj_z",
    "in_proj_b",
    "in_proj_a",
    "out_proj",
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)


def install_agent_chat_template(tokenizer) -> None:
    """Replace Qwen3.5's generation prefill with a bare assistant header."""
    marker = "{%- if add_generation_prompt %}"
    template = tokenizer.chat_template
    if not isinstance(template, str):
        raise ValueError("Qwen3.5 tokenizer has no chat template")
    start = template.rfind(marker)
    if start < 0:
        raise ValueError("Qwen3.5 chat template has no generation-prompt block")
    old_block = template[start:]
    if "<think>" not in old_block or not old_block.rstrip().endswith("{%- endif %}"):
        raise ValueError("unexpected Qwen3.5 generation-prompt block")
    tokenizer.chat_template = (
        template[:start]
        + "{%- if add_generation_prompt %}\n"
        + "    {{- '<|im_start|>assistant\\n' }}\n"
        + "{%- endif %}"
    )
    probe = tokenizer.apply_chat_template(
        [{"role": "user", "content": "template probe"}],
        tokenize=False,
        add_generation_prompt=True,
    )
    if not probe.endswith("<|im_start|>assistant\n") or "<think>" in probe:
        raise ValueError("chat template still pre-fills protocol tags")


class ChatJsonlDataset:
    def __init__(self, path: Path, *, limit: int | None = None, longest_first: bool = False):
        rows = read_jsonl(path, strict=True)
        if longest_first:
            rows.sort(key=lambda row: int(row.get("_chat_tokens", 0) or 0), reverse=True)
        self.rows = rows[:limit] if limit else rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.rows[index]


class AssistantOnlyCollator:
    """Mask prompt tokens without depending on tokenizer offset mappings."""

    def __init__(self, tokenizer, max_length: int):
        self.tokenizer = tokenizer
        self.max_length = max_length

    def _encode_one(self, row: dict[str, Any]) -> dict[str, list[int]]:
        messages = row["messages"]
        if len(messages) < 2 or messages[-1].get("role") != "assistant":
            raise ValueError("each row must end with one assistant message")
        full = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        history = self.tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=False
        )
        prompt = history + "<|im_start|>assistant\n"
        if not full.startswith(prompt):
            raise ValueError("sample does not start with the assistant-header prompt")
        full_ids = self.tokenizer(full, add_special_tokens=False)["input_ids"]
        prompt_ids = self.tokenizer(prompt, add_special_tokens=False)["input_ids"]
        if full_ids[: len(prompt_ids)] != prompt_ids:
            raise ValueError("tokenized prompt is not a sample prefix")
        if len(full_ids) > self.max_length:
            domain = row.get("_mix_domain") or row.get("_domain") or "unknown"
            raise ValueError(
                f"sample exceeds max length: tokens={len(full_ids)} "
                f"max={self.max_length} domain={domain}"
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
        max_length = max(len(item["input_ids"]) for item in encoded)
        pad_id = self.tokenizer.pad_token_id
        batch: dict[str, list[list[int]]] = {
            "input_ids": [],
            "attention_mask": [],
            "labels": [],
        }
        for item in encoded:
            padding = max_length - len(item["input_ids"])
            batch["input_ids"].append(item["input_ids"] + [pad_id] * padding)
            batch["attention_mask"].append(item["attention_mask"] + [0] * padding)
            batch["labels"].append(item["labels"] + [-100] * padding)
        return {name: torch.tensor(values, dtype=torch.long) for name, values in batch.items()}


def install_memory_efficient_loss(model) -> None:
    """Compute CE in forward so Accelerate never upcasts returned full logits."""
    import torch
    import torch.nn.functional as functional

    original_forward = model.forward

    def forward_with_loss(self, *args, labels=None, num_items_in_batch=None, **kwargs):
        if labels is None:
            return original_forward(*args, **kwargs)
        outputs = original_forward(*args, labels=None, **kwargs)
        shifted = torch.full_like(labels, -100)
        shifted[:, :-1] = labels[:, 1:]
        reduction = "sum" if num_items_in_batch is not None else "mean"
        with torch.autocast(device_type="cuda", enabled=False):
            loss = functional.cross_entropy(
                outputs.logits.reshape(-1, outputs.logits.shape[-1]),
                shifted.reshape(-1),
                ignore_index=-100,
                reduction=reduction,
            )
        if num_items_in_batch is not None:
            denominator = torch.as_tensor(
                num_items_in_batch, device=loss.device, dtype=loss.dtype
            ).clamp_min(1)
            loss = loss / denominator
        return {"loss": loss}

    model.forward = types.MethodType(forward_with_loss, model)


def validate_lora_scope(model) -> None:
    trainable = [name for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not trainable:
        raise RuntimeError("LoRA did not create trainable parameters")
    escaped = [name for name in trainable if ".language_model." not in name or ".visual." in name]
    if escaped:
        raise RuntimeError(f"LoRA escaped the language model: {escaped[:10]}")


def resolve_train_file(path: Path) -> Path:
    if path.is_file():
        return path
    preferred = path / "train.jsonl"
    if preferred.exists():
        return preferred
    candidates = sorted(path.glob("*.jsonl")) or sorted(path.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no train file under {path}")
    return candidates[0]


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("SFT config must be a schema_version=1 mapping")
    return config


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model")
    parser.add_argument("--data-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--train-size", type=int)
    parser.add_argument("--longest-first", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    config = load_config(args.config)
    model_config, data_config = config["model"], config["data"]
    training, lora_config = config["training"], config["lora"]
    model_path = args.model or model_config["path"]
    data_path = Path(args.data_dir or data_config["path"])
    output_dir = args.output_dir or training["output_dir"]
    max_steps = args.max_steps if args.max_steps is not None else training.get("max_steps", -1)

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForImageTextToText,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    set_seed(training["seed"])
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    install_agent_chat_template(tokenizer)
    dataset = ChatJsonlDataset(
        resolve_train_file(data_path),
        limit=args.train_size,
        longest_first=args.longest_first,
    )
    domains = Counter(
        row.get("_mix_domain") or row.get("_domain") or "unknown" for row in dataset.rows
    )
    print(json.dumps({"rows": len(dataset), "domains": dict(domains)}), flush=True)

    model = AutoModelForImageTextToText.from_pretrained(
        model_path,
        local_files_only=True,
        dtype=torch.bfloat16,
        attn_implementation=model_config["attn_implementation"],
    )
    model.config.use_cache = False
    if hasattr(model.config, "text_config"):
        model.config.text_config.use_cache = False
    model = get_peft_model(
        model,
        LoraConfig(
            r=lora_config["r"],
            lora_alpha=lora_config["alpha"],
            lora_dropout=lora_config["dropout"],
            target_modules=list(lora_config.get("target_modules", TEXT_LINEAR_TARGETS)),
            task_type="CAUSAL_LM",
        ),
    )
    validate_lora_scope(model)
    install_memory_efficient_loss(model)

    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    effective_batch = (
        world_size * training["per_device_batch_size"] * training["gradient_accumulation_steps"]
    )
    planned_steps = max_steps
    if planned_steps < 0:
        planned_steps = math.ceil(len(dataset) * training["epochs"] / effective_batch)
    print(
        f"effective_global_batch={effective_batch} planned_optimizer_steps={planned_steps}",
        flush=True,
    )
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=training["epochs"],
            max_steps=max_steps,
            per_device_train_batch_size=training["per_device_batch_size"],
            gradient_accumulation_steps=training["gradient_accumulation_steps"],
            learning_rate=training["learning_rate"],
            lr_scheduler_type="cosine_with_min_lr",
            lr_scheduler_kwargs={"min_lr": training["min_learning_rate"]},
            warmup_ratio=training["warmup_ratio"],
            logging_steps=training["logging_steps"],
            save_strategy=training["save_strategy"],
            save_steps=training.get("save_steps", 500),
            save_total_limit=training["save_total_limit"],
            bf16=True,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            report_to="none",
            remove_unused_columns=False,
            dataloader_num_workers=training["dataloader_num_workers"],
            ddp_find_unused_parameters=False,
        ),
        train_dataset=dataset,
        data_collator=AssistantOnlyCollator(tokenizer, data_config["max_seq_length"]),
        processing_class=tokenizer,
    )
    trainer.train()
    final_dir = Path(output_dir) / "final"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(final_dir)


if __name__ == "__main__":
    main()
