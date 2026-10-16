"""CPU exercise of the GPU glue on the tiny model: r_L calibration, activation callables, G3 features."""
import json
import os

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from transformers.models.qwen3_moe import Qwen3MoeConfig, Qwen3MoeForCausalLM

from chain_fixture import build_chain
from sycophancy_phase0.gates.g15 import BankPrefix
from sycophancy_phase0.gpu_glue import acts_fn_for, calibrate_r_L, g3_features_for, load_r_L
from sycophancy_phase0.stages import load_prefix_bank, load_problems

V, D = 256, 32


def tiny_model():
    torch.manual_seed(7)
    cfg = Qwen3MoeConfig(vocab_size=V, hidden_size=D, intermediate_size=64, moe_intermediate_size=32, num_hidden_layers=4, num_attention_heads=4,
                         num_key_value_heads=2, head_dim=8, num_experts=8, num_experts_per_tok=2, decoder_sparse_step=1, mlp_only_layers=[],
                         norm_topk_prob=True, max_position_embeddings=512, tie_word_embeddings=False, attn_implementation="eager",
                         pad_token_id=V - 1, eos_token_id=V - 2, bos_token_id=None)
    m = Qwen3MoeForCausalLM(cfg).eval()
    m.requires_grad_(False)
    return m


def test_glue_on_tiny_model(tmp_path):
    ctx, info = build_chain(str(tmp_path), run_id="GLUE", n_problems=3)
    ctx.model = tiny_model()
    # the fake tokenizer ids are far outside the tiny vocab: map them into range for the forward passes
    bank = load_prefix_bank(ctx)
    for bp in bank:
        bp.ids = [i % (V - 2) for i in bp.ids]
    rL = calibrate_r_L(ctx, [bp.ids for bp in bank if bp.level == 2][:5], layers=(0, 1, 2))
    assert set(rL) == {0, 1, 2} and all(v > 0 for v in rL.values()) and load_r_L(ctx) == rL
    acts = acts_fn_for(ctx, layers=(1, 2))([(bp.ids[:12], [3, 4, 5, V - 2]) for bp in bank[:3]])
    assert acts[1].shape == (3, D) and np.isfinite(acts[2]).all()
    problems = load_problems(ctx)
    # G3 features: the fake encoder yields large ids -> remap through a wrapper encode for the suffixes
    ctx.builder.encode = lambda t: [ord(c) % (V - 2) for c in t]
    feats = g3_features_for(ctx, bank, {p: "W" for p in problems}, {p: "G" for p in problems}, layers=(1, 2), batch_size=4)
    n = sum(1 for bp in bank if bp.level == 2 and bp.script in ("A3", "B") and bp.script in bp.stats and bp.stats[bp.script]["est"].get("n", 0) > 0)
    assert feats["logits_top50"].shape == (n, 50) and feats["suffix_ratio"].shape == (n,) and set(feats["z"]) == {f"{p}_L{L}" for p in ("R1", "R2", "R3") for L in (1, 2)}
    assert feats["z"]["R2_L1"].shape == (n, D)
