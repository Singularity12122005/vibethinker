from __future__ import annotations

import json
from pathlib import Path

from vibethinker_experiments.openthinker3.data_build import normalize_selected_row
from vibethinker_experiments.openthinker3.data_contract import (
    load_data_contract,
    prompt_fingerprint,
    prompt_tokens,
    valid_code,
    valid_math,
)

ROOT = Path(__file__).resolve().parents[2]


class FakeTokenizer:
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert tokenize and add_generation_prompt
        return list(range(len(messages[0]["content"].split()) + 2))


def _row(ability: str, gold: object) -> dict:
    return {
        "ability": ability,
        "prompt": [{"role": "user", "content": "Solve this clean prompt"}],
        "reward_model": {
            "style": "rule",
            "ground_truth": json.dumps(gold),
        },
        "extra_info": {
            "model_difficulty": {"DeepSeek-R1-Distill-Qwen-7B": 5},
        },
    }


def test_math_and_self_contained_code_routes() -> None:
    assert valid_math(_row("math", ["32"]))
    valid, route = valid_code(
        _row(
            "code",
            {
                "import_prefix": "from typing import *",
                "test_code": "def check(candidate):\n assert candidate(2) == 4",
                "entry_point": "solve",
            },
        )
    )
    assert valid and route == "import_prefix"


def test_question_id_route_is_rejected_without_external_archive() -> None:
    valid, route = valid_code(_row("code", {"question_id": "hidden-benchmark-key"}))
    assert not valid
    assert route is None


def test_normalization_keeps_json_boundary_and_copy_id() -> None:
    normalized = normalize_selected_row(_row("math", "32"), "math", 0)
    assert json.loads(normalized["reward_model"]["ground_truth"]) == ["32"]
    assert normalized["extra_info"]["repeat_copy"] == 0
    assert normalized["extra_info"]["selected_pool"] == "math"


def test_fingerprint_and_token_count_are_deterministic() -> None:
    first = _row("math", ["32"])
    second = _row("math", ["32"])
    second["prompt"][0]["content"] = "  solve   this CLEAN prompt "
    assert prompt_fingerprint(first) == prompt_fingerprint(second)
    assert prompt_tokens(first, FakeTokenizer()) == 6


def test_frozen_data_contract_uses_revision_and_hash_identity() -> None:
    contract = load_data_contract(ROOT / "configs/openthinker3/data.yaml")
    assert len(contract["source"]["revision"]) == 40
    assert contract["formal_id"].startswith("skywork-or1-rl-data@sha256:")
    assert contract["selection"]["math_unique"] == 30_000
    assert contract["selection"]["code_unique"] == 6_000
