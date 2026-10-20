import numpy as np, sys
from scipy.signal import fftconvolve
P=np.load('/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/atom_B1-atom_blind_replication/p.npy')
pa0,pa1,pb0,pb1=P
l0=np.log(pb0/pa0); l1=np.log(pb1/pa1)
print('l range',l0.min(),l0.max(),l1.min(),l1.max())
def dist(p,l,h,mode,n=100):
    if mode=='floor': idx=np.floor(l/h).astype(np.int64)
    elif mode=='ceil': idx=np.ceil(l/h).astype(np.int64)
    else: idx=np.round(l/h).astype(np.int64)
    off=idx.min(); v=np.zeros(idx.max()-off+1); np.add.at(v,idx-off,p)
    # power n by squaring, trimming tiny mass
    res=np.array([1.0]); roff=0; base=v; boff=off; k=n
    while k:
        if k&1:
            res=np.clip(fftconvolve(res,base),0,None); roff+=boff
        k>>=1
        if k:
            base=np.clip(fftconvolve(base,base),0,None); boff*=2
            # trim
            nz=np.nonzero(base>1e-300)[0]; base=base[nz[0]:nz[-1]+1]; boff+=nz[0]
        nz=np.nonzero(res>1e-300)[0]; res=res[nz[0]:nz[-1]+1]; roff+=nz[0]
    return res,roff
h=float(sys.argv[1])
for mode in ['floor','round','ceil']:
    d0,o0=dist(pa0,l0,h,mode); d1,o1=dist(pa1,l1,h,mode)
    d=np.clip(fftconvolve(d0,d1),0,None); o=o0+o1
    s=(np.arange(len(d))+o)*h
    print(mode,h,'mass',d.sum(),'1-TV',np.sum(d*np.minimum(1,np.exp(s))))
