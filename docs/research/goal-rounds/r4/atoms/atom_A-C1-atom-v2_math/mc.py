import numpy as np
rng=np.random.default_rng(1); m=4; w=0.5; be=np.array([0.3,-1.0,2.0]); b=0.7
def ff(K,j):
    o=np.ones_like(K,float)
    for i in range(j): o*=(K-i)
    return o
mj=[ff(np.array([m]),j)[0] for j in range(5)]
def draw(n):
    t=(rng.random(n)<w).astype(float)
    r=np.where(t==1,rng.beta(25,75,n),rng.beta(20,80,n))
    K=rng.binomial(m,r).astype(float)
    s=0.2+3*r  # sd
    y=be[0]+be[1]*r+be[2]*r**2+b*t+s*rng.standard_normal(n)
    U=np.stack([ff(K,j)/mj[j] for j in range(5)],1)
    return r,t,K,y,U
def MM(t,y,U):
    n=len(t); M=np.zeros((n,4,4)); mv=np.zeros((n,4))
    for j in range(3):
        for k in range(3): M[:,j,k]=U[:,j+k]
        M[:,j,3]=M[:,3,j]=U[:,j]*t; mv[:,j]=U[:,j]*y
    M[:,3,3]=t; mv[:,3]=t*y
    return M,mv
r,t,K,y,U=draw(4_000_000); M,mv=MM(t,y,U)
A=M.mean(0); th=np.r_[be,b]; psi=mv-np.einsum('nij,j->ni',M,th)
Q=A[:3,:3]; q=A[:3,3]; D=w-q@np.linalg.solve(Q,q) if False else A[3,3]-q@np.linalg.solve(Q,q)
g=np.linalg.solve(Q,q); phi=psi[:,3]-psi[:,:3]@g
V=np.mean(phi**2)/D**2; print("D",D,"theory V",V)
n=4000; est=[0]
if False:
  est=[]
  for rep in range(1):
    r,t,K,y,U=draw(n); M,mv=MM(t,y,U)
    est.append(np.linalg.solve(M.sum(0),mv.sum(0))[3])
est=np.array(est); print("MC var n*Var",n*est.var(),"bias",est.mean()-b)
for n in [40000,200000]:
    est=[]
    for rep in range(1000 if n==40000 else 300):
        r,t,K,y,U=draw(n); M,mv=MM(t,y,U)
        est.append(np.linalg.solve(M.sum(0),mv.sum(0))[3])
    est=np.array(est); iqr=np.subtract(*np.percentile(est,[75,25]))
    print(n,"n*Var",n*est.var(),"n*(IQR/1.349)^2",n*(iqr/1.349)**2,"median bias",np.median(est)-b)
