import sys, importlib.util, itertools
from fractions import Fraction
import numpy as np
P="/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py"
spec=importlib.util.spec_from_file_location("g6",P); g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
import inspect
print("default pd_rtol", inspect.signature(g.corrected_moment_matrix).parameters['pd_rtol'].default)

def falling(x,j):
    o=Fraction(1)
    for i in range(j): o*=(x-i)
    return o
def exactA(counts,m,t,p):
    k=p+2; A=[[Fraction(0)]*k for _ in range(k)]
    for K,ti in zip(counts,t):
        U=[falling(Fraction(K),j)/falling(Fraction(m),j) for j in range(2*p+1)]
        for a in range(p+1):
            for b in range(p+1): A[a][b]+=U[a+b]
            A[a][k-1]+=U[a]*ti; A[k-1][a]+=U[a]*ti
        A[k-1][k-1]+=ti
    return A
def det(M):
    M=[r[:] for r in M]; n=len(M); d=Fraction(1)
    for c in range(n):
        piv=next((r for r in range(c,n) if M[r][c]!=0),None)
        if piv is None: return Fraction(0)
        if piv!=c: M[c],M[piv]=M[piv],M[c]; d=-d
        d*=M[c][c]
        for r in range(c+1,n):
            f=M[r][c]/M[c][c]
            for cc in range(c,n): M[r][cc]-=f*M[c][cc]
    return d
def exact_pd(A):  # Sylvester
    return all(det([r[:i] for r in A[:i]])>0 for i in range(1,len(A)+1))

# exact example 1: docstring singular case m=4,p=2, class 0 counts (4,4)? class1 (0,4)
for counts,t,m,p in [([4,4,0,4],[0,0,1,1],4,2),([3,1,2,0,4,2,1,3],[0,0,0,0,1,1,1,1],4,2),([5,2,7,1,3,6,0,4],[0,1,0,1,0,1,0,1],8,1)]:
    A=exactA(counts,m,t,p); cm=g.corrected_moment_matrix(counts,m,t,p)
    maxdiff=max(abs(float(A[i][j])-cm["A"][i,j]) for i in range(p+2) for j in range(p+2))
    print("exact A match maxdiff",maxdiff,"exactPD",exact_pd(A),"det",det(A),"pd_ok",cm["pd_ok"],"min_eig",cm["min_eig"])

# invariance tests
rng=np.random.default_rng(1)
bad=0; trials=0
for trial in range(400):
    m=int(rng.integers(2,10)); p=int(rng.integers(1,m//2+1)); n=int(rng.integers(0,9))
    counts=rng.integers(0,m+1,n).astype(float)
    if trial%7==0 and n>0: counts[0]=np.inf
    if trial%11==0 and n>0: counts[-1]=np.nan
    t=rng.integers(0,2,n)
    cl0=None
    ref=None
    for dh,cl in [(rng.normal(size=n),None),(np.full(n,np.nan),list(range(n))),(list(rng.normal(size=n)*1e300),rng.integers(0,2,n)),
                  (counts,None),(np.zeros(n),["a"]*n),([np.float32(1)]*n,np.arange(n+3))]:
        cm_counts=list(counts) if trial%2 else counts
        try:
            with np.errstate(all="ignore"):
                r=g.endpoint_contrast_poly_cs(dh,cm_counts,m,t,p,cl)
            out=("ret", r["min_eig"], r.get("reason","").startswith("corrected moment matrix not positive"))
        except Exception as e:
            out=("exc",type(e).__name__)
        try:
            with np.errstate(all="ignore"):
                cm=g.corrected_moment_matrix(counts,m,t,p)
        except Exception as e:
            cmexc=type(e).__name__
            if out!=("exc",cmexc): bad+=1; print("BAD cm-exc mismatch",out,cmexc)
            trials+=1; continue
        trials+=1
        if out[0]=="ret":
            same_me = (np.isnan(out[1]) and np.isnan(cm["min_eig"])) or out[1]==cm["min_eig"]
            if not same_me or out[2]!=(not cm["pd_ok"]): bad+=1; print("BAD",trial,out,cm["min_eig"],cm["pd_ok"])
        else:
            if not cm["pd_ok"]: bad+=1; print("BAD exc in nonPD",trial,out)
print("trials",trials,"bad",bad)
# counts aliasing / mutation
c=np.array([1.,2,3,0]); t=np.array([0,1,0,1]); cc=c.copy()
g.endpoint_contrast_poly_cs(c,c,4,t,1)
print("counts unchanged", np.array_equal(c,cc))
# PD_RTOL change
c=[4,4,0,4]; t=[0,0,1,1]
a=g.corrected_moment_matrix(c,4,t,2)["pd_ok"]; g.PD_RTOL=1e300; b=g.corrected_moment_matrix(c,4,t,2)["pd_ok"]; g.PD_RTOL=-1; cc2=g.corrected_moment_matrix(c,4,t,2)["pd_ok"]
c3=[5,2,7,1,3,6,0,4]; t3=[0,1,0,1,0,1,0,1]
print("PD_RTOL change effect", a,b,cc2, g.corrected_moment_matrix(c3,8,t3,1)["pd_ok"])
# conversion of delta_hat raising non-ValueError
try: g.endpoint_contrast_poly_cs([10**400]*4,[1,2,3,0],4,[0,1,0,1],1)
except Exception as e: print("huge int delta_hat:",type(e).__name__,e)
try: g.endpoint_contrast_poly_cs(np.zeros((2,2)),[1,2,3,0],4,[0,1,0,1],1)
except Exception as e: print("2d delta:",type(e).__name__)
