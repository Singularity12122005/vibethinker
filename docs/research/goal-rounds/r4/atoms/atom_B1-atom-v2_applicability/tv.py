import numpy as np
from scipy.stats import betabinom
from scipy.signal import fftconvolve
m=32;k=np.arange(m+1)
pa=[betabinom.pmf(k,m,20,80),betabinom.pmf(k,m,25,75)]
pb=[betabinom.pmf(k,m,40.5,162),betabinom.pmf(k,m,50.6,151.8)]
for h in (2e-3,1e-3,5e-4):
    def dist(p,q):
        l=np.log(q/p); idx=np.round(l/h).astype(int); off=-idx.min()
        d=np.zeros(idx.max()+off+1); np.add.at(d,idx+off,p); return d,off
    tot=np.array([1.0]); toff=0
    for t in (0,1):
        d,off=dist(pa[t],pb[t]); acc=np.array([1.0]); aoff=0
        n=100; base=d; boff=off
        while n:  # binary exponentiation
            if n&1: acc=fftconvolve(acc,base); aoff+=boff; acc=np.clip(acc,0,None)
            n>>=1
            if n: base=np.clip(fftconvolve(base,base),0,None); boff*=2
        tot=np.clip(fftconvolve(tot,acc),0,None); toff+=aoff
    L=(np.arange(len(tot))-toff)*h
    print(h, tot.sum(), np.sum(tot*np.minimum(1,np.exp(L))))
