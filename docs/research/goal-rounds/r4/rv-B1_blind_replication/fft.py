from rep import *
import numpy as np
def fft_min(pa, pb, n=100, h=2e-4):
    # 1 - TV = E_a[min(1, exp(L))], L = sum llr; distribution of L under P_a via FFT on grid
    pa=[np.array([float(x) for x in p]) for p in pa]; pb=[np.array([float(x) for x in p]) for p in pb]
    llr=[np.log(pb[t])-np.log(pa[t]) for t in range(2)]
    mu=sum(n*(pa[t]*llr[t]).sum() for t in range(2))
    sd=np.sqrt(sum(n*((pa[t]*llr[t]**2).sum()-(pa[t]*llr[t]).sum()**2) for t in range(2)))
    lo=mu-60*sd; hi=mu+60*sd
    # shift each prefix llr by its mean so grid centers
    G=int(2**np.ceil(np.log2((hi-lo)/h+10)))
    h=(hi-lo)/(G-10)
    spec=np.ones(G,dtype=complex)
    off=0.0
    for t in range(2):
        c=(pa[t]*llr[t]).sum()
        v=(llr[t]-c)/h
        f=np.floor(v); w=v-f
        arr=np.zeros(G)
        np.add.at(arr,(f.astype(int))%G,pa[t]*(1-w))
        np.add.at(arr,(f.astype(int)+1)%G,pa[t]*w)
        spec*=np.fft.fft(arr)**n
        off+=n*c
    dist=np.real(np.fft.ifft(spec))
    idx=np.arange(G); idx=np.where(idx>G//2,idx-G,idx)
    L=off+idx*h
    return float((np.clip(dist,0,None)*np.minimum(1,np.exp(L))).sum()), float(np.clip(dist,0,None).sum()), h
A=('beta',FA); B=('beta',FB); Cc=('mix',C2)
Cpt=('mix',[[(Fr(1,5),1)],[(Fr(1,4),1)]])
for name,W,ms in [('FB',B,[32,128,512]),('C2',Cc,[32,128,512]),('Cpt',Cpt,[32,128])]:
    for m in ms:
        pa=pmfs(A,m); pb=pmfs(W,m)
        print(name,m,fft_min(pa,pb), fft_min(pa,pb,h=5e-5)[0])
