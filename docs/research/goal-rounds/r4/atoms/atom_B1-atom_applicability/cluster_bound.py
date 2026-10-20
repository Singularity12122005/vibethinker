# Applicability illustration: Hellinger bound when the 200 prefixes share risks within question clusters.
from mpmath import mp, mpf, binomial, rf, sqrt
mp.dps=40
def bb(m,a,b):
    a=mpf(a);b=mpf(b)
    return [binomial(m,k)*rf(a,k)*rf(b,m-k)/rf(a+b,m) for k in range(m+1)]
def rho(p,q): return sum(sqrt(x*y) for x,y in zip(p,q))
W={'a':[(20,80),(25,75)],'b':[(40.5,162),(50.6,151.8)]}
for c in [1,2,4]:   # c prefixes per question with identical risk -> sufficient stat Bin(32c, r), n/c clusters per type
    m=32*c; n=100//c
    r0=rho(bb(m,*W['a'][0]),bb(m,*W['b'][0])); r1=rho(bb(m,*W['a'][1]),bb(m,*W['b'][1]))
    rp=r0**n*r1**n
    print(c, float(r0), float(r1), float(1-sqrt(1-rp**2)))
