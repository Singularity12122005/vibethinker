import numpy as np
from rep import *
def dist_L(pa,pb,n=100,G=2**20):
    pa=[np.array([float(x) for x in p]) for p in pa]; pb=[np.array([float(x) for x in p]) for p in pb]
    llr=[np.log(pb[t])-np.log(pa[t]) for t in range(2)]
    mu=sum(n*(pa[t]*llr[t]).sum() for t in range(2))
    sd=np.sqrt(sum(n*((pa[t]*llr[t]**2).sum()-(pa[t]*llr[t]).sum()**2) for t in range(2)))
    h=(120*sd)/G
    spec=np.ones(G,dtype=complex); off=0
    for t in range(2):
        c=(pa[t]*llr[t]).sum(); v=(llr[t]-c)/h; f=np.floor(v); w=v-f
        arr=np.zeros(G); np.add.at(arr,f.astype(int)%G,pa[t]*(1-w)); np.add.at(arr,(f.astype(int)+1)%G,pa[t]*w)
        spec*=np.fft.fft(arr)**n; off+=n*c
    d=np.clip(np.real(np.fft.ifft(spec)),0,None)
    idx=np.arange(G); idx=np.where(idx>G//2,idx-G,idx); L=off+idx*h
    o=np.argsort(L); return L[o],d[o]
def power(pa,pb,gamma=0.05):
    L,da=dist_L(pa,pb); db=da*np.exp(L)
    print('  check sum db',db.sum(),' 1-TV',np.minimum(da,db).sum())
    cb=np.cumsum(db); i=np.searchsorted(cb,gamma)
    frac=(gamma-(cb[i-1] if i>0 else 0))/db[i]
    pw=da[:i].sum()+frac*da[i]
    return pw, 1-np.minimum(da,db).sum()+gamma
A=('beta',FA)
for name,W in [('FB',('beta',FB)),('C2',('mix',C2))]:
    pa=pmfs(A,32); pb=pmfs(W,32)
    print(name,'NP power at P_b(cert)=0.05:',power(pa,pb))
