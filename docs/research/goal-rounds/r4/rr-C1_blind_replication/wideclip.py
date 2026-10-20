import numpy as np
from scipy import stats
GS={'lin':(0.18,-0.8,0),'quad':(0.26,-1.6,2),'cheb':(0.5,-4,4)}
W={'narrow':((20,80),(25,75)),'halfvar':((40.5,162),(50.6,151.8)),'wide':((2,8),(2.5,7.5))}
r=np.linspace(1e-7,1-1e-7,2000001)
for w,ab in W.items():
  for gn,c in GS.items():
    g=c[0]+c[1]*r+c[2]*r*r
    clip=((r+g/2)<0)|((r+g/2)>1)|((r-g/2)<0)|((r-g/2)>1)
    neg=(2*r-2*r*r-g*g/2)<0
    pc=np.mean([np.trapezoid(stats.beta.pdf(r,a,b)*clip,r) for a,b in ab])
    pn=np.mean([np.trapezoid(stats.beta.pdf(r,a,b)*neg,r) for a,b in ab])
    print(w,gn,'P(prefix clips)=%.3g'%pc,'P(unclipped Var(eta|r)<0)=%.3g'%pn)
