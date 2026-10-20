import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
import numpy as np
import sycophancy_phase0.analysis.g6_iv as g
m=8; t=[0,0,0,1,1,1]
# (1) side-effecting delta_hat conversion: __float__ writes into counts
class Evil:
    def __init__(s,v,c,i): s.v,s.c,s.i=v,c,i
    def __float__(s):
        s.c[s.i]=int(s.v); return float(s.v)
for v in (0.0, 4.0):
    counts=[0,0,0,0,0,0]   # identical at call time
    dh=[Evil(v,counts,i) for i in range(6)]
    r=g.endpoint_contrast_poly_cs(dh,counts,m,t,1)
    print("delta values",v,"-> ok",r["ok"],"min_eig",r["min_eig"])
# (2) PD_RTOL global: same four args, different pd_ok
c=[1,3,5,2,4,6]
print(g.corrected_moment_matrix(c,m,t,1)["pd_ok"])
g.PD_RTOL=10.0
print(g.corrected_moment_matrix(c,m,t,1)["pd_ok"], g.endpoint_contrast_poly_cs([0]*6,c,m,t,1)["ok"])
g.PD_RTOL=1e-9
# (3) cluster-dependent raise after PD branch
try: g.endpoint_contrast_poly_cs([0.1]*6,c,m,t,1,cluster=[1,2]); print("no raise")
except Exception as e: print("raise", type(e).__name__)
