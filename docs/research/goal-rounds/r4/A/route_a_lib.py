"""r4 / Route A library: first-order sandwich of the degree-2 corrected-score TYPE coefficient, overlap D(F), the
A1 PD margin, pilot U-statistic estimators and delta-method bounds.  Pure functions; generic over Fraction / float.

Notation (matches analysis/g6_iv.py and archive §4): prefix i, type t_i in {0,1}, risk r_i | t ~ F_t, K_i | r_i ~ Bin(m, r_i),
U_j(K) = (K)_j / (m)_j with E[U_j | r] = r^j, x* = (1, r, r^2, t), y_i = g(r_i) + b_type t_i + eta_i, g = b0 + b1 r + b2 r^2,
E[eta | r, t, K] = 0, Var(eta | r) = sigma2(r).  mu_t[j] = E[r^j | t], j = 0..8.  w1 = P(t = 1).
"""
from __future__ import annotations

from fractions import Fraction
from math import comb, factorial, perm
from typing import List, Optional, Sequence

import numpy as np
from scipy import linalg as sla

Z_ONE_SIDED_95 = 1.6448536269514722


# --------------------------------------------------------------------------------------------- polynomial helpers (generic)
def pmul(p, q):
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a == 0:
            continue
        for j, b in enumerate(q):
            out[i + j] += a * b
    return out


def padd(p, q):
    n = max(len(p), len(q))
    return [(p[i] if i < len(p) else 0) + (q[i] if i < len(q) else 0) for i in range(n)]


def pscale(p, c):
    return [c * a for a in p]


def pmom(p, mu):
    """E[p(r)] = sum_j p_j mu_j  (mu[0] = 1)."""
    if len(p) > len(mu):
        raise ValueError("insufficient moments: need up to order %d" % (len(p) - 1))
    return sum(c * mu[j] for j, c in enumerate(p) if c != 0)


def monomial(j, c=1):
    p = [0] * (j + 1)
    p[j] = c
    return p


# --------------------------------------------------------------------------------------------- A1 identity, per r
def J_poly(m: int, j: int, k: int, exact: bool = True) -> list:
    """Coefficients (in r) of E[U_j(K) U_k(K) | r], K ~ Bin(m, r):  sum_l C(j,l)C(k,l) l! (m)_{j+k-l} / ((m)_j (m)_k) r^{j+k-l}.
    This is the archive's A1 identity before averaging over r (binomial_factorial_joint_moment averages it)."""
    if max(j, k) > m or min(j, k) < 0:
        raise ValueError("need 0 <= j, k <= m")
    one = Fraction(1) if exact else 1.0
    p = [0 * one] * (j + k + 1)
    den = perm(m, j) * perm(m, k)
    for l in range(max(0, j + k - m), min(j, k) + 1):
        c = comb(j, l) * comb(k, l) * factorial(l) * perm(m, j + k - l)
        p[j + k - l] += Fraction(c, den) if exact else c / den
    return p


def V_poly(m: int, j: int, k: int, exact: bool = True) -> list:
    """Cov(U_j, U_k | r) = E[U_j U_k | r] - r^{j+k}  (zero when j = 0 or k = 0)."""
    if j == 0 or k == 0:
        return [0]
    if not exact:
        return list(_V_poly_float(m, j, k))
    p = J_poly(m, j, k, exact)
    p[j + k] -= 1
    return p


from functools import lru_cache


@lru_cache(maxsize=None)
def _V_poly_float(m, j, k):
    p = J_poly(m, j, k, False)
    p[j + k] -= 1
    return tuple(p)


