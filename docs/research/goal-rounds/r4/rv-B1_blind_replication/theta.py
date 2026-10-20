from rep import *
A=('beta',FA); B=('beta',FB)
def hb(pa,pb,n=100):
    rho=[affinity(pa[t],pb[t]) for t in range(2)]
    return float(1-mp.sqrt(1-(rho[0]**n*rho[1]**n)**2))
m=128
pa=pmfs(A,m); pB=pmfs(B,m)
Cpt=pmfs(('mix',[[(Fr(1,5),1)],[(Fr(1,4),1)]]),m)
pC2=pmfs(('mix',C2),m)
means=[Fr(1,5),Fr(1,4)]
for th in [Fr(9,10),Fr(8,10),Fr(7,10)]:
    out={}
    out['mix a,b']=hb(pa,[[th*x+(1-th)*y for x,y in zip(pa[t],pB[t])] for t in range(2)])
    out['mix a,pt']=hb(pa,[[th*x+(1-th)*y for x,y in zip(pa[t],Cpt[t])] for t in range(2)])
    out['mix a,c2']=hb(pa,[[th*x+(1-th)*y for x,y in zip(pa[t],pC2[t])] for t in range(2)])
    # beta same mean variance scaled by th
    for lab,s in [('var*th',th),('var*th^2',th*th),('prec*th', None)]:
        ps=[]
        for t,(a,b) in enumerate(FA):
            mu=means[t]
            if s is None:
                S=Fr(a+b)*th  # precision scaled
            else:
                S=Fr(a+b+1)/s-1
            ps.append(bb_pmf(m,mu*S,(1-mu)*S))
        out[lab]=hb(pa,ps)
    # precision divided by th
    ps=[bb_pmf(m,means[t]*Fr(sum(FA[t]))/th,(1-means[t])*Fr(sum(FA[t]))/th) for t in range(2)]
    out['prec/th']=hb(pa,ps)
    print(float(th),{k:round(v,4) for k,v in out.items()})
