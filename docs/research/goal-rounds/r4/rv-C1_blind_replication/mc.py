"""Independent nested MC for sigma_delta (blind replication of C1)."""
import numpy as np, sys, json, time

M = 128
N = 200
T = np.r_[np.zeros(100), np.ones(100)]
CL = np.r_[np.arange(100) // 2, np.arange(100) // 2]   # 50 clusters x 4 (2 per type)
PD_RTOL = 1e-9

def ffall(K, j):
    out = np.ones_like(K, dtype=float)
    for i in range(j):
        out = out * (K - i)
    return out

FFM = [ffall(np.array([float(M)]), j)[0] for j in range(5)]

def batch_cs(y, K):
    """y, K: (B, N). Returns ok, t_HC1, t_CR1, se_HC1, se_CR1 (degree 2) - re-implementation of the production formula."""
    B = y.shape[0]
    U = [ffall(K, j) / FFM[j] for j in range(5)]
    k = 4
    Mm = np.zeros((B, N, k, k)); mv = np.zeros((B, N, k))
    t = np.broadcast_to(T, (B, N))
    for a in range(3):
        for b in range(3):
            Mm[:, :, a, b] = U[a + b]
        Mm[:, :, a, 3] = Mm[:, :, 3, a] = U[a] * t
        mv[:, :, a] = U[a] * y
    Mm[:, :, 3, 3] = t
    mv[:, :, 3] = t * y
    A = Mm.sum(1)
    eig = np.linalg.eigvalsh(A)
    ok = eig[:, 0] > PD_RTOL * np.maximum(1.0, np.abs(eig[:, -1]))
    Asafe = np.where(ok[:, None, None], A, np.eye(k)[None])
    beta = np.linalg.solve(Asafe, mv.sum(1)[..., None])[..., 0]
    psi = mv - np.einsum('bnij,bj->bni', Mm, beta)
    Ai = np.linalg.inv(Asafe)
    Bh = np.einsum('bni,bnj->bij', psi, psi) * (N / (N - k))
    S = np.zeros((B, 50, k))
    for c in range(50):
        S[:, c] = psi[:, CL == c].sum(1)
    Bc = np.einsum('bci,bcj->bij', S, S) * (50 / 49) * ((N - 1) / (N - k))
    ch = np.einsum('bij,bjk,bkl->bil', Ai, Bh, Ai)
    cc = np.einsum('bij,bjk,bkl->bil', Ai, Bc, Ai)
    seh = np.sqrt(np.clip(ch[:, 3, 3], 0, None)); sec = np.sqrt(np.clip(cc[:, 3, 3], 0, None))
    return ok, beta[:, 3] / seh, beta[:, 3] / sec, seh, sec

WORLDS = {'narrow': [(20, 80), (25, 75)], 'half': [(40.5, 162), (50.6, 151.8)]}
GS = {'lin': lambda r: 0.18 - 0.8 * r, 'quad': lambda r: 0.26 - 1.6 * r + 2 * r * r, 'cheb': lambda r: 0.5 * (1 - 8 * r + 8 * r * r)}

def events(y, K):
    ok, th, tc, seh, sec = batch_cs(y, K)
    return np.stack([ok & (np.abs(th) > 1.96), ok & (np.abs(tc) > 1.96), ~ok,
                     ok & (2 * 1.96 * seh <= 0.15), ok & (2 * 1.96 * sec <= 0.15)], 1).astype(float)
EV = ['rejHC1', 'rejCR1', 'nonPD', 'widthHC1', 'widthCR1']

def run(world, gname, n_out, n_in, seed):
    rng = np.random.default_rng(seed)
    g = GS[gname]
    a = np.r_[np.full(100, WORLDS[world][0][0]), np.full(100, WORLDS[world][1][0])]
    b = np.r_[np.full(100, WORLDS[world][0][1]), np.full(100, WORLDS[world][1][1])]
    Dbar = np.zeros((n_out, len(EV))); Dvar = np.zeros((n_out, len(EV)))
    Pbar = np.zeros((n_out, len(EV)))   # fresh event means (for sigma_0)
    Rbar = np.zeros((n_out, len(EV)))
    clip = 0
    for o in range(n_out):
        r0 = rng.beta(a, b)
        K32 = rng.binomial(32, r0)
        r = rng.beta(a + K32, b + 32 - K32, size=(n_in, N))     # posterior r | K32
        K96 = rng.binomial(96, r)
        Kf = rng.binomial(128, r)
        gg = g(r)
        qp, qm = r + gg / 2, r - gg / 2
        clip += np.sum((qp < 0) | (qp > 1) | (qm < 0) | (qm > 1))
        qp, qm = np.clip(qp, 0, 1), np.clip(qm, 0, 1)
        y = rng.binomial(16, qp) / 16 - rng.binomial(16, qm) / 16
        er = events(y, K32[None] + K96)
        ef = events(y, Kf)
        d = er - ef
        Dbar[o] = d.mean(0); Dvar[o] = d.var(0, ddof=1)
        Pbar[o] = ef.mean(0); Rbar[o] = er.mean(0)
    return dict(Dbar=Dbar, Dvar=Dvar, Pbar=Pbar, Rbar=Rbar, clip=clip / (n_out * n_in * N))

def anova(xbar, s2, n_in):
    return xbar.var(0, ddof=1) - s2.mean(0) / n_in

if __name__ == '__main__':
    world, gname, n_out, n_in, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    t0 = time.time()
    res = run(world, gname, n_out, n_in, seed)
    np.savez(f'res_{world}_{gname}_{seed}.npz', **{k: v for k, v in res.items() if k != 'clip'}, n_in=n_in)
    Dbar, Dvar = res['Dbar'], res['Dvar']
    s2 = anova(Dbar, Dvar, n_in)
    rng = np.random.default_rng(1)
    boots = np.array([anova(Dbar[i], Dvar[i], n_in) for i in (rng.integers(0, n_out, n_out) for _ in range(2000))])
    out = {}
    for j, e in enumerate(EV):
        ucl = np.quantile(boots[:, j], 0.95)
        out[e] = dict(sig2=float(s2[j]), ci90=[float(np.quantile(boots[:, j], .05)), float(ucl)],
                      ucl_sigma=float(np.sqrt(max(ucl, 0))), P_reuse=float(res['Rbar'][:, j].mean()), P_fresh=float(res['Pbar'][:, j].mean()))
    print(world, gname, 'clip', res['clip'], 'time', round(time.time() - t0))
    print(json.dumps(out, indent=1))
