import sys, warnings, itertools
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
import numpy as np
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng=np.random.default_rng(0)
# solve with nonfinite b for nonsingular A
bad=0
for trial in range(20000):
    k=rng.integers(3,6)
    A=rng.normal(size=(k,k)); A=A@A.T+np.eye(k)*rng.uniform(0,2)
    if rng.random()<0.3: A=A*10.0**rng.integers(-200,200)
    b=rng.normal(size=k)*10.0**rng.integers(-300,300)
    for i in range(k):
        r=rng.random()
        if r<0.3: b[i]=np.inf*rng.choice([-1,1])
        elif r<0.5: b[i]=np.nan
    try: np.linalg.solve(A,b)
    except np.linalg.LinAlgError: bad+=1
print("LinAlgError from nonfinite b with nonsingular A:",bad)
# singular A: does b matter?
A=np.array([[1.,1],[1,1]])
for b in [np.zeros(2),np.array([np.inf,np.nan]),np.array([1.,2])]:
    try: np.linalg.solve(A,b); print("no err",b)
    except np.linalg.LinAlgError as e: print("err",b,e)
# first sentence: default state, inf delta_hat
K=[0,1,2,3,4,0,2]; t=[0,0,1,1,0,1,1]; m=4
for y in [np.zeros(7), np.full(7,np.inf), np.full(7,np.nan), np.array([np.inf,-np.inf]*3+[np.nan])]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r=f(y,K,m,t,1); print(r["ok"], r["min_eig"], r.get("reason"))
# non-PD case with seterr raise
Kn=[4,4,0,0]; tn=[0,1,0,1]
print(f(np.zeros(4),Kn,4,tn,2)["ok"])
with np.errstate(all="raise"):
    try: print(f(np.zeros(4),Kn,4,tn,2)["ok"])
    except Exception as e: print("raise finite", type(e).__name__)
    try: print(f(np.array([np.inf]*4),Kn,4,tn,2)["ok"])
    except Exception as e: print("raise inf", type(e).__name__, e)
with warnings.catch_warnings():
    warnings.simplefilter("error")
    try: print(f(np.array([np.inf]*4),Kn,4,tn,2)["ok"])
    except Exception as e: print("warnings-error inf", type(e).__name__, e)
print(f(np.array([np.inf]*4),Kn,4,tn,2)["ok"])
