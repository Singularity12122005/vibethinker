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

识别强度：独立两半的组内相关为 λ_h；n·λ_h²/(1−λ_h²) 仅作同方差大样本设计近似，
不能保证本模块实际返回的 HC1 第一阶段统计量的分布或中位数。校正矩阵的非正定概率还取决于高阶风险结构。
标准误默认 HC1；给定 cluster（题目标识）时，终点回归使用 CR1。
Selection: prefixes must not be selected on the half used as REGRESSOR (selection on the instrument half is harmless).
"""
from __future__ import annotations

from fractions import Fraction
from math import comb, factorial, perm
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


PD_RTOL = 1e-9   # relative eigenvalue tolerance of the corrected moment matrix (see endpoint_contrast_poly_cs)


def _falling(K: np.ndarray, j: int) -> np.ndarray:
    out = np.ones_like(K, dtype=float)
    for i in range(j):
        out = out * (K - i)
    return out


def binomial_factorial_joint_moment(risk_moments: Sequence[float | Fraction], m: int, j: int, k: int) -> float | Fraction:
    """研究档案 r3/A1：精确恒等式 E[U_j(K)U_k(K)]，其中 K|r~Bin(m,r)、U_j=(K)_j/(m)_j。

    risk_moments[q] 为 E[r**q]，需要至 min(m,j+k) 阶。传入有理数时保留精确算术；
    浮点输入仅作该有限和的浮点求值。交叠项保留同一计数所生各阶矩的相关性。
    这不是非正定概率近似，也不提供样本量或续写预算保证。
    """
    if m < 1 or min(j, k) < 0 or max(j, k) > m:
        raise ValueError("require m >= 1 and 0 <= j, k <= m")
    if len(risk_moments) <= min(m, j + k):
        raise ValueError("insufficient risk moments")
    denominator = perm(m, j) * perm(m, k)
    return sum((Fraction(comb(j, ell) * comb(k, ell) * factorial(ell) * perm(m, j + k - ell), denominator)
                * risk_moments[j + k - ell]
                for ell in range(max(0, j + k - m), min(j, k) + 1)), Fraction(0))


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
    harmless).  Returns both coefficient vectors, HC1/CR1 SEs, t and two-sided p for the type coefficient, the HC1 first-stage
    squared t statistic of r̂_b for r̂_a with type partialled out (identification_strength gives a homoskedastic design approximation), the total
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
    b1, se1, _ = _ols(Z, ra)                      # HC1 标准误；非中心度公式只是同方差设计近似
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
def corrected_moment_matrix(counts: Sequence[int], m: int, type_: Sequence[int], degree: int, pd_rtol: float = PD_RTOL) -> Dict[str, object]:
    """Corrected moment matrix A = Σ_i M̂_i of the degree-p corrected-score estimator and its positive-definiteness decision, from
    the success counts, the types, the common number m of continuations and the degree ONLY.  The outcomes are deliberately not an
    argument (archive r4, B2 by construction): the PD decision of ``endpoint_contrast_poly_cs`` is this function's ``pd_ok``, so any
    pre-registered rule on it (e.g. escalating m) can be evaluated from the α=0 counts before a steered arm is run.
    Entries: A_ab = Σ U_{a+b}(K_i) (0 ≤ a, b ≤ p), A_{a,p+1} = Σ U_a(K_i) t_i, A_{p+1,p+1} = Σ t_i, with U_j(K) = K^{(j)}/m^{(j)};
    t must be coded 0/1.  pd_ok ⇔ λ_min(A) > pd_rtol·max(1, |λ_max(A)|) (pd_rtol defaults to the import-time value of PD_RTOL).
    counts and type_ are copied on entry.  Raises ValueError unless counts and type_ are one-dimensional of equal length, m is
    an integer ≥ 2 and 1 ≤ degree ≤ m/2."""
    K, t = np.array(counts, dtype=float, copy=True), np.array(type_, dtype=float, copy=True)
    if K.ndim != 1 or t.shape != K.shape:
        raise ValueError("counts and type_ must be one-dimensional of equal length")
    if int(m) != m or m < 2:
        raise ValueError("m must be an integer ≥ 2")
    if degree < 1 or 2 * degree > m:
        raise ValueError("need 1 ≤ degree ≤ m/2")
    n = K.size
    U = [_falling(K, j) / _falling(np.array([float(m)]), j)[0] for j in range(2 * degree + 1)]
    k = degree + 2
    M = np.zeros((n, k, k))
    for a in range(degree + 1):
        for b in range(degree + 1):
            M[:, a, b] = U[a + b]
        M[:, a, k - 1] = M[:, k - 1, a] = U[a] * t
    M[:, k - 1, k - 1] = t
    A = M.sum(0)
    eig = np.linalg.eigvalsh(A)
    min_eig, max_eig = float(eig[0]), float(eig[-1])
    # relative tolerance (round 14): an exactly singular state (e.g. m=4, p=2, class counts (4,4)/(0,4): the r and r^2 columns
    # coincide) can show a tiny positive floating-point minimum eigenvalue and then fail in the solve (archive r3 实施限制)
    pd_ok = bool(min_eig > pd_rtol * max(1.0, abs(max_eig)))
    return dict(A=A, M=M, U=U, t=t, min_eig=min_eig, max_eig=max_eig, pd_ok=pd_ok, n=int(n), k=k)


def endpoint_contrast_poly_cs(delta_hat: Sequence[float], counts: Sequence[int], m: int, type_: Sequence[int], degree: int = 1,
                              cluster: Optional[Sequence] = None) -> Dict[str, object]:
    """Corrected-score estimate of  Δ = Σ_{k≤degree} b_k r^k + b_type·type  from the success COUNTS K_i of m i.i.d. continuations.
    U_j(K) = K^{(j)}/m^{(j)} (falling factorials) is unbiased for r^j, so every entry of x*x*ᵀ (x* = (1, r, …, r^degree, type)) and of
    x*Δ has an unbiased per-prefix estimate; β solves Σ_i (m̂_i − M̂_i β) = 0, i.e. β = (Σ M̂_i)⁻¹ Σ m̂_i, with the M-estimator
    sandwich (HC1 / CR1).  degree=1 is the known-variance errors-in-variables estimator (v_i = r̂_i(1−r̂_i)/(m−1)).  Needs 2·degree ≤ m.
    Consistent for the ORACLE polynomial regression under E[η | r, type, K] = 0; returns ok=False when the corrected moment matrix
    is not positive definite.  Its failure probability cannot be diagnosed from low-order within-type risk variance alone."""
    # the PD decision is taken FIRST, from private copies of (counts, type_) with m and degree (archive r4, B2 by construction);
    # only then is delta_hat converted and shape-checked, and the outcomes and the cluster vector are first used after that
    cm = corrected_moment_matrix(counts, m, type_, degree)
    n, k, U, M, A, min_eig = cm["n"], cm["k"], cm["U"], cm["M"], cm["A"], cm["min_eig"]
    y = np.asarray(delta_hat, float)
    if y.ndim != 1 or y.shape != (n,):
        raise ValueError("delta_hat, counts and type_ must be one-dimensional of equal length")
    if not cm["pd_ok"]:
        return dict(ok=False, n=int(n), degree=int(degree), min_eig=min_eig,
                    reason="corrected moment matrix not positive definite; low-order risk variance alone does not diagnose the cause")
    t = cm["t"]
    mv = np.zeros((n, k))
    for a in range(degree + 1):
        mv[:, a] = U[a] * y
    mv[:, k - 1] = t * y
    try:
        beta = np.linalg.solve(A, mv.sum(0))
    except np.linalg.LinAlgError:
        return dict(ok=False, n=int(n), degree=int(degree), min_eig=min_eig, reason="corrected moment matrix numerically singular")
    psi = mv - np.einsum("nij,j->ni", M, beta)
    cov = _robust_cov(np.linalg.inv(A), psi, cluster)
    se = np.sqrt(np.clip(np.diag(cov), 0.0, None))          # saturated designs (n = k) give a zero / rounding-negative covariance
    t_type = float(beta[-1] / se[-1]) if se[-1] > 0 else float("nan")
    return dict(ok=True, n=int(n), degree=int(degree), min_eig=min_eig, beta=beta.tolist(), se=se.tolist(), t_type=t_type,
                p_type=float(2 * stats.norm.sf(abs(t_type))) if np.isfinite(t_type) else float("nan"), se_type="CR1" if cluster is not None else "HC1")


def endpoint_contrast_eiv(delta_hat: Sequence[float], r_hat: Sequence[float], type_: Sequence[int], m: int,
                          cluster: Optional[Sequence] = None) -> Dict[str, object]:
    """Known-variance corrected-score estimator (degree 1) from the pooled r̂ = K/m; see endpoint_contrast_poly_cs."""
    rh = np.asarray(r_hat, float)
    return endpoint_contrast_poly_cs(delta_hat, np.rint(rh * m), m, type_, degree=1, cluster=cluster)


# ----------------------------------------------------------------------------------------------------------------------- P3
def identification_strength(n: int, var_within: float, mean_r_one_minus_r: float, m_half: int, F_target: float = 10.0,
                            pass_prob: float = 0.8) -> Dict[str, float]:
    """P3 的同方差大样本设计近似：λ_h=V/(V+s)，s=E[r(1−r)]/m_half；以非中心 χ²₁
    及参数 ncp=n·λ_h²/(1−λ_h²) 估算通过概率和预算。该参数不是一般样本 F 的精确中位数，
    也不是 endpoint_contrast_iv 实际返回的 HC1 统计量的分布保证。ncp=F_target 时，
    近似模型内的通过概率约为一半。保留 F 返回键以兼容旧调用；它存的是设计非中心度。
    """
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


def corrected_schur_mean(m: int, p: int, risk_moments: Sequence, n_t: int) -> list:
    """研究档案 r3/A1（本会话补充）：单类 n_t 个独立前缀，消去类指示列后校正矩阵舒尔补的期望
    E[S_ab] = μ_{a+b} − μ_a μ_b − C_ab / n_t,  C_ab = E[U_a U_b] − μ_a μ_b  (1 ≤ a, b ≤ p)，
    −C/n_t 为类均值外积带来的负半定偏移；两类时按 w_t = n_t/n 加权求和。传入有理数矩时精确。不提供非正定概率。"""
    S = []
    for a in range(1, p + 1):
        row = []
        for b in range(1, p + 1):
            C_ab = binomial_factorial_joint_moment(risk_moments, m, a, b) - risk_moments[a] * risk_moments[b]
            row.append(risk_moments[a + b] - risk_moments[a] * risk_moments[b] - C_ab / n_t)
        S.append(row)
    return S
