import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
import sycophancy_phase0.analysis.g6_iv as g
rng = np.random.default_rng(0)
n=200
for m in (32,128):
  for p in (1,2,3):
    agree=0; tot=0; ok_ct=0
    for rep in range(200):
        t = np.repeat([0,1],100); r = np.clip(rng.beta(3,5,n)*0.5+0.1*t,0,1)
        K = rng.binomial(m, r)
        cm = g.corrected_moment_matrix(K, m, t, p)
        q = np.array([f"q{i%40}" for i in range(n)])
        outs = [g.endpoint_contrast_poly_cs(y, K, m, t, p, cl) for y,cl in
                [(rng.normal(size=n), q), (np.full(n,np.nan), None), (rng.binomial(16,.3,n)/16-rng.binomial(16,.3,n)/16, list(q))]]
        same = all(o["min_eig"]==cm["min_eig"] and o["ok"]==False for o in outs) if not cm["pd_ok"] else all(o["min_eig"]==cm["min_eig"] for o in outs)
        agree += same; tot += 1; ok_ct += cm["pd_ok"]
    print(m,p,"consistent",agree,"/",tot,"pd_ok rate",ok_ct/tot)
# type coded 1/2 as in plan wording: no error raised
t12 = np.repeat([1,2],100); K = rng.binomial(32, .3, n)
print("type 1/2 accepted:", g.corrected_moment_matrix(K,32,t12,1)["pd_ok"])
# pandas inputs
try:
    import pandas as pd
    o = g.endpoint_contrast_poly_cs(pd.Series(rng.normal(size=n)), pd.Series(K), 32, pd.Series(np.repeat([0,1],100)), 1, pd.Series(q))
    print("pandas ok:", o["ok"])
except ImportError: print("no pandas")
