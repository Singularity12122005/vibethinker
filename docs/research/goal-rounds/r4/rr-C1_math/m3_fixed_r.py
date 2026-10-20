# Frequentist (r fixed) version: outer = (r, K32) drawn from the world; inner = K96, K'128, eta given r.
# E[y|outer] = h - h0 with h = P(R|r,K32); Var over outer = E_r Var(h|r) = Var(h-h0) >= sigma_delta^2 (G32 version).
import sys, numpy as np, time
sys.path.insert(0,"/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/docs/research/goal-rounds/r4/C")
from c_common import WORLDS, G_CLASS, draw_dhat, run_test, between_variance_component, N_T
world, gname, n_out, n_in, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
rng=np.random.default_rng(seed); types=WORLDS[world]; g=G_CLASS[gname]
Y=np.zeros((n_out,n_in)); t0=time.time()
for o in range(n_out):
    r=np.concatenate([rng.beta(*types[0],N_T),rng.beta(*types[1],N_T)])
    K0=rng.binomial(32,r)
    for l in range(n_in):
        dh,_=draw_dhat(rng,r,g); Kr=K0+rng.binomial(96,r); Kf=rng.binomial(128,r)
        Y[o,l]=float(run_test(dh,Kr,128)[1])-float(run_test(dh,Kf,128)[1])
s2=between_variance_component(Y)
B=[]; 
for b in range(2000):
    idx=rng.integers(0,n_out,n_out); B.append(between_variance_component(Y[idx]))
print(world,gname,"sigma_F^2=%.3e sd=%.4f ucl95 sd=%.4f  mean diff=%.5f time %.0f"%(s2,np.sqrt(max(s2,0)),np.sqrt(max(np.quantile(B,.95),0)),Y.mean(),time.time()-t0))
