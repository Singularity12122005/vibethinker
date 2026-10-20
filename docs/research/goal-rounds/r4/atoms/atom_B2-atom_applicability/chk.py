import sys, numpy as np
sys.path.insert(0, sys.argv[1])
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng=np.random.default_rng(0)
# G6-like: n=200, 100/100 types, m=32 and 128, degrees 1-3, delta from 16-draw arms, question clusters
bad=0; tot=0
for m in (32,128):
  for p in (1,2,3):
    for rep in range(200):
      t=np.r_[np.zeros(100),np.ones(100)].astype(int)
      r=np.clip(np.where(t==1,0.25,0.2)+0.03*rng.standard_normal(200),0.01,0.99)
      K=rng.binomial(m,r); q=np.repeat(np.arange(50),4)
      outs=[]
      for d in [ (rng.binomial(16,0.4,200)-rng.binomial(16,0.5,200))/16, rng.standard_normal(200), np.full(200,np.nan), np.r_[np.inf,np.zeros(199)], np.r_[np.inf,-np.inf,np.zeros(198)]]:
        for cl in (None,q):
          o=f(d,K,m,t,degree=p,cluster=cl)
          outs.append((o["ok"] or o.get("reason","")[:20], o["min_eig"]))
      # ok status from PD/solve vs b: compare ok-or-reason across finite inputs; non-finite b: pass PD -> ok True (beta nan) or solve error?
      tot+=1
      if len(set(x[1] for x in outs))>1: bad+=1; print("mineig differs",m,p)
      st=set(x[0] for x in outs)
      if len(st)>1: print(m,p,st)
print("tot",tot,"mineig-varies",bad)
# t coded 1/2 instead of 0/1?
