import numpy as np
import pytest

from sycophancy_phase0.analysis.glm import logit_fit, wald
from sycophancy_phase0.analysis.scores import (linear_region, natural_gradient, r2_steer_out_of_fold, rho_v_disattenuated, rho_v_naive,
                                               rho_v_point, S_v)
from sycophancy_phase0.analysis.factorial import (G_statistic, backward_induction, cluster_robust_mean, dersimonian_laird, eb_shrink,
                                                  empirical_logit, fit_prefix, lrt_random_effect, mpc_vs_myopic, select_u3_star)


def test_logit_fit_and_cluster_robust():
    rng = np.random.default_rng(0)
    n = 4000
    X = np.stack([np.ones(n), rng.normal(size=n)], 1)
    beta = np.array([-0.5, 1.2])
    y = rng.binomial(1, 1 / (1 + np.exp(-(X @ beta))))
    r = logit_fit(X, y)
    assert np.allclose(r["beta"], beta, atol=0.12) and r["iters"] < 20
    # clustered data: within-cluster correlated noise -> robust SE > model SE
    G = 100
    cl = np.repeat(np.arange(G), 40)
    u = rng.normal(0, 1.0, G)[cl]
    x = rng.normal(size=n)
    y2 = rng.binomial(1, 1 / (1 + np.exp(-(0.3 * x + u))))
    r2 = logit_fit(np.stack([np.ones(n), x], 1), y2, cluster=cl)
    assert r2["n_clusters"] == G and r2["se_robust"][0] > np.sqrt(r2["cov_model"][0, 0]) * 1.5
    w = wald(r2["beta"], r2["cov_robust"], [0, 1])
    assert w["p"] < 0.05 and abs(w["z"]) > 2


def test_scores_synthetic():
    rng = np.random.default_rng(1)
    N, D = 400, 20
    v_true = rng.normal(size=D); v_true /= np.linalg.norm(v_true)
    G = rng.normal(size=(N, D))
    q = 0.5 - 0.2 * (G @ v_true) + 0.05 * rng.normal(size=N)        # q decreases along v_true
    ng = natural_gradient(q, G)
    assert abs(ng["v_ng"] @ v_true) / np.linalg.norm(ng["v_ng"]) > 0.9   # -F^{-1} m points along the risk-reducing direction
    r2 = r2_steer_out_of_fold(q, G)
    assert 0.7 < r2["R2_steer"] <= 1.0
    assert abs(S_v(np.ones(D), np.ones(D), 2.0) - 2.0 * np.sqrt(D)) < 1e-9
    S = G @ v_true
    log_w = {a: a * S + 0.002 * rng.normal(size=N) + (0.0 if a <= 0.5 else 0.3 * (a * S) ** 2) for a in (0.02, 0.05, 0.1, 0.2, 0.5, 1.0)}
    lr = linear_region(log_w, S)
    assert lr["alpha_lin"] == 0.5 and lr["table"][0.02]["R2"] > 0.9 and lr["table"][1.0]["R2"] < 0.9
    # rho_v: Va, Vb independent noisy measurements of a latent V correlated with S within prefix
    P, n = 40, 32
    prefix = np.repeat(np.arange(P), n)
    latent = rng.normal(size=P * n)
    S2 = 0.6 * latent + 0.8 * rng.normal(size=P * n)
    Va = latent + rng.normal(size=P * n); Vb = latent + rng.normal(size=P * n)
    rho2 = 0.6 ** 2 / (0.6 ** 2 + 0.8 ** 2)                           # Corr²(S, latent)
    est = rho_v_point(S2, Va, Vb, prefix)
    assert abs(est - rho2) < 0.08
    r = rho_v_disattenuated(S2, Va, Vb, prefix, n_boot=200, seed=0)
    assert r["lower95"] < est < 1.0 and r["n_prefix"] == P
    assert 0 < rho_v_naive(S2, Va, 0.5, prefix) < 1.0
    null = rho_v_point(rng.normal(size=P * n), Va, Vb, prefix)
    assert null < 0.05


