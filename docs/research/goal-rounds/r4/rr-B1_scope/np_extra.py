import numpy as np
from scipy.stats import betabinom, binom
from scipy.special import gammaln
import sys

def pmf_beta(m,a,b): return betabinom.pmf(np.arange(m+1),m,a,b)
def pmf_mix(m,atoms,w): return sum(wi*binom.pmf(np.arange(m+1),m,x) for x,wi in zip(atoms,w))
def theta_world(th):
    s=101/th-1
    return [('b',0.2*s,0.8*s),('b',0.25*s,0.75*s)]
W={'a':[('b',20,80),('b',25,75)],'b':[('b',40.5,162),('b',50.6,151.8)],
   'c':[('m',[0.2],[1]),('m',[0.25],[1])],
   'c2':[('m',[81/505,6/25],[101/201,100/201]),('m',[329/1616,29/100],[1616/3491,1875/3491])]}
for th in (0.9,0.8,0.7): W['t%.1f'%th]=theta_world(th)
def pmf(spec,m):
    return pmf_beta(m,spec[1],spec[2]) if spec[0]=='b' else pmf_mix(m,spec[1],spec[2])

def np_min(wa,wb,m,h=2e-4,n=100,cut=1e-16):
    # distribution of L=sum log(pa/pb) under a, on lattice; return E_a[min(1,e^L)] and hellinger
    dists=[];lo_tot=0;rho=1
    for t in (0,1):
        pa=pmf(W[wa][t],m); pb=pmf(W[wb][t],m)
        rho*=np.sum(np.sqrt(pa*pb))**n
        keep=pa>cut
        l=np.log(pa[keep])-np.log(pb[keep]); p=pa[keep]/pa[keep].sum()
        lo=l.min(); idx=np.round((l-lo)/h).astype(int)
        v=np.zeros(idx.max()+1); np.add.at(v,idx,p)
        dists.append((v,lo)); lo_tot+=n*lo
    L=sum(n*(len(v)-1) for v,_ in dists)+1
    N=1<<int(np.ceil(np.log2(L)))
    F=np.ones(N//2+1,complex)
    for v,_ in dists:
        F*=np.fft.rfft(v,N)**n
    d=np.fft.irfft(F,N)[:L]; d=np.clip(d,0,None)
    grid=lo_tot+h*np.arange(L)
    val=np.sum(d*np.minimum(1,np.exp(np.minimum(-grid,50))))
    hel=1-np.sqrt(1-rho**2)
    return val,hel,d.sum()
for wb,m in [("b",64),("b",96),("c2",64),("c2",96)]:
    for h in (1e-4,):
        v,hel,s=np_min('a',wb,m,h=h)
        print(wb,m,h,'NP=%.5f'%v,'Hell=%.5f'%hel,'mass=%.12f'%s,flush=True)
