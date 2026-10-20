import sys, warnings, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis import g6_iv as g
K=np.array([0,2,5,6,3,1]); t=np.array([0,1,0,1,1,0]); m=6
def run(dh, **kw):
    try: r=g.endpoint_contrast_poly_cs(dh,K,m,t,degree=1); return (r['ok'], r['min_eig'])
    except Exception as e: return 'EXC '+type(e).__name__+': '+str(e)[:80]
print("base", run(np.ones(6)))
print("2D (n,1)", run(np.ones((6,1))), len(np.ones((6,1))))
print("np.matrix col", run(np.matrix(np.ones((6,1)))))
dh=[np.inf]*6
with np.errstate(all='raise'): print("seterr raise, inf", run(dh))
with warnings.catch_warnings():
    warnings.simplefilter('error'); print("warnings error, default errstate, inf", run(dh))
print(np.geterr())
# solve with nonfinite b
rng=np.random.default_rng(1)
cnt=0
for trial in range(2000):
    k=int(rng.integers(2,6)); X=rng.normal(size=(k+3,k)); A=X.T@X
    if trial%3==0: A[0,1]=A[1,0]=np.sqrt(A[0,0]*A[1,1])*(1-1e-7)
    for b in [np.full(k,np.inf), np.r_[np.inf,-np.inf,np.zeros(k-2)], np.full(k,np.nan), rng.normal(size=k)*1e308, np.r_[np.nan, np.inf, np.zeros(k-2)]]:
        try: np.linalg.solve(A,b)
        except np.linalg.LinAlgError: cnt+=1
print("LinAlgError count nonsingular A with nonfinite b:", cnt)
# singular A raises for all b?
S=np.array([[1.,1.],[1.,1.]])
for b in [np.ones(2), np.full(2,np.nan), np.full(2,np.inf)]:
    try: np.linalg.solve(S,b); print("no raise")
    except np.linalg.LinAlgError as e: print("raise", e)
