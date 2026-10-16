"""Exponential-tilt KL frontier of the delayed effect (plan §8.2)."""
from __future__ import annotations

from typing import Dict, Sequence

import numpy as np


def eb_shrink(K: np.ndarray, M: int, mu: float, var: float) -> np.ndarray:
    """Beta-prior moment match (mu, var) -> posterior mean (K+a)/(M+a+b); falls back to K/M if var<=0."""
    K = np.asarray(K, dtype=float)
    if var <= 0 or mu <= 0 or mu >= 1 or var >= mu * (1 - mu):
        return K / M
    s = mu * (1 - mu) / var - 1
    a, b = mu * s, (1 - mu) * s
    return (K + a) / (M + a + b)


def tilt_frontier(q_sel: np.ndarray, q_est: np.ndarray, kappas: Sequence[float],
                  betas: np.ndarray = None) -> Dict[float, float]:
    """Cross-fitted frontier: tilt weights from q_sel, risk reduction measured on q_est.

    w_j(beta) ∝ exp(-beta q_sel_j);  tau(beta) = mean(q_est) - sum_j w_j q_est_j;  KL(beta) = sum_j w_j log(N w_j).
    tau*(kappa) = max{tau(beta): KL(beta) <= kappa}.
    """
    q_sel = np.asarray(q_sel, float)
    q_est = np.asarray(q_est, float)
    N = q_sel.shape[0]
    if betas is None:
        betas = np.concatenate([[0.0], np.logspace(-3, 3, 400)])
    qbar = q_est.mean()
    taus, kls = [], []
    for beta in betas:
        lw = -beta * q_sel
        lw = lw - lw.max()
        w = np.exp(lw); w /= w.sum()
        taus.append(qbar - (w * q_est).sum())
        kls.append((w * np.log(np.maximum(N * w, 1e-300))).sum())
    taus, kls = np.array(taus), np.array(kls)
    out = {}
    for k in kappas:
        ok = kls <= k
        out[float(k)] = float(taus[ok].max()) if ok.any() else 0.0
    return out


def dual_frontier(q: np.ndarray, kappas: Sequence[float]) -> Dict[float, float]:
    """Donsker–Varadhan dual: tau*(kappa) = inf_{beta>0} [Lambda(beta) + kappa]/beta, Lambda on (qbar - q)."""
    q = np.asarray(q, float)
    d = q.mean() - q
    betas = np.logspace(-3, 3, 600)
    lam = np.array([np.log(np.mean(np.exp(b * d))) for b in betas])
    return {float(k): float(np.min((lam + k) / betas)) for k in kappas}


def cs_bound(q: np.ndarray, kappa: float) -> float:
    """sd(q)·sqrt(e^kappa − 1): Cauchy–Schwarz evaluated at the *minimal* chi^2 consistent with KL = kappa.
    Reference only — at fixed KL chi^2 is unbounded above, so this is NOT an upper bound on tau*(kappa)."""
    return float(np.std(q, ddof=0) * np.sqrt(np.exp(kappa) - 1))


def bernstein_bound(q: np.ndarray, kappa: float) -> float:
    v = float(np.var(q, ddof=0))
    return float(np.sqrt(2 * v * kappa) + kappa / 3)