def test_factorial_fit_pool_lrt_induction():
    rng = np.random.default_rng(2)
    u_grid = [-1.0, 0.0, 1.0]
    u2 = np.repeat(u_grid, 3); u3 = np.tile(u_grid, 3)
    K = 64
    ests, vars_, cl = [], [], []
    true_c = []
    for i in range(60):
        a, g, c, kap = 0.2, 0.8, 0.5 + 0.3 * rng.normal(), 0.1
        true_c.append(c)
        p = 1 / (1 + np.exp(-(a - g * u3 - c * u2 - kap * u2 * u3)))
        k = rng.binomial(K, p)
        f = fit_prefix(u2, u3, k, np.full(9, K))
        ests.append(f["c"]); vars_.append(f["cov"][2, 2]); cl.append(i // 3)
    L, w = empirical_logit(np.array([0, 5, 10]), np.array([10, 10, 10]))
    assert L[0] < L[1] < L[2] and w[1] > w[0]
    assert abs(np.mean(ests) - np.mean(true_c)) < 0.08
    dl = dersimonian_laird(np.array(ests), np.array(vars_))
    assert abs(dl["mu"] - 0.5) < 0.1 and dl["tau2"] > 0.02
    cr = cluster_robust_mean(np.array(ests), np.array(vars_), np.array(cl), dl["tau2"])
    assert cr["n_clusters"] == 20 and cr["se_cluster"] > 0
    lrt = lrt_random_effect(np.array(ests), np.array(vars_))
    assert lrt["p"] < 0.05 and lrt["tau2"] > 0.02
    lrt0 = lrt_random_effect(np.array([0.5 + np.sqrt(v) * rng.normal() for v in vars_]), np.array(vars_))
    assert lrt0["p"] > 0.05 or lrt0["tau2"] < 0.02
    sh = eb_shrink(np.array(ests), np.array(vars_), dl["mu"], dl["tau2"])
    assert np.std(sh) < np.std(ests)
    # backward induction: u2 = -1 reduces turn-3/4 error a lot but costs λ; with small λ MPC disagrees with myopic
    table = np.array([[0.2, 0.3, 0.4], [0.5, 0.6, 0.7], [0.8, 0.85, 0.9]])     # rows u2, cols u3
    p_e2 = np.array([0.1, 0.1, 0.1])
    bi = backward_induction(table, p_e2, u_grid, lam=0.05)
    assert bi["mpc"] == (-1.0, -1.0) and bi["myopic"][0] == 0.0 and bi["disagree"] and bi["gain"] > 0
    bi2 = backward_induction(table, p_e2, u_grid, lam=1.0)
    assert bi2["mpc"][0] == 0.0 and not bi2["disagree"]
    sweep = mpc_vs_myopic([table] * 3, [p_e2] * 3, u_grid, [0.05, 1.0])
    assert sweep[0.05]["disagree_rate"] == 1.0 and sweep[1.0]["disagree_rate"] == 0.0
    Y = {("A3", 0.0, 1.0): np.array([1, 1, 0, 0]), ("A3", -1.0, 1.0): np.array([0, 0, 0, 1]),
         ("C", 0.0, 1.0): np.array([0, 0, 0, 0]), ("C", -1.0, 1.0): np.array([1, 0, 0, 0]),
         ("A3", 0.0, 0.0): np.array([1, 1, 1, 0]), ("A3", 0.0, -1.0): np.array([1, 1, 1, 1])}
    assert abs(G_statistic(Y, 1.0) - (0.8 * 0.25 - 0.2 * 0.25)) < 1e-12
    assert select_u3_star(Y, [-1.0, 0.0, 1.0], 0.05) == 1.0


def test_response_gradient_matches_finite_difference():
    torch = pytest.importorskip("torch")
    from transformers.models.qwen3_moe import Qwen3MoeConfig, Qwen3MoeForCausalLM
    from sycophancy_phase0.analysis.scores import response_gradient
    from sycophancy_phase0.inference.hf_engine import response_logprobs
    from sycophancy_phase0.inference.steering import Steer
    V, D = 256, 32
    torch.manual_seed(3)
    cfg = Qwen3MoeConfig(vocab_size=V, hidden_size=D, intermediate_size=64, moe_intermediate_size=32, num_hidden_layers=4,
                         num_attention_heads=4, num_key_value_heads=2, head_dim=8, num_experts=8, num_experts_per_tok=2,
                         decoder_sparse_step=1, mlp_only_layers=[], norm_topk_prob=True, max_position_embeddings=256,
                         tie_word_embeddings=False, attn_implementation="eager", pad_token_id=V - 1, eos_token_id=V - 2, bos_token_id=None)
    model = Qwen3MoeForCausalLM(cfg).eval()
    for p in model.parameters():
        p.requires_grad_(False)
    rng = np.random.default_rng(4)
    ids = rng.integers(0, V - 2, 12).tolist()
    v = torch.randn(D)
    st = Steer(model, 1, v, r_L=0.5)
    try:
        g, lp0 = response_gradient(model, st, ids, 7)
        sv = S_v(g, v.numpy(), 0.5)
        eps = 1e-3
        lp_p = float(response_logprobs(model, ids, 7, steer=st, alpha=eps).sum())
        lp_m = float(response_logprobs(model, ids, 7, steer=st, alpha=-eps).sum())
        fd = (lp_p - lp_m) / (2 * eps)
        assert abs(sv - fd) < 1e-2 * max(1.0, abs(fd)) and abs(float(response_logprobs(model, ids, 7).sum()) - lp0) < 1e-5
    finally:
        st.remove()
