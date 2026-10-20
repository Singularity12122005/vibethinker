# Independent numeric check: E[phi^2] via quadrature over r and exact enumeration of K, no polynomial algebra.
import numpy as np
from scipy import stats, special
from math import comb
z=1.959963984540054
def U(K,j,m):
    out=np.ones_like(K,dtype=float)
    for i in range(j): out*= (K-i)/(m-i)
    return out
def world(a0,b0,a1,b1,w1=0.5,N=4000):
    # Gauss-Jacobi-like: use fine grid on quantiles
    res=[]
    for (a,b) in ((a0,b0),(a1,b1)):
        x,wq=special.roots_jacobi(N,b-1,a-1)  # weight (1-x)^(b-1)(1+x)^(a-1) on [-1,1]
        r=(x+1)/2; wq=wq/wq.sum()
        res.append((r,wq))
    return res
def moments_D(W,w1):
    w=[1-w1,w1]
    X=lambda r: np.vstack([np.ones_like(r),r,r*r])
    Qxx=sum(w[t]*(X(W[t][0])*W[t][1])@X(W[t][0]).T for t in (0,1))
    q=w1*(X(W[1][0])@W[1][1])
    g=np.linalg.solve(Qxx,q); D=w1-q@g
    return D,g
def Ephi2(W,w1,m,beta,s2fun):
    D,gam=moments_D(W,w1); w=[1-w1,w1]
    K=np.arange(m+1)
    Us=np.array([U(K,j,m) for j in range(5)])
    tot=0;teta=0;tg=0
    for t in (0,1):
        r,wq=W[t]
        for ri,wi in zip(r,wq):
            pK=stats.binom.pmf(K,m,ri)
            u=Us[:3]; 
            res=t-gam@u   # t - gamma'u per K
            eta_part=s2fun(ri)*np.sum(pK*res**2)
            # Z = psi4_det - gamma' psi_x_det
            e=[sum(beta[b]*(Us[a]*ri**b-Us[a+b]) for b in range(3)) for a in range(3)]
            e4=t*sum(beta[b]*(ri**b-Us[b]) for b in range(3))
            Z=e4-sum(gam[a]*e[a] for a in range(3))
            gpart=np.sum(pK*Z**2)
            teta+=w[t]*wi*eta_part; tg+=w[t]*wi*gpart
    return D,gam,teta,tg
def width(D,tot,n=200): return 2*z*np.sqrt(tot/(n*D*D))
if __name__=="__main__":
    worlds={"narrow":(20,80,25,75),"halfvar":(40.5,162,50.6,151.8),"wide":(2,8,2.5,7.5)}
    beta=(0.18,-0.8,0.0)
    s2g=lambda r:(2*r*(1-r)-(beta[0]+beta[1]*r)**2/2)/16
    for nm,p in worlds.items():
        W=world(*p,N=400)
        D,gam,te,tg=Ephi2(W,0.5,128,beta,s2g)
        _,_,te0,_=Ephi2(W,0.5,100000,beta,s2g) if False else (0,0,0,0)
        print(nm,"D=%.5f"%D,"gamma",np.round(gam,3),"W1(m=128)=%.5f"%width(D,te+tg))
