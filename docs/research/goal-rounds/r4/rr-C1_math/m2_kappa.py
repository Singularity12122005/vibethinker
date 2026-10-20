# independent quadrature computation of kappa (F32 cap), G32 cap, U2 share, Ut2(5,0.2)
import numpy as np
from scipy import stats
from scipy.special import comb
WORLDS={"narrow":((20,80),(25,75)),"halfvar":((40.5,162),(50.6,151.8)),"wide":((2,8),(2.5,7.5))}
G={"lin":(0.18,-0.8,0.0),"quad":(0.26,-1.6,2.0),"cheb":(0.5,-4.0,4.0)}
x,wq=np.polynomial.legendre.leggauss(400); r=(x+1)/2; wq=wq/2
def U(K,j,m):
    out=np.ones_like(K,dtype=float)
    for i in range(j): out=out*(K-i)/(m-i)
    return out
def Ut(k,j,rr):
    return sum(comb(k,l)*comb(96,j-l)*rr**(j-l) for l in range(j+1))/comb(128,j)
print("Ut2(5,.2)=",Ut(5,2,0.2))
K128=np.arange(129); K32=np.arange(33)
pmf128=stats.binom.pmf(K128[None,:],128,r[:,None]); pmf32=stats.binom.pmf(K32[None,:],32,r[:,None])
for wn,(ab0,ab1) in WORLDS.items():
    dens=[stats.beta.pdf(r,*ab) for ab in (ab0,ab1)]
    # U2 share
    num=den=0
    for t in (0,1):
        f=dens[t]*wq
        Ut2=np.array([[Ut(k,2,rr) for k in K32] for rr in r])
        num+=0.5*np.sum(f[:,None]*pmf32*(Ut2-r[:,None]**2)**2)
        den+=0.5*np.sum(f[:,None]*pmf128*(U(K128,2,128)[None,:]-r[:,None]**2)**2)
    # A_pop
    mu=[[np.sum(dens[t]*wq*r**j) for j in range(5)] for t in (0,1)]
    A=np.zeros((4,4))
    for a in range(3):
        for b in range(3): A[a,b]=(mu[0][a+b]+mu[1][a+b])/2
        A[a,3]=A[3,a]=mu[1][a]/2
    A[3,3]=0.5
    w=np.linalg.solve(A,np.eye(4)[3])
    out=[]
    for gn,(c,b1,b2) in G.items():
        beta=(c,b1,b2); g=c+b1*r+b2*r**2
        veta=(2*r*(1-r)-g**2/2)/16
        Sig=0; Phi=0; PhiB=0
        for t in (0,1):
            f=dens[t]*wq
            # d rows for each (r,K128)
            Us=[U(K128,j,128)[None,:]*np.ones((len(r),1)) for j in range(5)]
            d=np.stack([Us[a]*g[:,None]-sum(beta[bb]*Us[a+bb] for bb in range(3)) for a in range(3)]+[t*(g[:,None]-sum(beta[bb]*Us[bb] for bb in range(3)))],-1)
            u=np.stack([Us[0],Us[1],Us[2],t*np.ones_like(Us[0])],-1)
            wd=d@w; wu=u@w
            Sig+=0.5*np.sum(f[:,None]*pmf128*(wd**2+veta[:,None]*wu**2))
            Uts=[np.array([[Ut(k,j,rr) for k in K32] for rr in r]) for j in range(5)]
            ph=np.stack([Uts[a]*g[:,None]-sum(beta[bb]*Uts[a+bb] for bb in range(3)) for a in range(3)]+[t*(g[:,None]-sum(beta[bb]*Uts[bb] for bb in range(3)))],-1)
            wph=ph@w
            Phi+=0.5*np.sum(f[:,None]*pmf32*wph**2)
            joint=f[:,None]*pmf32; pk=joint.sum(0)
            phibar=(joint*wph).sum(0)/pk
            PhiB+=0.5*np.sum(pk*phibar**2)
        out.append((gn,np.sqrt(Phi/Sig),np.sqrt(PhiB/Sig)))
    print(wn,"U2share",num/den,["%s kappa=%.4f G32=%.4f gauss=%.4f"%(gn,k1,k2,k2*np.sqrt(2/np.pi)) for gn,k1,k2 in out])
