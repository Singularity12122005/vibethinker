"""Orchestrator's exact checks for the r4 atoms (independent of the reviewers' scripts): the overlap D of A-C1-atom-v2 for the
narrow world Beta(20,80)/Beta(25,75), w_1 = 1/2, in exact rational arithmetic."""
from fractions import Fraction as Fr
def mom(a, b, J):
    mu = [Fr(1)]
    for j in range(1, J + 1):
        mu.append(mu[-1] * Fr(a + j - 1) / Fr(a + b + j - 1))
    return mu
m0, m1, w1 = mom(20, 80, 4), mom(25, 75, 4), Fr(1, 2)
Q = [[(1 - w1) * m0[i + j] + w1 * m1[i + j] for j in range(3)] for i in range(3)]
q = [w1 * m1[i] for i in range(3)]
A = [row[:] + [q[i]] for i, row in enumerate(Q)]
for c in range(3):
    p = next(i for i in range(c, 3) if A[i][c] != 0); A[c], A[p] = A[p], A[c]
    for i in range(3):
        if i != c:
            f = A[i][c] / A[c][c]; A[i] = [x - f * y for x, y in zip(A[i], A[c])]
x = [A[i][3] / A[i][i] for i in range(3)]
D = w1 - sum(qi * xi for qi, xi in zip(q, x))
print(f"D_narrow_exact = {D}")
print(f"D_narrow_float = {float(D):.10f}")
