import sys, numpy as np
sys.path.insert(0,"/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng=np.random.default_rng(1); n=200; m=128
t=np.r_[np.zeros(100),np.ones(100)]; K=rng.binomial(m,rng.beta(40.5,162,n))
y=rng.normal(size=n)
print(f(y,K,m,t,1)['ok'])
for cl in [np.arange(n+1), np.arange(n-1), ["a"]*n, np.r_[np.full(n,np.nan)]]:
  try: o=f(y,K,m,t,1,cluster=cl); print('cl ok',o['ok'],o['se'][-1])
  except Exception as e: print('cl EXC',type(e).__name__,str(e)[:60])
# singular A with finite y: LinAlgError branch reachable?
A=np.array([[1.,1],[1,1]])
try: np.linalg.solve(A,np.array([1.,2]))
except Exception as e: print('sing',type(e).__name__)
# seterr raise with inf y
old=np.seterr(all='raise')
for yy in [np.r_[np.inf, y[1:]], np.r_[1e308, y[1:]]]:
  try: o=f(yy,K,m,t*1e10,1); print('raise-mode ok',o['ok'])
  except Exception as e: print('raise-mode EXC',type(e).__name__,str(e)[:50])
np.seterr(**old)
# PD decision differs? exhaustive small check: tiny n, p=2, many y
from itertools import product
bad=0
for _ in range(2000):
  nn=6; mm=4; KK=rng.integers(0,mm+1,nn); tt=rng.integers(0,2,nn)
  outs={ (o['ok'],o['min_eig']) for o in (f(rng.normal(size=nn)*s,KK,mm,tt,2,cluster=c) for s in (1e-300,1,1e300) for c in (None,np.arange(nn)%2))}
  bad+= len(outs)>1
print('small-n disagreements',bad)
