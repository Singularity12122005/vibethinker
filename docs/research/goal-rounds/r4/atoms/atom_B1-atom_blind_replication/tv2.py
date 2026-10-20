import numpy as np, sys
from scipy.signal import fftconvolve
P=np.load('/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/atom_B1-atom_blind_replication/p.npy')
pa0,pa1,pb0,pb1=P
l0=np.log(pb0/pa0); l1=np.log(pb1/pa1)
CUT=-40.0
h=float(sys.argv[1]); modes=sys.argv[2:]
lost=[0.0]
def conv(a,oa,b,ob):
    c=np.clip(fftconvolve(a,b),0,None); o=oa+ob
    lo=int(np.ceil(CUT/h))-o
    if lo>0:
        lost[0]+=c[:lo].sum(); c=c[lo:]; o+=lo
    nz=np.nonzero(c>1e-300)[0]; c=c[nz[0]:nz[-1]+1]; o+=nz[0]
    return c,o
def vec(p,l,mode):
    f={'floor':np.floor,'ceil':np.ceil,'round':np.round}[mode]
    idx=f(l/h).astype(np.int64); off=idx.min(); v=np.zeros(idx.max()-off+1); np.add.at(v,idx-off,p); return v,off
def power(v,off,n):
    res=None; base,bo=v,off
    while n:
        if n&1: res=(base,bo) if res is None else conv(res[0],res[1],base,bo)
        n>>=1
        if n: base,bo=conv(base,bo,base,bo)
    return res
for mode in modes:
    lost[0]=0.0
    d0,o0=power(*vec(pa0,l0,mode),100); d1,o1=power(*vec(pa1,l1,mode),100)
    d,o=conv(d0,o0,d1,o1)
    s=(np.arange(len(d))+o)*h
    val=np.sum(d*np.minimum(1,np.exp(s)))
    print(mode,h,'mass',d.sum(),'lost',lost[0],'1-TV',val,'upper add',lost[0]*np.exp(-26.7),flush=True)
