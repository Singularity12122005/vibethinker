from __future__ import annotations

import pytest

from vibethinker_experiments.data.decontamination import BenchmarkDenyIndex
from vibethinker_experiments.qwen25.math500 import (
    candidates_from_sft,
    prompt_hash,
    select_math500,
    to_verl_records,
)


class FakeTokenizer:
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert not tokenize and add_generation_prompt
        return messages[0]["content"]

    def __call__(self, text, *, add_special_tokens):
        assert not add_special_tokens
        return {"input_ids": text.split()}


def candidate(index: int) -> dict:
    return {
        "problem": f"problem {index}",
        "answer": "42",
        "problem_hash": f"{index:064x}",
        "topic": "algebra",
        "difficulty": "warmup",
    }


def test_small_quota_selection_is_deterministic():
    quotas = {"algebra": {"warmup": 2}}
    rows = [candidate(3), candidate(1), candidate(2)]
    assert select_math500(rows, quotas) == select_math500(reversed(rows), quotas)


def test_verl_conversion_enforces_clean_768_token_prompts():
    records = to_verl_records([candidate(1)], FakeTokenizer())
    assert records[0]["prompt"] == [{"role": "user", "content": "problem 1"}]
    assert records[0]["reward_model"]["ground_truth"] == "42"

    dirty = candidate(2)
    dirty["problem"] = "<think>do it</think>"
    with pytest.raises(ValueError, match="forbidden"):
        to_verl_records([dirty], FakeTokenizer())

    long = candidate(3)
    long["problem"] = "x " * 769
    with pytest.raises(ValueError, match="768"):
        to_verl_records([long], FakeTokenizer())


def test_sft_candidate_builder_denies_benchmark_overlap():
    prompt = "A known benchmark problem with enough clean words for exact matching"
    digest = prompt_hash(prompt)
    sft = [
        {
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "<think>x</think>42"},
            ],
            "_domain": "math",
            "_prompt_hash": digest,
            "_verification": {
                "passed": True,
                "type": "math_verifier",
                "detail": {"extracted": "42"},
            },
        }
    ]
    pool = [{"_prompt_hash": digest, "_gold_answer": "42", "_topic": "algebra"}]
    eligible, rejected = candidates_from_sft(
        sft,
        pool,
        deny_index=BenchmarkDenyIndex.build([("benchmark", prompt)]),
    )
    assert eligible == []
    assert rejected["benchmark_exact"] == 1
