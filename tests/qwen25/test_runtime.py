from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from vibethinker_experiments.qwen25.runtime_model import (
    END_OF_TEXT_ID,
    IM_END_ID,
    build_runtime_view,
    validate_runtime,
)


def make_base(root: Path) -> Path:
    base = root / "base"
    base.mkdir()
    (base / "config.json").write_text(
        '{"model_type":"qwen2","max_position_embeddings":32768,"eos_token_id":151643}'
    )
    (base / "tokenizer_config.json").write_text(
        '{"eos_token":"<|endoftext|>","pad_token":"<|endoftext|>"}'
    )
    (base / "generation_config.json").write_text('{"eos_token_id":151643}')
    (base / "weights.safetensors").write_bytes(b"weights")
    (base / "vibethinker_sft_merge_manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": {"adapter_model.safetensors": "selected"},
                "weight_files": {"weights.safetensors": hashlib.sha256(b"weights").hexdigest()},
            }
        )
    )
    return base


def test_runtime_view_patches_metadata_and_symlinks_weights(tmp_path):
    output = tmp_path / "runtime"
    manifest = build_runtime_view(make_base(tmp_path), output)
    config = json.loads((output / "config.json").read_text())
    tokenizer = json.loads((output / "tokenizer_config.json").read_text())
    generation = json.loads((output / "generation_config.json").read_text())
    assert manifest["context_tokens"] == 65536
    assert config["max_position_embeddings"] == 65536
    assert config["eos_token_id"] == IM_END_ID
    assert tokenizer["eos_token"] == "<|im_end|>"
    assert generation["eos_token_id"] == [IM_END_ID, END_OF_TEXT_ID]
    assert (output / "weights.safetensors").is_symlink()
    assert (
        validate_runtime(output, expected_adapter_sha256="selected")["adapter_sha256"] == "selected"
    )
    (tmp_path / "base" / "weights.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="weight changed"):
        validate_runtime(output, expected_adapter_sha256="selected")


def test_runtime_view_rejects_nonformal_context(tmp_path):
    with pytest.raises(ValueError, match="65,536"):
        build_runtime_view(make_base(tmp_path), tmp_path / "runtime", 32768)
