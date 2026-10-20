"""Reviewer: recompute sigma_delta^2 (one-way ANOVA between component) from the c1 npz with an independent implementation,
an analytic (delta-method / jackknife) UCL, and a split-half check (estimate on inner halves, cross-product estimator
Cov_o(ybar_A, ybar_B), which is unbiased for Var(delta) without any noise subtraction)."""
import glob, os, sys
import numpy as np
D = sys.argv[1]
for f in sorted(glob.glob(os.path.join(D, "c1_stage1_*.npz"))):
    z = np.load(f)
    for s, sn in enumerate(("HC1", "CR1")):
        for ev in ("reject", "nonpd"):
            if ev == "reject":
                y = z["rej"][0, s].astype(float) - z["rej"][1, s].astype(float)
            else:
                y = z["ok"][0, s].astype(float) - z["ok"][1, s].astype(float)
            n_out, n_in = y.shape
            yb = y.mean(1); s2 = y.var(1, ddof=1)
            est = yb.var(ddof=1) - s2.mean() / n_in
            # split-half cross-product estimator
            ya, yb2 = y[:, : n_in // 2].mean(1), y[:, n_in // 2:].mean(1)
            cross = np.mean((ya - ya.mean()) * (yb2 - yb2.mean())) * n_out / (n_out - 1)
            # jackknife SE of est over outer units
            tot1 = yb.sum(); tot2 = (yb ** 2).sum(); s2s = s2.sum()
            jk = np.empty(n_out)
            for o in range(n_out):
                m1 = (tot1 - yb[o]) / (n_out - 1); m2 = (tot2 - yb[o] ** 2) / (n_out - 1)
                v = (m2 - m1 ** 2) * (n_out - 1) / (n_out - 2)
                jk[o] = v - (s2s - s2[o]) / (n_out - 1) / n_in
            se = np.sqrt((n_out - 1) / n_out * np.sum((jk - jk.mean()) ** 2))
            ucl = est + 1.645 * se
            print(f"{os.path.basename(f)[10:-4]:14s} {sn} {ev:7s} est={est:.3e} cross={cross:.3e} jackSE={se:.2e} "
                  f"normalUCL95={ucl:.3e} sd_ucl={np.sqrt(max(ucl,0)):.4f}  P(y!=0)={np.mean(y!=0):.4f}")
