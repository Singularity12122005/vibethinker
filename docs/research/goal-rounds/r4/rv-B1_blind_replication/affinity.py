# Independent re-implementation: exact rational beta-binomial / two-point pmfs, Hellinger affinities (mpmath 60 dps)
from fractions import Fraction as Fr
from math import comb
import mpmath as mp
mp.mp.dps = 60

def rising(x, n):
    out = Fr(1)
    for i in range(n): out *= (x + i)
    return out

def betabin_pmf(m, a, b):
    a, b = Fr(a), Fr(b)
    return [Fr(comb(m,k)) * rising(a,k) * rising(b,m-k) / rising(a+b, m) for k in range(m+1)]

def twopoint_pmf(m, atoms, weights):
    pm = [Fr(0)]*(m+1)
    for r, w in zip(atoms, weights):
        r, w = Fr(r), Fr(w)
        for k in range(m+1):
            pm[k] += w * comb(m,k) * r**k * (1-r)**(m-k)
    return pm

def point_pmf(m, r):
    return twopoint_pmf(m, [r], [1])

def affinity(p, q):
    assert abs(sum(p)-1) == 0 and abs(sum(q)-1) == 0
    return mp.fsum(mp.sqrt(mp.mpf(pk.numerator)/pk.denominator * mp.mpf(qk.numerator)/qk.denominator) for pk, qk in zip(p, q))

def lecam(rho0, rho1, n0=100, n1=100):
    rho = rho0**n0 * rho1**n1
    return 1 - mp.sqrt(1 - rho**2), rho

def mean_var(atoms, weights):
    atoms=[Fr(x) for x in atoms]; weights=[Fr(w) for w in weights]
    mu = sum(a*w for a,w in zip(atoms,weights))
    var = sum(w*(a-mu)**2 for a,w in zip(atoms,weights))
    return mu, var

def beta_mean_var(a,b):
    a,b=Fr(a),Fr(b)
    return a/(a+b), a*b/((a+b)**2*(a+b+1))

Fa = [(20,80),(25,75)]
Fb = [(Fr(81,2),162),(Fr(253,5),Fr(759,5))]
Fc2 = [([Fr(81,505),Fr(6,25)],[Fr(101,201),Fr(100,201)]), ([Fr(329,1616),Fr(29,100)],[Fr(1616,3491),Fr(1875,3491)])]

if __name__=="__main__":
  print("moment checks:")
  for t in range(2):
      print(" type",t,"Fa",beta_mean_var(*Fa[t]),"Fb",beta_mean_var(*Fb[t]),"Fc2",mean_var(*Fc2[t]))
      print("   Fa==Fc2 mean,var:", beta_mean_var(*Fa[t])==mean_var(*Fc2[t]))

  for m in (32,128,512):
      pa = [betabin_pmf(m,*Fa[t]) for t in range(2)]
      pb = [betabin_pmf(m,*Fb[t]) for t in range(2)]
      pc2 = [twopoint_pmf(m,*Fc2[t]) for t in range(2)]
      pc = [point_pmf(m, Fr(1,5)), point_pmf(m, Fr(1,4))]
      for name, pq in (("Fb",pb),("Fc2",pc2),("Fc point",pc)):
          r0 = affinity(pa[0],pq[0]); r1 = affinity(pa[1],pq[1])
          both, rho = lecam(r0,r1)
          only0 = 1 - mp.sqrt(1 - r0**200)
          print(f"m={m} Fa vs {name}: rho0={mp.nstr(r0,10)} rho1={mp.nstr(r1,10)} rho0^100={mp.nstr(r0**100,6)} "
                f"bound_both={mp.nstr(both,6)} bound_type0only={mp.nstr(only0,6)} lowerTV(1-rho)={mp.nstr(1-rho,6)}")
