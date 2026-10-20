"""Independent closed form for first-order var of corrected-score type coefficient (degree 2)."""
from fractions import Fraction as Fr
from math import comb, factorial, perm
import numpy as np

Z2 = Fr(391992797, 100000000)  # 2*z_0.975 ~ 3.91992797

# polynomials in r: list of Fractions, index = power
def padd(a, b):
    n = max(len(a), len(b)); return [(a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0) for i in range(n)]
def pmul(a, b):
    out = [Fr(0)] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x == 0: continue
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out
def psc(a, c): return [c * x for x in a]
def mono(k, c=1): return [Fr(0)] * k + [Fr(c)]
def pexp(p, mom): return sum((c * mom[i] for i, c in enumerate(p)), Fr(0))

def J(j, l, m):
    # E[U_j U_l | r] polynomial in r, from scratch via factorial-moment algebra
    out = [Fr(0)]
    for ell in range(0, min(j, l) + 1):
        c = Fr(comb(j, ell) * comb(l, ell) * factorial(ell) * perm(m, j + l - ell), perm(m, j) * perm(m, l))
        out = padd(out, mono(j + l - ell, c))
    return out
def V(j, l, m):
    return padd(J(j, l, m), mono(j + l, -1))

def beta_moms(a, b, K=9):
    a, b = Fr(a), Fr(b); mom = [Fr(1)]
    for k in range(1, K + 1): mom.append(mom[-1] * (a + k - 1) / (a + b + k - 1))
    return mom

def solve3(Mx, v):
    M = [list(r) + [v[i]] for i, r in enumerate(Mx)]
    n = 3
    for c in range(n):
        p = next(r for r in range(c, n) if M[r][c] != 0); M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c and M[r][c] != 0:
                f = M[r][c] / M[c][c]; M[r] = [M[r][k] - f * M[c][k] for k in range(n + 1)]
    return [M[i][n] / M[i][i] for i in range(n)]

def setup(moms, w):
    # moms[t] = moments of r in type t; w[t] weights
    Qxx = [[sum(w[t] * moms[t][i + j] for t in (0, 1)) for j in range(3)] for i in range(3)]
    q = [w[1] * moms[1][i] for i in range(3)]
    g = solve3(Qxx, q)
    D = w[1] - sum(q[i] * g[i] for i in range(3))
    return g, D

def Ephi2_parts(moms, w, m, sig2, gam):
    """returns T_eta (with sig2 polynomial) and Omega 2x2 (b,d in {1,2})."""
    g0, g1, g2 = gam
    Teta = Fr(0); Om = [[Fr(0)] * 2 for _ in range(2)]
    V2 = [[V(j, l, m) for l in (1, 2)] for j in (1, 2)]
    V4 = {(j, l): V(j, l, m) for j in range(1, 5) for l in range(1, 5)}
    for t in (0, 1):
        rho = [Fr(t) - g0, -g1, -g2]
        br = pmul(rho, rho)
        gt = [g1, g2]
        for a in range(2):
            for b in range(2):
                br = padd(br, psc(V2[a][b], gt[a] * gt[b]))
        Teta += w[t] * pexp(pmul(sig2, br), moms[t])
        # alpha_b(r,t) polynomial coefficients for j=1..4
        def alpha(bb):
            al = {j: [Fr(0)] for j in range(1, 5)}
            al[bb] = padd(al[bb], [-(Fr(t) - g0)])
            al[1] = padd(al[1], mono(bb, -g1))
            al[1 + bb] = padd(al[1 + bb], [g1])
            al[2] = padd(al[2], mono(bb, -g2))
            al[2 + bb] = padd(al[2 + bb], [g2])
            return al
        A = {1: alpha(1), 2: alpha(2)}
        for b in (1, 2):
            for d in (1, 2):
                p = [Fr(0)]
                for j in range(1, 5):
                    for l in range(1, 5):
                        p = padd(p, pmul(pmul(A[b][j], A[d][l]), V4[(j, l)]))
                Om[b - 1][d - 1] += w[t] * pexp(p, moms[t])
    return Teta, Om

def sig2_arms(beta, narm=16):
    b0, b1, b2 = [Fr(x) for x in beta]
    g = [b0, b1, b2]
    gg = pmul(g, g)
    return psc(padd([0, 2, -2], psc(gg, Fr(-1, 2))), Fr(1, narm))

def var1_total(moms, w, m, beta, sig2):
    gam, D = setup(moms, w)
    Te, Om = Ephi2_parts(moms, w, m, sig2, gam)
    b = [Fr(beta[1]), Fr(beta[2])]
    gt = sum(b[i] * Om[i][j] * b[j] for i in range(2) for j in range(2))
    return (Te + gt) / D ** 2, D, Te, Om

def W1(moms, w, m, beta, sig2, n):
    v, D, Te, Om = var1_total(moms, w, m, beta, sig2)
    return float(Z2) * float(v / n) ** 0.5, D
