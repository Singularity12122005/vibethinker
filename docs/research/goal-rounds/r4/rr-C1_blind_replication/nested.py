"""Blind nested MC of sigma_delta (reuse) and sigma_0 (fresh selection term) with a batched clone of the production
endpoint_contrast_poly_cs(degree=2), validated against the production function."""
import sys, json, time
import numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs, PD_RTOL

N, NT, MF, MP = 200, 100, 128, 32
t = np.r_[np.zeros(NT), np.ones(NT)]
# 50 clusters of 4: 2 of each type
cl = np.r_[np.repeat(np.arange(50), 2), np.repeat(np.arange(50), 2)]
WORLDS = {'narrow': ((20, 80), (25, 75)), 'halfvar': ((40.5, 162), (50.6, 151.8))}
GS = {'lin': (0.18, -0.8, 0.0), 'quad': (0.26, -1.6, 2.0), 'cheb': (0.5, -4.0, 4.0)}

def gfun(c, r):
    return c[0] + c[1] * r + c[2] * r * r

def batch_test(y, K, m=MF, cluster=False):
    """y,K: (B,N). returns ok, tstat, width (2*1.96*se)."""
    Bn = y.shape[0]
    U = [np.ones_like(K, float)]
    for j in range(1, 5):
        f = np.ones_like(K, float); fm = 1.0
        for i in range(j):
            f = f * (K - i); fm *= (m - i)
        U.append(f / fm)
    k = 4
    Mm = np.zeros((Bn, N, k, k)); mv = np.zeros((Bn, N, k))
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
    A2 = A.copy(); A2[~ok] = np.eye(k)
    beta = np.linalg.solve(A2, mv.sum(1)[..., None])[..., 0]
    psi = mv - np.einsum("bnij,bj->bni", Mm, beta)
    Ainv = np.linalg.inv(A2)
    if not cluster:
        Bm = np.einsum("bni,bnj->bij", psi, psi) * (N / (N - k))
    else:
        s = np.zeros((Bn, 50, k))
        np.add.at(s, (slice(None), cl), psi)
        Bm = np.einsum("bgi,bgj->bij", s, s) * (50 / 49) * ((N - 1) / (N - k))
    cov = Ainv @ Bm @ Ainv
    se = np.sqrt(np.clip(cov[:, 3, 3], 0, None))
    with np.errstate(divide='ignore', invalid='ignore'):
        tt = beta[:, 3] / se
    return ok, tt, 2 * 1.96 * se

def validate(rng):
    for _ in range(30):
        r = np.r_[rng.beta(40.5, 162, NT), rng.beta(50.6, 151.8, NT)]
        K = rng.binomial(MF, r)
        y = rng.normal(0, 0.1, N)
        for clu in (False, True):
            ok, tt, wd = batch_test(y[None], K[None].astype(float), cluster=clu)
            res = endpoint_contrast_poly_cs(y, K, MF, t, degree=2, cluster=cl if clu else None)
            assert res['ok'] == bool(ok[0])
            if res['ok']:
                assert abs(res['t_type'] - tt[0]) < 1e-7 * max(1, abs(tt[0])), (res['t_type'], tt[0])
    print("batched clone matches production on 60 cases")

def run(world, gname, O, I, seed):
    rng = np.random.default_rng(seed)
    (a0, b0), (a1, b1) = WORLDS[world]
    a = np.r_[np.full(NT, a0), np.full(NT, a1)]; b = np.r_[np.full(NT, b0), np.full(NT, b1)]
    c = GS[gname]
    out = {k: np.zeros((O, I)) for k in ['rejR_HC1', 'rejF_HC1', 'rejR_CR1', 'rejF_CR1', 'npdR', 'npdF', 'wR', 'wF']}
    K32s = np.zeros((O, N), int); clip = 0; tot = 0
    for o in range(O):
        r0 = rng.beta(a, b)
        K32 = rng.binomial(MP, r0); K32s[o] = K32
        rr = rng.beta(a + K32, b + MP - K32, size=(I, N))      # exact posterior given (t,K32)
        K96 = rng.binomial(MF - MP, rr); Kf = rng.binomial(MF, rr)
        g = gfun(c, rr)
        qp = np.clip(rr + g / 2, 0, 1); qm = np.clip(rr - g / 2, 0, 1)
        clip += np.sum((rr + g / 2 > 1) | (rr + g / 2 < 0) | (rr - g / 2 > 1) | (rr - g / 2 < 0)); tot += rr.size
        y = (rng.binomial(16, qp) - rng.binomial(16, qm)) / 16.0
        KR = (K32[None] + K96).astype(float)
        for lab, KK in (('R', KR), ('F', Kf.astype(float))):
            ok, tt, wd = batch_test(y, KK, cluster=False)
            out['rej%s_HC1' % lab][o] = ok & (np.abs(np.nan_to_num(tt)) > 1.96)
            out['npd%s' % lab][o] = ~ok
            out['w%s' % lab][o] = ok & (wd <= 0.15)
            ok2, tt2, _ = batch_test(y, KK, cluster=True)
            out['rej%s_CR1' % lab][o] = ok2 & (np.abs(np.nan_to_num(tt2)) > 1.96)
    np.savez_compressed(f"nested_{world}_{gname}_{O}x{I}_s{seed}.npz", K32=K32s, **out)
    return out, clip / tot

def between_sd(D):
    """one-way ANOVA between-variance of row means; returns sigma estimate (clipped at 0) and outer-bootstrap 95% UCL"""
    O, I = D.shape
    mu = D.mean(1); s2 = D.var(1, ddof=1)
    def est(idx):
        return max(0.0, mu[idx].var(ddof=1) - s2[idx].mean() / I)
    v = est(np.arange(O))
    rng = np.random.default_rng(777)
    bs = [est(rng.integers(0, O, O)) for _ in range(2000)]
    return np.sqrt(v), np.sqrt(np.quantile(bs, 0.95))

if __name__ == "__main__":
    validate(np.random.default_rng(1))
    world, gname, O, I, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    t0 = time.time()
    out, cliprate = run(world, gname, O, I, seed)
    res = dict(world=world, g=gname, O=O, I=I, seed=seed, cliprate=cliprate, secs=time.time() - t0)
    for se in ('HC1', 'CR1'):
        R, F = out['rejR_' + se], out['rejF_' + se]
        res['size_reuse_' + se] = R.mean(); res['size_fresh_' + se] = F.mean()
        res['sigdelta_rej_' + se] = between_sd(R - F)
        res['sig0_rej_' + se] = between_sd(F)
        res['sigcomb_rej_' + se] = between_sd(R)
    res['sigdelta_npd'] = between_sd(out['npdR'] - out['npdF'])
    res['sigdelta_w015_HC1'] = between_sd(out['wR'] - out['wF'])
    res['npd_rate_R'] = out['npdR'].mean(); res['npd_rate_F'] = out['npdF'].mean()
    print(json.dumps(res, default=lambda x: [float(v) for v in x] if isinstance(x, tuple) else float(x), indent=1))
