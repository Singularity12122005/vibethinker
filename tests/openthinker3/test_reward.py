from __future__ import annotations

import pytest

from vibethinker_experiments.openthinker3.reward import (
    FORMAL_RUNTIME_ENV,
    score_one,
    validate_formal_runtime,
)
from vibethinker_experiments.openthinker3.verifier import load_verifier, smoke_test_verifier


def fake_verifier(solution, ground_truth, *, task, timeout, is_binary_reward):
    assert task in {"math", "code"}
    assert timeout > 0
    assert is_binary_reward is True
    return solution.rsplit("</think>", 1)[-1].strip() in ground_truth, {"verifier_ok": True}


def failing_verifier(*_args, **_kwargs):
    raise RuntimeError("sandbox unavailable")


def test_reward_normalizes_json_boundary_and_binary_score() -> None:
    correct = score_one("<think>work</think>32", '["32"]', "math", verifier=fake_verifier)
    wrong = score_one("<think>work</think>31", ["32"], "math", verifier=fake_verifier)
    assert correct == {
        "score": 1.0,
        "acc": 1.0,
        "verifier_ok": True,
        "verifier_error": "",
    }
    assert wrong["score"] == 0.0
    assert wrong["verifier_ok"] is True


def test_verifier_failure_is_not_reported_as_normal_wrong_answer() -> None:
    result = score_one("answer", ["answer"], "math", verifier=failing_verifier)
    assert result["score"] == 0.0
    assert result["verifier_ok"] is False
    assert "sandbox unavailable" in result["verifier_error"]


def test_formal_runtime_fails_closed() -> None:
    validate_formal_runtime(dict(FORMAL_RUNTIME_ENV))
    incomplete = dict(FORMAL_RUNTIME_ENV)
    incomplete.pop("VT_CODE_CASE_TIMEOUT_SECONDS")
    with pytest.raises(RuntimeError, match="formal reward runtime"):
        validate_formal_runtime(incomplete)


def test_external_verifier_adapter_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VT_SKYWORK_VERIFIER", raising=False)
    with pytest.raises(RuntimeError, match="license-reviewed"):
        load_verifier()


def test_external_verifier_abi_smoke_test() -> None:
    result = smoke_test_verifier(f"{__name__}:fake_verifier")
    assert result == {"status": "ok", "result_type": "bool"}
