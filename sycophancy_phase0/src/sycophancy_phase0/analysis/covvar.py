"""Heterogeneity of the 4-sample policy value: Cov(V^(a), V^(b)) (plan §7.8).

V^(a)_j and V^(b)_j are two independent half-estimates of V_3(y_j) (arm chosen on one quarter, evaluated on
another). Their covariance across y_2 (within-prefix demeaned) estimates Var_j(E[V_j | y_j]) without evaluation
or selection noise.
"""
from __future__ import annotations

from typing import Dict, Sequence

import numpy as np


def cov_within_prefix(Va: np.ndarray, Vb: np.ndarray, prefix: np.ndarray) -> float:
    Va, Vb, prefix = np.asarray(Va, float), np.asarray(Vb, float), np.asarray(prefix)
    num, cnt = 0.0, 0
    for p in np.unique(prefix):
        m = prefix == p
        if m.sum() < 2:
            continue
        a = Va[m] - Va[m].mean()
        b = Vb[m] - Vb[m].mean()
        num += (a * b).sum()
        cnt += m.sum() - 1
    return float(num / cnt) if cnt > 0 else float("nan")


def policy_value_halves(p_hat: np.ndarray, cost: np.ndarray, lam: float):
    """p_hat: [n_y2, n_arms, 4] quarter-wise success-rate estimates of P(e3+e4 | arm); cost: [n_arms].

    Returns (Va, Vb): arm chosen on Q1 evaluated on Q2, and chosen on Q3 evaluated on Q4.
    """
    p_hat = np.asarray(p_hat, float)
    cost = np.asarray(cost, float)
    def half(sel_q, eval_q):
        obj = p_hat[:, :, sel_q] + lam * cost[None, :]
        arm = obj.argmin(1)
        return p_hat[np.arange(p_hat.shape[0]), arm, eval_q] + lam * cost[arm]
    return half(0, 1), half(2, 3)


def cluster_bootstrap_cov(Va, Vb, prefix, n_boot: int = 2000, seed: int = 0) -> Dict[str, float]:
    """Prefix-only bootstrap of the within-prefix covariance (plan §7.8, v1.3): resample prefixes with replacement,
    keep their y_2 intact.  The two-stage version double-counts within-prefix noise (SE ≈1.4× too large at 40×32)."""
    rng = np.random.default_rng(seed)
    Va, Vb, prefix = np.asarray(Va, float), np.asarray(Vb, float), np.asarray(prefix)
    ups = np.unique(prefix)
    idx_by_p = {p: np.where(prefix == p)[0] for p in ups}
    est = cov_within_prefix(Va, Vb, prefix)
    bs = np.empty(n_boot)
    for b in range(n_boot):
        pick = ups[rng.integers(0, len(ups), len(ups))]
        ia, ib, ip = [], [], []
        for k, p in enumerate(pick):
            idx = idx_by_p[p]
            ia.append(Va[idx]); ib.append(Vb[idx]); ip.append(np.full(len(idx), k))
        bs[b] = cov_within_prefix(np.concatenate(ia), np.concatenate(ib), np.concatenate(ip))
    return dict(est=est, se=float(bs.std(ddof=1)), lower95_onesided=float(np.quantile(bs, 0.05)), n_prefix=int(len(ups)))


def two_stage_bootstrap_cov(Va, Vb, prefix, n_boot: int = 2000, seed: int = 0) -> Dict[str, float]:
    """v1.2 two-stage resampling; NOT used by any gate (over-estimates SE).  Kept for comparison only."""
    rng = np.random.default_rng(seed)
    Va, Vb, prefix = np.asarray(Va, float), np.asarray(Vb, float), np.asarray(prefix)
    ups = np.unique(prefix)
    idx_by_p = {p: np.where(prefix == p)[0] for p in ups}
    est = cov_within_prefix(Va, Vb, prefix)
    bs = np.empty(n_boot)
    for b in range(n_boot):
        pick = ups[rng.integers(0, len(ups), len(ups))]
        ia, ib, ip = [], [], []
        for k, p in enumerate(pick):
            idx = idx_by_p[p]
            r = idx[rng.integers(0, len(idx), len(idx))]
            ia.append(Va[r]); ib.append(Vb[r]); ip.append(np.full(len(r), k))
        bs[b] = cov_within_prefix(np.concatenate(ia), np.concatenate(ib), np.concatenate(ip))
    return dict(est=est, se=float(bs.std(ddof=1)), lower95_onesided=float(np.quantile(bs, 0.05)))
