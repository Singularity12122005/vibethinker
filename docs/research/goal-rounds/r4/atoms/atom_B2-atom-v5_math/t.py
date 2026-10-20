import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
import numpy as np
from fractions import Fraction
from sycophancy_phase0.analysis import g6_iv as g
counts=[0,4,2,3,1,4]; t=[0,0,0,1,1,1]; m=4
cm=g.corrected_moment_matrix(counts,m,t,1); print("pd",cm["pd_ok"],cm["min_eig"])
for dh in ([10**400]+[0.0]*5, [Fraction(10**400)]+[0.0]*5, [np.longdouble('1e400')]+[0.0]*5, [0.0]*5, [[0.0]]*6):
    try:
        r=g.endpoint_contrast_poly_cs(dh,counts,m,t,1,None); print("ok",r["ok"],r["min_eig"])
    except Exception as e: print(type(e).__name__, e)
# not-PD case
c2=[4,4,4,4]; t2=[0,0,1,1]
print(g.corrected_moment_matrix(c2,4,t2,1)["pd_ok"])
for dh in ([10**400,0,0,0],[1,2,3,4]):
    try: print(g.endpoint_contrast_poly_cs(dh,c2,4,t2,1,cluster=[1,2]))
    except Exception as e: print(type(e).__name__, e)
g.PD_RTOL=1e9; print(g.corrected_moment_matrix(counts,m,t,1)["pd_ok"])
