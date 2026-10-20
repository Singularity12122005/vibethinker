from rep import *
from fft import fft_min
from theta import hb
A=('beta',FA)
means=[Fr(1,5),Fr(1,4)]
def Fth(th,m):
    return [bb_pmf(m,means[t]*(Fr(101)/th-1),(1-means[t])*(Fr(101)/th-1)) for t in range(2)]
for m,ths in [(128,[Fr(9,10),Fr(8,10),Fr(7,10)]),(512,[Fr(9,10),Fr(8,10)]),(32,[Fr(9,10),Fr(8,10)])]:
    pa=pmfs(A,m)
    for th in ths:
        pb=Fth(th,m)
        print(m,float(th),'H',round(hb(pa,pb),5),'NP fft',round(fft_min(pa,pb)[0],5),'MC',np.round(np_exact(pa,pb,N=200000,seed=3)[::2],4))
