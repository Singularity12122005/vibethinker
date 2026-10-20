"""Blind exact re-implementation: projection formula, U-shares, kappa (F32 CS cap), G32 CS cap. Under A0' (no clipping)."""
import sympy as sp
from fractions import Fraction as Fr
from math import comb
import sys

r = sp.symbols('r')
M, P = 128, 32
Q = M - P

def Utilde(j, k):
    return sp.Rational(1, comb(M, j)) * sum(comb(k, l) * comb(Q, j - l) * r ** (j - l) for l in range(0, j + 1))

# check projection value
val = Utilde(2, 5).subs(r, sp.Rational(1, 5))
print("Utilde_2(5,0.2) =", sp.nsimplify(val), float(val))

def falling(x, j):
    out = 1
    for i in range(j):
        out *= (x - i)
    return out

# E[U_j U_k | r] for K~Bin(128,r): exact identity
from math import factorial, perm
def EUU(j, k, m=M):
    den = perm(m, j) * perm(m, k)
    return sp.expand(sum(sp.Rational(comb(j, l) * comb(k, l) * factorial(l) * perm(m, j + k - l), den) * r ** (j + k - l)
                         for l in range(max(0, j + k - m), min(j, k) + 1)))

# E[Ut_j Ut_l | r] via sum over K32
pmf = [sp.binomial(P, kk) * r ** kk * (1 - r) ** (P - kk) for kk in range(P + 1)]
Ut = {(j, kk): sp.expand(Utilde(j, kk)) for j in range(5) for kk in range(P + 1)}
_cache = {}
def EUtUt(j, l):
    key = (min(j, l), max(j, l))
    if key not in _cache:
        _cache[key] = sp.expand(sum(pmf[kk] * Ut[(j, kk)] * Ut[(l, kk)] for kk in range(P + 1)))
    return _cache[key]

def beta_moments(a, b, n):
    mom = [sp.Integer(1)]
    for q in range(1, n + 1):
        mom.append(mom[-1] * (a + q - 1) / (a + b + q - 1))
    return mom

def Epoly(poly, mom):
    p = sp.Poly(sp.expand(poly), r)
    return sum(c * mom[e[0]] for e, c in zip(p.monoms(), p.coeffs()))

WORLDS = {
    'narrow': ((sp.Integer(20), sp.Integer(80)), (sp.Integer(25), sp.Integer(75))),
    'halfvar': ((sp.Rational(81, 2), sp.Integer(162)), (sp.Rational(253, 5), sp.Rational(759, 5))),
    'wide': ((sp.Integer(2), sp.Integer(8)), (sp.Rational(5, 2), sp.Rational(15, 2))),
}
GS = {
    'lin': [sp.Rational(18, 100), sp.Rational(-8, 10), 0],
    'quad': [sp.Rational(26, 100), sp.Rational(-16, 10), 2],
    'cheb': [sp.Rational(1, 2), -4, 4],
}

for wname, ab in WORLDS.items():
    moms = [beta_moments(a, b, 80) for (a, b) in ab]
    E = lambda poly: sum(Epoly(poly, mm) for mm in moms) / 2   # equal type weights
    # U shares
    num1 = E(EUtUt(1, 1) - r ** 2); den1 = E(EUU(1, 1) - r ** 2)
    num2 = E(EUtUt(2, 2) - r ** 4); den2 = E(EUU(2, 2) - r ** 4)
    s2 = sp.nsimplify(num2 / den2)
    print(wname, "share U1 =", sp.nsimplify(num1 / den1), " share U2 =", s2, float(s2))
    sys.stdout.flush()
    for gname, c in GS.items():
        g = c[0] + c[1] * r + c[2] * r ** 2
        # population A = E[x x'] with x=(1,r,r^2,t), t in {0,1} w.p. 1/2; type 1 = second Beta
        A = sp.zeros(4, 4)
        for ti, mm in enumerate(moms):
            x = [1, r, r ** 2, ti]
            for i in range(4):
                for jj in range(4):
                    A[i, jj] += Epoly(sp.expand(x[i] * x[jj]), mm) / 2
        w = A.inv() * sp.Matrix([0, 0, 0, 1])
        # w'd = sum_j L_j(r,t) U_j
        def Lcoef(ti):
            L = [sp.Integer(0)] * 5
            for a in range(3):
                L[a] += w[a] * g
                for b in range(3):
                    L[a + b] -= w[a] * c[b]
            if ti == 1:
                L[0] += w[3] * g
                for b in range(3):
                    L[b] -= w[3] * c[b]
            return [sp.expand(x) for x in L]
        varpsi = 0; varphi = 0; varbar = 0; meanchk = 0
        for ti, mm in enumerate(moms):
            L = Lcoef(ti)
            meanchk += sp.simplify(sum(L[j] * r ** j for j in range(5)))
            Ed2 = sum(L[j] * L[k] * EUU(j, k) for j in range(5) for k in range(5))
            Ephi2 = sum(L[j] * L[k] * EUtUt(j, k) for j in range(5) for k in range(5))
            veta = (2 * r - 2 * r ** 2 - g ** 2 / 2) / 16
            u = [w[0], w[1], w[2]]
            Eeta = veta * (w[0] ** 2 + 2 * w[0] * w[1] * r + 2 * w[0] * w[2] * r ** 2 + 2 * w[0] * w[3] * ti
                           + w[1] ** 2 * EUU(1, 1) + 2 * w[1] * w[2] * EUU(1, 2) + 2 * w[1] * w[3] * ti * r
                           + w[2] ** 2 * EUU(2, 2) + 2 * w[2] * w[3] * ti * r ** 2 + w[3] ** 2 * ti)
            varpsi += (Epoly(Ed2, mm) + Epoly(Eeta, mm)) / 2
            varphi += Epoly(Ephi2, mm) / 2
            # G32: E[w'phi | t,k] under posterior Beta(a+k, b+32-k)
            a0, b0 = ab[ti]
            for kk in range(P + 1):
                f = sp.expand(sum(L[j] * Ut[(j, kk)] for j in range(5)))
                pm = beta_moments(a0 + kk, b0 + P - kk, 12)
                cond = Epoly(f, pm)
                # P(k|t) beta-binomial
                pk = sp.binomial(P, kk) * sp.beta(a0 + kk, b0 + P - kk) / sp.beta(a0, b0)
                pk = sp.gammasimp(pk) if False else pk
                varbar += sp.N(pk, 40) * sp.N(cond, 40) ** 2 / 2
        kappa = sp.sqrt(varphi / varpsi)
        kg = sp.sqrt(varbar / varpsi)
        print(f"  {wname} {gname}: mean-check {meanchk}  kappa_F32 = {float(kappa):.5f}  G32 cap = {float(kg):.5f}  0.798*G32={float(kg)*0.7979:.4f}")
        sys.stdout.flush()
