"""Equivalence tests and paired cluster bootstraps for the G0 fidelity gates (plan §7.1)."""
from __future__ import annotations

from typing import Dict, Sequence

import numpy as np


def paired_cluster_bootstrap_diff(x: np.ndarray, y: np.ndarray, cluster: np.ndarray, n_boot: int = 2000,
                                  seed: int = 0, level: float = 0.90) -> Dict[str, float]:
    """Mean difference of binary outcomes x - y where x and y are paired by cluster (same h_3 / y_2 / prefix).

    Clusters are resampled together (both arms of a cluster move together), which is what makes the CI paired.
    Returns the point estimate and the central ``level`` CI.
    """
    x, y, cluster = np.asarray(x, float), np.asarray(y, float), np.asarray(cluster)
    ups = np.unique(cluster)
    idx = {c: np.where(cluster == c)[0] for c in ups}
    per_c = np.array([x[idx[c]].mean() - y[idx[c]].mean() for c in ups])
    est = float(per_c.mean())
    rng = np.random.default_rng(seed)
    bs = np.array([per_c[rng.integers(0, len(ups), len(ups))].mean() for _ in range(n_boot)])
    a = (1 - level) / 2
    return dict(est=est, lo=float(np.quantile(bs, a)), hi=float(np.quantile(bs, 1 - a)), n_clusters=int(len(ups)))


def tost_pass(ci_lo: float, ci_hi: float, margin: float) -> bool:
    """TOST at level 1-2a via the (1-2a) CI: pass iff the CI lies strictly inside (-margin, +margin)."""
    return (ci_lo > -margin) and (ci_hi < margin)


def tv_distance(counts_a: Sequence[int], counts_b: Sequence[int]) -> float:
    a = np.asarray(counts_a, float); b = np.asarray(counts_b, float)
    return float(0.5 * np.abs(a / a.sum() - b / b.sum()).sum())


def chi2_homogeneity_p(counts_a: Sequence[int], counts_b: Sequence[int]) -> float:
    from scipy import stats
    table = np.array([counts_a, counts_b], float)
    table = table[:, table.sum(0) > 0]
    return float(stats.chi2_contingency(table, correction=False)[1])
