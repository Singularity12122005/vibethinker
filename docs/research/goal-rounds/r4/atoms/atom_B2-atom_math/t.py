import sys, numpy as np, warnings
warnings.simplefilter("ignore")
sys.path.insert(0,"/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f
rng=np.random.default_rng(0)
specials=[np.nan,np.inf,-np.inf,1e308,-1e308,0.0,1e-320]
# 1) solve: raises or not independent of b
bad=0
for trial in range(3000):
    k=rng.integers(2,6)
    A=rng.integers(-2,3,(k,k)).astype(float)
    if rng.random()<0.5: A[-1]=A[0]*rng.integers(-2,3)
    outs=set()
    for bi in range(30):
        b=rng.normal(size=k)*10.0**float(rng.integers(-300,300))
        if bi>0:
            idx=rng.integers(0,k,rng.integers(1,k+1)); b[idx]=rng.choice(specials,idx.size)
        try: np.linalg.solve(A,b); outs.add(0)
        except np.linalg.LinAlgError: outs.add(1)
    if len(outs)>1: bad+=1; print("dep",A)
print("solve b-dependence cases:",bad)
# 2) function: min_eig, ok-branch vs y/cluster
diff=0
for trial in range(2000):
    m=int(rng.integers(2,9)); p=int(rng.integers(1,m//2+1)); n=int(rng.integers(1,8))
    K=rng.integers(0,m+1,n); t=rng.integers(0,2,n)
    res=[]
    for yi in range(8):
        y=rng.normal(size=n)*10.0**float(rng.integers(-300,300))
        if yi>0 and rng.random()<0.7:
            idx=rng.integers(0,n,rng.integers(1,n+1)); y[idx]=rng.choice(specials,idx.size)
        cl=None if yi%2 else rng.integers(0,3,n)
        r=f(y,K,m,t,degree=p,cluster=cl)
        res.append((r["min_eig"], r.get("reason","OK") if not r["ok"] else "OK"))
    if len({x[0] for x in res})>1 or len({x[1] for x in res if x[1]!="OK" and "positive" in x[1]} | {("pd" if "positive" not in x[1] else "npd") for x in res})>2:
        diff+=1
    # pass-or-not of PD and solve-fail
    pd={("npd" if "positive" in x[1] else "pd") for x in res}; sv={x[1]=="corrected moment matrix numerically singular" for x in res if "positive" not in x[1]}
    if len(pd)>1 or len(sv)>1: diff+=1; print("DIFF",m,p,K,t,res)
print("function y/cluster dependence cases:",diff)
# 3) length-mismatch edge: K,t length 1, delta_hat length 2
print(f([0.0],[2],4,[1],1)["min_eig"], f([0.0,0.0],[2],4,[1],1)["min_eig"])
try: f([0.0,0.0],[1,2,3],4,[0,1,1],1)
except Exception as e: print("mismatch:",type(e).__name__)
try: f(np.zeros((3,1)),[1,2,3],4,[0,1,1],1)
except Exception as e: print("column vec:",type(e).__name__, e)
