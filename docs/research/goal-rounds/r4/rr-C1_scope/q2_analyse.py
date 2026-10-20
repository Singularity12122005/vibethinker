import sys, os, glob
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/docs/research/goal-rounds/r4/C")
import numpy as np
from c_common import between_variance_component, bootstrap_outer
HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(11)
for f in sorted(glob.glob(os.path.join(HERE, "q1_*.npz"))):
    z = np.load(f); y = z["y"].astype(float); rr = z["rr"].astype(float); pd32 = z["pd32"]; vh = z["vh"]
    print("==", os.path.basename(f), y.shape, "P(PD32)=%.3f" % pd32.mean())
    for s, nm in enumerate(("HC1", "CR1")):
        est = between_variance_component(y[s]); b = bootstrap_outer(between_variance_component, [y[s]], rng, 2000)
        ucl = np.sqrt(max(np.percentile(b, 95), 0))
        estt = between_variance_component(rr[s]); bt = bootstrap_outer(between_variance_component, [rr[s]], rng, 2000)
        uclt = np.sqrt(max(np.percentile(bt, 95), 0))
        ybar = y[s].mean(1)
        out = []
        for rn, D in (("PD32", pd32), ("Vhat>med", vh > np.median(vh))):
            out.append(f"{rn}: pi={D.mean():.3f} reuse-fresh={ybar[D].mean():+.5f} se {ybar[D].std(ddof=1)/np.sqrt(D.sum()):.5f}")
        print(f"  {nm}: size_reuse={rr[s].mean():.4f} reuse-fresh={y[s].mean():+.5f}  sigma_delta^2={est:.2e} UCL sd={ucl:.5f} "
              f"bound@.1={3*ucl:.4f} | sd(P(R|G32)) UCL={uclt:.5f} x3={3*uclt:.4f} | " + " ; ".join(out))
