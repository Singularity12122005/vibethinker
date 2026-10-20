import numpy as np
from scipy.stats import betabinom
m=32;k=np.arange(m+1)
pa0=betabinom.pmf(k,m,20,80); pa1=betabinom.pmf(k,m,25,75)
pb0=betabinom.pmf(k,m,40.5,162); pb1=betabinom.pmf(k,m,50.6,151.8)
L0=np.log(pa0/pb0); L1=np.log(pa1/pb1)
rng=np.random.default_rng(1); vals=[]
for _ in range(40):
  n=500000
  c0=rng.multinomial(100,pa0,size=n); c1=rng.multinomial(100,pa1,size=n)
  L=c0@L0+c1@L1
  vals.append(np.clip(1-np.exp(-L),0,None))
v=np.concatenate(vals); print(1-v.mean(), v.std()/np.sqrt(len(v)))
