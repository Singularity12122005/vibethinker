"""Synthesis sanity check: the r4 A-C1 regression test is sensitive to a wrong closed form (mutations must break equality)."""
import sys, re
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/tests")
src = open("/home/user/vibethinker/sycophancy_phase0/tests/test_analysis.py").read()
start = src.index("# ---------------------------------------------------------------- archive r4")
block = src[start:]
mutations = {
    "alpha_sign": ("+ gam[1] * (j == 1 + b)", "- gam[1] * (j == 1 + b)"),
    "drop_Vgamma": ("rho ** 2 + sum(gam[j] * gam[l] * V[j, l] for j in (1, 2) for l in (1, 2))", "rho ** 2"),
    "U2share": ("Fr(221679769, 894945124)", "Fr(221679769, 894945125)"),
    "pilot_m": ("types, mp, m = (0, 0, 1, 1), 2, 4", "types, mp, m = (0, 0, 1, 1), 1, 4"),
}
import numpy as np, pytest
for name, (old, new) in mutations.items():
    assert old in block, name
    ns = {"np": np, "pytest": pytest}
    exec(compile(block.replace(old, new), "mut", "exec"), ns)
    fn = {"alpha_sign": "test_goal_r4_a_c1_candidate_closed_form_sandwich", "drop_Vgamma": "test_goal_r4_a_c1_candidate_closed_form_sandwich",
          "U2share": "test_goal_r4_c1_candidate_reuse_identity", "pilot_m": "test_goal_r4_c1_candidate_reuse_identity"}[name]
    try:
        ns[fn]()
        print(name, "NOT detected")
    except AssertionError as e:
        print(name, "detected")
