"""r4 problem-phase cheap check 2b: if the pilot were re-assessed at m = 128 (sequential 32 -> 128 -> decide), how well do the
128-counts of 100 prefixes per type determine V and the sign of lambda_min(H_w) in the narrow world?  Same estimators as check2.
Environment: CPU, python3 / numpy 2.5.3 / scipy 1.18.1, 2026-10-19."""
import sys, json
import numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/problem")
from check2_pilot_information import unbiased_Hw, true_Hw

OUT = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/problem/check2b_lmin_at_128.json"
rng = np.random.default_rng(11)
out = {}
for name, (a, b) in {"narrow_t0": (20, 80), "wide_t0": (2, 8)}.items():
    Hw, mu = true_Hw(a, b)
    for m in (32, 128, 512):
        Vh, lmin = [], []
        for _ in range(5000):
            K = rng.binomial(m, rng.beta(a, b, 100))
            H = unbiased_Hw(K, m); Vh.append(H[0, 0]); lmin.append(np.linalg.eigvalsh(H)[0])
        Vh, lmin = np.array(Vh), np.array(lmin)
        out[f"{name}|m={m}"] = dict(V_true=float(Hw[0, 0]), lmin_true=float(np.linalg.eigvalsh(Hw)[0]), Vhat_sd=float(Vh.std()),
                                    P_Vhat_le_0=float((Vh <= 0).mean()), P_Vhat_LCB95_pos=float((Vh - 1.645 * Vh.std() > 0).mean()),
                                    P_lmin_hat_le_0=float((lmin <= 0).mean()), lmin_hat_q05_50_95=[float(np.percentile(lmin, p)) for p in (5, 50, 95)])
        print(f"{name}|m={m}", json.dumps(out[f"{name}|m={m}"]), flush=True)
json.dump(out, open(OUT, "w"), indent=1)
