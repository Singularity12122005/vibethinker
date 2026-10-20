import sys
from fractions import Fraction as Fr
from math import perm
sys.path.insert(0, '.')
import cf
a=lambda j,l,m: Fr(perm(m,j+l),perm(m,j)*perm(m,l))
w={0:Fr(1,2),1:Fr(1,2)}
base={0:cf.beta_moms(20,80),1:cf.beta_moms(25,75)}
def tot(moms,m,beta,sig):
    return cf.var1_total(moms,w,m,beta,sig)[0]
def dep8(m,beta,sig):
    eps=Fr(1,10**6)
    pm={t:list(base[t]) for t in (0,1)}
    for t in (0,1): pm[t][8]+=eps
    return float((tot(pm,m,beta,sig)-tot(base,m,beta,sig))/eps)
m=128
b=(Fr(1),Fr(-8),Fr(8))
print('sym-arm sigma2, beta2=8: d/dmu8 =',dep8(m,b,cf.sig2_arms(b)))
s4=-b[2]**2*(a(4,4,m)-2*a(2,4,m)+a(2,2,m))/a(2,2,m)
sig=[Fr(1,100),0,0,0,s4]
print('s4=',float(s4),' sigma2=1/100+s4 r^4, beta2=8: d/dmu8 =',dep8(m,b,sig))
bl=(Fr(9,50),Fr(-4,5),Fr(0))
print('linear g, sigma2=1/100+r^4: d/dmu8 =',dep8(m,bl,[Fr(1,100),0,0,0,Fr(1)]))
print('linear g, sym-arm sigma2: d/dmu7,8 =',dep8(m,bl,cf.sig2_arms(bl)))
