import numpy as np
from scipy.stats import betabinom
m=32;k=np.arange(m+1)
pa0=betabinom.pmf(k,m,20,80); pa1=betabinom.pmf(k,m,25,75)
pb0=betabinom.pmf(k,m,40.5,162); pb1=betabinom.pmf(k,m,50.6,151.8)
L0=np.log(pa0/pb0); L1=np.log(pa1/pb1)
rng=np.random.default_rng(7); s=0;s2=0;n_tot=0
for _ in range(80):
  n=500000
  for (p0,p1) in [(pa0,pa1),(pb0,pb1)]:
    L=rng.multinomial(100,p0,size=n)@L0+rng.multinomial(100,p1,size=n)@L1
    v=np.abs(np.tanh(L/2)); s+=v.sum(); s2+=(v*v).sum(); n_tot+=n
mu=s/n_tot; sd=np.sqrt(s2/n_tot-mu*mu)/np.sqrt(n_tot)
print("1-TV",1-mu,"se",sd)
# linear-interp grid
for h in [1e-3,5e-4,2.5e-4]:
  o0=L0.min();o1=L1.min(); span=100*(L0.max()-o0+L1.max()-o1)
  N=1<<int(np.ceil(np.log2(span/h+10)))
  def g(p,L,o):
    t=(L-o)/h; i=np.floor(t).astype(int); f=t-i; G=np.zeros(N)
    np.add.at(G,i,p*(1-f)); np.add.at(G,i+1,p*f); return np.fft.rfft(G)
  ga=np.fft.irfft(g(pa0,L0,o0)**100*g(pa1,L1,o1)**100,N)
  x=100*(o0+o1)+h*np.arange(N)
  w=np.clip(1-np.exp(-x),0,None)
  print(h,1-np.sum(ga*w))
