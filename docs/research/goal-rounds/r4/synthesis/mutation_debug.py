import sys, traceback
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
src = open("/home/user/vibethinker/sycophancy_phase0/tests/test_analysis.py").read()
block = src[src.index("# ---------------------------------------------------------------- archive r4"):]
import numpy as np, pytest
ns = {"np": np, "pytest": pytest}
exec(compile(block.replace("types, mp, m = (0, 0, 1, 1), 2, 4", "types, mp, m = (0, 0, 1, 1), 1, 4"), "mut", "exec"), ns)
try:
    ns["test_goal_r4_c1_candidate_reuse_identity"]()
except AssertionError:
    traceback.print_exc(limit=-1)
