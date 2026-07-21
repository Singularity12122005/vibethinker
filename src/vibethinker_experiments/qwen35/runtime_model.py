"""Prepare, merge, and validate native Qwen3.5 runtime model views."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

BARE_GENERATION_SUFFIX = """{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\\n' }}
{%- endif %}"""


def _json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_chat_template(base: Path, tokenizer_config: dict) -> tuple[str, str]:
    inline = tokenizer_config.get("chat_template")
    if isinstance(inline, str) and inline.strip():
        return inline, "tokenizer_config.json"
    path = base / "chat_template.jinja"
    if path.is_file() and path.read_text().strip():
        return path.read_text(), path.name
    raise RuntimeError("Qwen3.5 tokenizer has no chat template")


def bare_chat_template(template: str) -> str:
    marker = "{%- if add_generation_prompt %}"
    start = template.rfind(marker)
    if start < 0:
        raise ValueError("Qwen3.5 template has no generation-prompt block")
    return template[:start] + BARE_GENERATION_SUFFIX


def prepare_base_view(base: Path, output: Path) -> dict:
    base, output = base.resolve(), output.resolve()
    if base == output:
        raise ValueError("output must differ from base model")
    output.mkdir(parents=True, exist_ok=True)
    config = _json(base / "tokenizer_config.json")
    template, source_name = load_chat_template(base, config)
    config["chat_template"] = bare_chat_template(template)
    for source in base.iterdir():
        if source.name in {"tokenizer_config.json", "chat_template.jinja"}:
            continue
        target = output / source.name
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"refusing to replace {target}")
        target.symlink_to(source)
    (output / "tokenizer_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "chat_template.jinja").write_text(config["chat_template"])
    return {"base_model": str(base), "output": str(output), "template_source": source_name}


def merge_sft_adapter(base_model: Path, adapter: Path, output: Path) -> dict:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoTokenizer

    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to replace non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    adapter_config_path = adapter / "adapter_config.json"
    adapter_weights_path = adapter / "adapter_model.safetensors"
    adapter_config = _json(adapter_config_path)
    if (
        adapter_config.get("peft_type") != "LORA"
        or adapter_config.get("r") != 16
        or adapter_config.get("lora_alpha") != 32
    ):
        raise ValueError("adapter must be the selected Qwen3.5 r16/alpha32 LoRA")
    if adapter_config.get("modules_to_save") is not None:
        raise ValueError("adapter unexpectedly contains modules_to_save")
    if _json(base_model / "config.json").get("model_type") != "qwen3_5":
        raise ValueError("base model must be Qwen3.5")

    base = AutoModelForImageTextToText.from_pretrained(
        base_model,
        local_files_only=True,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    )
    merged = PeftModel.from_pretrained(base, adapter, is_trainable=False).merge_and_unload(
        safe_merge=True
    )
    merged.save_pretrained(output, safe_serialization=True, max_shard_size="5GB")
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    tokenizer.chat_template = (adapter / "chat_template.jinja").read_text()
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": "protocol probe"}],
        tokenize=False,
        add_generation_prompt=True,
    )
    if not rendered.endswith("<|im_start|>assistant\n"):
        raise ValueError("adapter chat template must leave a bare assistant header")
    tokenizer.save_pretrained(output)
    (output / "chat_template.jinja").write_text(tokenizer.chat_template)

    processor_assets = []
    for name in (
        "preprocessor_config.json",
        "processor_config.json",
        "video_preprocessor_config.json",
    ):
        source = base_model / name
        if source.is_file():
            shutil.copy2(source, output / name)
            processor_assets.append(name)
    if "preprocessor_config.json" not in processor_assets:
        raise FileNotFoundError(base_model / "preprocessor_config.json")
    weights = sorted(output.glob("*.safetensors"))
    manifest = {
        "base_model": str(base_model.resolve()),
        "sft_adapter": str(adapter.resolve()),
        "dtype": "bfloat16",
        "safe_merge": True,
        "model_type": "qwen3_5",
        "chat_template": "bare_assistant_header",
        "processor_assets": {name: _sha256(output / name) for name in processor_assets},
        "source_sha256": {
            "adapter_model.safetensors": _sha256(adapter_weights_path),
            "adapter_config.json": _sha256(adapter_config_path),
            "base_config.json": _sha256(base_model / "config.json"),
        },
        "weight_files": {path.name: _sha256(path) for path in weights},
    }
    (output / "vibethinker_sft_merge_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    return manifest


def _native_context(config: dict, tokenizer_config: dict) -> int:
    values = [
        config.get("max_position_embeddings"),
        config.get("text_config", {}).get("max_position_embeddings"),
        tokenizer_config.get("model_max_length"),
    ]
    lengths = [int(value) for value in values if value is not None]
    if not lengths:
        raise ValueError("model metadata has no native context length")
    return min(lengths)


def build_runtime_view(base: Path, output: Path, context_tokens: int) -> dict:
    base, output = base.resolve(), output.resolve()
    if base == output:
        raise ValueError("output must differ from base model")
    config, tokenizer_config = _json(base / "config.json"), _json(base / "tokenizer_config.json")
    native_context = _native_context(config, tokenizer_config)
    if context_tokens > native_context:
        raise ValueError(
            f"requested context {context_tokens} exceeds native context {native_context}"
        )
    output.mkdir(parents=True, exist_ok=True)
    manifest_name = "vibethinker_runtime_manifest.json"
    for source in base.iterdir():
        if source.name == manifest_name:
            continue
        target = output / source.name
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"refusing to replace {target}")
        target.symlink_to(source)
    weights = sorted(base.glob("*.safetensors"))
    if not weights:
        raise RuntimeError("runtime source contains no safetensors weights")
    manifest = {
        "base_model": str(base),
        "runtime_model": str(output),
        "context_tokens": int(context_tokens),
        "native_context_tokens": native_context,
        "metadata_policy": "native_unmodified",
        "metadata_sha256": {
            name: _sha256(base / name) for name in ("config.json", "tokenizer_config.json")
        },
        "weight_files": {path.name: _sha256(path) for path in weights},
    }
    (output / manifest_name).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def validate_runtime(model: Path, min_context: int, expected_adapter_sha256: str) -> dict:
    runtime = _json(model / "vibethinker_runtime_manifest.json")
    merge = _json(model / "vibethinker_sft_merge_manifest.json")
    if runtime.get("metadata_policy") != "native_unmodified":
        raise ValueError("runtime must preserve native metadata")
    if (
        min(
            int(runtime.get("context_tokens", 0)),
            int(runtime.get("native_context_tokens", 0)),
        )
        < min_context
    ):
        raise ValueError("runtime context is below the configured training context")
    actual = merge.get("source_sha256", {}).get("adapter_model.safetensors")
    if actual != expected_adapter_sha256 or merge.get("model_type") != "qwen3_5":
        raise ValueError("runtime does not match the selected Qwen3.5 adapter")
    for name, expected in runtime.get("metadata_sha256", {}).items():
        if _sha256(model / name) != expected:
            raise ValueError(f"runtime metadata changed after preparation: {name}")
    weight_files = runtime.get("weight_files")
    if not isinstance(weight_files, dict) or not weight_files:
        raise ValueError("runtime manifest does not freeze model weights")
    if merge.get("weight_files") != weight_files:
        raise ValueError("runtime weights differ from the SFT merge manifest")
    for name, expected in weight_files.items():
        if _sha256(model / name) != expected:
            raise ValueError(f"runtime weight changed after preparation: {name}")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": "protocol probe"}],
        tokenize=False,
        add_generation_prompt=True,
    )
    if not rendered.endswith("<|im_start|>assistant\n"):
        raise ValueError("runtime chat template must leave a bare assistant header")
    return {
        "runtime_model": str(model.resolve()),
        "context_tokens": runtime["context_tokens"],
        "adapter_sha256": actual,
        "model_type": merge["model_type"],
        "native_eos_token": tokenizer.eos_token,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-base")
    prepare.add_argument("--base-model", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    merge = subparsers.add_parser("merge")
    merge.add_argument("--base-model", type=Path, required=True)
    merge.add_argument("--adapter", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    runtime = subparsers.add_parser("prepare-runtime")
    runtime.add_argument("--base-model", type=Path, required=True)
    runtime.add_argument("--output", type=Path, required=True)
    runtime.add_argument("--context-tokens", type=int, default=131072)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--model", type=Path, required=True)
    validate.add_argument("--min-context", type=int, required=True)
    validate.add_argument("--expected-adapter-sha256", required=True)
    args = parser.parse_args()
    if args.command == "prepare-base":
        result = prepare_base_view(args.base_model, args.output)
    elif args.command == "merge":
        result = merge_sft_adapter(args.base_model, args.adapter, args.output)
    elif args.command == "prepare-runtime":
        result = build_runtime_view(args.base_model, args.output, args.context_tokens)
    else:
        result = validate_runtime(args.model, args.min_context, args.expected_adapter_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
