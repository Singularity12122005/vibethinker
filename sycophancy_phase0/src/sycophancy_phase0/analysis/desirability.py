"""Scale-free Jensen gap J and the KL-class MPC advantage A(λ) = λ_KL · J (plan §8.4).

z_3(y_2) = continuation success probability under no intervention (for λ_KL <= 0.1, e^{-(e3+e4)/λ} ≈ 1[e3=e4=0]).
J = log E_{P_r}[z_3] - E_{P_r}[log z_3];  A(λ_dose) = λ_dose * J / κ_1.

Estimators (counts Z_j = error-free continuations out of M for response j):
  * ``jensen_gap_series``  — primary: cumulant series J ≈ c2/(2μ²) − c3/(3μ³) + c4/(4μ⁴) with central moments built
    from UNBIASED falling-factorial raw moments E[q^k] = E[Z^(k)]/M^(k) (no shrinkage, no log of a proportion);
  * ``jensen_gap_beta``    — parametric cross-check: Beta moment match, J = log μ − (ψ(a) − ψ(a+b));
  * ``delta``              — second-order term only (lower bound for right-skewed z).
Shrinkage-based plug-ins are biased downward (shrinking z̃ toward the mean shrinks the gap) and are not used.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from scipy.special import digamma

from .varcomp import u_stat_var


def _weights(N: int, w: Optional[np.ndarray]) -> np.ndarray:
    return np.ones(N) / N if w is None else np.asarray(w, float) / np.sum(w)


def raw_moments_unbiased(Z: np.ndarray, M: int, kmax: int = 4, w: Optional[np.ndarray] = None) -> np.ndarray:
    """m_k = Σ_j w_j Z_j^(k) / M^(k): unbiased for E_w[q^k] (falling factorials)."""
    Z = np.asarray(Z, float)
    w = _weights(Z.shape[0], w)
    out = np.empty(kmax + 1)
    out[0] = 1.0
    for k in range(1, kmax + 1):
        num = np.ones_like(Z)
        den = 1.0
        for i in range(k):
            num = num * (Z - i)
            den *= (M - i)
        out[k] = float((w * num).sum() / den)
    return out


def central_moments(m: np.ndarray) -> Dict[str, float]:
    mu = m[1]
    c2 = m[2] - mu ** 2
    c3 = m[3] - 3 * mu * m[2] + 2 * mu ** 3
    c4 = m[4] - 4 * mu * m[3] + 6 * mu ** 2 * m[2] - 3 * mu ** 4
    return dict(mu=float(mu), c2=float(c2), c3=float(c3), c4=float(c4))


def jensen_gap_series(Z: np.ndarray, M: int, w: Optional[np.ndarray] = None) -> Dict[str, float]:
    if M < 4:
        raise ValueError("series estimator needs M >= 4 continuations")
    cm = central_moments(raw_moments_unbiased(Z, M, 4, w))
    mu, c2, c3, c4 = cm["mu"], cm["c2"], cm["c3"], cm["c4"]
    if mu <= 0:
        return dict(J=float("nan"), delta=float("nan"), **cm)
    delta = c2 / (2 * mu ** 2)
    J = delta - c3 / (3 * mu ** 3) + c4 / (4 * mu ** 4)
    return dict(J=float(J), delta=float(delta), **cm)


def jensen_gap_beta(Z: np.ndarray, M: int, w: Optional[np.ndarray] = None) -> Dict[str, float]:
    """Beta(a,b) moment match on (μ, Var) → J = log μ − (ψ(a) − ψ(a+b))."""
    Z = np.asarray(Z, float)
    ww = _weights(Z.shape[0], w)
    mu = float((ww * Z).sum() / M)
    if w is None:
        var = max(u_stat_var(Z, M), 1e-12)
    else:
        var = max(central_moments(raw_moments_unbiased(Z, M, 2, w) if False else raw_moments_unbiased(Z, M, 4, w))["c2"], 1e-12)
    if mu <= 0 or mu >= 1 or var >= mu * (1 - mu):
        return dict(J=float("nan"), a=float("nan"), b=float("nan"), mu=mu, var=var)
    s = mu * (1 - mu) / var - 1
    a, b = mu * s, (1 - mu) * s
    return dict(J=float(np.log(mu) - (digamma(a) - digamma(a + b))), a=float(a), b=float(b), mu=mu, var=var)


def jensen_gap(Z: np.ndarray, M: int, w: Optional[np.ndarray] = None) -> Dict[str, float]:
    """Primary estimate (series) with the parametric cross-check and a heavy-tail flag."""
    ser = jensen_gap_series(Z, M, w)
    beta = jensen_gap_beta(Z, M, w)
    J, Jb = ser["J"], beta["J"]
    flag = bool(np.isfinite(Jb) and np.isfinite(J) and abs(J - Jb) > 0.3 * max(abs(J), abs(Jb), 1e-9))
    return dict(J=J, J_beta=Jb, delta=ser["delta"], zbar=ser["mu"], heavy_tail_flag=flag)


def jensen_gap_exact(z: np.ndarray, w: Optional[np.ndarray] = None) -> float:
    """Exact J for KNOWN z (simulations/tests only)."""
    z = np.asarray(z, float)
    w = _weights(z.shape[0], w)
    return float(np.log((w * z).sum()) - (w * np.log(z)).sum())


def A_of_lambda(J: float, lambda_dose: float, kappa1: float) -> float:
    return float(lambda_dose * J / kappa1)


def reactive_weights(e2: np.ndarray, lam_kl: float) -> np.ndarray:
    """P_r ∝ P^0 e^{-e_2/λ}: for small λ this is uniform over the e_2 = 0 responses."""
    e2 = np.asarray(e2, float)
    lw = -e2 / lam_kl
    lw = lw - lw.max()
    w = np.exp(lw)
    return w / w.sum()
