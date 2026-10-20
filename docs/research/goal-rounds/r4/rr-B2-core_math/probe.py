import sys, numpy as np
sys.path.insert(0,"/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
import sycophancy_phase0.analysis.g6_iv as g; print(g.__file__)
rng=np.random.default_rng(0)
n=200; m=128
t=np.r_[np.zeros(100),np.ones(100)]
r=rng.beta(40.5,162,n); K=rng.binomial(m,r)
for p in (1,2,3):
  base=f(rng.normal(size=n),K,m,t,degree=p)
  print(p, base['ok'], base['min_eig'])
  # finite but huge outcome: sums overflow
  for y in [np.full(n,1.7e308), np.r_[np.full(n//2,1.7e308),np.full(n//2,-1.7e308)], rng.normal(size=n)*1e307, np.full(n,1e300)]:
    try:
      o=f(y,K,m,t,degree=p); print('  ',o['ok'],o['min_eig']==base['min_eig'],o.get('reason'),o.get('beta',[None])[:2])
    except Exception as e: print('  EXC',type(e).__name__,e)
  with np.errstate(all='ignore'):
    pass
# direct: solve with inf rhs
A=np.array([[2.,1],[1,2]])
for b in [np.array([np.inf,1.]),np.array([np.inf,np.inf]),np.array([np.inf,-np.inf]),np.array([np.nan,1.])]:
  try: print(b,np.linalg.solve(A,b))
  except Exception as e: print(b,'EXC',type(e).__name__,e)
