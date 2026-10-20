import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/C__Sequential_internal-pilot_design__32___128___re-assess__and_validity_under_reuse")
from c_common import between_variance_component
D = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/review_C1_scope/"
rng = np.random.default_rng(7)
for n in ["iid", "clu70", "clu90"]:
    d = np.load(D + f"s1_{n}.npz"); y = d["y"]; rr = d["rej_r"]
    print(f"== {n}  n_out={y.shape[1]} n_in={y.shape[2]}  ESS_min median {np.median(d['ess_min']):.0f} q05 {np.quantile(d['ess_min'],.05):.0f}  P(PD32)={d['pd32'].mean():.3f}")
    for s, lab in enumerate(["HC1", "CR1"]):
        Y = y[s]; s2 = between_variance_component(Y)
        bs = np.array([between_variance_component(Y[rng.integers(0, Y.shape[0], Y.shape[0])]) for _ in range(1000)])
        ucl = np.sqrt(max(np.quantile(bs, .95), 0))
        # also total conditional-size variance under reuse (selection+reuse): Var(P(R|G32))
        R = rr[s].astype(float); s2t = between_variance_component(R)
        bst = np.array([between_variance_component(R[rng.integers(0, R.shape[0], R.shape[0])]) for _ in range(1000)])
        uclt = np.sqrt(max(np.quantile(bst, .95), 0))
        pd = d["pd32"]; ybar = Y.mean(1)
        print(f"  {lab}: size_reuse={R.mean():.4f} reuse-fresh={Y.mean():+.4f}  sigma_delta^2={s2:.2e} UCL sd={ucl:.6f}  bound@.5/.25/.1={ucl:.6f}/{ucl*np.sqrt(3):.6f}/{ucl*3:.6f} | "
              f"Var(P(R|G32)) UCL sd={uclt:.6f} (x3={uclt*3:.6f}) | rule PD32: reuse-fresh {ybar[pd].mean():+.5f} se {ybar[pd].std()/np.sqrt(pd.sum()):.5f}")
