from __future__ import annotations

import os

import pytest


@pytest.mark.gpu
@pytest.mark.skipif(
    os.environ.get("RUN_QWEN25_GPU_CONTRACT") != "1",
    reason="set RUN_QWEN25_GPU_CONTRACT=1 on the formal GPU host",
)
def test_formal_gpu_contract():
    import torch

    assert torch.cuda.device_count() == 16
    for index in range(torch.cuda.device_count()):
        properties = torch.cuda.get_device_properties(index)
        assert "A100" in properties.name
        assert properties.total_memory >= 79 * 1024**3


@pytest.mark.multinode
@pytest.mark.skipif(
    os.environ.get("RUN_QWEN25_MULTINODE_CONTRACT") != "1",
    reason="set RUN_QWEN25_MULTINODE_CONTRACT=1 under the formal launcher",
)
def test_formal_multinode_contract():
    assert int(os.environ["NNODES"]) == 2
    assert int(os.environ["NPROC_PER_NODE"]) == 8
    assert int(os.environ["WORLD_SIZE"]) == 16
