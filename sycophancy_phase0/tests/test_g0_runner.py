"""CPU checks of the G0 runner pieces and of the review-driven hook/sampler/template fixes (tiny Qwen3-MoE)."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
from transformers.models.qwen3_moe import Qwen3MoeConfig, Qwen3MoeForCausalLM

from fake_tok import encode, first_turn_ids, is_ws
from sycophancy_phase0.constants import IM_END, SYSTEM_PROMPT, TEMPERATURE, THINK_END, THINK_START
from sycophancy_phase0.gates.g0 import g0_1, g0_2, g0_3, g0_7
from sycophancy_phase0.gates.g0_runner import (batch_conditions, cache_vs_recompute_kl, continuation_specs, generate_with_cache, generation_vs_teacher_forcing, hook_selfcheck,
                                               paired_e3, sampler_chi2, support_defect_logps, template_consistency)
from sycophancy_phase0.inference.engine import EngineRouter, FakeEngine, HFEngine, GenRequest
from sycophancy_phase0.inference.hf_engine import generate_steered, left_pad, response_logprobs, extract_z
from sycophancy_phase0.inference.sampling import SeededGumbelSampler, generate_kwargs
from sycophancy_phase0.inference.steering import Steer, read_mask_from_spans
from sycophancy_phase0.inference.templates import TurnBuilder
from sycophancy_phase0.rollout import BankProblem, RolloutSpec, prefix_from_trajectory, run_rollouts
from sycophancy_phase0.trajectory import Arm

V, D, NL = 256, 32, 4


@pytest.fixture(scope="module")
def model():
    torch.manual_seed(1)
    cfg = Qwen3MoeConfig(vocab_size=V, hidden_size=D, intermediate_size=64, moe_intermediate_size=32, num_hidden_layers=NL,
                         num_attention_heads=4, num_key_value_heads=2, head_dim=8, num_experts=8, num_experts_per_tok=2,
                         decoder_sparse_step=1, mlp_only_layers=[], norm_topk_prob=True, max_position_embeddings=256,
                         tie_word_embeddings=False, attn_implementation="eager", pad_token_id=V - 1, eos_token_id=V - 2, bos_token_id=None)
    m = Qwen3MoeForCausalLM(cfg).eval()
    for p in m.parameters():
        p.requires_grad_(False)
    return m


def _seq(rng, n):
    return rng.integers(0, V - 2, n).tolist()


def test_hook_selfcheck_and_sampler_chi2(model):
    rng = np.random.default_rng(0)
    ids = _seq(rng, 14)
    st = Steer(model, 1, torch.randn(D), r_L=2.0)
    try:
        checks, diag = hook_selfcheck(model, st, ids, gen_start=7, with_diagnostics=True)
        assert all(checks.values()), checks
        assert diag["teacher_forcing_prefix_residual_maxdiff"] == 0.0 and diag["no_hook_repeat_logit_maxdiff"] == 0.0 and diag["hooked_layer"] == 1
        assert diag["teacher_forcing_suffix_residual_maxdiff"] > 0 and hook_selfcheck(model, st, ids, gen_start=7) == checks
        with pytest.raises(RuntimeError):
            Steer(model, 1, torch.randn(D), r_L=1.0)          # double attachment refused
        res = sampler_chi2(model, ids, n=3000, batch_size=500)
        assert res["p"] > 0.01 and res["n_bins"] >= 2
        assert g0_2(checks, res["p"]).passed
    finally:
        st.remove()
    with pytest.raises(RuntimeError):
        st.set([1.0])                                            # set after remove
    with pytest.raises(ValueError):
        Steer(model, 1, torch.zeros(D), r_L=1.0)


def test_cache_vs_recompute_and_support_defect(model):
    rng = np.random.default_rng(1)
    items = [(_seq(rng, 9), _seq(rng, 6)) for _ in range(5)]
    r = cache_vs_recompute_kl(model, items)
    kl = r["kl"]
    assert kl.shape == (5,) and r["n_not_applicable"] == 0 and g0_3(kl, min_valid=1).passed and float(np.max(kl)) < 1e-4 and r["temperature"] == TEMPERATURE
    # v1.4 (memo I2): a real generate cache — covers prompt + generated[:-1]; verified bitwise against ids_3, else "not applicable"
    ids_2 = _seq(rng, 9)
    c = generate_with_cache(model, ids_2, max_new_tokens=4, greedy=True, pad_id=V - 1)
    assert len(c["gen_ids"]) == 4 and c["cached_ids"] == ids_2 + c["gen_ids"][:-1] and c["n_cached"] == len(c["cached_ids"])
    delta = _seq(rng, 3)
    good = (ids_2, c["gen_ids"] + delta)
    bad = (ids_2, [c["gen_ids"][0], (c["gen_ids"][1] + 1) % V] + c["gen_ids"][2:] + delta)       # "normalisation" rewrote a cached token
    r2 = cache_vs_recompute_kl(model, [good, bad, good], caches=[(c["cached_ids"], c["past"])] * 3)
    assert np.isfinite(r2["kl"][0]) and r2["kl"][0] < 1e-4 and np.isnan(r2["kl"][1]) and r2["n_not_applicable"] == 1
    assert "not a prefix" in r2["reasons"][1] and r2["reasons"][0] is None and np.isfinite(r2["kl"][2])   # the caller's cache is untouched
    g3 = g0_3(r2["kl"], min_valid=1, max_na_rate=0.5)                        # NaN entries are counted by the gate itself
    assert g3.passed and g3.details["n_not_applicable"] == 1 and g3.details["n"] == 2
    lps = support_defect_logps(model, [(_seq(rng, 8), _seq(rng, 5)) for _ in range(3)])
    assert lps.shape == (15,) and g0_7(lps).passed


def test_S_read_in_generate_and_teacher_forcing(model):
    """S_read steers only the user-span positions: decode steps are untouched, and the first-token logits equal a
    teacher-forced forward with the same pos_mask."""
    rng = np.random.default_rng(2)
    seqs = [_seq(rng, 10), _seq(rng, 7)]
    spans = [(3, 6), (1, 4)]
    st = Steer(model, 1, torch.randn(D), r_L=3.0)
    try:
        pm = read_mask_from_spans(spans, [len(s) for s in seqs])
        kw = dict(do_sample=False, max_new_tokens=3, pad_token_id=V - 1, output_logits=True, return_dict_in_generate=True)
        ids, att = left_pad(seqs, pad_id=V - 1)
        st.set([1.0, 1.0], "S_read", pos_mask=pm)
        with torch.no_grad():
            out = model.generate(input_ids=ids, attention_mask=att, **kw)
        st.off()
        for b in range(2):
            lp = response_logprobs(model, seqs[b] + out.sequences[b, ids.shape[1]:ids.shape[1] + 1].tolist(), len(seqs[b]),
                                   steer=st, alpha=1.0, scope="S_read", pos_mask=pm[b:b + 1])
            tf_first = lp[0]
            gen_first = torch.log_softmax(out.logits[0][b].float() / TEMPERATURE, -1)[out.sequences[b, ids.shape[1]]]   # same T on both paths
            assert abs(float(tf_first) - float(gen_first)) < 1e-4
        # with the mask, alpha=1 differs from alpha=0 at the first token; after the span it is not re-applied at decode steps
        st.set([1.0, 1.0], "S_read", pos_mask=pm)
        with torch.no_grad():
            a1 = model.generate(input_ids=ids, attention_mask=att, **kw).logits
        st.set([0.0, 0.0], "S_read", pos_mask=pm)
        with torch.no_grad():
            a0 = model.generate(input_ids=ids, attention_mask=att, **kw).logits
        st.off()
        assert (a1[0] - a0[0]).abs().max() > 1e-4
        # use_cache=False decoding equals KV-cache decoding under S_gen (position-id rule, not shape rule)
        st.set([1.0, 0.5], "S_gen", gen_start=att.sum(-1) - 1)
        with torch.no_grad():
            c1 = model.generate(input_ids=ids, attention_mask=att, use_cache=True, **kw).logits
            c0 = model.generate(input_ids=ids, attention_mask=att, use_cache=False, **kw).logits
        st.off()
        assert max(float((x - y).abs().max()) for x, y in zip(c1, c0)) < 1e-4
    finally:
        st.remove()


def test_sampler_reseeds_per_generate_call(model):
    rng = np.random.default_rng(3)
    s = _seq(rng, 6)
    kw = generate_kwargs([11, 12], temperature=0.7, max_new_tokens=4, pad_token_id=V - 1, eos_token_id=(V - 2,))
    ids, att = left_pad([s, s], pad_id=V - 1)
    with torch.no_grad():
        a = model.generate(input_ids=ids, attention_mask=att, **kw)
        with pytest.raises(RuntimeError):                                # round 7: a sampler serves ONE generate call —
            model.generate(input_ids=ids, attention_mask=att, **kw)      # reuse is an error, never inferred from lengths
        kw["logits_processor"][0].reset()
        b = model.generate(input_ids=ids, attention_mask=att, **kw)      # explicit reset() restores reproducibility
        assert torch.equal(a, b)
        kw["logits_processor"][0].reset()
        longer, att2 = left_pad([s + s, s + s], pad_id=V - 1)              # the reviewer's case: a longer prompt after a shorter call
        model.generate(input_ids=longer, attention_mask=att2, **kw)
        with pytest.raises(RuntimeError):
            model.generate(input_ids=longer, attention_mask=att2, **kw)
    samp = SeededGumbelSampler([1], 0.7, device="cpu")
    with pytest.raises(ValueError):
        samp(torch.zeros(1, 3, dtype=torch.long), torch.full((1, 5), float("-inf")))


def test_hf_engine_batches_and_finish_reason(model):
    rng = np.random.default_rng(4)
    st = Steer(model, 2, torch.randn(D), r_L=1.0)
    try:
        eng = HFEngine(model, st, batch_size=2, pad_id=V - 1, eos_ids=(V - 2,))
        reqs = [GenRequest(_seq(rng, 5 + i), seed=100 + i, alpha=(0.5 if i == 1 else 0.0), max_new_tokens=3) for i in range(3)]
        res = eng.generate(reqs)
        assert len(res) == 3 and all(r.engine == "hf" for r in res)
        for r in res:
            assert (r.finish_reason == "stop") == (V - 2 in r.ids) or (r.finish_reason == "length" and len(r.ids) == 3)
        res2 = eng.generate(reqs)
        assert [r.ids for r in res] == [r.ids for r in res2]           # reproducible across calls
        gens, reasons = generate_steered(model, [reqs[0].ids], st, [0.0], generate_kwargs([5], 0.7, 3, V - 1, (V - 2,)))
        assert len(gens) == 1 and reasons[0] in ("stop", "length")
    finally:
        st.remove()


def test_extract_z_guards(model):
    rng = np.random.default_rng(5)
    seqs = [_seq(rng, 9), _seq(rng, 12)]
    z = extract_z(model, seqs, [0, 2], [(2, 5), (3, 7)], [(0, 2), None])
    assert z["R1"][0].shape == (2, D) and z["R1"][0].dtype == torch.float32 and torch.isfinite(z["R2"][2]).all()
    with pytest.raises(ValueError):
        extract_z(model, seqs, [0], [(7, 12), (3, 7)])              # span past row 0
    with pytest.raises(ValueError):
        extract_z(model, seqs, [0], [(3, 3), (3, 7)])               # empty span
    st = Steer(model, 1, torch.randn(D), r_L=1.0)
    try:
        st.set([1.0, 1.0], "S_gen", gen_start=torch.tensor([3, 3]))
        with pytest.raises(RuntimeError):
            extract_z(model, seqs, [0], [(2, 5), (3, 7)], steer=st)
    finally:
        st.remove()


def test_templates_think_edge_cases():
    b = TurnBuilder(encode, "hybrid_think", is_ws)
    n = b.normalize(encode("<think>\nabc</think>\n\n 答案") + [IM_END], "stop")
    assert n.ids == encode(" 答案") + [IM_END] and not n.no_think_close and n.think_ids[-1] == THINK_END   # space kept
    n2 = b.normalize(encode("<think>\nabc") + [IM_END], "stop")
    assert n2.no_think_close and not n2.truncated_in_think and n2.ids == [IM_END]
    n3 = b.normalize(encode("<think>\nabc"), "length")
    assert n3.no_think_close and n3.truncated_in_think and n3.truncated
    bi = TurnBuilder(encode, "instruct", is_ws)
    n4 = bi.normalize(encode("x</think>y") + [IM_END], "stop")
    assert n4.stray_think_tokens and THINK_END not in n4.ids and n4.ids == encode("xy") + [IM_END]
    # first-turn span ignores the trailing generation prompt even for a degenerate x_1
    ids1 = first_turn_ids(SYSTEM_PROMPT, "assistant", "instruct")
    s, e = bi.first_turn_user_span(ids1, "assistant")
    assert e <= len(ids1) - len(bi.post) and ids1[s:e] == encode("assistant")


def decode(ids):
    return "".join(chr(i - 1000) if i >= 1000 else ("\n\n" if i == 271 else "") for i in ids)


def test_template_consistency_and_batch_conditions():
    builder = TurnBuilder(encode, "instruct", is_ws)
    prob = BankProblem(problem_id="p", family="F2", statement_zh="S", gold="40", gold_type="integer", distractor="60")
    im_start = encode("<|im_start|>")[0]
    user = encode("user")
    def responder(ids, seed, alpha, mnt):
        n_user = sum(1 for i in range(len(ids)) if ids[i] == im_start and ids[i + 1:i + 1 + len(user)] == user)
        txt = "最终答案：40" if n_user in (1, 4) else f"答案是 {'60' if seed % 3 == 0 else '40'}（{seed % 997}）"  # distinct y_2 => distinct h_3
        return encode(txt) + [IM_END]
    eng = FakeEngine(responder)
    router = EngineRouter(eng, eng)
    FT = lambda x: first_turn_ids(SYSTEM_PROMPT, x, "instruct")
    base = run_rollouts([RolloutSpec(run_id="r", problem=prob, script="A3", arm=Arm.null(), trajectory_idx=i) for i in range(3)],
                        builder=builder, router=router, first_turn_ids=FT, decode=decode)
    def text_path(msgs):
        t = ""
        for m in msgs:
            t += f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
        return encode(t + "<|im_start|>assistant\n")
    n_mis, n_tot, ex, seg = template_consistency(base, builder, FT, text_path, SYSTEM_PROMPT)
    assert seg == 0 and g0_1(n_mis, n_tot, seg).details["segment_mismatches"] == 0
    assert (n_mis, n_tot) == (0, 3)
    # batch conditions: fake engine is order-independent, so all three conditions agree exactly
    pres = [(prob, prefix_from_trajectory(tr, builder, FT, upto_turn=3)) for tr in base]
    specs = continuation_specs("r", pres, n_per_prefix=4)
    conds = batch_conditions(specs, lambda sp, bs: run_rollouts(sp, builder=builder, router=router, first_turn_ids=FT, decode=decode))
    ea, eb, cl = paired_e3(conds["batch1"], conds["batch8_random"])
    assert ea.shape == (12,) and np.array_equal(ea, eb) and len(set(cl)) == 3
    assert [t.trajectory_idx for t in conds["batch8_grouped"]] == [s.trajectory_idx for s in specs]


def test_generation_logprobs_match_teacher_forcing_at_the_same_temperature(model):
    """RUNBOOK §6 item 2 on the CPU model: the decode-path log P_T recorded inside the sampler (raw scores, T applied) equals
    the teacher-forced log P_T of the same generated tokens up to fp32 noise; the processed ``output_scores`` would give 0."""
    rng = np.random.default_rng(9)
    ids = _seq(rng, 11)
    r = generation_vs_teacher_forcing(model, ids, max_new_tokens=6, seed=123, eos_ids=(V - 2,), pad_id=V - 1)
    assert r["n"] >= 1 and r["temperature"] == TEMPERATURE and r["max_abs_diff"] < 1e-3 and len(r["logp_gen"]) == r["n"]
    assert np.all(r["logp_gen"] <= 1e-6) and np.all(r["logp_gen"] > -50)
    r1 = generation_vs_teacher_forcing(model, ids, max_new_tokens=6, seed=123, eos_ids=(V - 2,), pad_id=V - 1, temperature=1.0)
    assert r1["gen_ids"] != r["gen_ids"] or abs(r1["logp_gen"][0] - r["logp_gen"][0]) > 1e-6     # T changes the distribution
