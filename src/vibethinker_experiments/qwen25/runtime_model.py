"""Qwen2.5 merged-SFT 基座与 64K 零拷贝 runtime view。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

END_OF_TEXT_ID = 151643
IM_END_ID = 151645
CONTEXT_TOKENS = 65536


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_adapter_config(adapter: Path) -> dict[str, Any]:
    config = _json(adapter / "adapter_config.json")
    if (
        config.get("peft_type") != "LORA"
        or int(config.get("r", 0)) != 16
        or int(config.get("lora_alpha", 0)) != 32
    ):
        raise ValueError("selected SFT adapter must be LoRA r16/alpha32")
    if config.get("modules_to_save") is not None:
        raise ValueError("selected adapter unexpectedly contains modules_to_save")
    return config


def merge_sft_adapter(base_model: Path, adapter: Path, output: Path) -> dict[str, Any]:
    """安全合并所选 SFT adapter，使 adapter-disabled reference 等于 SFT 起点。"""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    validate_adapter_config(adapter)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to replace non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        local_files_only=True,
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    )
    merged = PeftModel.from_pretrained(base, adapter, is_trainable=False).merge_and_unload(
        safe_merge=True
    )
    merged.save_pretrained(output, safe_serialization=True, max_shard_size="5GB")
    AutoTokenizer.from_pretrained(base_model, local_files_only=True).save_pretrained(output)
    weights = sorted(output.glob("*.safetensors"))
    if not weights:
        raise RuntimeError("merged model produced no safetensors weights")
    manifest = {
        "dtype": "bfloat16",
        "safe_merge": True,
        "adapter_contract": {"rank": 16, "alpha": 32},
        "source_sha256": {
            "adapter_model.safetensors": _sha256(adapter / "adapter_model.safetensors"),
            "adapter_config.json": _sha256(adapter / "adapter_config.json"),
            "base_config.json": _sha256(base_model / "config.json"),
        },
        "weight_files": {path.name: _sha256(path) for path in weights},
    }
    _write_json(output / "vibethinker_sft_merge_manifest.json", manifest)
    return manifest


def build_runtime_view(base: Path, output: Path, context_tokens: int = CONTEXT_TOKENS) -> dict:
    base, output = base.resolve(), output.resolve()
    if base == output:
        raise ValueError("output must differ from the merged model")
    if context_tokens != CONTEXT_TOKENS:
        raise ValueError("the formal Qwen2.5 recipe requires exactly 65,536 tokens")
    model_config = _json(base / "config.json")
    tokenizer_config = _json(base / "tokenizer_config.json")
    if not str(model_config.get("model_type", "")).startswith("qwen2"):
        raise ValueError("runtime base must be a Qwen2-family model")
    source_context = int(model_config.get("max_position_embeddings") or 0)
    if source_context <= 0 or source_context > context_tokens:
        raise ValueError(f"unexpected source max_position_embeddings={source_context}")

    output.mkdir(parents=True, exist_ok=True)
    patched = {
        "config.json",
        "tokenizer_config.json",
        "generation_config.json",
        "vibethinker_runtime_manifest.json",
    }
    for source in base.iterdir():
        if source.name in patched:
            continue
        target = output / source.name
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"refusing to replace runtime asset: {target}")
        target.symlink_to(source)

    model_config["max_position_embeddings"] = context_tokens
    model_config["eos_token_id"] = IM_END_ID
    _write_json(output / "config.json", model_config)

    extra = tokenizer_config.pop("extra_special_tokens", None)
    if isinstance(extra, list):
        tokenizer_config.setdefault("additional_special_tokens", extra)
    tokenizer_config.update(
        model_max_length=context_tokens,
        eos_token="<|im_end|>",
        pad_token="<|endoftext|>",
    )
    _write_json(output / "tokenizer_config.json", tokenizer_config)

    generation_path = base / "generation_config.json"
    generation = _json(generation_path) if generation_path.is_file() else {}
    generation.update(
        bos_token_id=END_OF_TEXT_ID,
        pad_token_id=END_OF_TEXT_ID,
        eos_token_id=[IM_END_ID, END_OF_TEXT_ID],
    )
    _write_json(output / "generation_config.json", generation)
    weights = sorted(base.glob("*.safetensors"))
    if not weights:
        raise RuntimeError("runtime source contains no safetensors weights")
    manifest = {
        "context_tokens": context_tokens,
        "source_context_tokens": source_context,
        "context_extension_strategy": "unscaled_rope_metadata_extension",
        "primary_eos_token_id": IM_END_ID,
        "accepted_stop_token_ids": [IM_END_ID, END_OF_TEXT_ID],
        "metadata_sha256": {
            name: _sha256(output / name)
            for name in ("config.json", "tokenizer_config.json", "generation_config.json")
        },
        "weight_files": {path.name: _sha256(path) for path in weights},
    }
    _write_json(output / "vibethinker_runtime_manifest.json", manifest)
    return manifest


def validate_runtime(
    model: Path, *, min_context: int = CONTEXT_TOKENS, expected_adapter_sha256: str | None = None
) -> dict[str, Any]:
    runtime = _json(model / "vibethinker_runtime_manifest.json")
    if int(runtime.get("context_tokens", 0)) < min_context:
        raise ValueError("runtime context is below the configured training context")
    if runtime.get("primary_eos_token_id") != IM_END_ID:
        raise ValueError("runtime primary EOS is not <|im_end|>")
    if runtime.get("accepted_stop_token_ids") != [IM_END_ID, END_OF_TEXT_ID]:
        raise ValueError("runtime stop-token set is not the audited Qwen set")
    for name, expected in runtime.get("metadata_sha256", {}).items():
        if _sha256(model / name) != expected:
            raise ValueError(f"runtime metadata changed after preparation: {name}")
    weight_files = runtime.get("weight_files")
    if not isinstance(weight_files, dict) or not weight_files:
        raise ValueError("runtime manifest does not freeze model weights")
    for name, expected in weight_files.items():
        if _sha256(model / name) != expected:
            raise ValueError(f"runtime weight changed after preparation: {name}")
    actual_adapter = None
    merge_path = model / "vibethinker_sft_merge_manifest.json"
    if merge_path.is_file():
        merge = _json(merge_path)
        actual_adapter = merge.get("source_sha256", {}).get("adapter_model.safetensors")
        if merge.get("weight_files") != weight_files:
            raise ValueError("runtime weights differ from the SFT merge manifest")
    if expected_adapter_sha256 is not None and actual_adapter != expected_adapter_sha256:
        raise ValueError("runtime does not match the selected SFT adapter")
    return {
        "context_tokens": runtime["context_tokens"],
        "adapter_sha256": actual_adapter,
        "eos_token_id": IM_END_ID,
        "pad_token_id": END_OF_TEXT_ID,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context-tokens", type=int, default=CONTEXT_TOKENS)
    args = parser.parse_args()
    print(
        json.dumps(
            build_runtime_view(args.base_model, args.output, args.context_tokens),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
