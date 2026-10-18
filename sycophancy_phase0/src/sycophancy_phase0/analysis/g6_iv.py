"""G6 identification under risk-measurement error (plan §7.11, round 12).

The pre-registered interaction test "type × dose, controlling for logit r̂^{sel}" is biased when the dose effect depends on
TRUE baseline risk r and type is correlated with r: r̂ is a noisy proxy (binomial error from 32 continuations), the slope on
r̂ is attenuated by the reliability λ = Var(r)/(Var(r)+Var(e)), and the residual (1−λ)·b_r·(E[r|type 2]−E[r|type 1]) is
absorbed by the type coefficient — a spurious "type carries information beyond risk".  With the two independent sel halves
(``subsplit`` 0/1, 16 continuations each) r̂_a and r̂_b have independent measurement errors, so r̂_b is a valid instrument
for r̂_a in the per-prefix ENDPOINT-CONTRAST regression

    Δ̂_i = c + b_r · r_i + b_type · type_i + ε_i,   Δ̂_i = Ȳ_i(d=+1) − Ȳ_i(d=−1),

and 2SLS identifies b_type under: (i) independent measurement errors across halves, (ii) Δ linear in r over the sampled
range (checked by the oracle-fit residual plot), (iii) a strong first stage (report F; below 10 the 2SLS t-test is not
reliable — use the Anderson–Rubin test instead).  Simulation (tests/test_analysis.py): reliability 0.86, naive size 0.17
vs 2SLS 0.06 at nominal 0.05.
"""
from __future__ import annotations

from typing import Dict, Sequence

import numpy as np
from scipy import stats


def _ols(X: np.ndarray, y: np.ndarray):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    n, k = X.shape
    s2 = float(res @ res / max(1, n - k))
    cov = s2 * np.linalg.inv(X.T @ X)
    return beta, np.sqrt(np.diag(cov)), res


def _tsls(X: np.ndarray, Z: np.ndarray, y: np.ndarray):
    PZX = Z @ np.linalg.solve(Z.T @ Z, Z.T @ X)
    beta = np.linalg.solve(PZX.T @ PZX, PZX.T @ y)
    res = y - X @ beta
    n, k = X.shape
    s2 = float(res @ res / max(1, n - k))
    cov = s2 * np.linalg.inv(PZX.T @ PZX)
    return beta, np.sqrt(np.diag(cov)), res


def endpoint_contrast_iv(delta_hat: Sequence[float], r_a: Sequence[float], r_b: Sequence[float], type_: Sequence[int]) -> Dict[str, object]:
    """Naive (r̂ = mean of the halves) vs split-half 2SLS estimates of the type coefficient in the endpoint-contrast regression.
    Returns both coefficient vectors [const, r, type], their SEs, t and two-sided p for the type coefficient, the first-stage F
    of r̂_b for r̂_a, the reliability estimate Cov(r̂_a, r̂_b)/Var((r̂_a+r̂_b)/2) and n."""
    y = np.asarray(delta_hat, float)
    ra, rb, t = np.asarray(r_a, float), np.asarray(r_b, float), np.asarray(type_, float)
    n = y.size
    one = np.ones(n)
    rf = (ra + rb) / 2
    bn, sen, _ = _ols(np.c_[one, rf, t], y)
    X, Z = np.c_[one, ra, t], np.c_[one, rb, t]
    bi, sei, _ = _tsls(X, Z, y)
    b1, se1, _ = _ols(Z, ra)
    F = float((b1[1] / se1[1]) ** 2)
    rel = float(np.cov(ra, rb)[0, 1] / max(1e-12, np.var(rf, ddof=1)))
    dfree = max(1, n - 3)
    out = dict(n=int(n), first_stage_F=F, reliability=rel,
               naive=dict(beta=bn.tolist(), se=sen.tolist(), t_type=float(bn[2] / sen[2]), p_type=float(2 * stats.t.sf(abs(bn[2] / sen[2]), dfree))),
               iv=dict(beta=bi.tolist(), se=sei.tolist(), t_type=float(bi[2] / sei[2]), p_type=float(2 * stats.t.sf(abs(bi[2] / sei[2]), dfree))),
               weak_instrument=bool(F < 10.0))
    return out


