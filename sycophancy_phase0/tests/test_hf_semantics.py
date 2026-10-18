"""CPU checks of the HF semantics the plan relies on (transformers==4.57.1, tiny random Qwen3-MoE)."""
import math
import numpy as np
import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
from transformers import GenerationConfig, LogitsProcessorList
from transformers.models.qwen3_moe import Qwen3MoeConfig, Qwen3MoeForCausalLM

from sycophancy_phase0.inference.steering import Steer, gen_start_from_prompt_lens
from sycophancy_phase0.inference.sampling import SeededGumbelSampler, generate_kwargs, has_temperature_warper, derive_seed
from sycophancy_phase0.inference.hf_engine import (right_pad, left_pad, position_ids_from_mask, clean_forward,
                                                   layer_output, residual_norm_median, response_logprobs,
                                                   next_token_kl, route_flip_fraction, generate_steered)

V, D, NL, NE, TOPK = 256, 32, 4, 8, 2


@pytest.fixture(scope="module")
def model():
    torch.manual_seed(0)
    cfg = Qwen3MoeConfig(vocab_size=V, hidden_size=D, intermediate_size=64, moe_intermediate_size=32,
                         num_hidden_layers=NL, num_attention_heads=4, num_key_value_heads=2, head_dim=8,
                         num_experts=NE, num_experts_per_tok=TOPK, decoder_sparse_step=1, mlp_only_layers=[],
                         norm_topk_prob=True, max_position_embeddings=256, tie_word_embeddings=False,
                         attn_implementation="eager", pad_token_id=V - 1, eos_token_id=V - 2, bos_token_id=None)
    m = Qwen3MoeForCausalLM(cfg).eval()
    for p in m.parameters():
        p.requires_grad_(False)
    return m


def _seq(rng, n):
    return rng.integers(0, V - 2, n).tolist()


def test_version_pin():
    assert transformers.__version__ == "4.57.1"


def test_hidden_states_indexing(model):
    rng = np.random.default_rng(0)
    s = _seq(rng, 12)
    captured = {}
    h = model.model.layers[1].register_forward_hook(lambda m, a, k, o: captured.setdefault("o", (o[0] if isinstance(o, tuple) else o).clone()), with_kwargs=True)
    out, att = clean_forward(model, [s], output_hidden_states=True)
    h.remove()
    hs = out.hidden_states
    assert len(hs) == NL + 1
    assert torch.allclose(layer_output(hs, 1), captured["o"], atol=1e-6)        # hidden_states[L+1] == layers[L] output
    with pytest.raises(ValueError):
        layer_output(hs, NL - 1)                                                   # last entry is post-norm


def test_recorder_sees_pre_hook_output(model):
    """With the out-of-place hook active, output_hidden_states still records the clean residual stream."""
    rng = np.random.default_rng(1)
    s = _seq(rng, 10)
    v = torch.randn(D)
    st = Steer(model, 1, v, r_L=1.0)
    try:
        clean, _ = clean_forward(model, [s], output_hidden_states=True)
        st.set([1.0], "S_all", pos_mask=torch.ones(1, len(s), dtype=torch.bool))
        steered, _ = clean_forward(model, [s], output_hidden_states=True)
    finally:
        st.remove()
    assert not torch.allclose(clean.logits, steered.logits, atol=1e-4)            # steering changed the logits
    assert torch.allclose(clean.hidden_states[2], steered.hidden_states[2], atol=1e-6)  # recorder = pre-hook
    assert not torch.allclose(clean.hidden_states[3], steered.hidden_states[3], atol=1e-4)  # downstream differs


def test_hook_noop_is_bitwise_identical_and_per_row_alpha(model):
    rng = np.random.default_rng(2)
    seqs = [_seq(rng, 9), _seq(rng, 9)]
    ref, _ = clean_forward(model, seqs)
    st = Steer(model, 2, torch.randn(D), r_L=1.0)
    try:
        st.off()
        out0, _ = clean_forward(model, seqs)
        assert torch.equal(ref.logits, out0.logits)                                # bitwise identical
        st.set([0.0, 1.0], "S_all", pos_mask=torch.ones(2, 9, dtype=torch.bool))
        out1, _ = clean_forward(model, seqs)
    finally:
        st.remove()
    assert torch.allclose(out1.logits[0], ref.logits[0], atol=1e-6)               # row with alpha=0 untouched
    assert not torch.allclose(out1.logits[1], ref.logits[1], atol=1e-4)


