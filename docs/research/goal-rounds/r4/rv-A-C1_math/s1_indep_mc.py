"""Independent MC of the ACTUAL sampling sd of sqrt(n) b_type-hat (own implementation of the corrected-score estimator, not the
sandwich estimator) vs the claimed formula sqrt(E phi^2)/D.  Also a Fraction-free numeric check with an unclipped g in the wide world."""
import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_")
from route_a_lib import beta_moments, first_order

def falling(K, j):
    out = np.ones_like(K, float)
    for i in range(j): out = out * (K - i)
    return out

def cs_estimate(y, K, m, t):
    U = [falling(K, j) / falling(np.array([float(m)]), j)[0] for j in range(5)]
    n = y.size
    M = np.zeros((n, 4, 4)); mv = np.zeros((n, 4))
    for a in range(3):
        for b in range(3): M[:, a, b] = U[a + b]
        M[:, a, 3] = M[:, 3, a] = U[a] * t
        mv[:, a] = U[a] * y
    M[:, 3, 3] = t; mv[:, 3] = t * y
    A = M.sum(0)
    beta = np.linalg.solve(A, mv.sum(0))
    psi = mv - np.einsum("nij,j->ni", M, beta)
    Ai = np.linalg.inv(A)
    cov = Ai @ (psi.T @ psi) @ Ai
    return beta, np.sqrt(np.diag(cov))

rng = np.random.default_rng(2024)
WORLDS = {"wide": ((2, 8), (2.5, 7.5)), "narrow": ((20, 80), (25, 75))}
cases = [("wide", (0.18, -0.8, 0.0), True, 128), ("wide", (0.0, 0.5, -0.5), False, 128), ("narrow", (0.18, -0.8, 0.0), False, 128), ("wide", (0.18, -0.8, 0.0), True, 32)]
n, reps = 4000, 1500
for wn, G, clipped, m in cases:
    ab0, ab1 = WORLDS[wn]
    mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
    fo = first_order(mu0, mu1, 0.5, m, n, beta=G)
    pred = np.sqrt(fo["Ephi2"]) / fo["D"]
    bs, ses, clipfrac = [], [], []
    for _ in range(reps):
        t = np.repeat([0.0, 1.0], n // 2)
        r = np.concatenate([rng.beta(*ab0, n // 2), rng.beta(*ab1, n // 2)])
        d = G[0] + G[1] * r + G[2] * r ** 2
        qp, qm = r + d / 2, r - d / 2
        clipfrac.append(np.mean((qp > 1) | (qm < 0)))
        y = rng.binomial(16, np.clip(qp, 0, 1)) / 16 - rng.binomial(16, np.clip(qm, 0, 1)) / 16
        K = rng.binomial(m, r)
        b, se = cs_estimate(y, K, m, t)
        bs.append(b[3]); ses.append(se[3])
    bs = np.array(bs); ses = np.array(ses)
    sd_emp = np.sqrt(n) * bs.std(ddof=1)
    se_sd = sd_emp / np.sqrt(2 * (reps - 1))
    print(f"{wn:7s} g={G} m={m:4d} clipfrac={np.mean(clipfrac):.3f}  pred sqrt(n)se_1={pred:.4f}  empirical sd(sqrt(n) b)={sd_emp:.4f} (+-{se_sd:.4f}) ratio={sd_emp/pred:.4f}  mean sandwich sqrt(n)se={np.sqrt(n)*ses.mean():.4f}  mean b={bs.mean():+.5f} (+-{bs.std(ddof=1)/np.sqrt(reps):.5f})", flush=True)
