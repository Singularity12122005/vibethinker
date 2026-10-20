import mpmath as mp, numpy as np
mp.mp.dps=40
m=32
def bb(a,b):
    a=mp.mpf(a);b=mp.mpf(b)
    return [mp.binomial(m,k)*mp.beta(k+a,m-k+b)/mp.beta(a,b) for k in range(m+1)]
pa0=bb(20,80);pa1=bb(25,75);pb0=bb('40.5',162);pb1=bb('50.6','151.8')
for p in (pa0,pa1,pb0,pb1): print(mp.nstr(sum(p),20))
r0=sum(mp.sqrt(x*y) for x,y in zip(pa0,pb0)); r1=sum(mp.sqrt(x*y) for x,y in zip(pa1,pb1))
print('rho0',mp.nstr(r0,15),'rho1',mp.nstr(r1,15))
H=1-mp.sqrt(1-r0**200*r1**200); print('hell',mp.nstr(H,15))
# TV via discretized LLR
def run(h):
    res=[]
    for rnd in (np.floor,np.ceil):
        pmfs=[]
        lo=0;hi=0
        comps=[]
        for pa,pb in ((pa0,pb0),(pa1,pb1)):
            l=np.array([float(mp.log(x/y)) for x,y in zip(pa,pb)])
            idx=rnd(l/h).astype(np.int64)
            w=np.array([float(x) for x in pa])
            comps.append((idx,w))
            lo+=100*idx.min(); hi+=100*idx.max()
        N=1<<int(np.ceil(np.log2(hi-lo+1)))
        F=np.ones(N,complex)
        for idx,w in comps:
            v=np.zeros(N); np.add.at(v,(idx-idx.min()),w)
            F*=np.fft.fft(v)**100
        dist=np.real(np.fft.ifft(F)); 
        Lgrid=(np.arange(N)+ (100*comps[0][0].min()+100*comps[1][0].min()))*h
        f=np.minimum(1,np.exp(-np.clip(Lgrid,-700,700)))
        res.append(float(np.sum(dist*f)))
    return res  # floor -> upper bound, ceil -> lower bound
for h in (1e-2,2e-3,5e-4):
    print(h,run(h))
