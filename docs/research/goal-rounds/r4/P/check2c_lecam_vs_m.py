"""r4 problem-phase cheap check 2c: Le Cam two-point lower bound on the sum of error probabilities of ANY rule that
tries to tell the narrow world Beta(20,80) (where the degree-2 test at (200,128) is near-nominal, check1b) from the
half-variance world Beta(40.5,162) (where it is not: non-PD 12.3%, 90th-pct width 0.49, check1b), from 100 prefixes'
counts at m in {32, 128, 512} (type-0 only; the type-1 pair adds a comparable factor).  Exact Beta-binomial pmfs.
Environment: CPU, python 3.13.16 x86_64 / numpy 2.5.3 / scipy 1.18.1, 2026-10-19."""
import json, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/problem")
from check2_pilot_information import betabinom_pmf, lecam
out = {}
for m in (32, 128, 512):
    for lab, (a2, b2) in {"half_var_Beta(40.5,162)": (40.5, 162.0), "double_var_Beta(9.5,38)": (9.5, 38.0)}.items():
        for n in (100, 200):
            res = lecam(betabinom_pmf(m, 20, 80), betabinom_pmf(m, a2, b2), n)
            out[f"narrow_vs_{lab}|m={m}|n={n}"] = res
            print(f"narrow Beta(20,80) vs {lab} | m={m} n={n}: affinity^1={res['affinity_1']:.6f} TV_n<= {res['tv_n_upper']:.3f}  errI+errII >= {res['min_sum_of_errors']:.3f}")
json.dump(out, open("check2c_lecam_vs_m.json", "w"), indent=1)
