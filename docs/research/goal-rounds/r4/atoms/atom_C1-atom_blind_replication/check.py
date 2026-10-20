from fractions import Fraction as F
from math import comb
import random, itertools
random.seed(7)
def pmf(n,p): return [comb(n,k)*p**k*(1-p)**(n-k) for k in range(n+1)]
# joint law of (r,t): r in {1/3,3/4}, t in {0,1} (correlated)
rt = {(F(1,3),0):F(1,5),(F(1,3),1):F(3,10),(F(3,4),0):F(2,5),(F(3,4),1):F(1,10)}
eta_law = {(F(1,3),0):[F(1,2),F(1,2)],(F(1,3),1):[F(1,7),F(6,7)],(F(3,4),0):[F(4,5),F(1,5)],(F(3,4),1):[F(2,3),F(1,3)]}
P = {r:(pmf(32,r),pmf(96,r),pmf(128,r)) for r in (F(1,3),F(3,4))}
def run(f, Dset):
    # joint over (t,k32): numerator P(R, t,k32), P(R',t,k32), P(t,k32)
    pR={};pRp={};pTK={}
    for (r,t),w in rt.items():
        p32,p96,p128=P[r]
        for e,we in enumerate(eta_law[(r,t)]):
            # R' prob given r,t,eta: independent of K32
            qRp = sum(p128[s] for s in range(129) if f(t,s,e))
            for k in range(33):
                base=w*we*p32[k]
                qR = sum(p96[j] for j in range(97) if f(t,k+j,e))
                key=(t,k)
                pR[key]=pR.get(key,0)+base*qR
                pRp[key]=pRp.get(key,0)+base*qRp
                pTK[key]=pTK.get(key,0)+base
    assert sum(pTK.values())==1
    delta={k:(pR[k]-pRp[k])/pTK[k] for k in pTK}
    Ed=sum(pTK[k]*delta[k] for k in pTK)
    pi=sum(pTK[k] for k in Dset)
    lhs=(sum(pR[k] for k in Dset)-sum(pRp[k] for k in Dset))/pi
    cov=sum(pTK[k]*delta[k]*(1 if k in Dset else 0) for k in pTK)-Ed*pi
    var=sum(pTK[k]*delta[k]**2 for k in pTK)-Ed**2
    # bound: lhs^2 <= var*(1-pi)/pi, exact
    ok_bound = lhs**2 <= var*(1-pi)/pi
    return Ed, lhs, cov/pi, ok_bound, float(lhs), float((var*(1-pi)/pi))**.5, float(var)
tab={(t,s,e):random.random()<0.5 for t in (0,1) for s in range(129) for e in (0,1)}
fs=[lambda t,s,e: tab[(t,s,e)], lambda t,s,e: (s>40+20*t) != bool(e), lambda t,s,e: s%3==t]
keys=[(t,k) for t in (0,1) for k in range(33)]
Ds=[set(k for k in keys if random.random()<0.5), set(k for k in keys if k[1]>15), set(k for k in keys if k[0]==1 and k[1]<12)]
for fi,f in enumerate(fs):
    for di,D in enumerate(Ds):
        Ed,lhs,cp,ok,lf,bd,vf=run(f,D)
        print(fi,di,'E[delta]==0:',Ed==0,'identity exact:',lhs==cp,'bound:',ok,'lhs=%.4g bound=%.4g var=%.3g'%(lf,bd,vf))
