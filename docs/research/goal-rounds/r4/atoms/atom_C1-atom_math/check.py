import numpy as np
from scipy.stats import binom
rng=np.random.default_rng(0)
worst=0
for trial in range(200):
    rs=np.array([0.1,0.5,0.85]); pr=rng.dirichlet(np.ones(3))
    ts=[0,1]; pt_r=rng.dirichlet(np.ones(2),size=3)  # P(t|r)
    pe=rng.random((3,2))  # P(eta=1|r,t)
    f=rng.integers(0,2,size=(2,129,2))
    # D: random subset of (t,k32)
    Dset=rng.integers(0,2,size=(2,33))
    # joint over (r,t,k32): compute P(R|t,k32) and P(R'|t,k32)
    num=np.zeros((2,33)); numR=np.zeros((2,33)); numRp=np.zeros((2,33))
    for a,r in enumerate(rs):
        p32=binom.pmf(np.arange(33),32,r); p96=binom.pmf(np.arange(97),96,r); p128=binom.pmf(np.arange(129),128,r)
        for t in ts:
            w=pr[a]*pt_r[a,t]
            fe=f[t,:,1]*pe[a,t]+f[t,:,0]*(1-pe[a,t])  # P(R=1|count) given r,t
            Rp=(p128*fe).sum()
            for k in range(33):
                RR=(p96*fe[k:k+97]).sum()
                num[t,k]+=w*p32[k]; numR[t,k]+=w*p32[k]*RR; numRp[t,k]+=w*p32[k]*Rp
    delta=(numR-numRp)/num; P=num
    Ed=(P*delta).sum(); pi=(P*Dset).sum()
    if not(0<pi<1): continue
    lhs=((P*Dset*(numR-numRp)/num).sum())/pi
    cov=(P*Dset*delta).sum()-Ed*pi
    sd=np.sqrt((P*delta**2).sum()-Ed**2)
    bound=sd*np.sqrt((1-pi)/pi)
    assert abs(Ed)<1e-12 and abs(lhs-cov/pi)<1e-12, (Ed,lhs,cov/pi)
    worst=max(worst,abs(lhs)/bound if bound>0 else 0)
print("ok, max |lhs|/bound =",worst)
