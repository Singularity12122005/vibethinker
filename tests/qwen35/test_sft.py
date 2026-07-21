from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from vibethinker_experiments.qwen35.train_sft_qwen35 import (  # noqa: E402
    AssistantOnlyCollator,
    install_agent_chat_template,
)


class FakeTokenizer:
    pad_token_id = 0
    chat_template = (
        "prefix\n{%- if add_generation_prompt %}\n"
        "{{ '<|im_start|>assistant\\n<think>\\n' }}\n{%- endif %}"
    )

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert not tokenize
        text = ""
        for message in messages:
            text += f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>\n"
        if add_generation_prompt:
            suffix = "<|im_start|>assistant\n"
            if "<think>" in self.chat_template[self.chat_template.rfind("{%- if") :]:
                suffix += "<think>\n"
            text += suffix
        return text

    def __call__(self, text, *, add_special_tokens):
        assert not add_special_tokens
        return {"input_ids": [ord(character) for character in text]}


def test_chat_template_removes_think_prefill():
    tokenizer = FakeTokenizer()
    install_agent_chat_template(tokenizer)
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": "probe"}],
        tokenize=False,
        add_generation_prompt=True,
    )
    assert rendered.endswith("<|im_start|>assistant\n")
    assert "<think>" not in rendered


def test_collator_masks_prompt_and_padding():
    tokenizer = FakeTokenizer()
    install_agent_chat_template(tokenizer)
    collator = AssistantOnlyCollator(tokenizer, max_length=200)
    rows = [
        {
            "messages": [
                {"role": "user", "content": "u"},
                {"role": "assistant", "content": "answer"},
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "longer"},
                {"role": "assistant", "content": "x"},
            ]
        },
    ]
    batch = collator(rows)
    assert batch["input_ids"].shape == batch["labels"].shape
    assert torch.any(batch["labels"] != -100)
    assert torch.all(batch["labels"][batch["attention_mask"] == 0] == -100)


def test_collator_rejects_truncation():
    tokenizer = FakeTokenizer()
    install_agent_chat_template(tokenizer)
    with pytest.raises(ValueError, match="exceeds max length"):
        AssistantOnlyCollator(tokenizer, max_length=4)._encode_one(
            {
                "messages": [
                    {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "a"},
                ]
            }
        )