# ----------------------------------------------------------------------------------------------------------------------
# Round 12 (goal document §4): closed forms behind the split-half design and a second consistent estimator.
# P1  naive_type_bias            population bias of the pre-registered "type × dose controlling for r̂" contrast
# P2  endpoint_contrast_eiv      corrected-score estimator using ALL m sel continuations (known binomial error variance)
# P3  identification_strength    first-stage F of the split-half instrument from design quantities (n, Var_w(r), E[r(1-r)], m)
# P4  lq_ceiling                 readout-reliability ceiling on the closed-loop advantage (linear-quadratic idealisation)
# P5  readout_reliability        disattenuated ρ²(ẑ, r) of any readout from two independent halves of r̂ (zero extra generation)
# ----------------------------------------------------------------------------------------------------------------------

def naive_type_bias(b_r: float, var_within: float, mean_r_one_minus_r: float, m: int, delta_mu: float) -> Dict[str, float]:
    """P1.  Population OLS of Δ̂ on (1, r̂, type) with r̂ = r + e (binomial error of m i.i.d. continuations, independent of
    type given r, and of Δ̂'s own sampling error) has type coefficient  b_type + b_r·(1−λ_w)·Δμ  where
    λ_w = Var_w(r)/(Var_w(r)+E[r(1−r)]/m) is the WITHIN-type reliability and Δμ = E[r|type 2]−E[r|type 1].
    (Frisch–Waugh: the within-type slope on r̂ is b_r·λ_w; the fitted between-type contrast must equal the actual one.)"""
    s = mean_r_one_minus_r / m
    lam_w = var_within / (var_within + s)
    return dict(reliability_within=lam_w, bias=b_r * (1.0 - lam_w) * delta_mu, error_variance=s)


def endpoint_contrast_eiv(delta_hat: Sequence[float], r_hat: Sequence[float], type_: Sequence[int], m: int) -> Dict[str, object]:
    """P2.  Corrected-score (errors-in-variables with KNOWN error variance) estimate of [const, r, type] in the endpoint-contrast
    regression, using the pooled r̂ of all m continuations.  Per row v_i = r̂_i(1−r̂_i)/(m−1) is unbiased for Var(e_i) = r_i(1−r_i)/m;
    β solves Σ_i [x_i(y_i − x_iᵀβ) + Σ_i β] = 0 with Σ_i = diag(0, v_i, 0), i.e. β = (XᵀX − ΣΣ_i)⁻¹Xᵀy; SE from the M-estimator sandwich.
    Consistent under the same linearity/independence assumptions as the 2SLS route; more efficient because the first stage does not
    spend half the draws.  Returns ok=False (no estimate) when the corrected moment matrix is not positive definite — the weak-
    identification regime, in which the 2SLS slope is also unstable (goal document §4, P3)."""
    y = np.asarray(delta_hat, float)
    rh, t = np.asarray(r_hat, float), np.asarray(type_, float)
    n = y.size
    if m < 2:
        raise ValueError("m must be ≥ 2 continuations per prefix")
    v = rh * (1.0 - rh) / (m - 1)
    X = np.c_[np.ones(n), rh, t]
    S = np.zeros((3, 3))
    S[1, 1] = v.sum()
    A = X.T @ X - S
    min_eig = float(np.linalg.eigvalsh(A).min())
    if min_eig <= 0:
        return dict(ok=False, n=int(n), min_eig=min_eig,
                    reason="corrected moment matrix not positive definite: within-type risk variation too small for the error variance")
    beta = np.linalg.solve(A, X.T @ y)
    res = y - X @ beta
    psi = X * res[:, None]
    psi[:, 1] += v * beta[1]
    Ai = np.linalg.inv(A)
    cov = Ai @ (psi.T @ psi) @ Ai
    se = np.sqrt(np.diag(cov))
    t_type = float(beta[2] / se[2])
    return dict(ok=True, n=int(n), min_eig=min_eig, beta=beta.tolist(), se=se.tolist(), t_type=t_type,
                p_type=float(2 * stats.norm.sf(abs(t_type))))


