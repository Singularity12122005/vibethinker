"""Attack: evaluate reuse effect E[1_R - 1_R' | D] for concrete K32-measurable rules, compare with claimed bound."""
import numpy as np, sys, mc

def pilot_stats(K32):
    rh = K32 / 32
    t = mc.T.astype(bool)
    gap = rh[t].mean() - rh[~t].mean()
    vw = 0.5 * (rh[t].var(ddof=1) + rh[~t].var(ddof=1))
    # degree-2 corrected moment matrix PD margin at m=32 (counts only)
    U = [mc.ffall(K32.astype(float), j) / mc.ffall(np.array([32.0]), j)[0] for j in range(5)]
    A = np.zeros((4, 4))
    for a in range(3):
        for b in range(3):
            A[a, b] = U[a + b].sum()
        A[a, 3] = A[3, a] = (U[a] * mc.T).sum()
    A[3, 3] = mc.T.sum()
    e = np.linalg.eigvalsh(A)
    # the type-direction pilot noise: residual of type gap in U1 regressed... use simple stats
    skew = np.mean(((rh - rh.mean()) / rh.std()) ** 3)
    return [gap, abs(gap), vw, e[0] / e[-1], skew, rh.max(), (K32 == 0).sum()]

def run(world, gname, n_out, n_in, seed):
    rng = np.random.default_rng(seed)
    g = mc.GS[gname]
    a = np.r_[np.full(100, mc.WORLDS[world][0][0]), np.full(100, mc.WORLDS[world][1][0])]
    b = np.r_[np.full(100, mc.WORLDS[world][0][1]), np.full(100, mc.WORLDS[world][1][1])]
    S = []; D = []; P = []
    for o in range(n_out):
        r0 = rng.beta(a, b); K32 = rng.binomial(32, r0)
        r = rng.beta(a + K32, b + 32 - K32, size=(n_in, mc.N))
        K96 = rng.binomial(96, r); Kf = rng.binomial(128, r)
        gg = g(r); qp, qm = np.clip(r + gg / 2, 0, 1), np.clip(r - gg / 2, 0, 1)
        y = rng.binomial(16, qp) / 16 - rng.binomial(16, qm) / 16
        er = mc.events(y, K32[None] + K96); ef = mc.events(y, Kf)
        S.append(pilot_stats(K32)); D.append((er - ef).mean(0)); P.append(ef.mean(0))
    np.savez(f'rules_{world}_{gname}_{seed}.npz', S=np.array(S), D=np.array(D), P=np.array(P), n_in=n_in)

if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
