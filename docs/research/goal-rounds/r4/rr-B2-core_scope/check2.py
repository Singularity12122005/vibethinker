import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng=np.random.default_rng(1)
K=rng.binomial(128,rng.uniform(.05,.6,200)).astype(float); t=np.r_[np.zeros(100),np.ones(100)]
for y in (np.zeros(200), np.full(200,np.nan), np.full(200,np.inf)):
  o=f(y,K,128,t,2); print(o["ok"], o["min_eig"], o.get("t_type"))
try:
  o=f(np.zeros(200),K,128,t,2,cluster=np.arange(10)); print("badcluster ok",o["ok"])
except Exception as e: print("badcluster raises",type(e).__name__)
# drop prefixes post hoc: PD of subset vs full
