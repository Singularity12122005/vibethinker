import numpy as np, mpmath as mp, sys, time
mp.mp.dps=60
F=mp.mpf
def beta_pmf(a,b,m):
    a=F(a);b=F(b)
    return [mp.exp(mp.loggamma(m+1)-mp.loggamma(k+1)-mp.loggamma(m-k+1)+mp.loggamma(a+k)+mp.loggamma(b+m-k)-mp.loggamma(a+b+m)-mp.loggamma(a)-mp.loggamma(b)+mp.loggamma(a+b)) for k in range(m+1)]
def disc_pmf(atoms,m):
    return [sum(w*mp.binomial(m,k)*x**k*(1-x)**(m-k) for x,w in atoms) for k in range(m+1)]
R=mp.mpf
def world(name,m):
    if name=='a': return [beta_pmf(20,80,m),beta_pmf(25,75,m)]
    if name=='b': return [beta_pmf(R(81)/2,162,m),beta_pmf(R(253)/5,R(759)/5,m)]
    if name=='c': return [disc_pmf([(R(1)/5,1)],m),disc_pmf([(R(1)/4,1)],m)]
    if name=='c2': return [disc_pmf([(R(81)/505,R(101)/201),(R(6)/25,R(100)/201)],m),disc_pmf([(R(329)/1616,R(1616)/3491),(R(29)/100,R(1875)/3491)],m)]
    th=R(name[1:])/10; s=101/th-1
    return [beta_pmf(s/5,4*s/5,m),beta_pmf(s/4,3*s/4,m)]
def run(name,m,N=2**25,lo=-120.,hi=60.):
    A=world('a',m);B=world(name,m)
    rho=[sum(mp.sqrt(p*q) for p,q in zip(A[t],B[t])) for t in (0,1)]
    for t in (0,1): assert abs(sum(A[t])-1)<1e-40 and abs(sum(B[t])-1)<1e-40
    hel=1-mp.sqrt(1-rho[0]**200*rho[1]**200); hel0=1-mp.sqrt(1-rho[0]**200)
    h=(hi-lo)/N
    res=[]
    for rnd in (mp.floor,mp.ceil):
        ch=None
        for t in (0,1):
            g=np.zeros(N)
            for p,q in zip(A[t],B[t]):
                l=mp.log(q)-mp.log(p)
                idx=int(rnd(l/h))%N
                g[idx]+=float(p)
            f=np.fft.rfft(g)**100
            ch=f if ch is None else ch*f
        d=np.fft.irfft(ch,N)
        # map index to value in [lo,hi): value = j*h with j in [lo/h, hi/h)
        j=np.arange(N); jl=int(round(lo/h)); val=((j-jl)%N+jl)*h
        res.append(float(np.sum(d*np.minimum(1.0,np.exp(np.minimum(val,0))))))
    return rho,hel,hel0,res,h
for name,m in [('b',32),('c',32),('c2',32),('b',128),('c2',128),('t9',128),('t8',128),('t7',128),('b',512),('t9',512),('t8',512)]:
    t0=time.time();rho,hel,hel0,res,h=run(name,m)
    print(f"{name:3s} m={m:3d} rho0={mp.nstr(rho[0],12)} rho1={mp.nstr(rho[1],12)} rho0^100={mp.nstr(rho[0]**100,6)} Hell={mp.nstr(hel,6)} Hell0={mp.nstr(hel0,6)} NP in [{res[0]:.5f},{res[1]:.5f}] h={h:.2e} [{time.time()-t0:.0f}s]",flush=True)
