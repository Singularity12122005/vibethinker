import numpy as np
from scipy.stats import betabinom
from mpmath import mp, mpf, sqrt as msqrt
m=32;k=np.arange(m+1)
pa0=betabinom.pmf(k,m,20,80); pa1=betabinom.pmf(k,m,25,75)
pb0=betabinom.pmf(k,m,40.5,162); pb1=betabinom.pmf(k,m,50.6,151.8)
r0=np.sum(np.sqrt(pa0*pb0)); r1=np.sum(np.sqrt(pa1*pb1))
print("%.12f %.12f"%(r0,r1))
mp.dps=30
R0=mpf(r0);R1=mpf(r1)
print(1-msqrt(1-R0**200*R1**200))
# exact-ish TV via grid FFT on L = log pa/pb
for h in [2e-3,1e-3,5e-4]:
  L0=np.log(pa0/pb0); L1=np.log(pa1/pb1)
  lo=100*(L0.min()+L1.min()); hi=100*(L0.max()+L1.max())
  # truncate range for practicality: use mean +- 40 sd
  N=1<<int(np.ceil(np.log2((hi-lo)/h+10)))
  def pmfgrid(p,L,off):
    g=np.zeros(N); idx=np.round((L-off)/h).astype(int); np.add.at(g,idx,p); return g
  o0=L0.min(); o1=L1.min()
  fa=np.fft.rfft(pmfgrid(pa0,L0,o0))**100*np.fft.rfft(pmfgrid(pa1,L1,o1))**100
  fb=np.fft.rfft(pmfgrid(pb0,L0,o0))**100*np.fft.rfft(pmfgrid(pb1,L1,o1))**100
  ga=np.fft.irfft(fa,N); gb=np.fft.irfft(fb,N)
  x=100*(o0+o1)+h*np.arange(N)
  tv=np.sum(np.clip(ga-gb,0,None)); tv2=ga[x>0].sum()-gb[x>0].sum()
  print(h,N,1-tv,1-tv2, ga.sum())
