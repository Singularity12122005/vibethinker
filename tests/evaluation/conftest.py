from __future__ import annotations

from pathlib import Path

import pytest

from vibethinker_experiments.evaluation.generation import (
    GenerationRequest,
    GenerationResponse,
    build_generation_result,
)
from vibethinker_experiments.evaluation.io import read_jsonl
from vibethinker_experiments.evaluation.models import EvaluationProfile, PanelManifest

REPOSITORY = Path(__file__).resolve().parents[2]


class SyntheticTransport:
    answers = {
        "toy-math-001": "<think>two plus two</think>4",
        "toy-code-001": "<think>define function</think>def double(n):\n    return n * 2",
        "toy-stem-001": "<think>open branch</think>C",
        "toy-ifc-001": "<think>two lines</think>An amber kite rises.\nIt turns.",
        "toy-knowledge-001": "<think>recall synthetic fact</think>Nivora has two moons.",
    }

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            text=self.answers[request.panel_id],
            prompt_tokens=40,
            completion_tokens=20,
            finish_reason="eos",
        )


@pytest.fixture
def toy_profile() -> EvaluationProfile:
    return EvaluationProfile.load(REPOSITORY / "configs/evaluation/toy-128k.yaml")


@pytest.fixture
def toy_manifest() -> PanelManifest:
    return PanelManifest.load(REPOSITORY / "data/panels/toy/manifest.yaml")


@pytest.fixture
def toy_rows() -> list[dict]:
    return read_jsonl(REPOSITORY / "data/panels/toy/panel.jsonl")


@pytest.fixture
def generation_results(toy_rows, toy_profile, toy_manifest) -> list[dict]:
    transport = SyntheticTransport()
    return [
        build_generation_result(
            row,
            profile=toy_profile,
            panel_sha256=toy_manifest.panel_sha256,
            transport=transport,
        )
        for row in toy_rows
    ]
