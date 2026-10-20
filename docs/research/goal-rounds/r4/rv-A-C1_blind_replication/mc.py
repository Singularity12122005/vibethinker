import numpy as np, sys
from fractions import Fraction as Fr
from formula import *
KMAX = 12
worlds = {
    'narrow':  ((20, 80), (25, 75)),
    'halfvar~': ((40.4, 161.6), (50.5, 151.5)),
    'wide':    ((2, 8), (2.5, 7.5)),
}
b0, b1, b2, bt = 0.18, -0.8, 0.0, 0.0
def ffv(K, j):
    out = np.ones_like(K, dtype=float)
    for i in range(j): out *= (K - i)
    return out
def estimate(r, t, y, m):
    n = len(r)
    K = np.random.binomial(m, r)
    U = [ffv(K, j) / ff(m, j) for j in range(5)]
    A = np.zeros((n, 4, 4)); bb = np.zeros((n, 4))
    u = np.stack([U[0], U[1], U[2], t], 1)
    A[:, 0] = np.stack([U[0], U[1], U[2], t], 1)
    A[:, 1] = np.stack([U[1], U[2], U[3], t * U[1]], 1)
    A[:, 2] = np.stack([U[2], U[3], U[4], t * U[2]], 1)
    A[:, 3] = np.stack([t, t * U[1], t * U[2], t], 1)
    bb = u * y[:, None]
    Ah = A.mean(0); bh = bb.mean(0)
    ev = np.linalg.eigvalsh(Ah)
    pd = ev.min() > 1e-9 * max(1, ev.max())
    beta = np.linalg.solve(Ah, bh)
    psi = bb - A @ beta
    Bh = psi.T @ psi / n
    Ai = np.linalg.inv(Ah)
    V = Ai @ Bh @ Ai / n * n / (n - 4)
    return beta, np.sqrt(V[3, 3]), pd
def gen(world, n, mode):
    (a0, c0), (a1, c1) = worlds[world]
    t = np.r_[np.zeros(n // 2), np.ones(n // 2)]
    r = np.r_[np.random.beta(a0, c0, n // 2), np.random.beta(a1, c1, n // 2)]
    g = b0 + b1 * r + b2 * r * r
    if mode == 'bern':
        qp = np.clip(r + g / 2, 0, 1); qm = np.clip(r - g / 2, 0, 1)
        y = (np.random.binomial(16, qp) - np.random.binomial(16, qm)) / 16 + bt * t
    else:
        s2 = (2 * r * (1 - r) - g * g / 2) / 16
        y = g + bt * t + np.random.normal(0, np.sqrt(s2))
    return r, t, y
# formula values
form = {}
for name, ((a0, c0), (a1, c1)) in worlds.items():
    m0 = beta_moments(Fr(a0), Fr(c0), KMAX); m1 = beta_moments(Fr(a1), Fr(c1), KMAX)
    Qxx, q, gamma, D = overlap(m0, m1, Fr(1, 2))
    for m in (32, 128):
        te, tg, _ = first_order_var_sum(m0, m1, Fr(1, 2), gamma, D, (Fr(-4, 5), Fr(0)), m, sigma2_arms(Fr(9, 50), Fr(-4, 5), Fr(0)))
        form[(name, m)] = (np.sqrt(float(te + tg)) / float(D), width(te + tg, D, 200))
np.random.seed(77)
print("n=20000, 20 reps: sqrt(n)*se_HC1 / formula")
for name in worlds:
    for m in (32, 128):
        for mode in ('bern', 'gauss'):
            rat = []; bias = []
            for rep in range(20):
                r, t, y = gen(name, 20000, mode)
                beta, se, pd = estimate(r, t, y, m)
                rat.append(np.sqrt(20000) * se / form[(name, m)][0]); bias.append(beta[3] - bt)
            print(f"  {name:9s} m={m:3d} {mode:5s}: ratio {np.mean(rat):.3f} ± {np.std(rat, ddof=1):.3f}  (min {np.min(rat):.3f}, max {np.max(rat):.3f}); mean b_type-hat {np.mean(bias):+.4f} ± {np.std(bias, ddof=1)/np.sqrt(20):.4f}")
print("\nn=200, 2000 reps (bern): realised HC1 width 3.92*se  vs first-order w1")
for name in worlds:
    for m in (32, 128):
        ws = []; npd = 0; cover = 0; bias = []
        for rep in range(2000):
            r, t, y = gen(name, 200, 'bern')
            beta, se, pd = estimate(r, t, y, m)
            if not pd: npd += 1
            ws.append(3.92 * se); bias.append(beta[3])
            cover += abs(beta[3] - bt) <= 1.96 * se
        ws = np.array(ws)
        print(f"  {name:9s} m={m:3d}: w1={form[(name, m)][1]:.4f}  realised median {np.median(ws):.4f} q90 {np.quantile(ws, .9):.4f} mean {ws.mean():.4f}; nonPD {npd/2000:.3f}; cover95 {cover/2000:.3f}; sd(b_hat) {np.std(bias):.4f} (w1/3.92={form[(name,m)][1]/3.92:.4f})")
