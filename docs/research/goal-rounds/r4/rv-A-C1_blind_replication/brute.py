"""Exact brute-force check: enumerate (t, r, K) for discrete laws, build psi from the
DEFINITION psi = b_tilde - A_tilde beta, compute B=E[psi psi'], Q=E[A_tilde], and the
(type,type) entry of Q^{-1} B Q^{-1}; compare with D^{-2} sum_t w_t E_t[phi^2] from formula.py."""
from formula import *
from fractions import Fraction as Fr
from math import comb

def inv4(A):
    n = 4
    M = [list(map(Fr, A[i])) + [Fr(int(i == j)) for j in range(n)] for i in range(n)]
    for i in range(n):
        piv = next(k for k in range(i, n) if M[k][i] != 0)
        M[i], M[piv] = M[piv], M[i]
        p = M[i][i]
        M[i] = [v / p for v in M[i]]
        for k in range(n):
            if k != i and M[k][i] != 0:
                f = M[k][i]
                M[k] = [M[k][c] - f * M[i][c] for c in range(2 * n)]
    return [row[n:] for row in M]

def matmul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]

def brute(law0, law1, w1, m, beta, b_type, sigma2_poly):
    w1 = Fr(w1); w0 = 1 - w1
    B = [[Fr(0)] * 4 for _ in range(4)]
    Q = [[Fr(0)] * 4 for _ in range(4)]
    for t, law, w in ((0, law0, w0), (1, law1, w1)):
        for r, pr in law:
            r = Fr(r); pr = Fr(pr)
            s2 = pexpect(sigma2_poly, [r ** k for k in range(10)])
            ydet = beta[0] + beta[1] * r + beta[2] * r * r + b_type * t
            for K in range(m + 1):
                pk = Fr(comb(m, K)) * r ** K * (1 - r) ** (m - K)
                U = [Fr(ff(K, j), ff(m, j)) for j in range(5)]
                At = [[U[0], U[1], U[2], t], [U[1], U[2], U[3], t * U[1]], [U[2], U[3], U[4], t * U[2]], [t, t * U[1], t * U[2], t]]
                bvec = [beta[0], beta[1], beta[2], b_type]
                u = [U[0], U[1], U[2], Fr(t)]
                psig = [ydet * u[i] - sum(At[i][j] * bvec[j] for j in range(4)) for i in range(4)]
                wt = w * pr * pk
                for i in range(4):
                    for j in range(4):
                        B[i][j] += wt * (s2 * u[i] * u[j] + psig[i] * psig[j])
                        Q[i][j] += wt * At[i][j]
    Qi = inv4(Q)
    V = matmul(matmul(Qi, B), Qi)
    return V[3][3], Q

law0 = [(Fr(1, 5), Fr(1, 2)), (Fr(3, 10), Fr(1, 2))]
law1 = [(Fr(1, 4), Fr(1, 3)), (Fr(2, 5), Fr(1, 3)), (Fr(1, 2), Fr(1, 3))]
beta = (Fr(1, 10), Fr(-4, 5), Fr(3, 2)); b_type = Fr(1, 3)
sig = sigma2_arms(beta[0], beta[1], beta[2])
mom0 = discrete_moments(law0, 12); mom1 = discrete_moments(law1, 12)
ok_all = True
for w1 in (Fr(1, 2), Fr(2, 5)):
    Qxx, q, gamma, D = overlap(mom0, mom1, w1)
    for m in (4, 8, 10):
        vb, Q = brute(law0, law1, w1, m, beta, b_type, sig)
        te, tg, dg = first_order_var_sum(mom0, mom1, w1, gamma, D, (beta[1], beta[2]), m, sig)
        vf = (te + tg) / D ** 2
        ok = (vb == vf)
        ok_all &= ok
        print(f"w1={w1} m={m}: brute={float(vb):.10g} formula={float(vf):.10g} exact_equal={ok} maxdeg={dg}")
# Also a law with 3 support points per type and b2 != 0 where moments up to 8 matter, m=4 edge
law0b = [(Fr(1, 10), Fr(1, 4)), (Fr(1, 2), Fr(1, 2)), (Fr(9, 10), Fr(1, 4))]
law1b = [(Fr(1, 3), Fr(1, 2)), (Fr(2, 3), Fr(1, 2))]
mom0b = discrete_moments(law0b, 12); mom1b = discrete_moments(law1b, 12)
for w1 in (Fr(1, 2), Fr(2, 5)):
    Qxx, q, gamma, D = overlap(mom0b, mom1b, w1)
    for m in (4, 5, 8):
        vb, Q = brute(law0b, law1b, w1, m, beta, b_type, sigma2_bound())
        te, tg, dg = first_order_var_sum(mom0b, mom1b, w1, gamma, D, (beta[1], beta[2]), m, sigma2_bound())
        vf = (te + tg) / D ** 2
        ok = (vb == vf); ok_all &= ok
        print(f"[law b] w1={w1} m={m}: brute={float(vb):.10g} formula={float(vf):.10g} exact_equal={ok} maxdeg={dg}")
print("ALL EXACT:", ok_all)
