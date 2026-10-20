# 1-TV = E_a[min(1,e^{-L})], min(1,e^{-x}) = e^{-x/2} e^{-|x|/2}, e^{-|x|/2} = int (1/(2pi)) /(1/4+t^2) e^{itx} dt
# => 1-TV = (1/pi) int_0^inf Re psi(t)/(1/4+t^2) dt, psi(t)= g0(t)^100 g1(t)^100, g_j(t)=sum_k sqrt(pa pb) e^{-i t l(k)}
import mpmath as mp, numpy as np
from scipy import integrate
mp.mp.dps=40; m=32
def bb(a,b):
    a=mp.mpf(a);b=mp.mpf(b)
    return [mp.binomial(m,k)*mp.beta(k+a,m-k+b)/mp.beta(a,b) for k in range(m+1)]
P=[(bb(20,80),bb('40.5',162)),(bb(25,75),bb('50.6','151.8'))]
W=[];Lv=[]
for pa,pb in P:
    W.append(np.array([float(mp.sqrt(x*y)) for x,y in zip(pa,pb)]))
    Lv.append(np.array([float(mp.log(x/y)) for x,y in zip(pa,pb)]))
def logpsi(t):
    t=np.atleast_1d(t)
    s=0
    for w,l in zip(W,Lv):
        g=(w[None,:]*np.exp(-1j*np.outer(t,l))).sum(1)
        s=s+100*np.log(g)
    return s
def integrand(t):
    return np.real(np.exp(logpsi(t)))/(0.25+t**2)/np.pi
# magnitude survey
for t in [0,0.1,0.2,0.5,1,2,5,10,50]:
    print(t,abs(np.exp(logpsi(t)))[0])
ts=np.linspace(1,2000,2_000_001)
mx=0
for c in np.array_split(ts,200):
    mx=max(mx,np.abs(np.exp(logpsi(c))).max())
print('max|psi| on [1,2000]',mx)
val,err=integrate.quad(lambda t: integrand(t)[0],0,5,limit=500,epsabs=1e-13,epsrel=1e-13)
val2,err2=integrate.quad(lambda t: integrand(t)[0],5,50,limit=2000,epsabs=1e-13)
print('1-TV ~',val+val2,err,err2, 'tail bound beyond 50:', mx/(np.pi*50))
mx=0
for a,b in [(50,2000),(2000,20000)]:
    ts=np.linspace(a,b,int((b-a)*500)+1)
    for c in np.array_split(ts,max(1,len(ts)//20000)):
        mx=max(mx,np.abs(np.exp(logpsi(c))).max())
print('max|psi| on [50,20000]',mx, 'tail beyond 20000 <=',1/(np.pi*20000))
# brute-force check of identity and of part (i) on a tiny example: 3 counts, m=2
import itertools
rng=np.random.default_rng(1)
qa=[rng.dirichlet(np.ones(3)) for _ in range(2)]; qb=[rng.dirichlet(np.ones(3)) for _ in range(2)]
types=[0,0,1]
pa={};pb={}
for K in itertools.product(range(3),repeat=3):
    pa[K]=np.prod([qa[t][k] for t,k in zip(types,K)]); pb[K]=np.prod([qb[t][k] for t,k in zip(types,K)])
tv=0.5*sum(abs(pa[K]-pb[K]) for K in pa)
phi={K:float(pa[K]>pb[K]) for K in pa}
err=sum(pa[K]*(1-phi[K])+pb[K]*phi[K] for K in pa)
r=[np.sum(np.sqrt(qa[t]*qb[t])) for t in range(2)]
print('tiny: err',err,'1-TV',1-tv,'hell',1-np.sqrt(1-(r[0]**2*r[1])**2))
for _ in range(1000):
    ph={K:rng.random() for K in pa}
    assert sum(pa[K]*(1-ph[K])+pb[K]*ph[K] for K in pa)>=1-tv-1e-15
W=[np.sqrt(qa[t]*qb[t]) for t in range(2)]; Lv=[np.log(qa[t]/qb[t]) for t in range(2)]
def ps(t):
    g=[(W[j]*np.exp(-1j*t*Lv[j])).sum() for j in range(2)]
    return g[0]**2*g[1]
v,_=integrate.quad(lambda t: np.real(ps(t))/(0.25+t*t)/np.pi,0,np.inf,limit=5000)
print('fourier tiny',v)
