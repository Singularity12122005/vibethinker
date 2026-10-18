"""Gradient scores, natural-gradient direction, linear region and disattenuated ρ_v (plan §8.3, §7.9).

* ``response_gradient``: one teacher-forced forward at B = 1 with an fp32 leaf ``delta`` injected at layer L on the
  generation-side positions (Steer gradient mode); g(y) = Σ_{p >= gen_start} ∇_{h_p^{(L)}} log P(y | h) ∈ R^D.
* ``S_v(y) = <g(y), v̂> r_L``.
* ``natural_gradient``: m = mean_j (q_j − q̄) g_j, F = mean_j g_j g_jᵀ + εI (ε = 1e-3 tr(F)/D), v_NG = −F⁻¹ m;
  out-of-fold R²_steer = Corr²(S_{v_NG}(y_j), q_j) by parity split, swapped and averaged.
* ``linear_region``: log w_α(y) = log P^α(y) − log P^0(y) regressed on α S_v(y); α_lin = largest α with R² > 0.9 and
  ESS/N > 0.25.
* ``rho_v_disattenuated``: ρ̂_v² = Cov(S, V^(a)) Cov(S, V^(b)) / [Var(S) Cov(V^(a), V^(b))] after per-prefix
  demeaning, clipped to [0, 1], with a prefix-level bootstrap lower bound (same resampling as G2′-b).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


# ---------------------------------------------------------------- gradients (HF)
def response_gradient(model, steer, ids: Sequence[int], prompt_len: int, scope: str = "S_gen", temperature: Optional[float] = None) -> Tuple[np.ndarray, float]:
    """Returns (g [D] fp32 numpy, log P_T(y | h) at alpha = 0), T = the generation temperature (plan §8.3: the gradient of the
    T-tempered log-probability; dividing a T=1 gradient by T afterwards is NOT equivalent because T also changes the softmax
    weights).  Requires model parameters frozen (checked)."""
    import torch

    from ..constants import TEMPERATURE
    from ..inference.hf_engine import response_logprobs
    temperature = TEMPERATURE if temperature is None else float(temperature)
    if any(p.requires_grad for p in model.parameters()):
        raise RuntimeError("freeze the model (model.requires_grad_(False)) before response_gradient")
    S = len(ids)
    D = model.config.hidden_size
    delta = torch.zeros(1, S, D, dtype=torch.float32, device=model.device, requires_grad=True)
    lp = response_logprobs(model, ids, prompt_len, steer=steer, alpha=0.0, scope=scope, grad_delta=delta, temperature=temperature)
    total = lp.sum()
    total.backward()
    mask = torch.zeros(S, dtype=torch.float32, device=model.device)
    mask[prompt_len - 1:] = 1.0
    g = (delta.grad[0] * mask[:, None]).sum(0)
    return g.detach().float().cpu().numpy(), float(total.detach())


def S_v(g: np.ndarray, v_unit: np.ndarray, r_L: float) -> float:
    v = np.asarray(v_unit, float)
    return float(np.asarray(g, float) @ (v / np.linalg.norm(v)) * r_L)


# ---------------------------------------------------------------- natural gradient
def natural_gradient(q: np.ndarray, G: np.ndarray, eps_rel: float = 1e-3) -> Dict[str, object]:
    q, G = np.asarray(q, float), np.asarray(G, float)
    N, D = G.shape
    m = ((q - q.mean())[:, None] * G).mean(0)
    F = G.T @ G / N
    F = F + eps_rel * np.trace(F) / D * np.eye(D)
    v = -np.linalg.solve(F, m)
    return dict(v_ng=v, m=m, trace_F=float(np.trace(F)))


def r2_steer_out_of_fold(q: np.ndarray, G: np.ndarray, r_L: float = 1.0) -> Dict[str, float]:
    """Parity split: fit v_NG on even j, score odd j (and vice versa); R² = Corr²(S_{v_NG}, q) on the held-out half."""
    q, G = np.asarray(q, float), np.asarray(G, float)
    idx = np.arange(len(q))
    r2s = []
    for fit_mask in (idx % 2 == 0, idx % 2 == 1):
        v = natural_gradient(q[fit_mask], G[fit_mask])["v_ng"]
        s = G[~fit_mask] @ v * r_L
        c = np.corrcoef(s, q[~fit_mask])[0, 1] if np.std(s) > 0 and np.std(q[~fit_mask]) > 0 else 0.0
        r2s.append(float(c ** 2))
    return dict(R2_steer=float(np.mean(r2s)), halves=r2s)


# ---------------------------------------------------------------- linear region
def linear_region(log_w: Dict[float, np.ndarray], S: np.ndarray, r2_min: float = 0.9, ess_min: float = 0.25) -> Dict[str, object]:
    """log_w: {alpha: array of log P^alpha(y_j) − log P^0(y_j)}; S: S_v(y_j).  Per alpha: R² of log w ~ a + b·(alpha S),
    ESS/N of w; alpha_lin = largest alpha satisfying both thresholds (grid assumed increasing)."""
    S = np.asarray(S, float)
    table = {}
    alpha_lin = 0.0
    for a in sorted(log_w):
        lw = np.asarray(log_w[a], float)
        x = a * S
        X = np.stack([np.ones_like(x), x], 1)
        coef, *_ = np.linalg.lstsq(X, lw, rcond=None)
        pred = X @ coef
        ss_res = float(((lw - pred) ** 2).sum()); ss_tot = float(((lw - lw.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        w = np.exp(lw - lw.max())
        ess = float(w.sum() ** 2 / (len(w) * (w ** 2).sum()))
        table[float(a)] = dict(R2=float(r2), slope=float(coef[1]), ess_ratio=ess)
        if r2 > r2_min and ess > ess_min:
            alpha_lin = float(a)
    return dict(alpha_lin=alpha_lin, table=table)


# ---------------------------------------------------------------- rho_v
def _demean(x: np.ndarray, prefix: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float).copy()
    for p in np.unique(prefix):
        m = prefix == p
        x[m] -= x[m].mean()
    return x


def rho_v_point(S: np.ndarray, Va: np.ndarray, Vb: np.ndarray, prefix: np.ndarray) -> float:
    prefix = np.asarray(prefix)
    s, a, b = _demean(S, prefix), _demean(Va, prefix), _demean(Vb, prefix)
    num = np.mean(s * a) * np.mean(s * b)
    den = np.mean(s * s) * np.mean(a * b)
    if den <= 0:
        return 0.0
    return float(np.clip(num / den, 0.0, 1.0))


def rho_v_disattenuated(S: np.ndarray, Va: np.ndarray, Vb: np.ndarray, prefix: np.ndarray, n_boot: int = 2000, seed: int = 0) -> Dict[str, float]:
    S, Va, Vb, prefix = (np.asarray(x) for x in (S, Va, Vb, prefix))
    ups = np.unique(prefix)
    idx = {p: np.where(prefix == p)[0] for p in ups}
    est = rho_v_point(S, Va, Vb, prefix)
    rng = np.random.default_rng(seed)
    bs = np.empty(n_boot)
    for b in range(n_boot):
        pick = ups[rng.integers(0, len(ups), len(ups))]
        ii = np.concatenate([idx[p] for p in pick])
        pp = np.concatenate([np.full(len(idx[p]), k) for k, p in enumerate(pick)])
        bs[b] = rho_v_point(S[ii], Va[ii], Vb[ii], pp)
    return dict(rho2=est, lower95=float(np.quantile(bs, 0.05)), se=float(bs.std(ddof=1)), n_prefix=int(len(ups)))


def rho_v_naive(S: np.ndarray, V: np.ndarray, rho_sh: float, prefix: np.ndarray) -> float:
    """ρ̂_v / sqrt(ρ_sh(V_3)): plain correlation disattenuated by the split-half reliability."""
    prefix = np.asarray(prefix)
    s, v = _demean(S, prefix), _demean(V, prefix)
    c = np.corrcoef(s, v)[0, 1] if np.std(s) > 0 and np.std(v) > 0 else 0.0
    return float(c / np.sqrt(rho_sh)) if rho_sh > 0 else float("nan")
