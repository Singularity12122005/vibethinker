"""Self-test of np_exact against brute-force enumeration on a tiny problem (n_t=2, m=3)."""
import itertools, numpy as np
import rev_b1_exact as R
from fractions import Fraction as Fr
m, n_t = 3, 2
pa = [R.bb_pmf(m, 2, 8), R.bb_pmf(m, 3, 7)]; pb = [R.bb_pmf(m, Fr(9, 2), 18), R.disc_pmf(m, [Fr(1, 5), Fr(3, 10)], [Fr(1, 2), Fr(1, 2)])]
ell = [[float(np.log(float(x) / float(y))) for x, y in zip(pa[t], pb[t])] for t in (0, 1)]
Pa = Pb = 0.0
for ks in itertools.product(range(m + 1), repeat=2 * n_t):
    L = sum(ell[0][k] for k in ks[:n_t]) + sum(ell[1][k] for k in ks[n_t:])
    wa = np.prod([float(pa[0][k]) for k in ks[:n_t]] + [float(pa[1][k]) for k in ks[n_t:]])
    wb = np.prod([float(pb[0][k]) for k in ks[:n_t]] + [float(pb[1][k]) for k in ks[n_t:]])
    if L > 0: Pa += wa; Pb += wb
print("brute force err_sum =", 1 - Pa + Pb)
r = R.np_exact(pa, pb, n_t=n_t, logN=16)
print("fft bracket =", r["err_sum_lower"], r["err_sum_upper"], "h", r["h"], "alias", r["alias_bound"])
