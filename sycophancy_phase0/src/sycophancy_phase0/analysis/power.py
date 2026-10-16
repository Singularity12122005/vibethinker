"""Paired-design variance components and sample-size rules (plan §8.6)."""
from __future__ import annotations

from typing import Dict

import numpy as np
from scipy import stats


def paired_components(d: np.ndarray, vbar: float) -> Dict[str, float]:
    """d: [F, P] per-prefix arm differences p0 - pu; vbar: mean unbiased binomial variance of a difference.

    Returns MS_f, MS_p, sigma_f^2, sigma_p^2 (truncated at 0), SE(tau)^2 = MS_f/(F P), and the 80% upper
    confidence bound of sigma_f^2.
    """
    d = np.asarray(d, float)
    Fn, P = d.shape
    dbar_f = d.mean(1)
    dbar = d.mean()
    ms_f = P * ((dbar_f - dbar) ** 2).sum() / (Fn - 1)
    ms_p = ((d - dbar_f[:, None]) ** 2).sum() / (Fn * (P - 1)) if P > 1 else float("nan")
    sig_p2 = max(ms_p - vbar, 0.0) if P > 1 else float("nan")
    sig_f2 = max((ms_f - ms_p) / P, 0.0) if P > 1 else float("nan")
    chi = stats.chi2.ppf(0.20, Fn - 1)
    sig_f2_ub = max(((Fn - 1) * ms_f / chi - ms_p) / P, 0.0) if P > 1 else float("nan")
    return dict(tau=float(dbar), MS_f=float(ms_f), MS_p=float(ms_p), sigma_f2=float(sig_f2), sigma_p2=float(sig_p2),
                sigma_f2_ub80=float(sig_f2_ub), se2_tau=float(ms_f / (Fn * P)), df=Fn - 1)


def F_required(sigma_f2: float, sigma_p2: float, P: int, n: int, delta: float, pbar: float = 0.3,
               power: float = 0.8, alpha: float = 0.05) -> float:
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    V1 = sigma_f2 + sigma_p2 / P + 2 * pbar * (1 - pbar) / (P * n)
    return float(z * z * V1 / delta ** 2 + 3)          # +3: t correction (plan §8.6)


def n_star(vbar: float, c_P: float, sigma_p2: float, c_n: float = 1.0) -> float:
    return float(np.sqrt(vbar * c_P / (2 * sigma_p2 * c_n))) if sigma_p2 > 0 else float("inf")
