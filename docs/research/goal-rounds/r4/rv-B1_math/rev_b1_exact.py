"""Independent re-derivation of B1: exact rational count laws via the DIRECT rising-factorial/Beta-function formula (not the
recursion), affinities with mpmath at 50 digits, Hellinger bound, and a rigorous near-exact value of the NP minimum
1 - TV(P_a, P_b) of the 200-prefix product law by circular-FFT lattice convolution with Chernoff-bounded aliasing.
Bracket: each log-LR value is rounded to a lattice of step h (error <= h/2 per term, <= 100 h over 200 terms), so
P(Lt > 100) <= P(L > 0) <= P(Lt > -100) where Lt is the integer lattice sum; the circular pmf of Lt mod N equals the true
pmf up to the mass outside the window, bounded by Chernoff with the exact lattice MGF."""
import sys, json, time
from fractions import Fraction as Fr
from math import comb
import numpy as np
import mpmath as mp
mp.mp.dps = 50
OUT = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/review_B1_math/rev_b1_exact.json"
N_T = 100

def rising(x, k):
    out = Fr(1)
    for i in range(k): out *= x + i
    return out

def bb_pmf(m, a, b):
    a, b = Fr(a), Fr(b)
    p = [comb(m, k) * rising(a, k) * rising(b, m - k) / rising(a + b, m) for k in range(m + 1)]
    assert sum(p) == 1
    return p

def disc_pmf(m, atoms, w):
    atoms = [Fr(x) for x in atoms]; w = [Fr(x) for x in w]; assert sum(w) == 1
    p = [sum(wj * comb(m, k) * x ** k * (1 - x) ** (m - k) for x, wj in zip(atoms, w)) for k in range(m + 1)]
    assert sum(p) == 1
    return p

def to_mpf(fr): return mp.mpf(fr.numerator) / mp.mpf(fr.denominator)
def affinity(p, q): return mp.fsum(mp.sqrt(to_mpf(x) * to_mpf(y)) for x, y in zip(p, q))

def theta_world(theta):
    s = Fr(101) / Fr(theta) - 1
    return ("beta", (s / 5, 4 * s / 5), (s / 4, 3 * s / 4))

F_A = ("beta", (20, 80), (25, 75))
WORLDS = {
    "F_b": ("beta", (Fr(81, 2), 162), (Fr(253, 5), Fr(759, 5))),
    "F_c": ("disc", ([Fr(1, 5)], [1]), ([Fr(1, 4)], [1])),
    "F_c2": ("disc", ([Fr(81, 505), Fr(6, 25)], [Fr(101, 201), Fr(100, 201)]), ([Fr(329, 1616), Fr(29, 100)], [Fr(1616, 3491), Fr(1875, 3491)])),
    "F_theta0.7": theta_world(Fr(7, 10)), "F_theta0.8": theta_world(Fr(4, 5)), "F_theta0.9": theta_world(Fr(9, 10)),
}
def pmf(world, t, m):
    if world[0] == "beta": return bb_pmf(m, *world[1 + t])
    return disc_pmf(m, *world[1 + t])

# ---- exact moment check of F_c2 vs F_a
for t in (0, 1):
    at, w = WORLDS["F_c2"][1 + t]; a, b = map(Fr, F_A[1 + t])
    m1 = sum(x * y for x, y in zip(at, w)); m2 = sum(x * x * y for x, y in zip(at, w))
    assert m1 == a / (a + b) and m2 - m1 ** 2 == a * b / ((a + b) ** 2 * (a + b + 1)), (t, m1, m2 - m1 ** 2)
print("F_c2 mean and variance match F_a exactly per type")

# ---- rigorous NP minimum via circular FFT
def chernoff_tail(ell, pw, n_t, thr, sign):
    """upper bound on P(sign * (sum of n_t iid lattice terms per type) >= sign*thr) via Chernoff, grid over s."""
    best = 1.0
    for s in np.logspace(-6, 2, 400):
        lm = 0.0
        for t in (0, 1):
            x = sign * s * (ell[t] - 0.0)
            mx = x.max(); lm += n_t * (mx + np.log(np.sum(pw[t] * np.exp(x - mx))))
        val = lm - sign * s * thr
        best = min(best, np.exp(min(val, 0.0)))
    return best