# --------------------------------------------------------------------------------------------- small exact linear algebra
def solve_generic(A, b):
    """Gaussian elimination with partial pivoting over Fractions or floats (3x3 here)."""
    n = len(b)
    M = [list(row) + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if M[piv][c] == 0:
            raise ZeroDivisionError("singular Q_xx")
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c and M[r][c] != 0:
                f = M[r][c] / M[c][c]
                M[r] = [M[r][i] - f * M[c][i] for i in range(n + 1)]
    return [M[i][n] / M[i][i] for i in range(n)]


def inverse_generic(A):
    n = len(A)
    cols = []
    for c in range(n):
        e = [0] * n
        e[c] = 1
        cols.append(solve_generic(A, e))
    return [[cols[c][r] for c in range(n)] for r in range(n)]


# --------------------------------------------------------------------------------------------- overlap D, gamma
def design_blocks(mu0, mu1, w1):
    """Q_xx = sum_t w_t E_t[x x^T], q = E[x t] = w1 (1, mu_{1,1}, mu_{2,1}),  x = (1, r, r^2)."""
    w0 = 1 - w1
    Qxx = [[w0 * mu0[a + b] + w1 * mu1[a + b] for b in range(3)] for a in range(3)]
    q = [w1 * mu1[a] for a in range(3)]
    return Qxx, q


def overlap_D(mu0, mu1, w1):
    """D(F) = w1 - q^T Q_xx^{-1} q = min_c E[(t - c^T x)^2]: residual (partial) variance of type after (1, r, r^2).
    Returns (D, gamma) with gamma = Q_xx^{-1} q the population regression of t on x.  Needs per-type moments <= 4."""
    Qxx, q = design_blocks(mu0, mu1, w1)
    gamma = solve_generic(Qxx, q)
    D = w1 - sum(qi * gi for qi, gi in zip(q, gamma))
    return D, gamma


# --------------------------------------------------------------------------------------------- first-order sandwich
def sigma2_poly_from_g(beta, n_arm=16):
    """Var(eta | r) for eta = Ybar(+) - Ybar(-), two independent arms of n_arm draws with q_± = r ± g(r)/2 (no clipping):
    [q+(1-q+) + q-(1-q-)] / n_arm = [2 r (1 - r) - g(r)^2 / 2] / n_arm."""
    g = list(beta)
    g2 = pmul(g, g)
    base = [0, 2, -2]  # 2r - 2r^2
    p = padd(base, pscale(g2, Fraction(-1, 2) if isinstance(beta[0], Fraction) else -0.5))
    return pscale(p, Fraction(1, n_arm) if isinstance(beta[0], Fraction) else 1.0 / n_arm)


def sigma2_bound_poly(n_arm=16, exact=False):
    """Uniform-in-g bound sigma2(r) <= 2 r (1 - r) / n_arm, valid whenever q_± in [0, 1] without clipping."""
    c = Fraction(2, n_arm) if exact else 2.0 / n_arm
    return [0, c, -c]


def osc_quadratic_01(b1, b2):
    """max - min of b1 r + b2 r^2 on [0, 1]."""
    vals = [0.0, b1 + b2]
    if b2 != 0:
        rs = -b1 / (2.0 * b2)
        if 0 < rs < 1:
            vals.append(b1 * rs + b2 * rs * rs)
    return max(vals) - min(vals)


def _osc_vec(c, s):
    """osc of c r + s r^2 on [0,1] for arrays c, s."""
    v0 = np.zeros_like(c)
    v1 = c + s
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(s != 0, -c / (2.0 * s), -1.0)
    inside = (rs > 0) & (rs < 1)
    vv = np.where(inside, c * rs + s * rs * rs, 0.0)
    mx = np.maximum(np.maximum(v0, v1), np.where(inside, vv, -np.inf))
    mn = np.minimum(np.minimum(v0, v1), np.where(inside, vv, np.inf))
    return mx - mn


_THETA_GRID = np.linspace(0, np.pi, 1440, endpoint=False)
_COS, _SIN = np.cos(_THETA_GRID), np.sin(_THETA_GRID)
_OSC = _osc_vec(_COS, _SIN)


def sup_quadratic_over_bounded_g(Omega, coef_bound=None):
    """sup of beta^T Omega beta over (b1, b2) admitting b0 with |b0 + b1 r + b2 r^2| <= 1 on [0,1], i.e. osc(b1 r + b2 r^2) <= 2,
    intersected (if coef_bound = c) with the box max(|b1|, |b2|) <= c.  Both sets are compact convex symmetric, so is the
    intersection; a PSD quadratic attains its sup on its boundary, whose radius in direction theta is the min of the two radii.
    Grid of 1440 angles plus a bounded local refinement."""
    Om = np.asarray(Omega, float)
    sc = 2.0 / _OSC
    if coef_bound is not None:
        sc = np.minimum(sc, coef_bound / np.maximum(np.abs(_COS), np.abs(_SIN)))
    b1, b2 = _COS * sc, _SIN * sc
    vals = Om[0, 0] * b1 * b1 + 2 * Om[0, 1] * b1 * b2 + Om[1, 1] * b2 * b2
    i = int(np.argmax(vals))

    def val(th):
        c, s = np.cos(th), np.sin(th)
        r = 2.0 / osc_quadratic_01(c, s)
        if coef_bound is not None:
            r = min(r, coef_bound / max(abs(c), abs(s)))
        b = np.array([c * r, s * r])
        return float(b @ Om @ b), b

    from scipy.optimize import minimize_scalar
    step = np.pi / _THETA_GRID.size
    res = minimize_scalar(lambda th: -val(th)[0], bounds=(_THETA_GRID[i] - step, _THETA_GRID[i] + step), method="bounded",
                          options=dict(xatol=1e-7))
    v, b = val(res.x)
    if v < vals[i]:
        v, b = val(_THETA_GRID[i])
    return v, b


def first_order(mu0: Sequence, mu1: Sequence, w1, m: int, n: int, beta: Optional[Sequence] = None,
                sigma2: Optional[Sequence] = None, sup_g: bool = False, n_arm: int = 16, exact: bool = False,
                z: float = 1.959963984540054):
    """First-order (asymptotic) sandwich variance of the degree-2 corrected-score type coefficient and the resulting
    95% full CI width  w_1 = 2 z sqrt(E[phi^2] / (n D^2)),  phi = psi_type - gamma^T psi_x.

        E[phi^2 | r, t] = sigma2(r) [rho(r,t)^2 + gamma_(1:2)^T V2(r) gamma_(1:2)] + sum_{b,d in {1,2}} b_b b_d alpha_b^T V4(r) alpha_d
    with rho = t - gamma^T x,  V_k(r)_{jl} = Cov(U_j, U_l | r) (A1 per r),  alpha_{b,j}(r,t) as in the derivation.
    sup_g=True replaces sigma2 by the uniform bound 2 r(1-r)/n_arm and the g-term by its sup over {|g| <= 1 on [0,1]}.
    Returns dict with D, gamma, the three variance components, E[phi^2], se_1, width_1 and (if sup_g) the maximising (b1,b2).
    All moment inputs are per-type lists mu_t[0..8]; needs orders <= 8 (exactly: deg sigma2 + 4 <= 8 and 7 for the g-term)."""
    one = Fraction(1) if exact else 1.0
    w1 = one * w1
    w0 = 1 - w1
    D, gamma = overlap_D(mu0, mu1, w1)
    g0, g1, g2 = gamma
    V2 = [[V_poly(m, j, l, exact) for l in (1, 2)] for j in (1, 2)]
    V4 = [[V_poly(m, j, l, exact) for l in (1, 2, 3, 4)] for j in (1, 2, 3, 4)]
    if sup_g:
        s2 = sigma2_bound_poly(n_arm, exact)
    elif sigma2 is not None:
        s2 = list(sigma2)
    else:
        s2 = sigma2_poly_from_g(beta, n_arm)
    # gamma^T V2 gamma  (polynomial)
    gVg = [0]
    for a, ga in enumerate((g1, g2)):
        for b, gb in enumerate((g1, g2)):
            gVg = padd(gVg, pscale(V2[a][b], ga * gb))
    out_t = []
    Omega_t = []
    for t, mu, w in ((0, mu0, w0), (1, mu1, w1)):
        rho = [t - g0, -g1, -g2]                       # t - gamma^T x
        term1 = pmom(pmul(s2, padd(pmul(rho, rho), gVg)), mu)   # E_t[sigma2 (rho^2 + g'V2 g)]
        oracle = pmom(pmul(s2, pmul(rho, rho)), mu)
        # alpha_{b,j}(r,t), j = 1..4
        alpha = {}
        for b in (1, 2):
            al = [[0] for _ in range(5)]              # index 1..4
            al[b] = padd(al[b], [-(t - g0)])
            al[1] = padd(al[1], monomial(b, -g1))
            al[1 + b] = padd(al[1 + b], [g1])
            al[2] = padd(al[2], monomial(b, -g2))
            al[2 + b] = padd(al[2 + b], [g2])
            alpha[b] = al
        Om = [[0, 0], [0, 0]]
        for b in (1, 2):
            for d in (1, 2):
                acc = [0]
                for j in (1, 2, 3, 4):
                    for l in (1, 2, 3, 4):
                        acc = padd(acc, pmul(pmul(alpha[b][j], alpha[d][l]), V4[j - 1][l - 1]))
                Om[b - 1][d - 1] = pmom(acc, mu)
        Omega_t.append(Om)
        out_t.append(dict(term_eta=term1, oracle=oracle, Omega=Om))
    Omega = [[w0 * Omega_t[0][a][b] + w1 * Omega_t[1][a][b] for b in range(2)] for a in range(2)]
    term_eta = w0 * out_t[0]["term_eta"] + w1 * out_t[1]["term_eta"]
    oracle = w0 * out_t[0]["oracle"] + w1 * out_t[1]["oracle"]
    if sup_g:
        term_g, bstar = sup_quadratic_over_bounded_g(Omega)
        term_g = term_g * one
    else:
        b1, b2 = beta[1], beta[2]
        term_g = b1 * b1 * Omega[0][0] + 2 * b1 * b2 * Omega[0][1] + b2 * b2 * Omega[1][1]
        bstar = (b1, b2)
    Ephi2 = term_eta + term_g
    var1 = Ephi2 / (n * D * D)
    se1 = var1 ** 0.5 if not exact else None
    return dict(D=D, gamma=gamma, term_eta=term_eta, term_eta_oracle=oracle, term_g=term_g, Omega=Omega, Ephi2=Ephi2,
                var1=var1, se1=se1, width1=(2 * z * se1) if se1 is not None else None,
                width_oracle=(2 * z * (oracle / (n * D * D)) ** 0.5) if not exact else None, beta_star=bstar)


# --------------------------------------------------------------------------------------------- A1 PD margin (moments <= 4)
def pd_margin(mu0, mu1, w1, m, n0, n1):
    """E[S_w(m)] = sum_t w_t [H_t - C_t(m)/n_t]  (A1, Schur complement after eliminating the two class columns),
    Nbar(m) = sum_t w_t E_t[Cov((U_1,U_2) | r)] (mean measurement-noise covariance, 1 <= a,b <= 2).
    kappa(m) = smallest generalised eigenvalue of (E[S_w], Nbar): signal of the within-type (r, r^2) covariance in its weakest
    direction relative to the measurement noise there.  Dimensionless, moments <= 4.  DIAGNOSTIC: not a non-PD bound (CE-B1)."""
    w0 = 1 - w1
    ES = np.zeros((2, 2))
    Nb = np.zeros((2, 2))
    Hw = np.zeros((2, 2))
    for mu, w, nt in ((mu0, w0, n0), (mu1, w1, n1)):
        mu = [float(x) for x in mu]
        for a in (1, 2):
            for b in (1, 2):
                Jab = float(pmom(J_poly(m, a, b, exact=False), mu))
                H = mu[a + b] - mu[a] * mu[b]
                C = Jab - mu[a] * mu[b]
                ES[a - 1, b - 1] += w * (H - C / nt)
                Nb[a - 1, b - 1] += w * (Jab - mu[a + b])
                Hw[a - 1, b - 1] += w * H
    try:
        ev = sla.eigh(ES, Nb, eigvals_only=True)
        kappa = float(ev[0])
    except Exception:
        kappa = float("nan")
    return dict(ES=ES, Nbar=Nb, Hw=Hw, kappa=kappa, lmin_ES=float(np.linalg.eigvalsh(ES)[0]), lmin_Hw=float(np.linalg.eigvalsh(Hw)[0]))


# --------------------------------------------------------------------------------------------- pilot estimators
def U_matrix(K, m, jmax=8):
    """n x jmax matrix of U_j(K_i), j = 1..jmax (unbiased for r^j)."""
    K = np.asarray(K, float)
    out = np.ones((K.size, jmax))
    cur = np.ones(K.size)
    for j in range(1, jmax + 1):
        cur = cur * (K - (j - 1)) / (m - (j - 1))
        out[:, j - 1] = cur
    return out


def pilot_theta(K, t, m, cluster=None, jmax=8):
    """Per-type moment estimates theta_t = mean_i U_{1..jmax}(K_i) (unbiased) and their covariance: iid (sample covariance / n_t)
    and question-cluster robust (sum over clusters of within-cluster sums, G/(G-1) factor).  Returns theta (2*jmax,), Sigma_iid, Sigma_cl."""
    K = np.asarray(K); t = np.asarray(t)
    th, Si, Sc = [], [], []
    for k in (0, 1):
        idx = np.flatnonzero(t == k)
        Uk = U_matrix(K[idx], m, jmax)
        nt = Uk.shape[0]
        mean = Uk.mean(0)
        th.append(mean)
        Si.append(np.cov(Uk.T, ddof=1) / nt)
        if cluster is None:
            Sc.append(Si[-1])
        else:
            cl = np.asarray(cluster)[idx]
            groups = np.unique(cl)
            G = groups.size
            S = np.zeros((jmax, jmax))
            for g in groups:
                s = (Uk[cl == g] - mean).sum(0)
                S += np.outer(s, s)
            Sc.append(S / nt ** 2 * G / max(1, G - 1))
    theta = np.concatenate(th)
    return theta, sla.block_diag(*Si), sla.block_diag(*Sc)


def theta_to_mu(theta, jmax=8):
    mu0 = [1.0] + list(theta[:jmax])
    mu1 = [1.0] + list(theta[jmax:2 * jmax])
    return mu0, mu1


def widths_from_components(term_eta, Omega, D, n, beta=None, coef_bounds=(None, 2.0), z=1.959963984540054):
    """Given the eta-term (with the uniform sigma2 bound) and Omega, the first-order widths for: the full class |g| <= 1
    (coef_bound None), coefficient-bounded classes, and (if beta given) the specific g."""
    out = []
    for c in coef_bounds:
        tg, _ = sup_quadratic_over_bounded_g(Omega, coef_bound=c)
        out.append(2 * z * ((term_eta + tg) / (n * D * D)) ** 0.5)
    if beta is not None:
        b1, b2 = beta[1], beta[2]
        tg = b1 * b1 * Omega[0][0] + 2 * b1 * b2 * Omega[0][1] + b2 * b2 * Omega[1][1]
        out.append(2 * z * ((term_eta + tg) / (n * D * D)) ** 0.5)
    return out


def functional_names(targets, coef_bounds=(None, 2.0), with_beta=False):
    names = ["D"]
    for m in targets:
        for c in coef_bounds:
            names.append("w1sup_m%d_c%s" % (m, "inf" if c is None else str(c)))
        if with_beta:
            names.append("w1_g_m%d" % m)
    for m in targets:
        names.append("kappa_m%d" % m)
    return names


def certificate_functionals(theta, w1, n, n0, n1, targets=(32, 128), jmax=8, n_arm=16, coef_bounds=(None, 2.0), beta=None):
    """f(theta) = [D, widths(m) for m in targets (per class, and at beta if given), kappa(m) for m in targets]."""
    mu0, mu1 = theta_to_mu(theta, jmax)
    nw = len(coef_bounds) + (1 if beta is not None else 0)
    try:
        D, _ = overlap_D(mu0, mu1, w1)
    except ZeroDivisionError:
        return np.full(1 + (nw + 1) * len(targets), np.nan)
    vals = [D]
    for m in targets:
        try:
            fo = first_order(mu0, mu1, w1, m, n, sup_g=True, n_arm=n_arm)
            # term_eta uses the uniform sigma2 bound 2r(1-r)/n_arm; the specific-g width below therefore also uses that bound
            if D > 0:
                vals.extend(widths_from_components(fo["term_eta"], fo["Omega"], D, n, beta=beta, coef_bounds=coef_bounds))
            else:
                vals.extend([np.nan] * nw)
        except Exception:
            vals.extend([np.nan] * nw)
    for m in targets:
        vals.append(pd_margin(mu0, mu1, w1, m, n0, n1)["kappa"])
    return np.array(vals, float)


def delta_bounds(theta, Sigma, w1, n, n0, n1, targets=(32, 128), jmax=8, n_arm=16, z=Z_ONE_SIDED_95, rel_step=1e-6,
                 coef_bounds=(None, 2.0), beta=None):
    """Delta-method one-sided bounds: f(theta_hat) -/+ z * sqrt(grad' Sigma grad), gradient by central differences.
    Returns dict(point, sd, lcb, ucb, names)."""
    kw = dict(targets=targets, jmax=jmax, n_arm=n_arm, coef_bounds=coef_bounds, beta=beta)
    f0 = certificate_functionals(theta, w1, n, n0, n1, **kw)
    p = theta.size
    Jm = np.zeros((f0.size, p))
    for j in range(p):
        h = rel_step * max(abs(theta[j]), 1e-6)
        tp = theta.copy(); tp[j] += h
        tm = theta.copy(); tm[j] -= h
        Jm[:, j] = (certificate_functionals(tp, w1, n, n0, n1, **kw) - certificate_functionals(tm, w1, n, n0, n1, **kw)) / (2 * h)
    var = np.einsum("ij,jk,ik->i", Jm, Sigma, Jm)
    sd = np.sqrt(np.clip(var, 0, None))
    names = functional_names(targets, coef_bounds, beta is not None)
    return dict(point=f0, sd=sd, lcb=f0 - z * sd, ucb=f0 + z * sd, names=names, jac=Jm)


# --------------------------------------------------------------------------------------------- exact Beta moments
def beta_moments(a, b, jmax=8, exact=False):
    """E[r^j] for r ~ Beta(a, b): prod_{i<j} (a+i)/(a+b+i)."""
    if exact:
        a, b = Fraction(a), Fraction(b)
        mu = [Fraction(1)]
    else:
        mu = [1.0]
    for j in range(1, jmax + 1):
        mu.append(mu[-1] * (a + j - 1) / (a + b + j - 1))
    return mu
