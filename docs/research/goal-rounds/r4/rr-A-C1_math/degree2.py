import sys
sys.path.insert(0,'/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/rereview_A-C1_math')
from degree import coef, F, beta_moments
mu0=beta_moments(20,80,exact=True); mu1=beta_moments(25,75,exact=True)
w1=F(2,5)
c=coef(mu0,mu1,w1,8,[F(9,50),F(-4,5),F(3,10)],8)
print("narrow w1=2/5 m=8: coef mu8_t / w_t:", float(c[0]/(1-w1)), float(c[1]/w1))
# linear g with a degree-4 sigma2 = r^2(1-r)^2 (nonnegative), m=8
s2=[F(0),F(0),F(1),F(-2),F(1)]
print("linear g, sigma2=r^2(1-r)^2: coef mu8", [float(x) for x in coef(mu0,mu1,F(1,2),8,[F(9,50),F(-4,5),F(0)],8,sigma2=s2)])
