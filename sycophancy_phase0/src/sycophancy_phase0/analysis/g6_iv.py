"""G6 identification under risk-measurement error (plan §7.11; research archive `docs/research/sycophancy-phase0-goal.md` §4).

The pre-registered interaction test "type × dose, controlling for logit r̂^{sel}" is biased when the dose effect depends on
TRUE baseline risk r and type is correlated with r: r̂ is a noisy proxy (binomial error from m = 32 continuations), the slope
on r̂ is attenuated by the WITHIN-type reliability λ_w = Var_w(r)/(Var_w(r)+E[r(1−r)]/m), and the residual b_r·(1−λ_w)·Δμ is
absorbed by the type coefficient (P1).  Two consistent estimators of the per-prefix ENDPOINT-CONTRAST regression

    Δ̂_i = c + b_r · r_i + b_type · type_i + ε_i,   Δ̂_i = Ȳ_i(d=+1) − Ȳ_i(d=−1),

are provided: (a) repeated-measurement 2SLS with the two independent `subsplit` halves r̂_a, r̂_b (16 continuations each; r̂_b
instruments r̂_a), (b) a corrected-score estimator that uses all m continuations and the KNOWN binomial error variance
(`endpoint_contrast_eiv`), generalised to a polynomial in r of any degree ≤ m/2 via U-statistics of the success count
(`endpoint_contrast_poly_cs`).  Both recover the ORACLE regression (the one with true r); what they cannot repair is a
misspecified functional form: if E[Δ | r] is not in the fitted polynomial class and the types occupy different parts of the
r-range, the oracle regression itself attributes the misfit to type (adversarial review, round 12).  Hence: report overlap of
the two types' r̂ ranges, fit degrees 1–3, and treat a type effect that disappears with degree as functional form.

Identification strength: with independent halves, Corr(r̂_a, r̂_b | type) = λ_h and the first-stage F of r̂_b for r̂_a has
non-centrality n·λ_h²/(1−λ_h²) (P3); below ≈10 the 2SLS slope has no finite mean and the corrected moment matrix can fail to be
positive definite.  Standard errors: HC1 by default, cluster-robust (CR1) when `cluster` (question id) is given.
Selection: prefixes must not be selected on the half used as REGRESSOR (selection on the instrument half is harmless).
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np
from scipy import stats
from scipy.optimize import brentq


# ----------------------------------------------------------------------------------------------------------------------- helpers
def _robust_cov(A_inv: np.ndarray, psi: np.ndarray, cluster: Optional[np.ndarray]) -> np.ndarray:
    """Sandwich A⁻¹ B A⁻¹ with B = Σψψᵀ (HC1 small-sample factor) or the cluster sum (CR1)."""
    n, k = psi.shape
    if cluster is None:
        B = psi.T @ psi * (n / max(1, n - k))
    else:
        cl = np.asarray(cluster)
        groups = np.unique(cl)
        G = groups.size
        S = np.zeros((k, k))
        for g in groups:
            s = psi[cl == g].sum(0)
            S += np.outer(s, s)
        B = S * (G / max(1, G - 1)) * ((n - 1) / max(1, n - k))
    return A_inv @ B @ A_inv


def _ols(X: np.ndarray, y: np.ndarray, cluster=None):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    A_inv = np.linalg.inv(X.T @ X)
    cov = _robust_cov(A_inv, X * res[:, None], cluster)
    return beta, np.sqrt(np.diag(cov)), res


def _tsls(X: np.ndarray, Z: np.ndarray, y: np.ndarray, cluster=None):
    Xh = Z @ np.linalg.solve(Z.T @ Z, Z.T @ X)
    beta = np.linalg.solve(Xh.T @ X, Xh.T @ y)
    res = y - X @ beta
    A_inv = np.linalg.inv(Xh.T @ X)
    cov = _robust_cov(A_inv, Xh * res[:, None], cluster)
    return beta, np.sqrt(np.diag(cov)), res


def _falling(K: np.ndarray, j: int) -> np.ndarray:
    out = np.ones_like(K, dtype=float)
    for i in range(j):
        out = out * (K - i)
    return out


# ----------------------------------------------------------------------------------------------------------------------- P1
def naive_type_bias(b_r: float, var_within: float, mean_r_one_minus_r: float, m: int, delta_mu: float) -> Dict[str, float]:
    """P1.  Population OLS of Δ̂ on (1, r̂, type) with r̂ = r + e (E[e | r, type] = 0, Var(e | r) = r(1−r)/m, and E[η | r, type, e] = 0
    for Δ̂'s own sampling error) has type coefficient  b_type + b_r·(1−λ_w)·Δμ,  λ_w = Var_w(r)/(Var_w(r)+E[r(1−r)]/m) the WITHIN-type
    reliability (NOT the total reliability) and Δμ = E[r|type 2]−E[r|type 1].  Frisch–Waugh: the within-type slope on r̂ is
    b_r·λ_w; the fitted between-type contrast must equal the actual one.  Linear-probability surrogate of the FE logistic test."""
    s = mean_r_one_minus_r / m
    lam_w = var_within / (var_within + s)
    return dict(reliability_within=lam_w, bias=b_r * (1.0 - lam_w) * delta_mu, error_variance=s)


# ----------------------------------------------------------------------------------------------------------------------- P2(a)
def endpoint_contrast_iv(delta_hat: Sequence[float], r_a: Sequence[float], r_b: Sequence[float], type_: Sequence[int],
                         cluster: Optional[Sequence] = None) -> Dict[str, object]:
    """Naive (r̂ = mean of the halves) vs repeated-measurement 2SLS estimates of [const, r, type] in the endpoint-contrast regression.
    ``r_a`` is the REGRESSOR half and must not have been used to select prefixes; ``r_b`` is the instrument (selection on it is
    harmless).  Returns both coefficient vectors, HC1/CR1 SEs, t and two-sided p for the type coefficient, the classical first-stage
    F of r̂_b for r̂_a with type partialled out (its non-centrality is n·λ_h²/(1−λ_h²), see identification_strength), the total
    reliability Cov(r̂_a, r̂_b)/Var(r̄) and the within-type reliability (the λ_w of P1, from type-demeaned halves), and n.
    Just-identified 2SLS has no finite moments: with F < 10 report the median/IQR over bootstrap draws, not the point estimate."""
    y = np.asarray(delta_hat, float)
    ra, rb, t = np.asarray(r_a, float), np.asarray(r_b, float), np.asarray(type_, float)
    n = y.size
    one = np.ones(n)
    rf = (ra + rb) / 2
    bn, sen, _ = _ols(np.c_[one, rf, t], y, cluster)
    X, Z = np.c_[one, ra, t], np.c_[one, rb, t]
    bi, sei, _ = _tsls(X, Z, y, cluster)
    b1, se1, _ = _ols(Z, ra)                      # classical F (matches the non-centrality formula)
    F = float((b1[1] / se1[1]) ** 2)
    rel_total = float(np.cov(ra, rb)[0, 1] / max(1e-12, np.var(rf, ddof=1)))
    ra_w = ra - np.array([ra[t == k].mean() for k in (0, 1)])[t.astype(int)]
    rb_w = rb - np.array([rb[t == k].mean() for k in (0, 1)])[t.astype(int)]
    rf_w = (ra_w + rb_w) / 2
    rel_within = float(np.cov(ra_w, rb_w)[0, 1] / max(1e-12, np.var(rf_w, ddof=1)))
    dfree = max(1, n - 3)
    return dict(n=int(n), first_stage_F=F, reliability=rel_total, reliability_within=rel_within,
                naive=dict(beta=bn.tolist(), se=sen.tolist(), t_type=float(bn[2] / sen[2]), p_type=float(2 * stats.t.sf(abs(bn[2] / sen[2]), dfree))),
                iv=dict(beta=bi.tolist(), se=sei.tolist(), t_type=float(bi[2] / sei[2]), p_type=float(2 * stats.t.sf(abs(bi[2] / sei[2]), dfree))),
                weak_instrument=bool(F < 10.0), se_type="CR1" if cluster is not None else "HC1")


# ----------------------------------------------------------------------------------------------------------------------- P2(b)
def endpoint_contrast_poly_cs(delta_hat: Sequence[float], counts: Sequence[int], m: int, type_: Sequence[int], degree: int = 1,
                              cluster: Optional[Sequence] = None) -> Dict[str, object]:
    """Corrected-score estimate of  Δ = Σ_{k≤degree} b_k r^k + b_type·type  from the success COUNTS K_i of m i.i.d. continuations.
    U_j(K) = K^{(j)}/m^{(j)} (falling factorials) is unbiased for r^j, so every entry of x*x*ᵀ (x* = (1, r, …, r^degree, type)) and of
    x*Δ has an unbiased per-prefix estimate; β solves Σ_i (m̂_i − M̂_i β) = 0, i.e. β = (Σ M̂_i)⁻¹ Σ m̂_i, with the M-estimator
    sandwich (HC1 / CR1).  degree=1 is the known-variance errors-in-variables estimator (v_i = r̂_i(1−r̂_i)/(m−1)).  Needs 2·degree ≤ m.
    Consistent for the ORACLE polynomial regression under E[η | r, type, K] = 0; returns ok=False when the corrected moment matrix
    is not positive definite (weak identification: within-type variation of r too small for the error variance)."""
    y, K, t = np.asarray(delta_hat, float), np.asarray(counts, float), np.asarray(type_, float)
    n = y.size
    if degree < 1 or 2 * degree > m:
        raise ValueError("need 1 ≤ degree ≤ m/2")
    U = [_falling(K, j) / _falling(np.array([float(m)]), j)[0] for j in range(2 * degree + 1)]
    k = degree + 2
    M = np.zeros((n, k, k))
    mv = np.zeros((n, k))
    for a in range(degree + 1):
        for b in range(degree + 1):
            M[:, a, b] = U[a + b]
        M[:, a, k - 1] = M[:, k - 1, a] = U[a] * t
        mv[:, a] = U[a] * y
    M[:, k - 1, k - 1] = t
    mv[:, k - 1] = t * y
    A = M.sum(0)
    min_eig = float(np.linalg.eigvalsh(A).min())
    if min_eig <= 0:
        return dict(ok=False, n=int(n), degree=int(degree), min_eig=min_eig,
                    reason="corrected moment matrix not positive definite: within-type risk variation too small for the error variance")
    beta = np.linalg.solve(A, mv.sum(0))
    psi = mv - np.einsum("nij,j->ni", M, beta)
    cov = _robust_cov(np.linalg.inv(A), psi, cluster)
    se = np.sqrt(np.diag(cov))
    t_type = float(beta[-1] / se[-1])
    return dict(ok=True, n=int(n), degree=int(degree), min_eig=min_eig, beta=beta.tolist(), se=se.tolist(), t_type=t_type,
                p_type=float(2 * stats.norm.sf(abs(t_type))), se_type="CR1" if cluster is not None else "HC1")


def endpoint_contrast_eiv(delta_hat: Sequence[float], r_hat: Sequence[float], type_: Sequence[int], m: int,
                          cluster: Optional[Sequence] = None) -> Dict[str, object]:
    """Known-variance corrected-score estimator (degree 1) from the pooled r̂ = K/m; see endpoint_contrast_poly_cs."""
    rh = np.asarray(r_hat, float)
    return endpoint_contrast_poly_cs(delta_hat, np.rint(rh * m), m, type_, degree=1, cluster=cluster)


# ----------------------------------------------------------------------------------------------------------------------- P3
def identification_strength(n: int, var_within: float, mean_r_one_minus_r: float, m_half: int, F_target: float = 10.0,
                            pass_prob: float = 0.8) -> Dict[str, float]:
    """P3.  λ_h = V/(V+s), V = Var_w(r), s = E[r(1−r)]/m_half; the first-stage F of r̂_b for r̂_a (type partialled out) is
    non-central χ²₁ (large n) with NON-CENTRALITY  ncp = n·λ_h²/(1−λ_h²) = n·V²/(s(2V+s)) — the median of the sample F, not a
    guarantee: at ncp = F_target the sample F clears F_target with probability ≈ 0.5.  Returns ncp, λ_h, P(sample F ≥ F_target),
    the ncp needed to clear F_target with probability ``pass_prob``, and the n / m_half that reach it at the given (V, E[r(1−r)])."""
    s = mean_r_one_minus_r / m_half
    lam = var_within / (var_within + s)
    ncp = n * lam ** 2 / (1.0 - lam ** 2)
    p_pass = float(stats.ncx2.sf(F_target, 1, ncp))
    ncp_needed = float(brentq(lambda c: stats.ncx2.sf(F_target, 1, c) - pass_prob, 1e-9, 1e4))
    n_needed = ncp_needed * (1.0 - lam ** 2) / lam ** 2
    lam_star = np.sqrt(ncp_needed / (n + ncp_needed))                       # λ_h needed at this n
    s_max = var_within * (1.0 / lam_star - 1.0)
    return dict(F=float(ncp), noncentrality=float(ncp), reliability_half=float(lam), error_variance_half=float(s),
                pass_probability=p_pass, ncp_for_pass_prob=ncp_needed, n_for_pass_prob=float(n_needed),
                m_half_for_pass_prob=float(mean_r_one_minus_r / s_max) if s_max > 0 else float("inf"),
                n_for_F_target=float(F_target * (1.0 - lam ** 2) / lam ** 2), weak=bool(ncp < F_target))


# ----------------------------------------------------------------------------------------------------------------------- P4
def lq_ceiling(var_r: float, mean_r_one_minus_r: float, m: int, kappa: float = 1.0, b: float = 1.0) -> Dict[str, float]:
    """P4 (single-stage LINEAR-QUADRATIC idealisation only).  J(d; r) = J*(r) + (κ/2)(d − a − b·r)²; readout r̂ = r + e with
    Var(e) = E[r(1−r)]/m, λ = Var(r)/(Var(r)+Var(e)).  Regret vs the oracle d = a + b·r:  open loop (κ/2)b²Var(r);  best LINEAR closed
    loop d = a + b(μ + λ(r̂ − μ)) (κ/2)b²Var(r)(1−λ);  plug-in d = a + b·r̂ (κ/2)b²Var(e).  So a linear closed loop realises at most the
    fraction λ (= ρ²) of the oracle advantage, exactly λ at the optimum, and the plug-in controller loses to open loop iff λ < 1/2.
    For arbitrary controllers the bound is the correlation ratio η² ≥ ρ² (equal for Beta priors by conjugacy); under non-quadratic
    costs the realisable fraction is a value-of-information quantity that can be far from λ in either direction (archive §7) — do
    not use this function outside the LQ idealisation."""
    s = mean_r_one_minus_r / m
    lam = var_r / (var_r + s)
    base = 0.5 * kappa * b ** 2
    return dict(reliability=lam, open_loop_regret=base * var_r, linear_closed_loop_regret=base * var_r * (1 - lam),
                plug_in_regret=base * s, fraction_realisable=lam, plug_in_beats_open_loop=bool(lam > 0.5))


def value_of_information_fraction(cost: np.ndarray, prior_w: np.ndarray, m: int, r_grid: np.ndarray) -> Dict[str, float]:
    """Exact (grid) value of information of a binomial readout K ~ Bin(m, r) for a DISCRETE action problem: cost[i, d] is the cost
    of action d at risk r_grid[i], prior_w the prior weights.  Returns oracle, open-loop, Bayes-policy costs and the realised
    fraction of the oracle gain, with λ and η² for comparison.  This replaces the refuted "fraction ≈ λ" rule."""
    cost, w, r = np.asarray(cost, float), np.asarray(prior_w, float) / np.sum(prior_w), np.asarray(r_grid, float)
    J_or = float(np.sum(w * cost.min(1)))
    J_open = float((w[:, None] * cost).sum(0).min())
    ks = np.arange(m + 1)
    lik = stats.binom.pmf(ks[None, :], m, r[:, None])                     # [grid, K]
    post_w = w[:, None] * lik                                              # unnormalised posterior over grid for each K
    J_bayes = float(sum((post_w[:, j][:, None] * cost).sum(0).min() for j in range(m + 1)))
    var_r = float(np.sum(w * r ** 2) - np.sum(w * r) ** 2)
    lam = var_r / (var_r + float(np.sum(w * r * (1 - r))) / m)
    pk = post_w.sum(0)
    Er_k = (post_w * r[:, None]).sum(0) / np.where(pk > 0, pk, 1)
    eta2 = float(np.sum(pk * (Er_k - np.sum(w * r)) ** 2) / var_r) if var_r > 0 else float("nan")
    gain = J_open - J_or
    return dict(oracle=J_or, open_loop=J_open, bayes=J_bayes, oracle_gain=gain,
                fraction=float((J_open - J_bayes) / gain) if gain > 0 else float("nan"), reliability=lam, eta2=eta2)


# ----------------------------------------------------------------------------------------------------------------------- P5
def readout_reliability(z: Sequence[float], r_a: Sequence[float], r_b: Sequence[float], *, cluster: Optional[Sequence] = None,
                        n_boot: int = 1000, seed: int = 0) -> Dict[str, object]:
    """P5.  Disattenuated squared correlation of a readout ẑ (cross-fitted / LOQO probe prediction, logit feature, …) with TRUE
    prefix risk r:  ρ²(ẑ, r) = Cov(ẑ, r̂_a)·Cov(ẑ, r̂_b) / (Var(ẑ)·Cov(r̂_a, r̂_b)),  exact in population when the halves have
    independent errors given r and ẑ is computed without those continuations (an in-sample probe inflates it).  Naive
    Corr(ẑ, r̄)² = ρ²·λ.  Needs Cov(r̂_a, r̂_b) > 0.  Percentile bootstrap over prefixes, or over ``cluster`` (question id) when
    prefixes share questions — the iid bootstrap under-covers then (≈88–91% at nominal 95%).  With a question×script-demeaned target
    the result is a WITHIN-question ρ², not the total one."""
    z, ra, rb = (np.asarray(a, float) for a in (z, r_a, r_b))
    n = z.size
    def est(idx):
        c = np.cov(np.c_[z[idx], ra[idx], rb[idx]].T)
        return c[0, 1] * c[0, 2] / (c[0, 0] * c[1, 2]) if c[1, 2] > 0 else np.nan
    full = est(np.arange(n))
    rng = np.random.default_rng(seed)
    if cluster is None:
        boots = np.array([est(rng.integers(0, n, n)) for _ in range(n_boot)])
    else:
        cl = np.asarray(cluster)
        groups = np.unique(cl)
        members = [np.flatnonzero(cl == g) for g in groups]
        boots = np.array([est(np.concatenate([members[j] for j in rng.integers(0, groups.size, groups.size)])) for _ in range(n_boot)])
    boots = boots[np.isfinite(boots)]
    rbar = (ra + rb) / 2
    return dict(n=int(n), rho2=float(full), naive_corr2=float(np.corrcoef(z, rbar)[0, 1] ** 2),
                half_reliability=float(np.corrcoef(ra, rb)[0, 1]),
                ci95=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))] if boots.size else [float("nan")] * 2,
                n_boot_valid=int(boots.size), bootstrap="cluster" if cluster is not None else "iid")
