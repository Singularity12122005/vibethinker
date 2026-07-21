from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibethinker_experiments.checkpoints import validate_committed_checkpoint
from vibethinker_experiments.qwen35.checkpoint_schedule import (
    mark_checkpoint_committed,
    should_save_training_checkpoint,
)
from vibethinker_experiments.qwen35.runtime_model import (
    bare_chat_template,
    build_runtime_view,
)


def test_checkpoint_schedule_and_atomic_marker(tmp_path: Path):
    base = dict(save_freq=50, steps_per_epoch=32, esi_close_to_expiration=False)
    assert should_save_training_checkpoint(global_steps=32, is_last_step=False, **base)
    assert should_save_training_checkpoint(global_steps=50, is_last_step=False, **base)
    assert not should_save_training_checkpoint(global_steps=31, is_last_step=False, **base)
    (tmp_path / "state.bin").write_bytes(b"state")
    marker = mark_checkpoint_committed(tmp_path, 32)
    manifest = validate_committed_checkpoint(tmp_path)
    assert manifest["global_step"] == 32
    assert manifest["metadata"]["family"] == "qwen35"
    assert [item["path"] for item in manifest["files"]] == ["state.bin"]
    assert not (marker.parent / ".COMMITTED.tmp").exists()


def test_runtime_preserves_native_metadata(tmp_path: Path):
    base, output = tmp_path / "base", tmp_path / "runtime"
    base.mkdir()
    (base / "config.json").write_text('{"text_config":{"max_position_embeddings":262144}}')
    (base / "tokenizer_config.json").write_text('{"model_max_length":262144}')
    (base / "weights.safetensors").write_bytes(b"weights")
    manifest = build_runtime_view(base, output, 131072)
    assert manifest["metadata_policy"] == "native_unmodified"
    assert (output / "weights.safetensors").is_symlink()
    assert json.loads((output / "config.json").read_text()) == json.loads(
        (base / "config.json").read_text()
    )


def test_runtime_rejects_context_extension(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "config.json").write_text('{"max_position_embeddings":128}')
    (base / "tokenizer_config.json").write_text('{"model_max_length":128}')
    with pytest.raises(ValueError, match="exceeds native context"):
        build_runtime_view(base, tmp_path / "runtime", 129)


def test_bare_chat_template_replaces_generation_block():
    template = (
        "prefix\n{%- if add_generation_prompt %}\n"
        "{{ '<|im_start|>assistant\\n<think>\\n' }}\n{%- endif %}"
    )
    rewritten = bare_chat_template(template)
    assert rewritten.endswith("{%- endif %}")
    assert "<think>" not in rewritten
    assert "<|im_start|>assistant" in rewritten
