import sys, itertools, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng = np.random.default_rng(5)
n=200; m=128
r = np.r_[rng.beta(40.5,162,100), rng.beta(50.6,151.8,100)]; t = np.r_[np.zeros(100), np.ones(100)]
for _ in range(50):
    K = rng.binomial(m, r)
    if f(np.zeros(n), K, m, t, degree=2)["ok"]: break
y = rng.normal(size=n)
for name, cl in [("short cluster", np.arange(10)), ("mixed-type cluster", np.array([None]+list(range(n-1)), dtype=object))]:
    try: print(name, f(y, K, m, t, degree=2, cluster=cl)["ok"])
    except Exception as e: print(name, "RAISES", type(e).__name__, e)
# non-PD case with bad cluster
Kbad = np.full(n, 10)
for name, cl in [("short cluster nonPD", np.arange(10))]:
    print(name, f(y, Kbad, m, t, degree=2, cluster=cl)["ok"])
# search LinAlgError branch over small exhaustive configs
hits = 0; tot=0
for m_ in (2,3,4,5,6):
  for p in range(1, m_//2+1):
    for n_ in (3,4,5):
      for Ks in itertools.product(range(m_+1), repeat=n_):
        for ts in itertools.product((0,1), repeat=n_):
          tot+=1
          o = f(np.ones(n_), Ks, m_, ts, degree=p)
          if o.get("reason","").startswith("corrected moment matrix numerically"): hits+=1
print("small exhaustive configs", tot, "LinAlgError-branch hits", hits)
