"""Independent exact implementation of the first-order sandwich for the degree-2
corrected-score TYPE coefficient. Written from the claim statement only.

Model: x=(1,r,r^2), t in {0,1}, K|r ~ Bin(m,r), U_j=(K)_j/(m)_j.
Score (true beta): psi_j = U_j*eta + b1*(r*eps_j - eps_{j+1}) + b2*(r^2*eps_j - eps_{j+2}), j=0,1,2 (eps_0=0)
                   psi_t = t*eta - t*(b1*eps_1 + b2*eps_2)
phi = psi_t - gamma' psi_x.
"""
from fractions import Fraction as Fr
from math import comb, factorial, sqrt
import itertools

# ---------- polynomials in r: dict power -> Fraction ----------
def padd(*ps):
    out = {}
    for p in ps:
        for k, v in p.items():
            out[k] = out.get(k, 0) + v
    return {k: v for k, v in out.items() if v != 0}

def pmul(p, q):
    out = {}
    for k1, v1 in p.items():
        for k2, v2 in q.items():
            out[k1 + k2] = out.get(k1 + k2, 0) + v1 * v2
    return {k: v for k, v in out.items() if v != 0}

def pscale(p, c):
    return {k: v * c for k, v in p.items() if v * c != 0}

def pconst(c):
    return {0: Fr(c)} if c != 0 else {}

def pmono(k, c=1):
    return {k: Fr(c)}

def pexpect(p, mom):
    """mom[k] = E[r^k]"""
    return sum(v * mom[k] for k, v in p.items())

def pdeg(p):
    return max(p.keys()) if p else -1

# ---------- falling factorial & binomial U-moments ----------
def ff(m, j):
    out = 1
    for i in range(j):
        out *= (m - i)
    return out

def J_poly(j, l, m):
    """E[U_j U_l | r] as polynomial in r."""
    out = {}
    for el in range(0, min(j, l) + 1):
        c = Fr(comb(j, el) * comb(l, el) * factorial(el) * ff(m, j + l - el), ff(m, j) * ff(m, l))
        out = padd(out, pmono(j + l - el, c))
    return out

def V_poly(j, l, m):
    return padd(J_poly(j, l, m), pmono(j + l, -1))

# ---------- Beta moments ----------
def beta_moments(a, b, kmax):
    a, b = Fr(a), Fr(b)
    mom = [Fr(1)]
    for k in range(1, kmax + 1):
        mom.append(mom[-1] * (a + k - 1) / (a + b + k - 1))
    return mom

def discrete_moments(points, kmax):
    """points: list of (r, prob)"""
    return [sum(Fr(p) * Fr(r) ** k for r, p in points) for k in range(kmax + 1)]

# ---------- overlap D and gamma ----------
def solve3(A, b):
    # Gaussian elimination with Fractions
    n = len(A)
    M = [list(map(Fr, A[i])) + [Fr(b[i])] for i in range(n)]
    for i in range(n):
        piv = next(k for k in range(i, n) if M[k][i] != 0)
        M[i], M[piv] = M[piv], M[i]
        for k in range(n):
            if k != i and M[k][i] != 0:
                f = M[k][i] / M[i][i]
                M[k] = [M[k][c] - f * M[i][c] for c in range(n + 1)]
    return [M[i][n] / M[i][i] for i in range(n)]

def overlap(mom0, mom1, w1):
    w1 = Fr(w1); w0 = 1 - w1
    Qxx = [[w0 * mom0[i + j] + w1 * mom1[i + j] for j in range(3)] for i in range(3)]
    q = [w1 * mom1[i] for i in range(3)]
    gamma = solve3(Qxx, q)
    D = w1 - sum(q[i] * gamma[i] for i in range(3))
    return Qxx, q, gamma, D

