import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
K=[0,1,2,3,4,1,2,3]; t=[0,0,0,0,1,1,1,1]; m=4
print(f([0.1]*8,K,m,t,1)["min_eig"], f([np.inf,np.nan]+[1.0]*6,K,m,t,1))
for d in ([[0.1]]*8, [[0.1,0.2]]*8):
    print(len(d), np.asarray(d,float).shape)
    try: print(f(d,K,m,t,1))
    except Exception as e: print("RAISED before eigen test:", type(e).__name__, e)
