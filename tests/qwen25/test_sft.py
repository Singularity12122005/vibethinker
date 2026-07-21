from __future__ import annotations

from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from vibethinker_experiments.qwen25.sft import (  # noqa: E402
    AssistantOnlyCollator,
    load_config,
)

ROOT = Path(__file__).resolve().parents[2]


class FakeTokenizer:
    pad_token_id = 0

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert not tokenize
        text = ""
        for message in messages:
            if message["role"] == "user":
                text += f"<u>{message['content']}</u>"
            else:
                text += f"<a>{message['content']}</a>"
        if add_generation_prompt:
            text += "<a>"
        return text

    def __call__(self, text, *, add_special_tokens):
        assert not add_special_tokens
        return {"input_ids": [ord(character) for character in text]}


def test_collator_masks_prompt_and_padding_without_offsets():
    collator = AssistantOnlyCollator(FakeTokenizer(), max_length=200)
    batch = collator(
        [
            {
                "messages": [
                    {"role": "user", "content": "user"},
                    {"role": "assistant", "content": "answer"},
                ]
            },
            {
                "messages": [
                    {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "longer answer"},
                ]
            },
        ]
    )
    assert batch["input_ids"].shape == batch["labels"].shape
    assert torch.any(batch["labels"] != -100)
    assert torch.all(batch["labels"][batch["attention_mask"] == 0] == -100)


def test_collator_rejects_truncation():
    with pytest.raises(ValueError, match="without truncation"):
        AssistantOnlyCollator(FakeTokenizer(), max_length=4)._encode_one(
            {
                "messages": [
                    {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "a"},
                ]
            }
        )


@pytest.mark.parametrize(
    ("name", "rows", "steps", "selected"),
    [
        ("sft_15k.yaml", 15000, 1180, 1),
        ("sft_30k_native.yaml", 30000, 2350, 5),
    ],
)
def test_sft_manifests_freeze_real_schedule(name, rows, steps, selected):
    config = load_config(ROOT / "configs" / "qwen25" / name)
    assert config["data"]["rows"] == rows
    assert config["data"]["packing"] is False
    assert config["data"]["truncation"] == "error"
    assert config["training"]["epochs"] == 10
    assert config["training"]["planned_optimizer_steps"] == steps
    assert config["training"]["selected_epoch_for_rl"] == selected
