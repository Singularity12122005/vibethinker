"""Pool-adjacent-violators isotonic regression and a bootstrap one-sided lower bound (plan §4.7 step 2)."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np


def pava(y: np.ndarray, w: Optional[np.ndarray] = None, increasing: bool = True) -> np.ndarray:
    """Weighted isotonic fit of y (in the given x-order) — non-decreasing if ``increasing`` else non-increasing."""
    y = np.asarray(y, float)
    w = np.ones_like(y) if w is None else np.asarray(w, float)
    if not increasing:
        return -pava(-y, w, True)
    vals, wts, cnts = [], [], []
    for yi, wi in zip(y, w):
        vals.append(yi); wts.append(wi); cnts.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v = (vals[-2] * wts[-2] + vals[-1] * wts[-1]) / (wts[-2] + wts[-1])
            wts[-2] += wts[-1]; cnts[-2] += cnts[-1]
            vals[-2] = v
            vals.pop(); wts.pop(); cnts.pop()
    return np.concatenate([np.full(c, v) for v, c in zip(vals, cnts)])


def isotonic_lower_bound(values: np.ndarray, clusters: np.ndarray, grid_index: np.ndarray, n_grid: int, *, increasing: bool,
                         n_boot: int = 1000, seed: int = 0, level: float = 0.95) -> Dict[str, np.ndarray]:
    """values[i] observed at grid point grid_index[i] from cluster clusters[i] (problem).  Returns the isotonic fit on
    the grid and its one-sided ``level`` lower bound from a cluster bootstrap (problems resampled)."""
    values, clusters, grid_index = np.asarray(values, float), np.asarray(clusters), np.asarray(grid_index)

    def fit_idx(idx):
        means = np.full(n_grid, np.nan); wts = np.zeros(n_grid)
        gi, vv = grid_index[idx], values[idx]
        for g in range(n_grid):
            v = vv[gi == g]
            if v.size:
                means[g] = v.mean(); wts[g] = v.size
        ok = ~np.isnan(means)
        out = np.full(n_grid, np.nan)
        out[ok] = pava(means[ok], wts[ok], increasing)
        return out

    all_idx = np.arange(values.size)
    est = fit_idx(all_idx)
    ups = np.unique(clusters)
    by_c = {c: np.where(clusters == c)[0] for c in ups}
    rng = np.random.default_rng(seed)
    boots = np.empty((n_boot, n_grid))
    for b in range(n_boot):
        pick = ups[rng.integers(0, len(ups), len(ups))]
        boots[b] = fit_idx(np.concatenate([by_c[c] for c in pick]))
    lower = np.nanquantile(boots, 1 - level, axis=0)
    return dict(fit=est, lower=lower, n_clusters=len(ups))
