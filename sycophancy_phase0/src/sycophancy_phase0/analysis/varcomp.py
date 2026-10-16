"""Between-response variance component of a binary outcome (plan §8.1, v1.3).

Input per prefix: N responses y_j, each with M_j continuations and K_j successes (M may vary across j).
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence

import numpy as np


def _M_arr(K: np.ndarray, M) -> np.ndarray:
    M = np.broadcast_to(np.asarray(M, float), K.shape).astype(float)
    if np.any(M < 2):
        raise ValueError("every response needs M>=2 continuations")
    if np.any(K > M) or np.any(K < 0):
        raise ValueError("counts must lie in [0, M_j]")
    return M


def u_stat_var(K: np.ndarray, M) -> float:
    """Unbiased U-statistic for Var_j(q_j); M scalar or per-response array (generalised to unbalanced designs:
    within = mean_j K_j(K_j−1)/(M_j(M_j−1)), between = [(Σ p_j)² − Σ p_j²]/(N(N−1)), p_j = K_j/M_j)."""
    K = np.asarray(K, dtype=float)
    N = K.shape[0]
    if N < 2:
        raise ValueError("need N>=2 responses")
    M = _M_arr(K, M)
    within = np.mean(K * (K - 1) / (M * (M - 1)))                      # E[q^2]
    p = K / M
    between = (p.sum() ** 2 - (p ** 2).sum()) / (N * (N - 1))          # E[q]^2 (unbiased)
    return float(within - between)


def anova_mom_var(K: np.ndarray, M: int) -> float:
    """(MSB - MSW)/M for the balanced design, for the equivalence check."""
    K = np.asarray(K, dtype=float)
    N = K.shape[0]
    p = K / M
    pbar = p.mean()
    msb = M * ((p - pbar) ** 2).sum() / (N - 1)
    msw = (K * (M - K) / M).sum() / (N * (M - 1))
    return float((msb - msw) / M)


def icc(K: np.ndarray, M) -> Dict[str, float]:
    K = np.asarray(K, dtype=float)
    Ma = _M_arr(K, M)
    mu = K.sum() / Ma.sum()
    v = u_stat_var(K, M)
    denom = mu * (1 - mu)
    return dict(mu=float(mu), var=v, icc=float(v / denom) if denom > 0 else float("nan"))


def bootstrap_var(K: np.ndarray, M, n_boot: int = 2000, seed: int = 0, n_inner: int = 50) -> Dict[str, float]:
    """y_2-group bootstrap of the U-statistic.  The one-sided 95% upper limit uses the bootstrap-t (studentised)
    distribution: est − t*_{0.05}·SE with t* from inner resamples; the normal version est + 1.645·SE under-covers
    (0.926 at (N,M)=(128,16)) because SE and est are positively correlated."""
    rng = np.random.default_rng(seed)
    K = np.asarray(K)
    Ma = np.broadcast_to(np.asarray(M), K.shape)
    N = K.shape[0]
    est = u_stat_var(K, M)
    bs, ts = np.empty(n_boot), np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, N, N)
        Kb, Mb = K[idx], Ma[idx]
        vb = u_stat_var(Kb, Mb)
        inner = np.array([u_stat_var(Kb[j], Mb[j]) for j in (rng.integers(0, N, (n_inner, N)))])
        se_b = inner.std(ddof=1)
        bs[b] = vb
        ts[b] = (vb - est) / se_b if se_b > 0 else 0.0
    se = float(bs.std(ddof=1))
    t_lo, t_hi = np.quantile(ts, [0.05, 0.95])
    return dict(est=est, se=se, upper95=float(est - t_lo * se), lower95=float(est - t_hi * se),
                upper95_normal=est + 1.645 * se)


def cluster_bootstrap(stat_fn: Callable[[Sequence[np.ndarray]], float], groups: Sequence[np.ndarray], n_boot: int = 2000,
                      seed: int = 0) -> np.ndarray:
    """Prefix-only (cluster) bootstrap: resample prefixes with replacement, keep each prefix's responses intact.
    This is the correct resampling for a statistic that is a prefix-level average (plan §7.4/§7.8, v1.3)."""
    rng = np.random.default_rng(seed)
    G = len(groups)
    out = np.empty(n_boot)
    for b in range(n_boot):
        out[b] = stat_fn([groups[g] for g in rng.integers(0, G, G)])
    return out


def two_stage_bootstrap(stat_fn, groups: Sequence[np.ndarray], n_boot: int = 2000, seed: int = 0) -> np.ndarray:
    """Resample prefixes, then y_2 within prefix (v1.2).  NOT used by any gate: it double-counts the within-prefix
    component (SE inflated ≈1.4× at 40×32, Davison & Hinkley §3.8).  Kept for comparison only."""
    rng = np.random.default_rng(seed)
    G = len(groups)
    out = np.empty(n_boot)
    for b in range(n_boot):
        picked = [groups[g] for g in rng.integers(0, G, G)]
        resampled = [grp[rng.integers(0, len(grp), len(grp))] for grp in picked]
        out[b] = stat_fn(resampled)
    return out