def np_exact(pa_f, pb_f, n_t=N_T, logN=25, target=1e-9):
    pa = [np.array([float(x) for x in p]) for p in pa_f]; pb = [np.array([float(x) for x in p]) for p in pb_f]
    ell = [np.array([float(mp.log(to_mpf(x)) - mp.log(to_mpf(y))) for x, y in zip(pa_f[t], pb_f[t])]) for t in (0, 1)]
    N = 2 ** logN
    # moments of L under both worlds
    def mv(pw):
        mu = sum(n_t * np.sum(pw[t] * ell[t]) for t in (0, 1))
        var = sum(n_t * (np.sum(pw[t] * ell[t] ** 2) - np.sum(pw[t] * ell[t]) ** 2) for t in (0, 1))
        return mu, np.sqrt(var)
    (mua, sda), (mub, sdb) = mv(pa), mv(pb)
    sd = max(sda, sdb)
    W = 6 * sd
    while True:
        lo, hi = min(mua, mub) - W, max(mua, mub) + W
        tails = []
        for pw in (pa, pb):
            tails.append(chernoff_tail(ell, pw, n_t, hi, +1)); tails.append(chernoff_tail(ell, pw, n_t, lo, -1))
        if max(tails) < target: break
        W *= 1.25
    h = (hi - lo) / (N - 4)
    lt = [np.rint(ell[t] / h).astype(np.int64) for t in (0, 1)]
    lo_i, hi_i = int(np.floor(lo / h)) - 1, int(np.floor(lo / h)) - 1 + N
    def phi(pw):
        out = np.ones(N, dtype=np.complex128)
        for t in (0, 1):
            v = np.zeros(N)
            np.add.at(v, lt[t] % N, pw[t])          # single-term lattice pmf placed on the circle
            out *= np.fft.fft(v) ** n_t             # fft: A[j] = sum_v q_v exp(-2 pi i j v / N); ifft inverts to q_v at index v
        return out
    res = {}
    for name, pw in (("a", pa), ("b", pb)):
        q = np.fft.ifft(phi(pw)).real
        mass = q.sum()
        vals = np.arange(lo_i, hi_i)                  # representatives of residues
        qq = q[vals % N]
        res[name] = dict(P_gt_plus=float(qq[vals > 100].sum()), P_gt_minus=float(qq[vals > -100].sum()),
                         P_tie_band=float(qq[(vals >= -100) & (vals <= 100)].sum()), mass=float(mass), neg_mass=float(np.abs(qq[qq < 0]).sum()))
    alias = max(tails)
    err_lo = 1 - res["a"]["P_gt_minus"] + res["b"]["P_gt_plus"] - 2 * alias
    err_hi = 1 - res["a"]["P_gt_plus"] + res["b"]["P_gt_minus"] + 2 * alias
    return dict(err_sum_lower=err_lo, err_sum_upper=err_hi, h=h, N=N, window=(lo, hi), alias_bound=alias,
                mean_sd_a=(mua, sda), mean_sd_b=(mub, sdb), detail=res)

PLAN = [("F_b", 32), ("F_c", 32), ("F_c2", 32), ("F_b", 128), ("F_c2", 128), ("F_theta0.7", 128), ("F_theta0.8", 128), ("F_theta0.9", 128),
        ("F_b", 512), ("F_theta0.8", 512), ("F_theta0.9", 512)]
CLAIMED_NP = {("F_b", 32): (0.5210, 0.0014, "0.5233 seed2"), ("F_c", 32): (0.1735, 0.0009, ""), ("F_c2", 32): (0.8537, 0.0016, "0.8517 seed2"),
              ("F_b", 128): (0.0967, 0.0007, ""), ("F_c2", 128): (0.1638, 0.0009, "0.1656 seed2"), ("F_theta0.7", 128): (0.3547, 0.0012, ""),
              ("F_theta0.8", 128): (0.5499, 0.0014, ""), ("F_theta0.9", 128): (0.7721, 0.0015, ""), ("F_b", 512): (0.0060, 0.0002, ""),
              ("F_theta0.8", 512): (0.3561, 0.0012, ""), ("F_theta0.9", 512): (0.6581, 0.0015, "")}
if __name__ == '__main__':
    out = {}
    for name, m in PLAN:
        t0 = time.time()
        pa = [pmf(F_A, t, m) for t in (0, 1)]; pb = [pmf(WORLDS[name], t, m) for t in (0, 1)]
        rho = [affinity(pa[t], pb[t]) for t in (0, 1)]
        rp = rho[0] ** N_T * rho[1] ** N_T
        hell_both = 1 - mp.sqrt(1 - rp ** 2); hell_t0 = 1 - mp.sqrt(1 - rho[0] ** (2 * N_T))
        r = np_exact(pa, pb, logN=(24 if m == 512 else 25))
        c = CLAIMED_NP[(name, m)]
        z = (c[0] - 0.5 * (r["err_sum_lower"] + r["err_sum_upper"])) / c[1]
        row = dict(m=m, rho0=mp.nstr(rho[0], 12), rho1=mp.nstr(rho[1], 12), hellinger_both=mp.nstr(hell_both, 8), hellinger_type0_only=mp.nstr(hell_t0, 8),
                   np_bracket=[r["err_sum_lower"], r["err_sum_upper"]], claimed=c, z_claimed=z, h=r["h"], alias=r["alias_bound"], detail=r["detail"],
                   mean_sd=(r["mean_sd_a"], r["mean_sd_b"]))
        out[f"{name}|m={m}"] = row
        print(f"{name:11s} m={m:3d}: rho0={mp.nstr(rho[0],10)} rho1={mp.nstr(rho[1],10)} Hell(both)={mp.nstr(hell_both,6)} Hell(t0)={mp.nstr(hell_t0,6)} "
              f"NP in [{r['err_sum_lower']:.5f}, {r['err_sum_upper']:.5f}]  claimed {c[0]} (SE {c[1]}) z={z:+.2f} {c[2]}  h={r['h']:.2e} alias<={r['alias_bound']:.1e} "
              f"mass={r['detail']['a']['mass']:.9f}/{r['detail']['b']['mass']:.9f} negmass={r['detail']['a']['neg_mass']:.1e}  [{time.time()-t0:.0f}s]", flush=True)
    json.dump(out, open(OUT, "w"), indent=1, default=str)
