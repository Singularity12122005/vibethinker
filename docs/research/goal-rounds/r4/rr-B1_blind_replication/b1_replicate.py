"""Independent blind replication of claim B1 (r4): Hellinger bound and NP minimum 1-TV.
Exact rational pmfs (Fraction), affinities in mpmath at 60 digits, TV by grid convolution
of the per-prefix log-likelihood ratio, tracking P_a and P_b masses separately per bin."""
import sys, json
from fractions import Fraction as Fr
from math import comb
import mpmath as mp
import numpy as np
from scipy.signal import fftconvolve

mp.mp.dps = 60


def bb_pmf(m, a, b):
    a = Fr(a); b = Fr(b)
    out = []
    for k in range(m + 1):
        num = Fr(comb(m, k))
        for j in range(k):
            num *= a + j
        for j in range(m - k):
            num *= b + j
        den = Fr(1)
        for j in range(m):
            den *= a + b + j
        out.append(num / den)
    return out


def mix_pmf(m, atoms):  # atoms: list of (r, w)
    out = []
    for k in range(m + 1):
        s = Fr(0)
        for r, w in atoms:
            s += w * Fr(comb(m, k)) * r ** k * (1 - r) ** (m - k)
        out.append(s)
    return out


def check_pmf(p):
    assert sum(p) == 1, "pmf does not sum to 1"


def world(name, m):
    if name == 'a':
        return [bb_pmf(m, 20, 80), bb_pmf(m, 25, 75)]
    if name == 'b':
        return [bb_pmf(m, Fr(81, 2), 162), bb_pmf(m, Fr(253, 5), Fr(759, 5))]
    if name == 'c':
        return [mix_pmf(m, [(Fr(1, 5), Fr(1))]), mix_pmf(m, [(Fr(1, 4), Fr(1))])]
    if name == 'c2':
        return [mix_pmf(m, [(Fr(81, 505), Fr(101, 201)), (Fr(6, 25), Fr(100, 201))]),
                mix_pmf(m, [(Fr(329, 1616), Fr(1616, 3491)), (Fr(29, 100), Fr(1875, 3491))])]
    if name.startswith('th'):
        th = Fr(name[2:])
        s = Fr(101) / th - 1
        out = []
        for mu in (Fr(1, 5), Fr(1, 4)):
            out.append(bb_pmf(m, mu * s, (1 - mu) * s))
        return out
    raise ValueError(name)


def affinity(p, q):
    return mp.fsum(mp.sqrt(mp.mpf(x.numerator) / x.denominator * mp.mpf(y.numerator) / y.denominator)
                   for x, y in zip(p, q))


def trim(pa, pb, lo, eps):
    """drop tail bins whose cumulative mass under both a and b is < eps; return dropped mass."""
    tot = pa + pb
    c = np.cumsum(tot)
    i0 = np.searchsorted(c, eps)
    cr = np.cumsum(tot[::-1])
    j0 = np.searchsorted(cr, eps)
    i1 = len(tot) - j0
    dropped_a = pa[:i0].sum() + pa[i1:].sum()
    dropped_b = pb[:i0].sum() + pb[i1:].sum()
    return pa[i0:i1].copy(), pb[i0:i1].copy(), lo + i0, dropped_a, dropped_b


def conv(A, B, eps):
    pa1, pb1, lo1 = A; pa2, pb2, lo2 = B
    pa = np.clip(fftconvolve(pa1, pa2), 0, None)
    pb = np.clip(fftconvolve(pb1, pb2), 0, None)
    return trim(pa, pb, lo1 + lo2, eps)


def type_dist(pa_list, pb_list, h, n, eps):
    la = np.array([float(mp.log(mp.mpf(x.numerator) / x.denominator)) for x in pa_list])
    lb = np.array([float(mp.log(mp.mpf(x.numerator) / x.denominator)) for x in pb_list])
    fa = np.array([float(x) for x in pa_list]); fb = np.array([float(x) for x in pb_list])
    keep = (fa > 1e-30) | (fb > 1e-30)
    drop = (fa[~keep].sum(), fb[~keep].sum())
    l = la[keep] - lb[keep]
    idx = np.rint(l / h).astype(np.int64)
    lo = idx.min(); size = idx.max() - lo + 1
    if size > 5_000_000:
        raise RuntimeError('grid too large %d' % size)
    pa = np.zeros(size); pb = np.zeros(size)
    np.add.at(pa, idx - lo, fa[keep]); np.add.at(pb, idx - lo, fb[keep])
    base = (pa, pb, int(lo))
    dropped = [n * drop[0], n * drop[1]]
    result = None
    cur = base
    k = n
    while k:
        if k & 1:
            if result is None:
                result = cur
            else:
                r = conv(result, cur, eps); result = r[:3]; dropped[0] += r[3]; dropped[1] += r[4]
        k >>= 1
        if k:
            r = conv(cur, cur, eps); cur = r[:3]; dropped[0] += r[3] * 2; dropped[1] += r[4] * 2
    return result, dropped


def tv(Wa, Wb, h=1e-4, eps=1e-16, n=100):
    d0, dr0 = type_dist(Wa[0], Wb[0], h, n, eps)
    d1, dr1 = type_dist(Wa[1], Wb[1], h, n, eps)
    pa, pb, lo, da, db = conv(d0, d1, eps)
    grid = (np.arange(len(pa)) + lo)
    diff = pa - pb
    # LR test on the rounded statistic: certify-region = {Lr > t}; best t gives a valid test
    pos = diff > 0
    tv_bins = diff[pos].sum()  # = max over unions of bins (optimal test measurable wrt bins)
    tv_thr0 = diff[grid > 0].sum() + 0.5 * diff[grid == 0].sum()
    return dict(tv_bins=float(tv_bins), tv_thr0=float(tv_thr0),
                np_bins=1 - float(tv_bins), np_thr0=1 - float(tv_thr0),
                dropped=float(sum(dr0) + sum(dr1) + da + db), bins=len(pa))


def hell(Wa, Wb):
    r0 = affinity(Wa[0], Wb[0]); r1 = affinity(Wa[1], Wb[1])
    return dict(rho0=mp.nstr(r0, 20), rho1=mp.nstr(r1, 20),
                rho0_100=mp.nstr(r0 ** 100, 10),
                hell=mp.nstr(1 - mp.sqrt(1 - r0 ** 200 * r1 ** 200), 10),
                hell_t0=mp.nstr(1 - mp.sqrt(1 - r0 ** 200), 10))


if __name__ == '__main__':
    cells = [(32, 'b'), (32, 'c2'), (32, 'c'), (128, 'b'), (128, 'c2'), (128, 'th9/10'),
             (128, 'th4/5'), (128, 'th7/10'), (512, 'b'), (512, 'th9/10'), (512, 'th4/5')]
    if len(sys.argv) > 1:
        cells = [c for c in cells if str(c[0]) in sys.argv[1:]]
    hs = [1e-4, 2.5e-5] if all(c[0] == 32 for c in cells) else [1e-4, 5e-5]
    out = {}
    for m, w in cells:
        Wa = world('a', m); Wb = world(w, m)
        for P in Wa + Wb:
            check_pmf(P)
        res = dict(m=m, world=w, **hell(Wa, Wb))
        for h in hs:
            try:
                res['h=%g' % h] = tv(Wa, Wb, h=h)
            except RuntimeError as e:
                res['h=%g' % h] = str(e)
        print(json.dumps(res), flush=True)
        out['%d_%s' % (m, w)] = res
    json.dump(out, open(__file__.replace('.py', '_%s.json' % '_'.join(sys.argv[1:] or ['all'])), 'w'), indent=1)
