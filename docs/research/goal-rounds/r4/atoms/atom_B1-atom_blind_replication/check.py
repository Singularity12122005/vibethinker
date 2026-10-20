import mpmath as mp, numpy as np, itertools
mp.mp.dps=40
def bb(n,a,b):
    a=mp.mpf(a);b=mp.mpf(b)
    return [mp.binomial(n,k)*mp.beta(k+a,n-k+b)/mp.beta(a,b) for k in range(n+1)]
pa0=bb(32,20,80);pa1=bb(32,25,75);pb0=bb(32,'40.5',162);pb1=bb(32,'50.6','151.8')
r0=mp.fsum(mp.sqrt(x*y) for x,y in zip(pa0,pb0)); r1=mp.fsum(mp.sqrt(x*y) for x,y in zip(pa1,pb1))
print(mp.nstr(r0,15),mp.nstr(r1,15), mp.nstr(1-mp.sqrt(1-r0**200*r1**200),12))
# small example for (i): 2 positions, m=2
pa=[0.5,0.3,0.2]; pb=[0.2,0.3,0.5]
xs=list(itertools.product(range(3),repeat=2))
PA=np.array([pa[i]*pa[j] for i,j in xs]); PB=np.array([pb[i]*pb[j] for i,j in xs])
tv=0.5*abs(PA-PB).sum()
phi=(PA<PB).astype(float)
print('1-TV',1-tv,'rule as stated',((1-phi)*PA).sum()+(phi*PB).sum(),'flipped',(phi*PA).sum()+((1-phi)*PB).sum())
np.save('/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/atom_B1-atom_blind_replication/p.npy',np.array([[float(x) for x in v] for v in (pa0,pa1,pb0,pb1)]))
