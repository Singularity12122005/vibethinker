"""Between-response variance component of a binary outcome (plan §8.1).

Input per prefix: N responses y_j, each with M continuations and K_j successes.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np


def u_stat_var(K: np.ndarray, M: int) -> float:
    """Unbiased U-statistic for Var_j(q_j) == (MSB - MSW)/M of the balanced one-way ANOVA."""
    K = np.asarray(K, dtype=float)
    N = K.shape[0]
    if N < 2 or M < 2:
        raise ValueError("need N>=2 responses and M>=2 continuations")
    within = np.mean(K * (K - 1) / (M * (M - 1)))                      # E[q^2]
    between = (K.sum() ** 2 - (K ** 2).sum()) / (N * (N - 1) * M * M)  # E[q]^2 (unbiased)
    return float(within - between)


def anova_mom_var(K: np.ndarray, M: int) -> float:
    """(MSB - MSW)/M, for the equivalence check."""
    K = np.asarray(K, dtype=float)
    N = K.shape[0]
    p = K / M
    pbar = p.mean()
    msb = M * ((p - pbar) ** 2).sum() / (N - 1)
    msw = (K * (M - K) / M).sum() / (N * (M - 1))
    return float((msb - msw) / M)


def icc(K: np.ndarray, M: int) -> Dict[str, float]:
    K = np.asarray(K, dtype=float)
    mu = K.sum() / (K.shape[0] * M)
    v = u_stat_var(K, M)
    denom = mu * (1 - mu)
    return dict(mu=float(mu), var=v, icc=float(v / denom) if denom > 0 else float("nan"))


def bootstrap_var(K: np.ndarray, M: int, n_boot: int = 2000, seed: int = 0) -> Dict[str, float]:
    """y_2-group bootstrap of the U-statistic; one-sided 95% upper limit = est + 1.645*SE."""
    rng = np.random.default_rng(seed)
    K = np.asarray(K)
    N = K.shape[0]
    est = u_stat_var(K, M)
    bs = np.array([u_stat_var(K[rng.integers(0, N, N)], M) for _ in range(n_boot)])
    se = float(bs.std(ddof=1))
    return dict(est=est, se=se, upper95=est + 1.645 * se, lower95=est - 1.645 * se)


def two_stage_bootstrap(stat_fn, groups: Sequence[np.ndarray], n_boot: int = 2000, seed: int = 0) -> np.ndarray:
    """Resample prefixes (groups) first, then y_2 within each resampled prefix (plan §7.4)."""
    rng = np.random.default_rng(seed)
    G = len(groups)
    out = np.empty(n_boot)
    for b in range(n_boot):
        picked = [groups[g] for g in rng.integers(0, G, G)]
        resampled = [grp[rng.integers(0, len(grp), len(grp))] for grp in picked]
        out[b] = stat_fn(resampled)
    return out