def test_left_padding_rope_invariance_and_explicit_positions(model):
    """A plain forward does not derive positions from attention_mask; RoPE makes a uniform shift exactly invariant in
    fp32, but bf16 leaks ~1e-2 logit differences at large pad counts (measured). Explicit position_ids are exact."""
    rng = np.random.default_rng(3)
    a, b = _seq(rng, 6), _seq(rng, 11)
    ref_a = model(input_ids=torch.tensor([a]), use_cache=False).logits[0]
    ids, att = left_pad([a, b], pad_id=V - 1)
    naive = model(input_ids=ids, attention_mask=att, use_cache=False).logits[0, -len(a):]
    fixed = model(input_ids=ids, attention_mask=att, position_ids=position_ids_from_mask(att), use_cache=False).logits[0, -len(a):]
    assert torch.allclose(naive, ref_a, atol=1e-5)                                # fp32: shift-invariant
    assert torch.allclose(fixed, ref_a, atol=1e-6)
    out, att_r = clean_forward(model, [a, b])                                     # right padding + explicit positions
    assert torch.allclose(out.logits[0, :len(a)], ref_a, atol=1e-6)
    # bf16: explicit positions remove the numerical leak of a large uniform shift
    mb = Qwen3MoeForCausalLM(model.config).eval()
    mb.load_state_dict(model.state_dict()); mb = mb.to(torch.bfloat16)
    ids2, att2 = left_pad([a, [1] * 200], pad_id=V - 1)
    refb = mb(input_ids=torch.tensor([a]), use_cache=False).logits[0].float()
    nb = mb(input_ids=ids2, attention_mask=att2, use_cache=False).logits[0, -len(a):].float()
    fb = mb(input_ids=ids2, attention_mask=att2, position_ids=position_ids_from_mask(att2), use_cache=False).logits[0, -len(a):].float()
    assert torch.equal(fb, refb)
    assert float((nb - refb).abs().max()) >= 1e-4


def test_processor_order_and_sampler_distribution(model):
    sampler = SeededGumbelSampler([1, 2], 0.7, device="cpu")
    gc = GenerationConfig(do_sample=True, temperature=0.7, top_k=0, top_p=1.0, max_new_tokens=1)
    procs = model._get_logits_processor(generation_config=gc, input_ids_seq_length=4, encoder_input_ids=None,
                                        prefix_allowed_tokens_fn=None, logits_processor=LogitsProcessorList([sampler]), device="cpu")
    names = [type(p).__name__ for p in procs]
    assert has_temperature_warper(procs) and names.index("SeededGumbelSampler") < names.index("TemperatureLogitsWarper")
    gc1 = GenerationConfig(do_sample=True, temperature=1.0, top_k=0, top_p=1.0, min_p=None, max_new_tokens=1)
    procs1 = model._get_logits_processor(generation_config=gc1, input_ids_seq_length=4, encoder_input_ids=None,
                                         prefix_allowed_tokens_fn=None, logits_processor=LogitsProcessorList([sampler]), device="cpu")
    assert not has_temperature_warper(procs1) and [type(p).__name__ for p in procs1] == ["SeededGumbelSampler"]
    # distribution check: one-row sampler over a fixed 8-logit vector
    logits = torch.tensor([[2.0, 1.0, 0.0, -1.0, 0.5, 0.2, -2.0, 1.5]])
    T = 0.7
    counts = torch.zeros(8)
    for seed in range(20000):
        s = SeededGumbelSampler([seed], T, device="cpu")
        counts[int(s(None, logits.clone())[0].argmax())] += 1
    p = torch.softmax(logits[0] / T, 0)
    chi2 = float(((counts - 20000 * p) ** 2 / (20000 * p)).sum())
    from scipy import stats
    assert stats.chi2.sf(chi2, 7) > 0.01


def test_generate_reproducible_and_seed_range(model):
    rng = np.random.default_rng(4)
    seqs = [_seq(rng, 7), _seq(rng, 5)]
    ids, att = left_pad(seqs, pad_id=V - 1)
    kw = generate_kwargs([11, 22], temperature=0.7, max_new_tokens=6, pad_token_id=V - 1, eos_token_id=[V - 2], device="cpu")
    o1 = model.generate(input_ids=ids, attention_mask=att, **kw)
    kw2 = generate_kwargs([11, 22], temperature=0.7, max_new_tokens=6, pad_token_id=V - 1, eos_token_id=[V - 2], device="cpu")
    o2 = model.generate(input_ids=ids, attention_mask=att, **kw2)
    assert torch.equal(o1, o2)
    assert 0 <= derive_seed("r", "p", "x", "a", 3, 2) < 2 ** 63


