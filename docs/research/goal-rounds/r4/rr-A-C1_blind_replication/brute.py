"""Exact brute force: enumerate r (discrete support), t, K ~ Bin(m,r), arm counts A+,A- ~ Bin(16,q+-) and form psi exactly
following the production estimating equation (columns 1,r,r^2,type), then compare [Q^-1 B Q^-1]_tt with the closed form."""
import sys
from fractions import Fraction as Fr
from math import comb, perm
sys.path.insert(0, '/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/rereview_A-C1_blind_replication')
import cf

def binpmf(n, p, k): return comb(n, k) * p ** k * (1 - p) ** (n - k)

def inv(M):
    n = len(M); A = [list(M[i]) + [Fr(int(i == j)) for j in range(n)] for i in range(n)]
    for c in range(n):
        p = next(r for r in range(c, n) if A[r][c] != 0); A[c], A[p] = A[p], A[c]
        piv = A[c][c]; A[c] = [x / piv for x in A[c]]
        for r in range(n):
            if r != c and A[r][c] != 0:
                f = A[r][c]; A[r] = [A[r][k] - f * A[c][k] for k in range(2 * n)]
    return [row[n:] for row in A]

def brute(laws, w, m, beta, btype=Fr(0), narm=4):
    b0, b1, b2 = [Fr(x) for x in beta]
    # population Q = E[M], beta_full=(b0,b1,b2,btype)
    bf = [b0, b1, b2, btype]
    Q = [[Fr(0)] * 4 for _ in range(4)]
    B = [[Fr(0)] * 4 for _ in range(4)]
    for t in (0, 1):
        for r, pr in laws[t]:
            g = b0 + b1 * r + b2 * r * r + btype * t
            qp, qm = r + g / 2, r - g / 2
            assert 0 <= qp <= 1 and 0 <= qm <= 1
            for K in range(m + 1):
                pK = binpmf(m, r, K)
                U = [Fr(perm(K, j), perm(m, j)) for j in range(5)]
                M = [[U[a + c] for c in range(3)] + [U[a] * t] for a in range(3)] + [[U[a] * t for a in range(3)] + [Fr(t)]]
                for a in range(4):
                    for c in range(4): Q[a][c] += w[t] * pr * pK * M[a][c]
                for Ap in range(narm + 1):
                    pA = binpmf(narm, qp, Ap)
                    for Am in range(narm + 1):
                        pB = binpmf(narm, qm, Am)
                        y = Fr(Ap - Am, narm)
                        mv = [U[a] * y for a in range(3)] + [t * y]
                        psi = [mv[a] - sum(M[a][c] * bf[c] for c in range(4)) for a in range(4)]
                        wt = w[t] * pr * pK * pA * pB
                        for a in range(4):
                            for c in range(4): B[a][c] += wt * psi[a] * psi[c]
    Qi = inv(Q)
    return sum(Qi[3][a] * B[a][c] * Qi[c][3] for a in range(4) for c in range(4))

def moms_of(law, K=9):
    return [sum(p * r ** k for r, p in law) for k in range(K + 1)]

if __name__ == '__main__':
    laws = {0: [(Fr(1, 10), Fr(1, 3)), (Fr(3, 10), Fr(1, 3)), (Fr(1, 2), Fr(1, 3))],
            1: [(Fr(1, 5), Fr(1, 4)), (Fr(2, 5), Fr(1, 2)), (Fr(7, 10), Fr(1, 4))]}
    for (w1, m, beta, btype, narm) in [(Fr(1, 2), 4, (Fr(1, 20), Fr(-1, 5), Fr(1, 10)), Fr(0), 4),
                                (Fr(2, 5), 5, (Fr(0), Fr(1, 4), Fr(-1, 5)), Fr(0), 3),
                                (Fr(1, 2), 8, (Fr(9, 50), Fr(-4, 5), Fr(3, 10)), Fr(0), 4),
                                (Fr(2, 5), 10, (Fr(1, 10), Fr(-1, 10), Fr(-1, 5)), Fr(0), 3)]:
        w = {0: 1 - w1, 1: w1}
        bb = brute(laws, w, m, beta, btype, narm)
        moms = {t: moms_of(laws[t]) for t in (0, 1)}
        cfv = cf.var1_total(moms, w, m, beta, cf.sig2_arms(beta, narm))[0]
        print(m, w1, beta, 'brute', bb, 'cf', cfv, 'equal', bb == cfv, float(bb))
