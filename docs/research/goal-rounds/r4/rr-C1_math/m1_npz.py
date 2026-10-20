import numpy as np, glob
D="/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/C__Sequential_internal-pilot_design__32___128___re-assess__and_validity_under_reuse/"
for f in sorted(glob.glob(D+"c1_stage1_*.npz")):
    z=np.load(f); rej=z["rej"]; ok=z["ok"]
    print(f.split("/")[-1], rej.shape)
    for s,nm in enumerate(["HC1","CR1"]):
        y=rej[0,s].astype(float)-rej[1,s].astype(float)
        yb=y.mean(1); 
        diff=yb.mean(); se=yb.std(ddof=1)/np.sqrt(len(yb))
        s2=yb.var(ddof=1)-y.var(1,ddof=1).mean()/y.shape[1]
        # sigma_tot and sigma_0
        a=rej[0,s].astype(float).mean(1); b=rej[1,s].astype(float).mean(1)
        s2a=a.var(ddof=1)-rej[0,s].astype(float).var(1,ddof=1).mean()/y.shape[1]
        s2b=b.var(ddof=1)-rej[1,s].astype(float).var(1,ddof=1).mean()/y.shape[1]
        print(f"  {nm} reuse-fresh={diff:.5f} se={se:.5f} z={diff/se:.2f} sig2d={s2:.3e} sig2tot={s2a:.3e} sig2_0={s2b:.3e}")
    # nonpd
    y=(~ok[0,0]).astype(float)-(~ok[1,0]).astype(float); yb=y.mean(1)
    print("  nonpd diff", yb.mean(), yb.std(ddof=1)/np.sqrt(len(yb)), "sig2", yb.var(ddof=1)-y.var(1,ddof=1).mean()/y.shape[1])
