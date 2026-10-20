import sys
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
import numpy as np
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
Kn=[4,4,0,0]; tn=[0,1,0,1]
print(f([0,0,0,0],Kn,4,tn,2))
try: print(f([10**400,0,0,0],Kn,4,tn,2))
except Exception as e: print("raised", type(e).__name__, e)
