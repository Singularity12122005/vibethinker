"""Isotonic lower bounds, alpha_max selection logic, router top-k sets / kappa_1 on the tiny model, directions."""
import numpy as np
import pytest

from sycophancy_phase0.analysis.isotonic import isotonic_lower_bound, pava
from sycophancy_phase0.inference.calibration import (COARSE_GRID, FINE_GRID, alpha_max_from_curves, coarse_grid_rates, worse_sign)
from sycophancy_phase0.inference.directions import (cosine_matrix, d_agree, lofo, orthogonalise, paired_problem_diff, save_direction,
                                                    load_direction, v_cap)


def test_pava_and_isotonic_lower_bound():
    y = np.array([1.0, 0.9, 0.95, 0.7, 0.75, 0.2])
    f = pava(y, increasing=False)
    assert np.all(np.diff(f) <= 1e-12) and abs(f[1] - 0.925) < 1e-12 and abs(f[3] - 0.725) < 1e-12
    assert np.allclose(pava(-y, increasing=True), -f)
    rng = np.random.default_rng(0)
    grid = np.linspace(0, 2, 9)
    truth = 0.9 - 0.1 * grid
    vals, cl, gi = [], [], []
    for pid in range(60):
        for g in range(9):
            for _ in range(2):
                vals.append(rng.binomial(1, truth[g])); cl.append(pid); gi.append(g)
    r = isotonic_lower_bound(np.array(vals), np.array(cl), np.array(gi), 9, increasing=False, n_boot=200, seed=1)
    assert np.all(np.diff(r["fit"]) <= 1e-12) and np.all(r["lower"] <= r["fit"] + 1e-12) and r["n_clusters"] == 60
    assert np.mean(r["lower"] <= truth) > 0.8


def test_alpha_max_selection_logic():
    fine = {a: dict(kl=0.02 * a, flip=0.01 * a, kl_pos=0, kl_neg=0, flip_pos=0, flip_neg=0) for a in FINE_GRID}   # kl hits 0.10 at a=5 (never); flip 0.05 at a=5
    rng = np.random.default_rng(2)
    def obs(drop_at):
        d = {}
        for a in (0.0,) + COARSE_GRID:
            rate = 0.99 if a < drop_at else 0.7
            d[a] = [(f"p{i}", float(rng.random() < rate)) for i in range(100) for _ in range(2)]
        return d
    coarse = coarse_grid_rates(worse_sign(obs(1.3), obs(1.6)), worse_sign(obs(2.5), obs(2.5)), n_boot=100, seed=0)
    r = alpha_max_from_curves(fine, coarse)
    assert 0.9 <= r["alpha_max"] <= 1.3 and "x2" in next(iter(r["first_failure"].values())) and not r["switch_layer"]
    fine2 = dict(fine); fine2[0.15] = dict(fine[0.15], kl=0.2)
    r2 = alpha_max_from_curves(fine2, coarse)
    assert r2["alpha_max"] == 0.1 and r2["switch_layer"]


def test_directions():
    rng = np.random.default_rng(3)
    D = 8
    true = rng.normal(size=D); true /= np.linalg.norm(true)
    acts, st, pf = [], [], []
    for p in range(6):
        base = rng.normal(size=D)
        for _ in range(5):
            acts.append(base + 2 * true + 0.1 * rng.normal(size=D)); st.append("USER"); pf.append(f"h{p}")
            acts.append(base + 0.1 * rng.normal(size=D)); st.append("ORIG"); pf.append(f"h{p}")
        acts.append(base); st.append("OTHER"); pf.append(f"h{p}")
    r = v_cap(np.array(acts), st, pf)
    assert r["n_prefix"] == 6 and abs(r["v"] @ true) > 0.99
    with pytest.raises(ValueError):
        v_cap(np.array(acts), ["USER"] * len(st), pf)
    pa = [f"q{i}" for i in range(10) for _ in range(3)]
    A = np.array([true * 3 + rng.normal(size=D) * 0.1 for _ in pa]); B = np.array([rng.normal(size=D) * 0.1 for _ in pa])
    assert abs(paired_problem_diff(A, B, pa, pa)["v"] @ true) > 0.99
    da = d_agree({"A3": (np.array(acts), st), "D": (np.array(acts), st)})
    perp = orthogonalise(r["v"] + 0.5 * da["v"], da["v"])
    assert abs(perp @ da["v"]) < 1e-9 and abs(np.linalg.norm(perp) - 1) < 1e-9
    folds = np.array([i % 5 for i in range(len(acts))])
    vers = lofo(lambda m: v_cap(np.array(acts)[m], np.array(st)[m], np.array(pf)[m]), folds)
    cm = cosine_matrix([vers[k]["v"] for k in range(5)])
    assert cm.shape == (5, 5) and cm.min() > 0.98
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        path = save_direction(d, "v_cap", 20, 0, r["v"], dict(n_prefix=r["n_prefix"]))
        assert os.path.exists(path) and np.allclose(load_direction(d, "v_cap", 20, 0), r["v"].astype(np.float32))


def test_router_sets_and_kappa1_on_tiny_model():
    torch = pytest.importorskip("torch")
    from transformers.models.qwen3_moe import Qwen3MoeConfig, Qwen3MoeForCausalLM
    from sycophancy_phase0.inference.calibration import fine_grid_stats, kappa1
    from sycophancy_phase0.inference.hf_engine import next_token_kl, router_topk_sets
    from sycophancy_phase0.inference.steering import Steer
    V, D = 256, 32
    torch.manual_seed(0)
    cfg = Qwen3MoeConfig(vocab_size=V, hidden_size=D, intermediate_size=64, moe_intermediate_size=32, num_hidden_layers=4,
                         num_attention_heads=4, num_key_value_heads=2, head_dim=8, num_experts=8, num_experts_per_tok=2,
                         decoder_sparse_step=1, mlp_only_layers=[], norm_topk_prob=True, max_position_embeddings=256,
                         tie_word_embeddings=False, attn_implementation="eager", pad_token_id=V - 1, eos_token_id=V - 2, bos_token_id=None)
    model = Qwen3MoeForCausalLM(cfg).eval()
    rng = np.random.default_rng(1)
    items = [(rng.integers(0, V - 2, 7).tolist(), rng.integers(0, V - 2, 5).tolist()) for _ in range(3)]
    st = Steer(model, 1, torch.randn(D), r_L=2.0)
    try:
        sets = router_topk_sets(model, items[0][0] + items[0][1], 7, st, 0.0, top_k=2)
        assert set(sets) == {0, 1, 2, 3} and sets[2].shape == (5, 2)
        res = fine_grid_stats(model, st, items, alphas=(0.5, 1.0), top_k=2)
        assert set(res) == {0.5, 1.0} and res[1.0]["kl"] >= res[0.5]["kl"] * 0.5 and 0 <= res[1.0]["flip"] <= 1
        assert res[0.5]["kl"] == max(res[0.5]["kl_pos"], res[0.5]["kl_neg"])
        k = kappa1(model, st, items, 1.0)
        assert k["n"] == 3 and k["kappa1"] >= 0
        kl_a0 = next_token_kl(model, items[0][0] + items[0][1], 7, st, 1.0, direction="alpha_to_zero")
        assert kl_a0.shape == (5,) and float(kl_a0.min()) >= -1e-6
    finally:
        st.remove()
