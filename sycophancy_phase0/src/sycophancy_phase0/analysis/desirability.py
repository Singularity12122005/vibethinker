"""Scale-free Jensen gap J and the KL-class MPC advantage A(λ) = λ_KL · J (plan §8.4, v1.3).

z_3(y_2) = continuation success probability under no intervention (for λ_KL <= 0.1, e^{-(e3+e4)/λ} ≈ 1[e3=e4=0]).
J = log E_{P_r}[z_3] - E_{P_r}[log z_3];  A(λ_dose) = λ_dose * J / κ_1.  J is computed **per prefix** and averaged
over prefixes (between-prefix dispersion of z_3 is not exploitable at turn 2 and must not enter J).

Estimators (counts Z_j = error-free continuations out of M for response j; F_j = M - Z_j failures):
  * ``jensen_gap_u``      — PRIMARY (v1.4 r7): difference of U-statistics, unbiased for the truncated target T_K <= J_0.
  * ``jensen_gap_lb``     — diagnostic (v1.3 primary): -E log z = Σ_{k>=1} E[(1-z)^k]/k, truncated at k = M, with each
    E[(1-z)^k] estimated UNBIASEDLY by the failure falling factorials F^(k)/M^(k).  All omitted terms are
    positive, so the estimator is a lower bound of J in expectation (up to the O(1/N) plug-in bias of log μ̂, which
    is corrected to second order).  It converges for every z in (0, 1] (no divergence at low μ) and is unbiased to
    4 decimals whenever z stays away from 0 (Beta(60,40), Beta(6,4), Beta(8,2): simulation in tests).
  * ``jensen_gap_series`` — diagnostic: μ-centred cumulant series c2/(2μ²) − c3/(3μ³) + c4/(4μ⁴) (v1.2 primary;
    one-sidedly low under near-zero mass, divergent for μ < 0.25 — see tests/test_analysis.py).
  * ``jensen_gap_beta``   — diagnostic: Beta moment match, J = log μ − (ψ(a) − ψ(a+b)).
Regime flags (per prefix): ``n_zero`` = #{j: Z_j = 0} among the P_r support (>= 2 => near-zero mass: under any
smooth truth with z̄ >= 0.5, P(Z = 0) = E(1-z)^M ≈ 0) and ``mu < 0.25``.  When flags are present Ĵ_LB is loose
(a lower bound only): the G2′-a KILL rule is suspended (plan §7.4).
Shrinkage-based plug-ins are biased downward and are not used.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np
from scipy.special import digamma

from .varcomp import u_stat_var


def _weights(N: int, w: Optional[np.ndarray]) -> np.ndarray:
    return np.ones(N) / N if w is None else np.asarray(w, float) / np.sum(w)


def raw_moments_unbiased(Z: np.ndarray, M: int, kmax: int = 4, w: Optional[np.ndarray] = None) -> np.ndarray:
    """m_k = Σ_j w_j Z_j^(k) / M^(k): unbiased for E_w[q^k] (falling factorials), k <= M."""
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
    """Plug-in central moments from unbiased raw moments (O(1/N) bias in the products)."""
    mu = m[1]
    c2 = m[2] - mu ** 2
    c3 = m[3] - 3 * mu * m[2] + 2 * mu ** 3
    c4 = m[4] - 4 * mu * m[3] + 6 * mu ** 2 * m[2] - 3 * mu ** 4
    return dict(mu=float(mu), c2=float(c2), c3=float(c3), c4=float(c4))


def jensen_gap_lb(Z: np.ndarray, M, w: Optional[np.ndarray] = None, kmax: Optional[int] = None) -> Dict[str, float]:
    """DIAGNOSTIC since round 7 (``J_approx``): log μ̂ + Var̂(μ̂)/(2μ̂²) + Σ_{k=1}^{K} (1/k) Σ_j w_j F_j^(k)/M_j^(k).  The first
    two terms are a second-order bias correction for log μ, not an unbiased estimator of it, so the expectation of the
    whole is not guaranteed to stay below J_0 ("the dropped terms are positive" only applies to the population target
    T_K).  Agrees with ``jensen_gap_u`` to 4 decimals when z stays away from 0, falls below T_K at low μ.  Supports
    non-uniform weights (finite-λ descriptive use) and unequal M_j (series truncated at the smallest M_j)."""
    Z = np.asarray(Z, float)
    N = Z.shape[0]
    Ma = np.broadcast_to(np.asarray(M, float), Z.shape).astype(float)
    if N < 2 or np.any(Ma < 2):
        raise ValueError("need N>=2 responses and M_j>=2 continuations")
    if np.any(Z < 0) or np.any(Z > Ma):
        raise ValueError("counts must lie in [0, M_j]")
    ww = _weights(N, w)
    F = Ma - Z
    q = Z / Ma
    mu = float((ww * q).sum())
    if mu <= 0:
        return dict(J=float("nan"), mu=mu, n_zero=int((Z == 0).sum()), K=0)
    var_mu = float((ww ** 2 * (q - mu) ** 2).sum())
    total = float(np.log(mu) + var_mu / (2 * mu ** 2))
    Kmax = int(Ma.min())
    K = Kmax if kmax is None else min(int(kmax), Kmax)
    num = np.ones_like(F)
    den = np.ones_like(F)
    for k in range(1, K + 1):
        num = num * (F - (k - 1))
        den = den * (Ma - (k - 1))
        total += float((ww * num / den).sum()) / k
    return dict(J=total, mu=mu, n_zero=int((Z == 0).sum()), K=K, var_mu=var_mu)


def jensen_gap_u(Z: np.ndarray, M, w: Optional[np.ndarray] = None, kmax: Optional[int] = None) -> Dict[str, object]:
    """PRIMARY (v1.4, round 7): difference of U-statistics, strictly unbiased for the truncated target

        T_K = Σ_{k=1}^{K} [E(1−z)^k − (1−μ)^k] / k  ≤  J_0 = Σ_{k≥1} [E(1−z)^k − (1−μ)^k] / k,   K = min_j M_j,

    every term ≥ 0 by Jensen (x^k convex on [0,1]).  E(1−z)^k is estimated by the unbiased falling-factorial moment of the
    failure counts F_j = M_j − Z_j, (1−μ)^k by the degree-k U-statistic U_k = e_k(p̂_1..p̂_N)/C(N,k) with p̂_j = F_j/M_j
    (independent across responses, each unbiased for 1−z_j), e_k the elementary symmetric polynomial.  No logarithm, no
    delta correction: μ̂ = 0 gives 0, not NaN.  ``w`` must be uniform on its support (the small-λ reactive weights are:
    uniform on e_2 = 0); non-uniform weights are refused (use ``jensen_gap_lb`` as an approximate estimator then).
    The truncation remainder J_0 − T_K is non-negative and NOT controlled by the data (plan §8.4, regime flags)."""
    from math import comb
    Z = np.asarray(Z, float)
    Ma = np.broadcast_to(np.asarray(M, float), Z.shape).astype(float)
    if w is not None:
        w = np.asarray(w, float)
        sup = w > 0
        if not np.allclose(w[sup], w[sup][0]):
            raise ValueError("jensen_gap_u needs weights that are uniform on their support")
        Z, Ma = Z[sup], Ma[sup]
    N = Z.shape[0]
    if N < 2 or np.any(Ma < 2):
        raise ValueError("need N>=2 responses and M_j>=2 continuations")
    if np.any(Z < 0) or np.any(Z > Ma):
        raise ValueError("counts must lie in [0, M_j]")
    F = Ma - Z
    p = F / Ma
    Kmax = min(int(Ma.min()), N)                           # a degree-k U-statistic needs k responses: K <= N as well as <= M_j
    K = Kmax if kmax is None else min(int(kmax), Kmax)
    e = np.zeros(K + 1)
    e[0] = 1.0
    for pj in p:                                           # elementary symmetric polynomials e_1..e_K of p̂ (O(N K))
        for k in range(K, 0, -1):
            e[k] += pj * e[k - 1]
    total = 0.0
    num = np.ones_like(F)
    den = np.ones_like(F)
    for k in range(1, K + 1):
        num = num * (F - (k - 1))
        den = den * (Ma - (k - 1))
        total += (float((num / den).mean()) - e[k] / comb(N, k)) / k
    return dict(J=float(total), target=f"T_{K}", K=K, mu=float((Z / Ma).mean()), n_zero=int((Z == 0).sum()), N=N)


def jensen_gap_series(Z: np.ndarray, M: int, w: Optional[np.ndarray] = None) -> Dict[str, float]:
    """Diagnostic μ-centred series (v1.2 primary)."""
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
    """Diagnostic Beta(a,b) moment match on (μ, Var) → J = log μ − (ψ(a) − ψ(a+b)).

    v1.4 (memo S4): undefined — J = NaN with ``reason`` — when μ ∉ (0,1), when the unbiased variance estimate is ≤ 0
    (returned as is, negative values included; it is never clamped into a degenerate fit) or when Var ≥ μ(1−μ)
    (no Beta has that dispersion)."""
    Z = np.asarray(Z, float)
    ww = _weights(Z.shape[0], w)
    mu = float((ww * Z).sum() / M)
    var = float(u_stat_var(Z, M) if w is None else central_moments(raw_moments_unbiased(Z, M, 4, w))["c2"])
    reason = None
    if not (0.0 < mu < 1.0):
        reason = "mu_out_of_(0,1)"
    elif var <= 0.0:
        reason = "var_le_0"
    elif var >= mu * (1 - mu):
        reason = "var_ge_mu(1-mu)"
    if reason is not None:
        return dict(J=float("nan"), a=float("nan"), b=float("nan"), mu=mu, var=var, reason=reason)
    s = mu * (1 - mu) / var - 1
    a, b = mu * s, (1 - mu) * s
    return dict(J=float(np.log(mu) - (digamma(a) - digamma(a + b))), a=float(a), b=float(b), mu=mu, var=var, reason=None)


def regime_flags(Z: np.ndarray, M: int, w: Optional[np.ndarray] = None, mu_min: float = 0.25, n_zero_max: int = 1) -> Dict[str, object]:
    Z = np.asarray(Z, float)
    ww = _weights(Z.shape[0], w)
    support = ww > 0
    n_zero = int(((Z == 0) & support).sum())
    mu = float((ww * Z).sum() / M)
    n_sup = int(support.sum())
    return dict(n_zero=n_zero, mu=mu, near_zero_mass=n_zero > n_zero_max, low_mean=mu < mu_min,
                flagged=(n_zero > n_zero_max) or (mu < mu_min),
                # rule of three: 95% upper bound on the probability of a zero-count y_2 when none/few were seen (descriptive)
                zero_count_mass_ub95=float(3.0 / n_sup) if n_zero == 0 and n_sup > 0 else float("nan"))


def jensen_gap(Z: np.ndarray, M, w: Optional[np.ndarray] = None) -> Dict[str, float]:
    """One prefix: primary Ĵ_U (unbiased for the truncated target T_K; falls back to the approximate Ĵ_LB only for
    non-uniform weights) plus diagnostics and regime flags (diagnostics need a scalar M: they use the minimum)."""
    lb = jensen_gap_lb(Z, M, w)
    try:
        ju = jensen_gap_u(Z, M, w)
        J, estimator, target = ju["J"], "U", ju["target"]
    except ValueError as exc:                                 # non-uniform weights (finite λ): approximate estimator, flagged
        if "uniform" not in str(exc):
            raise
        J, estimator, target = lb["J"], "approx_weighted", "J(lambda) plug-in-like"
    Ms = int(np.min(np.asarray(M)))
    balanced = bool(np.all(np.asarray(M) == Ms))
    ser = jensen_gap_series(Z, Ms, w) if (balanced and Ms >= 4) else dict(J=float("nan"), delta=float("nan"))
    beta = jensen_gap_beta(Z, Ms, w) if balanced else dict(J=float("nan"), reason="unbalanced_M")
    fl = regime_flags(Z, Ms, w)
    return dict(J=J, estimator=estimator, target=target, J_approx=lb["J"], J_series=ser["J"], J_beta=beta["J"], J_beta_reason=beta.get("reason"),
                delta=ser["delta"], zbar=lb["mu"], n_zero=fl["n_zero"], near_zero_mass=fl["near_zero_mass"], low_mean=fl["low_mean"],
                flagged=fl["flagged"], zero_count_mass_ub95=fl["zero_count_mass_ub95"])


def jensen_gap_by_prefix(Z: np.ndarray, M, prefix: np.ndarray, w: Optional[np.ndarray] = None) -> Dict[str, object]:
    """Per-prefix Ĵ_LB (weights renormalised within prefix) and their unweighted mean over prefixes; M scalar or per-row."""
    Z, prefix = np.asarray(Z, float), np.asarray(prefix)
    Ma = np.broadcast_to(np.asarray(M, float), Z.shape).astype(float)
    w = None if w is None else np.asarray(w, float)
    per: Dict[object, Dict[str, float]] = {}
    for p in np.unique(prefix):
        m = prefix == p
        wp = None if w is None else w[m]
        if wp is not None and wp.sum() <= 0:
            continue
        per[p] = jensen_gap(Z[m], Ma[m], wp)
    Js = np.array([d["J"] for d in per.values()])
    return dict(J=float(np.nanmean(Js)) if len(Js) else float("nan"), per_prefix=per, n_prefix=len(per),
                frac_flagged=float(np.mean([d["flagged"] for d in per.values()])) if per else float("nan"))


def jensen_gap_exact(z: np.ndarray, w: Optional[np.ndarray] = None) -> float:
    """Exact J for KNOWN z (simulations/tests only)."""
    z = np.asarray(z, float)
    w = _weights(z.shape[0], w)
    return float(np.log((w * z).sum()) - (w * np.log(z)).sum())


def jensen_gap_lambda_by_prefix(Z, S1, S2, M, e2, prefix, lam_kl: float) -> Dict[str, object]:
    """Descriptive finite-λ curve (plan §8.4, v1.4): per y_2, ẑ_3(λ) = (Z + S1·e^{−1/λ} + S2·e^{−2/λ}) / M with S1/S2 the
    continuations with e_3+e_4 = 1 / 2; P_r weights ∝ e^{−e_2/λ}; J(λ) = log Σ_j w_j ẑ_j − Σ_j w_j log ẑ_j per prefix (plug-in
    with stable log-sum-exp), averaged over prefixes.  Report only — it carries none of Ĵ_LB's bias guarantees."""
    from scipy.special import logsumexp
    Z, S1, S2, M, e2, prefix = (np.asarray(x) for x in (Z, S1, S2, M, e2, prefix))
    with np.errstate(divide="ignore"):
        terms = np.stack([np.log(Z.astype(float)), np.log(S1.astype(float)) - 1.0 / lam_kl, np.log(S2.astype(float)) - 2.0 / lam_kl])
        logz = logsumexp(terms, axis=0) - np.log(M.astype(float))
    per: Dict[str, float] = {}
    for pid in sorted(set(prefix.tolist())):
        idx = np.where(prefix == pid)[0]
        lz = logz[idx]
        if not np.all(np.isfinite(lz)):
            per[pid] = float("nan")
            continue
        w = reactive_weights(e2[idx], lam_kl)
        per[pid] = float(logsumexp(lz, b=w) - (w * lz).sum())
    vals = [v for v in per.values() if np.isfinite(v)]
    return dict(J=float(np.mean(vals)) if vals else float("nan"), per_prefix=per, lam_kl=float(lam_kl), n_prefix=len(vals))


def A_of_lambda(J: float, lambda_dose: float, kappa1: float) -> float:
    return float(lambda_dose * J / kappa1)


def reactive_weights(e2: np.ndarray, lam_kl: float) -> np.ndarray:
    """P_r ∝ P^0 e^{-e_2/λ}: for small λ this is uniform over the e_2 = 0 responses."""
    e2 = np.asarray(e2, float)
    lw = -e2 / lam_kl
    lw = lw - lw.max()
    w = np.exp(lw)
    return w / w.sum()


def g2a_decision(J_hat: float, lo95: float, hi95: float, frac_flagged: float, kill_ub: float = 0.02, go_lb: float = 0.08,
                 max_flagged: float = 0.10) -> str:
    """plan §7.4: UB < 0.02 => KILL (only when < 10% of prefixes carry regime flags, since Ĵ_LB is then a loose lower
    bound); LB >= 0.08 => GO (always valid: Ĵ_LB under-estimates); else GO-with-caveat."""
    if lo95 >= go_lb:
        return "GO"
    if hi95 < kill_ub and frac_flagged < max_flagged:
        return "KILL"
    return "GO-with-caveat"
