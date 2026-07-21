from __future__ import annotations

import pytest

from vibethinker_experiments.data.decontamination import BenchmarkDenyIndex
from vibethinker_experiments.qwen25.assembly import assemble_domains, audit_dataset


def row(domain: str, index: int, *, verified: bool = False) -> dict:
    value = {
        "messages": [
            {"role": "user", "content": f"{domain} prompt {index}"},
            {"role": "assistant", "content": "<think>reasoning</think>answer"},
        ],
        "_domain": domain,
        "_prompt_hash": f"{domain}-{index}",
    }
    if verified:
        value["_verification"] = {
            "passed": True,
            "type": {
                "math": "math_verifier",
                "code": "code_tests",
                "general": "general_judge",
            }[domain],
        }
    return value


def test_assembler_is_order_independent_and_deterministic():
    parts = {domain: [row(domain, 1), row(domain, 0)] for domain in ("math", "code", "general")}
    first = assemble_domains(parts, rows_per_domain=2, seed="frozen")
    second = assemble_domains(
        {domain: list(reversed(rows)) for domain, rows in parts.items()},
        rows_per_domain=2,
        seed="frozen",
    )
    assert first == second


def test_native_audit_requires_domain_specific_verification():
    rows = assemble_domains(
        {domain: [row(domain, 0, verified=True)] for domain in ("math", "code", "general")},
        rows_per_domain=1,
        seed="native",
    )
    audit = audit_dataset(rows, rows_per_domain=1, require_native_verification=True)
    assert audit.rows == 3
    assert audit.benchmark_audit == "not_provided"
    assert audit.near_deny_matches is None

    rows[0]["_verification"]["passed"] = False
    with pytest.raises(ValueError, match="unverified=1"):
        audit_dataset(rows, rows_per_domain=1, require_native_verification=True)


def test_benchmark_audit_reports_evidence_without_zero_by_default():
    rows = assemble_domains(
        {domain: [row(domain, 0)] for domain in ("math", "code", "general")},
        rows_per_domain=1,
        seed="audit",
    )
    index = BenchmarkDenyIndex.build([("known", "math prompt 0")])
    audit = audit_dataset(rows, rows_per_domain=1, deny_index=index)
    assert audit.benchmark_audit == "performed"
    assert audit.hard_deny_matches == 1
