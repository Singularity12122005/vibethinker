"""Independent exact computation of pilot shares, kappa, ME share (blind replication of C1, Prop. 2)."""
from fractions import Fraction as F
from math import comb, perm, factorial
import sys

def padd(p, q, c=1):
    out = dict(p)
    for k, v in q.items():
        out[k] = out.get(k, 0) + c * v
    return {k: v for k, v in out.items() if v != 0}

def pmul(p, q):
    out = {}
    for a, x in p.items():
        for b, y in q.items():
            out[a + b] = out.get(a + b, 0) + x * y
    return {k: v for k, v in out.items() if v != 0}

def pscale(p, c):
    return {k: v * c for k, v in p.items()}

def ff(n, j):  # falling factorial
    out = 1
    for i in range(j):
        out *= (n - i)
    return out

def Ejoint_ff(m, j, k):
    """E[(K)_j (K)_k | r] for K~Bin(m,r), polynomial in r."""
    p = {}
    for l in range(0, min(j, k) + 1):
        if j + k - l > m:
            continue
        p = padd(p, {j + k - l: F(comb(j, l) * comb(k, l) * factorial(l) * ff(m, j + k - l))})
    return p

M = 128; MP = 32; MR = 96

def EUU(j, k):
    return pscale(Ejoint_ff(M, j, k), F(1, ff(M, j) * ff(M, k)))

def EUtUt(j, k):
    """E[Ut_j Ut_k | r], Ut_j = E[U_j(K32+K96) | K32, r] = sum_l C(j,l)(K32)_l (96)_{j-l} r^{j-l} / (128)_j"""
    p = {}
    for l in range(j + 1):
        for l2 in range(k + 1):
            c = F(comb(j, l) * comb(k, l2) * ff(MR, j - l) * ff(MR, k - l2), ff(M, j) * ff(M, k))
            p = padd(p, pmul({j - l + k - l2: c}, Ejoint_ff(MP, l, l2)))
    return p

def beta_moments(a, b, n):
    mom = [F(1)]
    for q in range(n):
        mom.append(mom[-1] * (a + q) / (a + b + q))
    return mom

def integ(p, mom):
    return sum(v * mom[k] for k, v in p.items())

WORLDS = {
    'narrow': [(F(20), F(80)), (F(25), F(75))],
    'half': [(F(81, 2), F(162)), (F(253, 5), F(759, 5))],
}
if len(sys.argv) > 1:
    pass
GS = {'lin': [F(9, 50), F(-4, 5), F(0)], 'quad': [F(13, 50), F(-8, 5), F(2)], 'cheb': [F(1, 2), F(-4), F(4)]}

# pilot share of ME variance of U_1, U_2
def share(world, j, pertype=False):
    num = den = 0
    res = []
    for (a, b) in WORLDS[world]:
        mom = beta_moments(a, b, 60)
        # Var(Ut_j|r) = E[Ut_j^2|r] - r^{2j}; Var(U_j|r) = E[U_j^2|r]-r^{2j}
        vt = integ(padd(EUtUt(j, j), {2 * j: F(1)}, -1), mom)
        vu = integ(padd(EUU(j, j), {2 * j: F(1)}, -1), mom)
        res.append(vt / vu)
        num += vt; den += vu
    return num / den, res

for w in WORLDS:
    for j in (1, 2):
        s, per = share(w, j)
        print(w, 'U%d' % j, 'pooled', s, float(s), 'per type', [float(x) for x in per])

# kappa
import numpy as np
def mats(world, g):
    beta = g  # population coefficients (b0,b1,b2), beta_t = 0
    k = 4
    A = [[F(0)] * k for _ in range(k)]
    Sig = [[F(0)] * k for _ in range(k)]
    SME = [[F(0)] * k for _ in range(k)]
    Phi = [[F(0)] * k for _ in range(k)]
    gpoly = {i: c for i, c in enumerate(g) if c != 0}
    # Var(eta|r) = (2r - 2r^2 - g^2/2)/16
    veta = pscale(padd(padd({1: F(2)}, {2: F(-2)}), pscale(pmul(gpoly, gpoly), F(-1, 2))), F(1, 16))
    for tval, (a, b) in zip((0, 1), WORLDS[world]):
        mom = beta_moments(a, b, 80)
        # representation: each component is sum_j coef_j(r) * U_j  (+ for type comp. times t)
        # d_a = g U_a - sum_b beta_b U_{a+b}; d_t = t (g U_0 - sum_b beta_b U_b)
        comps = []
        for aa in range(3):
            c = {}
            c[aa] = padd(c.get(aa, {}), gpoly)
            for bb in range(3):
                if beta[bb] != 0:
                    c[aa + bb] = padd(c.get(aa + bb, {}), {0: -beta[bb]})
            comps.append(c)
        ct = {}
        if tval:
            ct[0] = dict(gpoly)
            for bb in range(3):
                if beta[bb] != 0:
                    ct[bb] = padd(ct.get(bb, {}), {0: -beta[bb]})
        comps.append(ct)
        # v = (U0,U1,U2,t)
        vcomp = [{0: {0: F(1)}}, {1: {0: F(1)}}, {2: {0: F(1)}}, ({0: {0: F(1)}} if tval else {})]
        x = [{0: {0: F(1)}}, {1: {0: F(1)}}, {2: {0: F(1)}}, ({0: {0: F(1)}} if tval else {})]  # x* entries as U-combos (A = E[x x'] corrected)
        def quad(c1, c2, E):
            p = {}
            for j, pj in c1.items():
                for kk, pk in c2.items():
                    p = padd(p, pmul(pmul(pj, pk), E(j, kk)))
            return p
        for i in range(k):
            for jx in range(k):
                dd = quad(comps[i], comps[jx], EUU)
                vv = quad(vcomp[i], vcomp[jx], EUU)
                SME[i][jx] += F(1, 2) * integ(dd, mom)
                Sig[i][jx] += F(1, 2) * (integ(dd, mom) + integ(pmul(vv, veta), mom))
                Phi[i][jx] += F(1, 2) * integ(quad(comps[i], comps[jx], EUtUt), mom)
                # A: E[x_i x_j] with true r: x = (1,r,r^2,t)
                xi = [{0: F(1)}, {1: F(1)}, {2: F(1)}, ({0: F(1)} if tval else {})]
                A[i][jx] += F(1, 2) * integ(pmul(xi[i], xi[jx]), mom)
    return A, Sig, SME, Phi

import sympy
for world in WORLDS:
    for gname, g in GS.items():
        A, Sig, SME, Phi = mats(world, g)
        Ai = sympy.Matrix(A).inv()
        w = Ai[3, :].T
        S = sympy.Matrix(Sig); Sm = sympy.Matrix(SME); P = sympy.Matrix(Phi)
        ws = (w.T * S * w)[0]; wm = (w.T * Sm * w)[0]; wp = (w.T * P * w)[0]
        print(world, gname, 'kappa=%.4f' % float(sympy.sqrt(wp / ws)), 'ME share=%.4f' % float(wm / ws),
              'pilot share of ME (type dir)=%.4f' % float(wp / wm),
              'PSD checks:', min(np.linalg.eigvalsh(np.array((Sm - P).evalf(), float))), min(np.linalg.eigvalsh(np.array((S - Sm).evalf(), float))))
