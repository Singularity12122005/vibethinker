import sys, numpy as np
sys.path.insert(0, sys.argv[1])
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng=np.random.default_rng(0); n=200; m=32
t=np.r_[np.zeros(100),np.ones(100)].astype(int)
r=np.clip(np.where(t==0,0.2,0.25)+0.03*rng.standard_normal(n),0,1)
K=rng.binomial(m,r); q=np.repeat(np.arange(50),4)
for p in (1,2,3):
    outs=set()
    for y in (rng.standard_normal(n), np.full(n,np.nan), np.full(n,np.inf), rng.integers(-16,17,n)/16):
        for c in (None,q):
            o=f(y,K,m,t,degree=p,cluster=c); outs.add((o["ok"],o["min_eig"],o.get("reason")))
    print(p,outs)
