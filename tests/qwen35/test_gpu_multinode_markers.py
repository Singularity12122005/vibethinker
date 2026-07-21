"""Execution placeholders: these contracts require the pinned GPU runtime."""

from __future__ import annotations

import pytest


@pytest.mark.gpu
@pytest.mark.skip(reason="requires 8×A100-80GB and the pinned Qwen3.5 runtime")
def test_sft_one_step_and_memory_efficient_loss_equivalence():
    pass


@pytest.mark.gpu
@pytest.mark.multinode
@pytest.mark.skip(reason="requires 2 nodes, 16 GPUs, Ray, vLLM, and patched VERL v0.8.0")
def test_verl_128k_one_step_checkpoint_and_weight_refresh():
    pass
