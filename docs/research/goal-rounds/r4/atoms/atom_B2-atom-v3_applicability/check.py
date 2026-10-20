import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng=np.random.default_rng(0)
n=200; t=np.repeat([0,1],100); q=rng.integers(0,40,n)
for m,p in [(32,1),(32,2),(32,3),(128,2)]:
    K=rng.binomial(m,np.clip(0.2+0.05*t+rng.normal(0,.03,n),0,1))
    outs=set()
    for trial in range(30):
        d=rng.integers(-16,17,n)/16.0
        if trial%3==0: d[rng.integers(0,n,5)]=np.nan
        if trial%5==0: d[0]=np.inf
        cl=None if trial%2 else q
        o=f(d,K,m,t,degree=p,cluster=cl); outs.add((o["ok"] if "beta" not in o or True else None, o["min_eig"], o.get("reason")))
    print(m,p,{(a,c) for a,b,c in outs}, len({b for a,b,c in outs}))
try:
    import pandas as pd
    s=pd.Series([0.1,pd.NA],dtype="Float64")
    print(np.asarray(s,float))
    s2=pd.Series([0.1,None],dtype=object); print(np.asarray(s2,float))
except Exception as e: print("pandas:",type(e).__name__,e)
