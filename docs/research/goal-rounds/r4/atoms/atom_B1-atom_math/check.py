import numpy as np
from mpmath import mp, mpf, binomial, exp, log, sqrt, loggamma
def betaln(a,b): return loggamma(a)+loggamma(b)-loggamma(a+b)
mp.dps=40
m=32
def bb(a,b):
    a=mpf(str(a)); b=mpf(str(b))
    return [binomial(m,k)*exp(betaln(k+a,m-k+b)-betaln(a,b)) for k in range(m+1)]
pa0=bb(20,80); pa1=bb(25,75); pb0=bb(40.5,162); pb1=bb(50.6,151.8)
r0=sum(sqrt(x*y) for x,y in zip(pa0,pb0)); r1=sum(sqrt(x*y) for x,y in zip(pa1,pb1))
print('rho0',mp.nstr(r0,15),'rho1',mp.nstr(r1,15))
print('hell',mp.nstr(1-sqrt(1-r0**200*r1**200),15))
# TV via binned log-LR tracking both masses
h=2e-5
def dist(pa,pb):
    pa=np.array([float(x) for x in pa]); pb=np.array([float(x) for x in pb])
    S=np.log(pa/pb); idx=np.round(S/h).astype(int)
    return idx,pa,pb
def conv_power(idx,pa,pb,n):
    off=idx.min(); L=idx.max()-off+1
    A=np.zeros(L); B=np.zeros(L)
    np.add.at(A,idx-off,pa); np.add.at(B,idx-off,pb)
    from scipy.signal import fftconvolve
    # repeated squaring with direct fft conv
    resA=np.array([1.0]); resB=np.array([1.0]); roff=0
    baseA,baseB,boff=A,B,off
    while n:
        if n&1:
            resA=fftconvolve(resA,baseA); resB=fftconvolve(resB,baseB); roff+=boff
        n>>=1
        if n:
            baseA=fftconvolve(baseA,baseA); baseB=fftconvolve(baseB,baseB); boff*=2
    return np.clip(resA,0,None),np.clip(resB,0,None),roff
from scipy.signal import fftconvolve
A0,B0,o0=conv_power(*dist(pa0,pb0),100)
A1,B1,o1=conv_power(*dist(pa1,pb1),100)
A=fftconvolve(A0,A1); B=fftconvolve(B0,B1); off=o0+o1
A=np.clip(A,0,None);B=np.clip(B,0,None)
pos=np.arange(len(A))+off
tv_lb=np.sum(np.clip(A-B,0,None))
near=np.abs(pos)<=200
print('sumA',A.sum(),'sumB',B.sum())
print('TV lb',tv_lb,'1-TV',1-tv_lb,'near-zero mass',(A[near]+B[near]).sum())
# also sanity: using bins TV-ish
# second check: Monte Carlo
rng=np.random.default_rng(0)
def samp(p,n,N):
    p=np.array([float(x) for x in p]);p/=p.sum()
    return rng.choice(m+1,size=(N,n),p=p)
N=200000
la0=np.log(np.array([float(x) for x in pa0])/np.array([float(x) for x in pb0]))
la1=np.log(np.array([float(x) for x in pa1])/np.array([float(x) for x in pb1]))
S=la0[samp(pa0,100,N)].sum(1)+la1[samp(pa1,100,N)].sum(1)
print('MC TV',np.mean(np.clip(1-np.exp(-S),0,None)))
# rule check on small example
pa=np.array([.7,.3]); pb=np.array([.2,.8]); phi=(pa<pb).astype(float)
print('stated rule value',np.sum(pa*(1-phi)+pb*phi),'1-TV',1-0.5*np.abs(pa-pb).sum(),'1+TV',1+0.5*np.abs(pa-pb).sum())
