from fractions import Fraction as Fr
from math import comb
import mpmath as mp
import numpy as np
mp.mp.dps = 60

def bb_pmf(m, a, b):
    # exact beta-binomial pmf with rational a,b: C(m,k) (a)_k (b)_{m-k} / (a+b)_m
    a = Fr(a); b = Fr(b)
    def rising(x, n):
        r = Fr(1)
        for i in range(n): r *= (x + i)
        return r
    den = rising(a + b, m)
    return [Fr(comb(m, k)) * rising(a, k) * rising(b, m - k) / den for k in range(m + 1)]

def mix_pmf(m, atoms):
    # atoms: list of (r, w) exact
    out = []
    for k in range(m + 1):
        out.append(sum(Fr(w) * Fr(comb(m, k)) * Fr(r) ** k * (1 - Fr(r)) ** (m - k) for r, w in atoms))
    return out

def affinity(p, q):
    return mp.fsum(mp.sqrt(mp.mpf(x.numerator) / x.denominator * mp.mpf(y.numerator) / y.denominator) for x, y in zip(p, q))

def mom(atoms):
    mu = sum(Fr(r) * Fr(w) for r, w in atoms)
    v = sum(Fr(r) ** 2 * Fr(w) for r, w in atoms) - mu ** 2
    return mu, v

def beta_mom(a, b):
    a = Fr(a); b = Fr(b)
    return a / (a + b), a * b / ((a + b) ** 2 * (a + b + 1))

FA = [(20, 80), (25, 75)]
FB = [(Fr(81, 2), 162), (Fr(253, 5), Fr(759, 5))]
C2 = [[(Fr(81, 505), Fr(101, 201)), (Fr(6, 25), Fr(100, 201))],
      [(Fr(329, 1616), Fr(1616, 3491)), (Fr(29, 100), Fr(1875, 3491))]]
print('moments FA', [beta_mom(*x) for x in FA])
print('moments FB', [tuple(float(y) for y in beta_mom(*x)) for x in FB])
print('moments C2', [mom(x) for x in C2])

def pmfs(world, m):
    kind, spec = world
    if kind == 'beta':
        return [bb_pmf(m, *spec[t]) for t in range(2)]
    if kind == 'mix':
        return [mix_pmf(m, spec[t]) for t in range(2)]

def report(name, wa, wb, m, n=100):
    pa = pmfs(wa, m); pb = pmfs(wb, m)
    rho = [affinity(pa[t], pb[t]) for t in range(2)]
    bc = rho[0] ** n * rho[1] ** n
    bound = 1 - mp.sqrt(1 - bc ** 2)
    b0 = 1 - mp.sqrt(1 - rho[0] ** (2 * n))
    print(f'{name} m={m}: rho0={mp.nstr(rho[0],12)} rho1={mp.nstr(rho[1],12)} rho0^100={mp.nstr(rho[0]**n,8)} '
          f'bound_both={mp.nstr(bound,8)} type0only_bound={mp.nstr(b0,8)}')
    return pa, pb, float(bound)

def np_exact(pa, pb, n=100, N=400000, seed=1):
    rng = np.random.default_rng(seed)
    pa = [np.array([float(x) for x in p]) for p in pa]
    pb = [np.array([float(x) for x in p]) for p in pb]
    llr = [np.log(pb[t]) - np.log(pa[t]) for t in range(2)]  # log dPb/dPa per count
    def sample(p, t):
        # multinomial counts of categories across n draws -> sum of llr
        c = rng.multinomial(n, p[t] / p[t].sum(), size=N)
        return c @ llr[t]
    La = sample(pa, 0) + sample(pa, 1)
    Lb = sample(pb, 0) + sample(pb, 1)
    # min error sum = E_a[min(1, LR)] ; also indicator version
    est1 = np.minimum(1.0, np.exp(La))
    est2 = np.minimum(1.0, np.exp(-Lb))
    e_ind = (La > 0).mean() + (Lb <= 0).mean()
    return est1.mean(), est1.std() / np.sqrt(N), est2.mean(), est2.std() / np.sqrt(N), e_ind
