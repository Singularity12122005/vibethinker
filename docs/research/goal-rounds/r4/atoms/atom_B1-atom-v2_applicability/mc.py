import numpy as np
from scipy.stats import betabinom
m=32;k=np.arange(m+1)
pa=[betabinom.pmf(k,m,20,80),betabinom.pmf(k,m,25,75)]
pb=[betabinom.pmf(k,m,40.5,162),betabinom.pmf(k,m,50.6,151.8)]
l=[np.log(pb[t]/pa[t]) for t in (0,1)]
print("llr range",[ (x.min(),x.max()) for x in l])
rng=np.random.default_rng(1)
res=[];resb=[]
for rep in range(40):
    N=100000
    L=np.zeros(N); Lb=np.zeros(N)
    for t in (0,1):
        Ka=rng.choice(m+1,size=(N,100),p=pa[t]); L+=l[t][Ka].sum(1)
        Kb=rng.choice(m+1,size=(N,100),p=pb[t]); Lb+=l[t][Kb].sum(1)
    res.append(np.minimum(1,np.exp(L)).mean()); resb.append(np.minimum(1,np.exp(-Lb)).mean())
res=np.array(res);resb=np.array(resb)
print("E_a min(1,LR):",res.mean(),"+-",res.std()/np.sqrt(len(res)))
print("E_b min(1,1/LR):",resb.mean(),"+-",resb.std()/np.sqrt(len(resb)))