def test_S_gen_generate_matches_teacher_forcing(model):
    """First-token logits under S_gen steering during generate == teacher-forced forward with gen_start mask."""
    rng = np.random.default_rng(5)
    s = _seq(rng, 10)
    v = torch.randn(D)
    st = Steer(model, 1, v, r_L=2.0)
    try:
        ids, att = left_pad([s], pad_id=V - 1)
        st.set([1.0], "S_gen", gen_start=att.sum(-1) - 1)
        out = model.generate(input_ids=ids, attention_mask=att, do_sample=False, max_new_tokens=1, output_logits=True,
                             return_dict_in_generate=True, pad_token_id=V - 1)
        gen_logits = out.logits[0][0].float()
        st.set([1.0], "S_gen", generating=False, gen_start=torch.tensor([len(s) - 1]))
        tf = model(input_ids=torch.tensor([s]), use_cache=False).logits[0].float()
        st.off()
        clean = model(input_ids=torch.tensor([s]), use_cache=False).logits[0].float()
    finally:
        st.remove()
    assert torch.allclose(gen_logits, tf[-1], atol=1e-4)
    assert torch.allclose(tf[:-1], clean[:-1], atol=1e-5)                          # positions before gen_start untouched
    assert not torch.allclose(tf[-1], clean[-1], atol=1e-4)


def test_response_logprobs_kl_and_route_flip(model):
    rng = np.random.default_rng(6)
    prompt, resp = _seq(rng, 8), _seq(rng, 6)
    ids = prompt + resp
    st = Steer(model, 1, torch.randn(D), r_L=1.0)
    try:
        lp0 = response_logprobs(model, ids, len(prompt))
        lpa = response_logprobs(model, ids, len(prompt), steer=st, alpha=1.0)
        kl = next_token_kl(model, ids, len(prompt), st, alpha=1.0)
        kl0 = next_token_kl(model, ids, len(prompt), st, alpha=0.0)
        # round 10: the KL family is pinned to the generation temperature (logits / 0.7), not to raw logits
        kl_t1 = next_token_kl(model, ids, len(prompt), st, alpha=1.0, temperature=1.0)
        base_lg = clean_forward(model, [ids])[0].logits.float()[0]
        st.set([1.0], "S_gen", gen_start=torch.tensor([len(prompt) - 1]))
        st_lg = clean_forward(model, [ids])[0].logits.float()[0]
        st.off()
        k = len(prompt) - 1
        lp0m, lpam = torch.log_softmax(base_lg[k] / 0.7, -1), torch.log_softmax(st_lg[k] / 0.7, -1)
        kl_manual = float((lp0m.exp() * (lp0m - lpam)).sum())
        out0, att = clean_forward(model, [ids], output_router_logits=True)
        st.set([1.0], "S_gen", generating=False, gen_start=torch.tensor([len(prompt) - 1]))
        outa, _ = clean_forward(model, [ids], output_router_logits=True)
        st.off()
    finally:
        st.remove()
    assert lp0.shape == (len(resp),) and not torch.allclose(lp0, lpa)
    assert kl.shape == (len(resp),) and (kl >= -1e-6).all() and torch.allclose(kl0, torch.zeros_like(kl0), atol=1e-6)
    assert abs(float(kl[0]) - kl_manual) < 1e-5 and abs(float(kl[0]) - float(kl_t1[0])) > 1e-6
    assert len(out0.router_logits) == NL and out0.router_logits[0].shape == (len(ids), NE)
    mask = torch.zeros(1, len(ids), dtype=torch.bool); mask[0, len(prompt) - 1:] = True
    f0 = route_flip_fraction(out0.router_logits, out0.router_logits, 1, TOPK, mask)
    fa = route_flip_fraction(out0.router_logits, outa.router_logits, 1, TOPK, mask)
    assert f0 == 0.0 and 0.0 <= fa <= 1.0


def test_gradient_mode(model):
    rng = np.random.default_rng(7)
    prompt, resp = _seq(rng, 6), _seq(rng, 5)
    ids = prompt + resp
    st = Steer(model, 1, torch.randn(D), r_L=1.0)
    try:
        delta = torch.zeros(1, len(ids), D, dtype=torch.float32, requires_grad=True)
        lp = response_logprobs(model, ids, len(prompt), steer=st, alpha=0.0, grad_delta=delta)
        lp.sum().backward()
    finally:
        st.remove()
    g = delta.grad[0]
    assert g.shape == (len(ids), D)
    assert torch.count_nonzero(g[: len(prompt) - 1]) == 0                          # masked positions get no gradient
    assert torch.count_nonzero(g[len(prompt) - 1:]) > 0


def test_residual_norm_median_and_generate_steered(model):
    rng = np.random.default_rng(8)
    seqs = [_seq(rng, 14), _seq(rng, 12)]
    r = residual_norm_median(model, seqs, 1, min_pos=8)
    assert r > 0
    st = Steer(model, 1, torch.randn(D), r_L=r)
    try:
        kw = generate_kwargs([1, 2], temperature=0.7, max_new_tokens=4, pad_token_id=V - 1, eos_token_id=[V - 2], device="cpu")
        outs, reasons = generate_steered(model, seqs, st, [0.0, 1.0], kw)
    finally:
        st.remove()
    assert len(outs) == 2 and all(len(o) == 4 for o in outs)
