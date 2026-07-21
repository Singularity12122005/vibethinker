from __future__ import annotations

import pytest

from vibethinker_experiments.qwen35.data_pipeline import (
    assemble_verified_row,
    audit_final_dataset,
    canonical_prompt_hash,
    fill_domain_quota,
    finalize_sft_dataset,
    join_and_verify_domain,
)


def prompt_row(index: int, domain: str, *, tranche: str = "primary") -> dict:
    prompt = f"{domain} prompt {index}"
    row = {
        "messages": [{"role": "user", "content": prompt}],
        "_domain": domain,
        "_mix_domain": domain,
        "_prompt_hash": canonical_prompt_hash(prompt),
        "_source_tranche": tranche,
    }
    if domain == "math":
        row["_gold_answer"] = str(index)
    elif domain == "code":
        row["_quality_grade"] = "A"
        row["_tests"] = {"inputs": [["x"]], "outputs": [["x"]]}
    else:
        row["_reference_answer"] = f"reference {index}"
    return row


def teacher_result(row: dict, index: int, *, attempt: int = 1) -> dict:
    return {
        "_prompt_hash": row["_prompt_hash"],
        "reasoning": f"reasoning {index}",
        "content": f"answer {index}",
        "finish_reason": "stop",
        "think_tokens": 10,
        "visible_tokens": 4,
        "chat_tokens": 24,
        "attempt": attempt,
    }


def passing_verifier(_row: dict, _visible: str) -> tuple[bool, dict]:
    return True, {"accepted": True}


def code_verifier(_row: dict, _visible: str) -> tuple[bool, dict]:
    return True, {"n_pass": 1, "n_total": 1}


def test_join_is_pool_ordered_and_uses_a_later_verified_attempt():
    pool = [prompt_row(index, "general") for index in range(3)]
    results = [
        teacher_result(pool[2], 2),
        teacher_result(pool[0], 0, attempt=2),
        {**teacher_result(pool[0], 0, attempt=1), "finish_reason": "length"},
        {**teacher_result(pool[1], 1, attempt=1), "chat_tokens": 30_001},
        teacher_result(pool[1], 1, attempt=2),
    ]
    rows, audit = join_and_verify_domain(pool, results, "general", passing_verifier)
    assert [row["_prompt_hash"] for row in rows] == [source["_prompt_hash"] for source in pool]
    assert audit["verified_prompts"] == 3
    assert audit["rejections"] == {
        "teacher result did not finish with stop": 1,
        "teacher result violates token limits": 1,
    }


def test_quota_fill_consumes_reserve_in_frozen_pool_order():
    pool = [
        prompt_row(0, "general"),
        prompt_row(1, "general"),
        prompt_row(2, "general", tranche="reserve"),
    ]
    verified = [
        assemble_verified_row(pool[2], teacher_result(pool[2], 2), "general", passing_verifier),
        assemble_verified_row(pool[0], teacher_result(pool[0], 0), "general", passing_verifier),
    ]
    selected = fill_domain_quota(pool, verified, "general", quota=2)
    assert [row["_source_tranche"] for row in selected] == ["primary", "reserve"]
    with pytest.raises(ValueError, match="insufficient verified"):
        fill_domain_quota(pool, verified, "general", quota=3)


def test_assembly_strips_verifier_payloads_from_final_rows():
    source = prompt_row(1, "code")
    row = assemble_verified_row(source, teacher_result(source, 1), "code", code_verifier)
    assert "_tests" not in row
    assert row["_verification"] == {
        "type": "code_tests",
        "passed": True,
        "detail": {"n_pass": 1, "n_total": 1},
    }


def test_final_audit_checks_contract_and_shuffle_is_deterministic():
    rows_by_domain = {}
    for domain in ("math", "code", "general"):
        source = prompt_row(1, domain)
        verifier = code_verifier if domain == "code" else passing_verifier
        rows_by_domain[domain] = [
            assemble_verified_row(
                source,
                teacher_result(source, 1),
                domain,
                verifier,
            )
        ]
    audit = audit_final_dataset(rows_by_domain, quota=1)
    assert audit["domains"] == {"math": 1, "code": 1, "general": 1}
    first, _ = finalize_sft_dataset(rows_by_domain, quota=1)
    second, _ = finalize_sft_dataset(rows_by_domain, quota=1)
    assert [row["_prompt_hash"] for row in first] == [row["_prompt_hash"] for row in second]


def test_final_audit_rejects_token_wall():
    rows_by_domain = {}
    for domain in ("math", "code", "general"):
        source = prompt_row(1, domain)
        verifier = code_verifier if domain == "code" else passing_verifier
        rows_by_domain[domain] = [
            assemble_verified_row(
                source,
                teacher_result(source, 1),
                domain,
                verifier,
            )
        ]
    rows_by_domain["general"][0]["_chat_tokens"] = 30_001
    with pytest.raises(ValueError, match="token limit"):
        audit_final_dataset(rows_by_domain, quota=1)
