"""Reviewer (math lens) of r4 C1: independent Monte Carlo of kappa (F32 version), the G32-restricted tilt ratio,
the achievable (not Cauchy-Schwarz) tilt at P(D)=1/2, and the U2 pilot share.  Written from scratch (no c3 code reused)."""
import numpy as np
from math import comb
rng = np.random.default_rng(91)
WORLDS = {"narrow": ((20., 80.), (25., 75.)), "halfvar": ((40.5, 162.), (50.6, 151.8))}
G = {"lin": (0.18, -0.8, 0.0), "quad": (0.26, -1.6, 2.0), "cheb": (0.5, -4.0, 4.0)}

def U(K, j, m):
    out = np.ones_like(K, float)
    for i in range(j):
        out = out * (K - i) / (m - i)
    return out

def Ut(j, k, r):
    return sum(comb(32, l) * comb(96, j - l) / comb(128, j) * r ** (j - l) * U(k, l, 32) for l in range(j + 1))

def score_rows(Uf, gr, beta, t):
    rows = [gr * Uf(a) - sum(beta[b] * Uf(a + b) for b in range(3)) for a in range(3)]
    rows.append(t * (gr - sum(beta[b] * Uf(b) for b in range(3))))
    return np.stack(rows, -1)

N = 2_000_000
for wn, ab in WORLDS.items():
    # population A and w
    mus = []
    for a, b in ab:
        mu = [1.0]
        for j in range(5):
            mu.append(mu[-1] * (a + j) / (a + b + j))
        mus.append(mu)
    A = np.zeros((4, 4))
    for a in range(3):
        for b in range(3):
            A[a, b] = (mus[0][a + b] + mus[1][a + b]) / 2
        A[a, 3] = A[3, a] = mus[1][a] / 2
    A[3, 3] = .5
    w = np.linalg.solve(A, np.eye(4)[3])
    # share of U2
    sh_num = sh_den = 0
    for gn, g in G.items():
        EZpsi2 = EZphi2 = EZd2 = EZg2 = 0.0
        for t, (a, b) in enumerate(ab):
            r = rng.beta(a, b, N)
            K32 = rng.binomial(32, r); K = K32 + rng.binomial(96, r)
            gr = g[0] + g[1] * r + g[2] * r ** 2
            qp, qm = np.clip(r + gr / 2, 0, 1), np.clip(r - gr / 2, 0, 1)
            eta = rng.binomial(16, qp) / 16 - rng.binomial(16, qm) / 16 - gr
            dh = gr + eta
            psi = score_rows(lambda j: U(K, j, 128), gr, g, t)  # d part
            uhat = np.stack([U(K, 0, 128), U(K, 1, 128), U(K, 2, 128), t * np.ones(N)], -1)
            full = uhat * eta[:, None] + psi
            phi = score_rows(lambda j: Ut(j, K32, r), gr, g, t)
            EZpsi2 += np.mean((full @ w) ** 2) / 2; EZphi2 += np.mean((phi @ w) ** 2) / 2; EZd2 += np.mean((psi @ w) ** 2) / 2
            # G32 projection E[w'phi | K32=k] by posterior Monte Carlo
            kk = np.arange(33); proj = np.zeros(33)
            for k in kk:
                rp = rng.beta(a + k, b + 32 - k, 200_000)
                grp = g[0] + g[1] * rp + g[2] * rp ** 2
                kv = np.full(rp.size, k)
                proj[k] = (score_rows(lambda j: Ut(j, kv, rp), grp, g, t) @ w).mean()
            EZg2 += np.mean(proj[K32] ** 2) / 2
            if gn == "lin":
                sh_num += np.mean((Ut(2, K32, r) - r ** 2) ** 2) / 2; sh_den += np.mean((U(K, 2, 128) - r ** 2) ** 2) / 2
        kap = np.sqrt(EZphi2 / EZpsi2); kapG = np.sqrt(EZg2 / EZpsi2)
        print(f"{wn} {gn}: kappa(F32, CS bound)={kap:.4f}  ME share={EZd2/EZpsi2:.4f}  G32-measurable tilt ratio={kapG:.4f}  "
              f"Gaussian-achievable at pi=1/2 (x sqrt(2/pi)) F32={kap*np.sqrt(2/np.pi):.4f} G32={kapG*np.sqrt(2/np.pi):.4f}")
    print(f"{wn} U2 pilot share MC = {sh_num/sh_den:.4f}")
