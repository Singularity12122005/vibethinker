from formula import *
from fractions import Fraction as Fr
KMAX = 12
beta_g = (Fr(-4, 5), Fr(0)); sig_g = sigma2_arms(Fr(9, 50), Fr(-4, 5), Fr(0)); n = 200
cands = {
 'a+b=201 exact half var': (beta_moments(Fr(201,5), Fr(804,5), KMAX), beta_moments(Fr(201,4), Fr(603,4), KMAX)),
 'a+b=202': (beta_moments(Fr(202,5), Fr(808,5), KMAX), beta_moments(Fr(101,2), Fr(303,2), KMAX)),
 'a+b=200': (beta_moments(40, 160, KMAX), beta_moments(50, 150, KMAX)),
}
for name, (m0, m1) in cands.items():
    Qxx, q, gamma, D = overlap(m0, m1, Fr(1, 2))
    print(f"== {name}: D={float(D):.4f} gamma=({float(gamma[0]):.2f},{float(gamma[1]):.2f},{float(gamma[2]):.2f})")
    orc = Fr(0)
    for t, mom, w in ((0, m0, Fr(1,2)), (1, m1, Fr(1,2))):
        rho = padd(pconst(t - gamma[0]), pmono(1, -gamma[1]), pmono(2, -gamma[2]))
        orc += w * pexpect(pmul(sig_g, pmul(rho, rho)), mom)
    print(f"   oracle width n=200: {width(orc, D, n):.4f}")
    for m in (32, 128, 512):
        te, tg, dg = first_order_var_sum(m0, m1, Fr(1,2), gamma, D, beta_g, m, sig_g)
        print(f"   m={m}: w1={width(te+tg, D, n):.4f}")
