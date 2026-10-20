"""Own check of r4 B1 (Le Cam constants, NP minimum) and B2 (non-PD at (200,128) in the half-variance world), not using the
attackers' scripts.  F_a = Beta(20,80)/Beta(25,75); F_b = Beta(40.5,162)/Beta(50.6,151.8) (same means, ~half the variance)."""
import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/verify_r4")
import numpy as np
from scipy import stats
from size_sim import simulate
Fa, Fb = ((20, 80), (25, 75)), ((40.5, 162), (50.6, 151.8))
for (a0, b0), (a1, b1) in zip(Fa, Fb):
    print(f"Beta({a0},{b0}) mean {a0/(a0+b0):.4f} var {a0*b0/((a0+b0)**2*(a0+b0+1)):.6f} | Beta({a1},{b1}) mean {a1/(a1+b1):.4f} var {a1*b1/((a1+b1)**2*(a1+b1+1)):.6f}")
def rho(m, A, B):
    k = np.arange(m + 1)
    return float(np.sum(np.sqrt(stats.betabinom.pmf(k, m, *A) * stats.betabinom.pmf(k, m, *B))))
for m in (32, 128, 512):
    r0, r1 = rho(m, Fa[0], Fb[0]), rho(m, Fa[1], Fb[1])
    both = 1 - np.sqrt(1 - (r0 ** 100 * r1 ** 100) ** 2)
    t0 = 1 - np.sqrt(1 - (r0 ** 100) ** 2)
    print(f"m={m}: rho0 {r0:.10f} rho1 {r1:.10f}  Hellinger bound both types {both:.5f}  type-0 only {t0:.5f}")
# NP-optimal error sum = 1 - TV(P_a, P_b) = P_a(LR_b>LR_a) + P_b(LR_b<=LR_a); MC with the exact LR on 200 counts
rng = np.random.default_rng(42)
m, R = 32, 200000
k = np.arange(m + 1)
llr = [np.log(stats.betabinom.pmf(k, m, *Fb[t])) - np.log(stats.betabinom.pmf(k, m, *Fa[t])) for t in (0, 1)]
def total_llr(world):
    tot = np.zeros(R)
    for t in (0, 1):
        A = world[t]
        K = rng.binomial(m, rng.beta(*A, size=(R, 100)))
        tot += llr[t][K].sum(1)
    return tot
la, lb = total_llr(Fa), total_llr(Fb)
err = np.mean(la > 0) + np.mean(lb <= 0)
se = np.sqrt(np.mean(la > 0) * (1 - np.mean(la > 0)) / R + np.mean(lb <= 0) * (1 - np.mean(lb <= 0)) / R)
print(f"NP (LR test) minimal error sum at m=32, 100+100 prefixes: {err:.4f} (MC SE {se:.4f})")
# B2: non-PD at (200,128) of the production degree-2 test
for name, F, mm, R2 in (("F_b", Fb, 128, 4000), ("F_a", Fa, 128, 4000), ("F_b", Fb, 512, 1500)):
    res = simulate(lambda rng, n, A=F[0]: rng.beta(*A, n), lambda rng, n, A=F[1]: rng.beta(*A, n), 200, mm, R2, seed=7 + mm)
    lo, hi = stats.beta.ppf(0.025, res["nonpd_rate"] * R2, R2 - res["nonpd_rate"] * R2 + 1), stats.beta.ppf(0.975, res["nonpd_rate"] * R2 + 1, R2 - res["nonpd_rate"] * R2)
    print(f"{name} m={mm}: non-PD {res['nonpd_rate']:.4f} [{np.nan_to_num(lo):.4f}, {hi:.4f}]  size|PD {res['size']:.4f}  median width|PD {res['median_width']:.3f}  (R={R2})")
