import sys
sys.path.insert(0,'/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/docs/research/goal-rounds/r4/A')
from fractions import Fraction as F
from math import perm
from route_a_lib import first_order, overlap_D, beta_moments
def coef(mu0,mu1,w1,m,beta,order,sigma2=None):
    out=[]
    for t in (0,1):
        a=[list(mu0),list(mu1)]
        base=first_order(a[0],a[1],w1,m,200,beta=beta,sigma2=sigma2,exact=True)["Ephi2"]
        a[t][order]+=1
        pert=first_order(a[0],a[1],w1,m,200,beta=beta,sigma2=sigma2,exact=True)["Ephi2"]
        out.append(pert-base)
    return out
# Counterexample: r~U(0,1), P(t=1|r)=r
mu1=[F(2,j+2) for j in range(9)]; mu0=[F(2,(j+1)*(j+2)) for j in range(9)]
D,g=overlap_D(mu0,mu1,F(1,2)); print("U-world D,gamma",D,g)
beta=[F(1,10),F(-1,5),F(3,10)]
for m in (4,8,128):
    print(" m",m,"coef mu8",coef(mu0,mu1,F(1,2),m,beta,8),"coef mu7",coef(mu0,mu1,F(1,2),m,beta,7),"coef mu6",coef(mu0,mu1,F(1,2),m,beta,6))
# Is g in G_phys there? |g|<=2min(r,1-r) on [0,1]? g(0)=0.1>0 -> no; choose g with g(0)=g(1)=0: g=c r(1-r)
beta2=[F(0),F(1,2),F(-1,2)]
print(" g=0.5r(1-r):", [coef(mu0,mu1,F(1,2),m,beta2,8) for m in (4,128)])
# A(m) = L22-2L24+L44 and with sigma2 symmetric-arm lead
L=lambda m,j,l: F(perm(m,j+l),perm(m,j)*perm(m,l))-1
for m in list(range(4,40))+[64,128]:
    A=L(m,2,2)-2*L(m,2,4)+L(m,4,4); tot=A-(1+L(m,2,2))/32
    print(m,float(A),float(tot),end=' | ')
print()