def identification_strength(n: int, var_within: float, mean_r_one_minus_r: float, m_half: int, F_target: float = 10.0) -> Dict[str, float]:
    """P3.  With independent halves of m_half continuations, Corr(r̂_a, r̂_b | type) = λ_h = V/(V+s), V = Var_w(r), s = E[r(1−r)]/m_half,
    so the first-stage F of r̂_b for r̂_a (one instrument, type partialled out) is  F ≈ n·λ_h²/(1−λ_h²) = n·V²/(s(2V+s)).
    Returns the predicted F, λ_h, the n needed for F_target at this (V, s) and the m_half needed at this n."""
    s = mean_r_one_minus_r / m_half
    lam = var_within / (var_within + s)
    F = n * lam ** 2 / (1.0 - lam ** 2)
    n_needed = F_target * (1.0 - lam ** 2) / lam ** 2
    # m_half needed at this n: λ_h² ≥ F_target/(n+F_target)  ⇔  s ≤ V(1/λ* − 1)
    lam_star = np.sqrt(F_target / (n + F_target))
    s_max = var_within * (1.0 / lam_star - 1.0)
    return dict(F=float(F), reliability_half=float(lam), error_variance_half=float(s), n_for_F_target=float(n_needed),
                m_half_for_F_target=float(mean_r_one_minus_r / s_max), weak=bool(F < F_target))


def lq_ceiling(var_r: float, mean_r_one_minus_r: float, m: int, kappa: float = 1.0, b: float = 1.0) -> Dict[str, float]:
    """P4.  Linear-quadratic idealisation J(d; r) = J*(r) + (κ/2)(d − a − b·r)²; readout r̂ = r + e with Var(e) = E[r(1−r)]/m,
    λ = Var(r)/(Var(r)+Var(e)).  Regret vs the oracle d = a + b·r:  open loop (constant d) (κ/2)b²Var(r);  best linear closed loop
    d = a + b(μ + λ(r̂ − μ)) (κ/2)b²Var(r)(1−λ);  plug-in d = a + b·r̂ (κ/2)b²Var(e).  Hence the fraction of the oracle advantage any
    LINEAR closed loop can realise is exactly λ, and the plug-in controller is worse than open loop iff λ < 1/2.
    (The same algebra with E[r | ẑ] in place of the linear predictor gives the correlation ratio η² for arbitrary controllers.)"""
    s = mean_r_one_minus_r / m
    lam = var_r / (var_r + s)
    base = 0.5 * kappa * b ** 2
    return dict(reliability=lam, open_loop_regret=base * var_r, linear_closed_loop_regret=base * var_r * (1 - lam),
                plug_in_regret=base * s, fraction_realisable=lam, plug_in_beats_open_loop=bool(lam > 0.5))


def readout_reliability(z: Sequence[float], r_a: Sequence[float], r_b: Sequence[float], *, n_boot: int = 1000, seed: int = 0) -> Dict[str, object]:
    """P5.  Disattenuated squared correlation of a readout ẑ (probe score, logit feature, …) with TRUE prefix risk r:
    ρ²(ẑ, r) = Cov(ẑ, r̂_a)·Cov(ẑ, r̂_b) / (Var(ẑ)·Cov(r̂_a, r̂_b)),  exact in population when the two halves have independent
    errors given r and ẑ is computed without those continuations (cross-fitted / LOQO predictions).  Needs Cov(r̂_a, r̂_b) > 0.
    Returns the estimate, the naive Corr(ẑ, r̄)², the half-reliability Corr(r̂_a, r̂_b) and a percentile bootstrap CI over prefixes."""
    z, ra, rb = (np.asarray(a, float) for a in (z, r_a, r_b))
    n = z.size
    def est(idx):
        c = np.cov(np.c_[z[idx], ra[idx], rb[idx]].T)
        return c[0, 1] * c[0, 2] / (c[0, 0] * c[1, 2]) if c[1, 2] > 0 else np.nan
    full = est(np.arange(n))
    rng = np.random.default_rng(seed)
    boots = np.array([est(rng.integers(0, n, n)) for _ in range(n_boot)])
    boots = boots[np.isfinite(boots)]
    rbar = (ra + rb) / 2
    return dict(n=int(n), rho2=float(full), naive_corr2=float(np.corrcoef(z, rbar)[0, 1] ** 2),
                half_reliability=float(np.corrcoef(ra, rb)[0, 1]),
                ci95=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))] if boots.size else [float("nan")] * 2,
                n_boot_valid=int(boots.size))
