import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng = np.random.default_rng(7)
laws = {
 "mix_point": lambda n: np.where(rng.random(n)<.5, .2, .25),
 "uniform_narrow": lambda n: rng.uniform(.15,.3,n),
 "logitnormal": lambda n: 1/(1+np.exp(-rng.normal(-1.3,.3,n))),
 "atoms3": lambda n: rng.choice([.05,.2,.6],n),
}
tot=0; mism=0; nonpd=0
for name,law in laws.items():
  for m in (16,32,128,512):
    for p in (1,2,3):
      if 2*p>m: continue
      for rep in range(30):
        n=200; t=np.r_[np.zeros(100),np.ones(100)]
        r=law(n); K=rng.binomial(m,r).astype(float)
        cl=np.repeat(np.arange(50),4)
        ref=None
        for g in range(4):
          for ev in range(3):
            y = (g*r**2 - r + .3*t*g) + rng.normal(0, [0,.1,1][ev], n) + (rng.standard_t(2,n) if ev==2 else 0)
            for c in (None, cl, rng.integers(0,7,n)):
              o=f(y,K,m,t,degree=p,cluster=c); tot+=1
              key=(o["ok"],o["min_eig"])
              if ref is None: ref=key
              elif key!=ref: mism+=1
        nonpd += (not ref[0])
print("calls",tot,"mismatch",mism,"nonpd draws",nonpd)
# t coded 1/2 and NaN/inf delta
K=rng.binomial(128,rng.uniform(.15,.3,200)).astype(float); t2=np.r_[np.ones(100),2*np.ones(100)]
a=f(np.zeros(200),K,128,t2,2); b=f(np.full(200,np.nan),K,128,t2,2); c=f(np.full(200,np.inf),K,128,t2,2)
print(a["ok"],b["ok"],c["ok"],a["min_eig"]==b["min_eig"]==c["min_eig"])
# wrong length cluster
try:
  o=f(np.zeros(200),K,128,t2,2,cluster=np.arange(10)); print("badcluster ok",o["ok"])
except Exception as e: print("badcluster raises",type(e).__name__)
