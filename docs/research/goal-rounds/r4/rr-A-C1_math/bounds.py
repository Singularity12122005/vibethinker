import numpy as np, sys
sys.path.insert(0,'/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/rereview_A-C1_math')
from indep import *
W=world(20,80,25,75,N=400); m=128
beta=(0.18,-0.8,0.0)
s2g=lambda r:(2*r*(1-r)-(beta[0]+beta[1]*r)**2/2)/16
D,gam=moments_D(W,0.5)
# oracle
orc=sum(0.5*np.sum(W[t][1]*s2g(W[t][0])*(t-gam[0]-gam[1]*W[t][0]-gam[2]*W[t][0]**2)**2) for t in (0,1))
print("oracle",width(D,orc))
_,_,a,_=Ephi2(W,0.5,m,(0,1,0),lambda r:0.0)
O11=Ephi2(W,0.5,m,(0,1,0),lambda r:0)[3]; O22=Ephi2(W,0.5,m,(0,0,1),lambda r:0)[3]; S=Ephi2(W,0.5,m,(0,1,1),lambda r:0)[3]
O12=(S-O11-O22)/2; Om=np.array([[O11,O12],[O12,O22]]); print("Omega",Om,"eig",np.linalg.eigvalsh(Om))
te8=Ephi2(W,0.5,m,(0,0,0),lambda r:r*(1-r)/8)[2]; te32=Ephi2(W,0.5,m,(0,0,0),lambda r:1/32)[2]
# dense grid over (b1,b2), osc<=2
b1,b2=np.meshgrid(np.linspace(-12,12,2401),np.linspace(-12,12,2401))
rr=np.linspace(0,1,401)
def osc(b1,b2):
    vals=[0*b1,b1+b2]
    with np.errstate(all='ignore'):
        rs=np.where(b2!=0,-b1/(2*b2),-1)
    ins=(rs>0)&(rs<1); v=np.where(ins,b1*rs+b2*rs*rs,0)
    return np.maximum.reduce([vals[0],vals[1],v])-np.minimum.reduce([vals[0],vals[1],v])
o=osc(b1,b2); q=Om[0,0]*b1**2+2*Om[0,1]*b1*b2+Om[1,1]*b2**2
for nm,mask in (("full",o<=2+1e-12),("c2",(o<=2+1e-12)&(abs(b1)<=2)&(abs(b2)<=2))):
    i=np.argmax(np.where(mask,q,-1)); 
    print(nm,"max g-term",q.flat[i],"at",b1.flat[i],b2.flat[i],"Wbar r(1-r)/8=%.4f"%width(D,te8+q.flat[i]),"Wbar 1/32=%.4f"%width(D,te32+q.flat[i]))
# exact (-8,8)
print("q(-8,8)",np.array([-8,8])@Om@np.array([-8,8]))
