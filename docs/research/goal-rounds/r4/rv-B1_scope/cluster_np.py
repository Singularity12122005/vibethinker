"""Scope review of B1: NP-exact minimal error sum 1-TV for F_a vs F_b (and F_theta) when prefixes are clustered by question.
Model: 50 questions x (2 type-0 + 2 type-1) prefixes (the B2 cluster layout); Gaussian copula: z_p = sqrt(rho) z_q + sqrt(1-rho) e_p,
r_p = F_t^{-1}(Phi(z_p)); same Beta marginals as the claim's worlds. rho=0 reproduces the iid claim. LR test MC."""
import numpy as np, sys
from scipy import stats
from numpy.polynomial.hermite_e import hermegauss
M = int(sys.argv[1]) if len(sys.argv) > 1 else 32
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
NQ, LAY = 50, (0, 0, 1, 1)
W = {"F_a": ((20, 80), (25, 75)), "F_b": ((40.5, 162), (50.6, 151.8))}
def theta_world(th):
    s = 101 / th - 1; return ((0.2 * s, 0.8 * s), (0.25 * s, 0.75 * s))
for th in (0.7, 0.9): W[f"F_{th}"] = theta_world(th)
zq, wq = hermegauss(60); wq = wq / wq.sum()
ze, we = hermegauss(60); we = we / we.sum()
k = np.arange(M + 1)
def table(world, rho):
    # h[t][iq, k] = P(K=k | z_q node iq) for type t
    out = []
    for t in (0, 1):
        a, b = world[t]
        z = np.sqrt(rho) * zq[:, None] + np.sqrt(1 - rho) * ze[None, :]
        r = stats.beta.ppf(stats.norm.cdf(z), a, b)
        pm = stats.binom.pmf(k[None, None, :], M, r[:, :, None])  # (q, e, k)
        out.append(np.einsum('qek,e->qk', pm, we))
    return out
def sample(world, rho, rng, n):
    zqs = rng.standard_normal((n, NQ, 1))
    e = rng.standard_normal((n, NQ, 4))
    z = np.sqrt(rho) * zqs + np.sqrt(1 - rho) * e
    K = np.empty((n, NQ, 4), dtype=np.int64)
    for j, t in enumerate(LAY):
        a, b = world[t]
        r = stats.beta.ppf(stats.norm.cdf(z[:, :, j]), a, b)
        K[:, :, j] = rng.binomial(M, r)
    return K
def loglik(K, h):
    # K (n, NQ, 4); p = sum_q wq prod_j h[t_j][q, K_j]
    acc = np.ones(K.shape[:2] + (len(wq),))
    for j, t in enumerate(LAY):
        acc *= h[t][:, K[:, :, j]].transpose(1, 2, 0)
    return np.log(acc @ wq).sum(1)
def np_min(A, B, rho, rng):
    ha, hb = table(W[A], rho), table(W[B], rho)
    res = []
    for world in (A, B):
        s = []
        for _ in range(REPS // 2000):
            K = sample(W[world], rho, rng, 2000)
            s.append(loglik(K, ha) - loglik(K, hb))
        res.append(np.concatenate(s))
    eI, eII = (res[0] <= 0).mean(), (res[1] > 0).mean()
    return eI + eII, np.sqrt(eI * (1 - eI) / REPS + eII * (1 - eII) / REPS)
rng = np.random.default_rng(20261019)
for B in ("F_b", "F_0.7", "F_0.9"):
    for rho in (0.0, 0.3, 0.6, 0.9):
        v, se = np_min("F_a", B, rho, rng)
        print(f"m={M} F_a vs {B:6s} rho={rho:.1f}: NP err sum {v:.4f} (SE {se:.4f})", flush=True)
