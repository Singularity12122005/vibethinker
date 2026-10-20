import numpy as np
from scipy import stats, special
from numpy.polynomial.legendre import leggauss
m=10; w1=0.5; beta=np.array([0.,1.,1.]); b=0.5
def U(K,j): return special.poch(K-j+1,j)/special.poch(m-j+1,j) if j>0 else np.ones_like(K)
def falling(K,j):
    out=np.ones_like(K,dtype=float)
    for i in range(j): out=out*(K-i)
    return out
def Uj(K,j): return falling(K,j)/falling(np.array([float(m)]),j)[0]
# beta-dist quadrature via fine grid
def beta_rule(a,bb,N=4000):
    x,w=leggauss(N); r=(x+1)/2; w=w/2*stats.beta.pdf(r,a,bb); return r,w/w.sum()
def gauss_rule(r,w,k):  # k-point Gauss rule matching moments up to 2k-1 (Golub-Welsch via Stieltjes on discrete measure)
    # Lanczos/Stieltjes
    p_prev=np.zeros_like(r); p=np.ones_like(r); al=[];be=[]
    nrm_prev=1
    for i in range(k):
        nrm=np.sum(w*p*p); a_i=np.sum(w*r*p*p)/nrm; al.append(a_i)
        bi = nrm/nrm_prev if i>0 else 0; be.append(bi)
        p_new=(r-a_i)*p-(bi*p_prev if i>0 else 0); p_prev,p=p,p_new; nrm_prev=nrm
    J=np.diag(al)+np.diag(np.sqrt(be[1:]),1)+np.diag(np.sqrt(be[1:]),-1)
    ev,V=np.linalg.eigh(J); return ev, V[0]**2
def analyze(rules, sig2):
    # rules: {t:(r,w)}
    wt={0:1-w1,1:w1}
    Qxx=np.zeros((3,3)); q=np.zeros(3)
    for t,(r,w) in rules.items():
        X=np.vstack([r**0,r,r**2])
        Qxx+=wt[t]*(X*w)@X.T; q+=wt[t]*t*(X*w).sum(1)
    gam=np.linalg.solve(Qxx,q); D=w1-q@gam
    Ks=np.arange(m+1.0); Ev=0; mom=[]
    for t,(r,w) in rules.items():
        pk=stats.binom.pmf(Ks[None,:],m,r[:,None])  # nodes x K
        Uk=[Uj(Ks,j) for j in range(5)]
        a=t-sum(gam[j]*Uk[j] for j in range(3))
        c=-t*sum(beta[k]*Uk[k] for k in range(3))-b*t+sum(gam[j]*(sum(beta[k]*Uk[j+k] for k in range(3))+b*t*Uk[j]) for j in range(3))
        mu=(beta[0]+beta[1]*r+beta[2]*r**2+b*t)[:,None]
        val=a[None,:]**2*sig2(r)[:,None]+(a[None,:]*mu+c[None,:])**2
        Ev+=wt[t]*np.sum(w[:,None]*pk*val)
        mom.append([np.sum(w*r**k) for k in range(9)])
    return D,Ev,Ev/D**2,np.array(mom)
r0,w0=beta_rule(20,80); r1,w1r=beta_rule(25,75)
D,_,_,_=analyze({0:(r0,w0),1:(r1,w1r)},lambda r:np.ones_like(r)); print("D",round(D,6))
g1=gauss_rule(r1,w1r,6)  # matches moments to 11
sig=lambda r:(r>0.25).astype(float)
A=analyze({0:(r0,w0),1:(r1,w1r)},sig); B=analyze({0:(r0,w0),1:g1},sig)
print("Beta F1 : D=%.6f V=%.6f"%(A[0],A[2])); print("Gauss F1: D=%.6f V=%.6f"%(B[0],B[2]))
print("max moment diff orders 0..8:",np.abs(A[3]-B[3]).max())
s1=lambda r:np.ones_like(r)
print("const sigma: ",analyze({0:(r0,w0),1:(r1,w1r)},s1)[2],analyze({0:(r0,w0),1:g1},s1)[2])
