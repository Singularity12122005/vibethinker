from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibethinker_experiments.evaluation.models import EvaluationProfile, PanelManifest
from vibethinker_experiments.evaluation.validation import (
    load_and_validate_panel,
    validate_panel_rows,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def test_128k_context_is_loaded_explicitly(toy_profile):
    assert toy_profile.context_tokens == 131_072
    assert toy_profile.generation_cap_tokens == 4096


def test_context_has_no_implicit_default():
    values = {
        "profile_id": "missing-context",
        "mode": "toy",
        "generation_cap_tokens": 10,
        "temperature": 0,
        "top_p": 1,
        "seed": 1,
        "require_judgments": False,
    }
    with pytest.raises(ValueError, match="context_tokens"):
        EvaluationProfile.from_mapping(values)


def test_panel_hash_and_mode_are_validated(toy_profile, toy_manifest):
    rows = load_and_validate_panel(
        REPOSITORY / "data/panels/toy/panel.jsonl", toy_manifest, toy_profile
    )
    assert len(rows) == 5
    formal = EvaluationProfile.from_mapping(
        {**toy_profile.to_dict(), "profile_id": "formal", "mode": "formal"}
    )
    with pytest.raises(ValueError, match="formal/toy isolation"):
        toy_manifest.assert_compatible(formal)


def test_negative_fixtures_are_rejected():
    cases = json.loads((REPOSITORY / "data/panels/negative/invalid-panels.json").read_text())
    for case in cases:
        domains = tuple(sorted({row["domain"] for row in case["rows"]}))
        manifest = PanelManifest.from_mapping(
            {
                "panel_name": case["case"],
                "panel_version": "negative",
                "mode": case["mode"],
                "panel_sha256": "0" * 64,
                "row_count": len(case["rows"]),
                "domains": domains,
            }
        )
        with pytest.raises(ValueError):
            validate_panel_rows(case["rows"], manifest)
