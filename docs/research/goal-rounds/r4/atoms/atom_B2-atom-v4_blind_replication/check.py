import sys, numpy as np, itertools
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis import g6_iv as g
import inspect
print(inspect.signature(g.corrected_moment_matrix))
print(inspect.signature(g.endpoint_contrast_poly_cs))
from fractions import Fraction
# exact independent min-eig sign check via exact A
def exactA(K, t, m, p):
    def ff(x,j):
        r=Fraction(1)
        for i in range(j): r*= (x-i)
        return r
    U=lambda x,j: ff(Fraction(x),j)/ff(Fraction(m),j)
    k=p+2; A=[[Fraction(0)]*k for _ in range(k)]
    for Ki,ti in zip(K,t):
        for a in range(p+1):
            for b in range(p+1): A[a][b]+=U(Ki,a+b)
            A[a][k-1]+=U(Ki,a)*ti; A[k-1][a]+=U(Ki,a)*ti
        A[k-1][k-1]+=ti
    return A
rng=np.random.default_rng(0)
cases=[([4,4,0,4],[0,0,1,1],4,2), ([1,2,3,0,4,2],[0,1,0,1,1,0],4,1), ([3,3,3,3],[0,0,1,1],6,1)]
for _ in range(200):
    m=int(rng.integers(2,9)); p=int(rng.integers(1,m//2+1)); n=int(rng.integers(2,10))
    cases.append((rng.integers(0,m+1,n).tolist(), rng.integers(0,2,n).tolist(), m, p))
nbad=0; nfalse=0
for K,t,m,p in cases:
    cm=g.corrected_moment_matrix(K,m,t,p)
    A=np.array([[float(x) for x in row] for row in exactA(K,t,m,p)])
    assert np.allclose(A, cm["A"]), "A mismatch"
    outs=[]
    for trial in range(6):
        y = [np.nan]*len(K) if trial==0 else ([np.inf]*len(K) if trial==1 else rng.normal(size=len(K))*10**trial)
        cl = None if trial%2 else rng.integers(0,3,len(K))
        r=g.endpoint_contrast_poly_cs(y,K,m,t,p,cl)
        outs.append((r["min_eig"], r.get("reason","")=="corrected moment matrix not positive definite; low-order risk variance alone does not diagnose the cause"))
    if len(set(outs))!=1: nbad+=1; print("DEP", K,t,m,p,outs)
    assert outs[0][0]==cm["min_eig"] and outs[0][1]==(not cm["pd_ok"])
    nfalse += (not cm["pd_ok"])
print("cases",len(cases),"dependence",nbad,"nonPD cases",nfalse)
# first case exact: rank check
A=exactA(*cases[0]); import sympy
print("case0 exact det", sympy.Matrix(A).det(), g.corrected_moment_matrix([4,4,0,4],4,[0,0,1,1],2)["pd_ok"])
# shape check
for y,K in [([1,2],[1,2,3]),([[1,2]],[1,2]),(5.0,[1])]:
    try: g.endpoint_contrast_poly_cs(y,K,4,[0,1,0][:len(np.atleast_1d(K))],1); print("no raise",y,K)
    except ValueError as e: print("VE",e)
