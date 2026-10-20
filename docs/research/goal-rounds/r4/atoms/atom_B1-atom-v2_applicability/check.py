import numpy as np
from scipy.stats import betabinom
def rho(m,a1,b1,a2,b2):
    k=np.arange(m+1); return np.sum(np.sqrt(betabinom.pmf(k,m,a1,b1)*betabinom.pmf(k,m,a2,b2)))
for m in (32,64,128):
    r0=rho(m,20,80,40.5,162); r1=rho(m,25,75,50.6,151.8)
    print(m, f"{r0:.10f} {r1:.10f}", "hell LB on 1-TV:", 1-np.sqrt(1-(r0*r1)**200), "upper on 1-TV (>= 1-sqrt..), BC^2 based upper:", (r0*r1)**200)
def lam(a,b,m):
    mu=a/(a+b); v=a*b/((a+b)**2*(a+b+1)); return v/(v+(mu*(1-mu)-v)/m)
for ab in [(20,80),(25,75),(40.5,162),(50.6,151.8)]: print(ab, [round(lam(*ab,m),3) for m in (32,128)], ab[0]/sum(ab))
