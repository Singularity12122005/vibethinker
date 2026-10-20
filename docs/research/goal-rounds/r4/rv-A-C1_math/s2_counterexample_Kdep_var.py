"""Counterexample for the CLAIM'S stated assumptions (E[eta|r,t,K]=0, Var(eta|r)=sigma^2(r)) without the derivation's stronger
'eta independent of K given (r,t)': Var(eta | r, K) = sigma2(r) * (1 + c (U_1(K) - r)).  Exact enumeration (Fractions) of the true
first-order sandwich [Q^{-1} B Q^{-1}]_44 vs the claimed closed form D^{-2} sum_t w_t E_t[phi^2]."""
import sys
from fractions import Fraction as F
from math import comb
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_")
from route_a_lib import first_order, inverse_generic

def falling(K, j):
    o = 1
    for i in range(j): o *= (K - i)
    return o
def U(K, j, m): return F(falling(K, j), falling(m, j))

def brute(laws, w1, m, beta, c, n_arm=16):
    w = [1 - w1, w1]
    Q = [[F(0)] * 4 for _ in range(4)]; B = [[F(0)] * 4 for _ in range(4)]; mus = []
    for t in (0, 1):
        mu = [sum(pr * r ** j for r, pr in laws[t]) for j in range(9)]
        for r, pr in laws[t]:
            xs = [F(1), r, r * r, F(t)]
            for a in range(4):
                for b in range(4): Q[a][b] += w[t] * pr * xs[a] * xs[b]
            g = beta[0] + beta[1] * r + beta[2] * r * r
            qp, qm = r + g / 2, r - g / 2
            assert 0 <= qp <= 1 and 0 <= qm <= 1
            s2 = (qp * (1 - qp) + qm * (1 - qm)) / n_arm
            for K in range(m + 1):
                pK = comb(m, K) * r ** K * (1 - r) ** (m - K)
                Us = [U(K, j, m) for j in range(5)]
                u = [Us[0], Us[1], Us[2], F(t)]
                e = [sum(beta[b] * (Us[a] * r ** b - Us[a + b]) for b in range(3)) for a in range(3)]
                e.append(F(t) * sum(beta[b] * (r ** b - Us[b]) for b in range(3)))
                varK = s2 * (1 + c * (Us[1] - r))          # E[varK | r] = s2  (Var(eta|r) = sigma2(r) holds), E[eta|r,t,K]=0 holds
                assert varK > 0
                for a in range(4):
                    for d in range(4): B[a][d] += w[t] * pr * pK * (varK * u[a] * u[d] + e[a] * e[d])
        mus.append(mu)
    return Q, B, mus

laws1 = [[(F(1, 5), F(1, 2)), (F(3, 10), F(1, 2))], [(F(1, 4), F(1, 3)), (F(2, 5), F(1, 3)), (F(1, 2), F(1, 3))]]
beta = [F(9, 50), F(-4, 5), F(3, 10)]
for m, c in ((8, F(0)), (8, F(9, 10)), (8, F(-9, 10)), (32, F(9, 10))):
    Q, B, mus = brute(laws1, F(1, 2), m, beta, c)
    Qi = inverse_generic(Q)
    v = sum(Qi[3][i] * B[i][j] * Qi[j][3] for i in range(4) for j in range(4))
    fo = first_order(mus[0], mus[1], F(1, 2), m, 200, beta=beta, exact=True)
    f = fo["Ephi2"] / (fo["D"] ** 2)
    print(f"m={m:3d} c={float(c):+.2f}: true [Q^-1 B Q^-1]_44 = {float(v):.8f}   claimed formula = {float(f):.8f}   ratio true/formula = {float(v / f):.6f}  (exact equal: {v == f})")