# ---------- E_t[phi^2] ----------
def Ephi2_poly(t, gamma, beta, m, sigma2_poly):
    """Polynomial in r whose E_t gives E_t[phi^2]. beta=(b1,b2); gamma=(g0,g1,g2)."""
    g0, g1, g2 = gamma
    b = {1: Fr(beta[0]), 2: Fr(beta[1])}
    rho = padd(pconst(t - g0), pmono(1, -g1), pmono(2, -g2))
    V2 = {(j, l): V_poly(j, l, m) for j in (1, 2) for l in (1, 2)}
    quad2 = {}
    gt = {1: g1, 2: g2}
    for j in (1, 2):
        for l in (1, 2):
            quad2 = padd(quad2, pscale(V2[(j, l)], gt[j] * gt[l]))
    eta_part = pmul(sigma2_poly, padd(pmul(rho, rho), quad2))
    # alpha_{b,j}, j=1..4
    def alpha(bb, j):
        out = {}
        if j == bb:
            out = padd(out, pconst(-(t - g0)))
        if j == 1:
            out = padd(out, pmono(bb, -g1))
        if j == 1 + bb:
            out = padd(out, pconst(g1))
        if j == 2:
            out = padd(out, pmono(bb, -g2))
        if j == 2 + bb:
            out = padd(out, pconst(g2))
        return out
    V4 = {(j, l): V_poly(j, l, m) for j in range(1, 5) for l in range(1, 5)}
    g_part = {}
    for bb in (1, 2):
        for d in (1, 2):
            if b[bb] == 0 or b[d] == 0:
                continue
            for j in range(1, 5):
                for l in range(1, 5):
                    term = pmul(pmul(alpha(bb, j), alpha(d, l)), V4[(j, l)])
                    g_part = padd(g_part, pscale(term, b[bb] * b[d]))
    return eta_part, g_part

def Omega(t, gamma, m):
    """2x2 PSD matrix in (b1,b2) for the g-part, polynomial entries."""
    g0, g1, g2 = gamma
    def alpha(bb, j):
        out = {}
        if j == bb: out = padd(out, pconst(-(t - g0)))
        if j == 1: out = padd(out, pmono(bb, -g1))
        if j == 1 + bb: out = padd(out, pconst(g1))
        if j == 2: out = padd(out, pmono(bb, -g2))
        if j == 2 + bb: out = padd(out, pconst(g2))
        return out
    V4 = {(j, l): V_poly(j, l, m) for j in range(1, 5) for l in range(1, 5)}
    Om = [[{} for _ in range(2)] for _ in range(2)]
    for bb in (1, 2):
        for d in (1, 2):
            for j in range(1, 5):
                for l in range(1, 5):
                    Om[bb - 1][d - 1] = padd(Om[bb - 1][d - 1], pmul(pmul(alpha(bb, j), alpha(d, l)), V4[(j, l)]))
    return Om

def sigma2_arms(beta0, beta1, beta2, ndraw=16):
    """sigma^2(r) = [2r(1-r) - g^2/2]/ndraw with g = b0 + b1 r + b2 r^2 (unclipped)."""
    g = padd(pconst(beta0), pmono(1, beta1), pmono(2, beta2))
    return pscale(padd(pmono(1, 2), pmono(2, -2), pscale(pmul(g, g), Fr(-1, 2))), Fr(1, ndraw))

def sigma2_bound(ndraw=16):
    return pscale(padd(pmono(1, 1), pmono(2, -1)), Fr(2, ndraw))  # r(1-r)/8

def first_order_var_sum(mom0, mom1, w1, gamma, D, beta, m, sigma2_poly):
    """returns Sum_t w_t E_t[phi^2] (exact Fraction) and pieces"""
    w1 = Fr(w1); w0 = 1 - w1
    tot_eta = Fr(0); tot_g = Fr(0); maxdeg = -1
    for t, mom, w in ((0, mom0, w0), (1, mom1, w1)):
        e, g = Ephi2_poly(t, gamma, beta, m, sigma2_poly)
        maxdeg = max(maxdeg, pdeg(e), pdeg(g))
        tot_eta += w * pexpect(e, mom)
        tot_g += w * pexpect(g, mom)
    return tot_eta, tot_g, maxdeg

def width(S, D, n):
    return 3.92 * sqrt(float(S) / (n * float(D) ** 2))
