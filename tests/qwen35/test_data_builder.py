from __future__ import annotations

import pytest

from vibethinker_experiments.data.decontamination import BenchmarkDenyIndex
from vibethinker_experiments.qwen35.data_builder import (
    audit_rows,
    combine_math500_gsm500,
    select_math500,
    to_verl_records,
)


def row(index: int) -> dict:
    return {
        "problem": f"What is {index} plus zero?",
        "answer": str(index),
        "source": "fixture",
        "difficulty": "warmup",
        "topic": "algebra",
    }


def test_audit_rejects_protocol_hints_and_duplicates():
    with pytest.raises(ValueError, match="dirty prompt"):
        audit_rows([{"problem": "<think>solve</think>", "answer": "1"}])
    with pytest.raises(ValueError, match="duplicate"):
        audit_rows([row(1), row(1)])


def test_prepare_verl_schema_keeps_component():
    source = {**row(7), "rl_component": "gsm8k500"}
    records = to_verl_records([source])
    assert records[0]["data_source"] == "vibethinker_math"
    assert records[0]["reward_model"]["ground_truth"] == "7"
    assert records[0]["extra_info"]["rl_component"] == "gsm8k500"
    assert records[0]["prompt"] == [{"role": "user", "content": source["problem"]}]


def test_union_requires_exact_component_sizes():
    with pytest.raises(ValueError, match=r"expected 500\+500"):
        combine_math500_gsm500([row(1)], [row(2)])


def test_math500_selection_requires_and_enforces_deny_receipt() -> None:
    quotas = {"algebra": {"warmup": 1}}
    empty_index = BenchmarkDenyIndex.build([])
    selected = select_math500(
        [row(1)],
        deny_index=empty_index,
        deny_receipt_sha256="a" * 64,
        quotas=quotas,
    )
    assert selected[0]["benchmark_deny_receipt_sha256"] == "a" * 64

    denied = BenchmarkDenyIndex.build([("benchmark", row(1)["problem"])])
    with pytest.raises(ValueError, match="deny hit"):
        select_math500(
            [row(1)],
            deny_index=denied,
            deny_receipt_sha256="b" * 64,
            quotas=quotas,
        )
