import sys, warnings, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis import g6_iv as g
from fractions import Fraction
print(np.__version__)
rng=np.random.default_rng(0)
m=6
def Aexact(K,t,m,p):
    from math import perm
    def U(k,j):
        num=1
        for i in range(j): num*= (k-i)
        return Fraction(num, perm(m,j))
    kk=p+2
    A=[[Fraction(0)]*kk for _ in range(kk)]
    for Ki,ti in zip(K,t):
        for a in range(p+1):
            for b in range(p+1): A[a][b]+=U(Ki,a+b)
            A[a][kk-1]+=U(Ki,a)*ti; A[kk-1][a]+=U(Ki,a)*ti
        A[kk-1][kk-1]+=ti
    return A
# replicate A via monkeypatch of eigvalsh to capture
cap={}
orig=np.linalg.eigvalsh
def spy(A): cap['A']=A.copy(); return orig(A)
g.np.linalg.eigvalsh=spy
for p in (1,2,3):
  for trial in range(30):
    n=int(rng.integers(3,12)); K=rng.integers(0,m+1,n); t=rng.integers(0,2,n)
    res=set(); As=[]
    for dh in [rng.normal(size=n), np.full(n,np.nan), np.r_[np.inf, -np.inf*np.ones(n-1)], [float(x) for x in rng.normal(size=n)*1e300], np.zeros(n)]:
      for cl in [None, rng.integers(0,3,n), ['x']*n]:
        with warnings.catch_warnings():
          warnings.simplefilter("ignore")
          try: r=g.endpoint_contrast_poly_cs(dh,K,m,t,degree=p,cluster=cl)
          except Exception as e: r={'ok':'EXC '+repr(e),'min_eig':None}
        As.append(cap['A']); res.add((r['min_eig'], r.get('reason','')[:20] if not r['ok'] or r['ok'] is not True else 'ok_branch_passed_pd'))
    assert all(np.array_equal(As[0],a) for a in As)
    E=np.array(Aexact(K,t,m,p),dtype=object)
    err=max(abs(float(E[i,j])-As[0][i,j]) for i in range(p+2) for j in range(p+2))
    mins={x[0] for x in res}
    pdbranch={x[1].startswith('corrected moment matrix not') for x in res}
    if len(mins)>1 or len(pdbranch)>1: print("DIFF",p,K,t,res)
  print("p",p,"ok; last exact err",err)
# exact singular example from docstring
K=np.array([4,4,0,4]); t=np.array([0,0,1,1])
print(g.endpoint_contrast_poly_cs(np.ones(4),K,4,t,degree=2))
