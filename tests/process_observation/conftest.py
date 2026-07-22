from __future__ import annotations

from pathlib import Path

import pytest

from vibethinker_experiments.evaluation.io import read_jsonl
from vibethinker_experiments.process_observation.artifacts import load_profile
from vibethinker_experiments.process_observation.models import (
    ARUCandidate,
    CheckpointReference,
    NaturalRolloutReference,
)

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.fixture
def process_profile():
    return load_profile(REPOSITORY / "configs/process_observation/toy-qwen25-15k.yaml")


@pytest.fixture
def checkpoint_reference():
    return CheckpointReference.from_mapping(
        read_jsonl(REPOSITORY / "data/process_observation/toy/checkpoint_reference.jsonl")[0]
    )


@pytest.fixture
def natural_rollout():
    return NaturalRolloutReference.from_mapping(
        read_jsonl(REPOSITORY / "data/process_observation/toy/natural_rollouts.jsonl")[0]
    )


@pytest.fixture
def aru_candidate():
    return ARUCandidate.from_mapping(
        read_jsonl(REPOSITORY / "data/process_observation/toy/aru_candidates.jsonl")[0]
    )
