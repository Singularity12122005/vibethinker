import sys, numpy as np, itertools
from fractions import Fraction
sys.path.insert(0,'/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src')
import sycophancy_phase0.analysis.g6_iv as g
rec={}
orig_eig=np.linalg.eigvalsh; orig_solve=np.linalg.solve
def eig(A): rec['A']=A.copy(); return orig_eig(A)
def solve(A,b):
    rec['SA']=A.copy(); rec['b']=b.copy()
    try: return orig_solve(A,b)
    except np.linalg.LinAlgError: rec['raised']=True; raise
g.np.linalg.eigvalsh=eig; g.np.linalg.solve=solve
def ff(x,j):
    r=Fraction(1)
    for i in range(j): r*=(x-i)
    return r
def exactA(K,t,m,p):
    k=p+2; A=[[Fraction(0)]*k for _ in range(k)]
    for Ki,ti in zip(K,t):
        U=[ff(Fraction(Ki),j)/ff(Fraction(m),j) for j in range(2*p+1)]
        for a in range(p+1):
            for b in range(p+1): A[a][b]+=U[a+b]
            A[a][k-1]+=U[a]*ti; A[k-1][a]+=U[a]*ti
        A[k-1][k-1]+=ti
    return A
rng=np.random.default_rng(1)
bad=0; cnt=0; nraise=0; npd=0
with np.errstate(all='ignore'):
  pass
import warnings; warnings.simplefilter('ignore')
for trial in range(400):
    m=int(rng.integers(2,9)); p=int(rng.integers(1,m//2+1)); n=int(rng.integers(1,7))
    K=rng.integers(0,m+1,n); t=rng.integers(0,2,n)
    outs=[]
    ys=[rng.normal(size=n), np.full(n,np.nan), np.full(n,np.inf), np.where(rng.random(n)<.5,np.inf,-np.inf), np.zeros(n), 1e308*np.ones(n)]
    cls=[None, np.arange(n), np.zeros(n,int)]
    for y,c in itertools.product(ys,cls):
        rec.clear()
        try: r=g.endpoint_contrast_poly_cs(y,K,m,t,degree=p,cluster=c)
        except Exception as e: r={'exc':repr(e)}
        outs.append((rec['A'].tobytes(), r.get('min_eig'), r.get('reason'), 'SA' in rec, rec.get('raised',False), r.get('ok')))
        cnt+=1
    Aset={o[0] for o in outs}; me={o[1] for o in outs}; pdb={o[2]=='corrected moment matrix not positive definite; low-order risk variance alone does not diagnose the cause' for o in outs}
    reached={o[3] for o in outs}; raised={o[4] for o in outs}
    Aex=exactA(K,t,m,p); Af=np.frombuffer(next(iter(Aset))).reshape(p+2,p+2)
    exact_ok=np.allclose(Af,np.array([[float(x) for x in row] for row in Aex]),rtol=1e-12,atol=1e-12)
    if len(Aset)!=1 or len(me)!=1 or len(pdb)!=1 or len(reached)!=1 or len(raised)!=1 or not exact_ok:
        bad+=1; print('BAD',m,p,K,t,outs[:3])
    if True in raised: nraise+=1
    if True in pdb: npd+=1
print('trials',400,'calls',cnt,'bad',bad,'notPD trials',npd,'solve-raised trials',nraise)
# solve(A,b) raise depends on A only: singular A that would pass to solve
Ss=[np.array([[1.,1,0],[1,1,0],[0,0,1]]), np.array([[1.,2],[2,4]]), np.zeros((3,3)), np.array([[0.,1],[1,0]]), np.array([[2.,1,1],[1,3,2],[1,2,4]])]
bs=lambda k:[np.ones(k), np.full(k,np.nan), np.full(k,np.inf), np.array([np.inf,-np.inf]+[np.nan]*(k-2)), np.full(k,1e308)]
for S in Ss:
    res=[]
    for b in bs(S.shape[0]):
        try: x=orig_solve(S,b); res.append(False)
        except np.linalg.LinAlgError: res.append(True)
    print(S.shape, res)
# nonsingular nondiagonal A where getrs produces inf-inf
A=np.array([[1.,1],[1,2]])
print(orig_solve(A,np.array([np.inf,np.inf])), orig_solve(A,np.array([np.inf,-np.inf])))
