"""Minimal logistic regression with Newton–Raphson, cluster-robust (sandwich) covariance and Wald tests — avoids a
statsmodels dependency for the G6 / §8.9 fixed-effects logits.  Fixed effects are passed as ordinary dummy columns;
a tiny ridge (1e-8) keeps separation from breaking the solve (reported in the result)."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np
from scipy import stats


def logit_fit(X: np.ndarray, y: np.ndarray, cluster: Optional[np.ndarray] = None, max_iter: int = 100, tol: float = 1e-9,
              ridge: float = 1e-8, w: Optional[np.ndarray] = None) -> Dict[str, object]:
    X, y = np.asarray(X, float), np.asarray(y, float)
    n, p = X.shape
    w = np.ones(n) if w is None else np.asarray(w, float)
    beta = np.zeros(p)
    for it in range(max_iter):
        eta = X @ beta
        mu = 1 / (1 + np.exp(-eta))
        W = w * mu * (1 - mu)
        grad = X.T @ (w * (y - mu)) - ridge * beta
        H = X.T @ (X * W[:, None]) + ridge * np.eye(p)
        step = np.linalg.solve(H, grad)
        beta = beta + step
        if np.max(np.abs(step)) < tol:
            break
    eta = X @ beta
    mu = 1 / (1 + np.exp(-eta))
    W = w * mu * (1 - mu)
    H = X.T @ (X * W[:, None]) + ridge * np.eye(p)
    Hinv = np.linalg.inv(H)
    score = X * (w * (y - mu))[:, None]
    if cluster is None:
        meat = score.T @ score
        G = n
    else:
        cluster = np.asarray(cluster)
        ups = np.unique(cluster)
        G = len(ups)
        S = np.stack([score[cluster == c].sum(0) for c in ups])
        meat = S.T @ S * (G / (G - 1)) if G > 1 else S.T @ S
    cov = Hinv @ meat @ Hinv
    ll = float((w * (y * np.log(np.clip(mu, 1e-12, 1)) + (1 - y) * np.log(np.clip(1 - mu, 1e-12, 1)))).sum())
    return dict(beta=beta, cov_robust=cov, cov_model=Hinv, loglik=ll, n=n, n_clusters=G, iters=it + 1, mu=mu,
                se_robust=np.sqrt(np.diag(cov)))


def wald(beta: np.ndarray, cov: np.ndarray, contrast: np.ndarray) -> Dict[str, float]:
    """Two-sided Wald test of cᵀβ = 0."""
    c = np.asarray(contrast, float)
    est = float(c @ beta)
    se = float(np.sqrt(c @ cov @ c))
    z = est / se if se > 0 else float("nan")
    return dict(est=est, se=se, z=z, p=float(2 * stats.norm.sf(abs(z))) if np.isfinite(z) else float("nan"))
