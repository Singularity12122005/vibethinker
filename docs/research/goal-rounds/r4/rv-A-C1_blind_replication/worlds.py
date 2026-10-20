from formula import *
from fractions import Fraction as Fr

KMAX = 12
worlds = {
    'narrow':   (beta_moments(20, 80, KMAX), beta_moments(25, 75, KMAX)),
    'halfvar':  (beta_moments(40, 160, KMAX), beta_moments(50, 150, KMAX)),
    'wide':     (beta_moments(2, 8, KMAX), beta_moments(Fr(5, 2), Fr(15, 2), KMAX)),
}
beta_g = (Fr(-4, 5), Fr(0))          # g = 0.18 - 0.8 r  -> b1=-0.8, b2=0
sig_g = sigma2_arms(Fr(9, 50), Fr(-4, 5), Fr(0))
n = 200
for name, (m0, m1) in worlds.items():
    Qxx, q, gamma, D = overlap(m0, m1, Fr(1, 2))
    print(f"== {name}: D={float(D):.4f} gamma=({float(gamma[0]):.2f},{float(gamma[1]):.2f},{float(gamma[2]):.2f})")
    # oracle width
    orc = Fr(0)
    for t, mom, w in ((0, m0, Fr(1,2)), (1, m1, Fr(1,2))):
        rho = padd(pconst(t - gamma[0]), pmono(1, -gamma[1]), pmono(2, -gamma[2]))
        orc += w * pexpect(pmul(sig_g, pmul(rho, rho)), mom)
    print(f"   oracle width n=200: {width(orc, D, n):.4f}")
    for m in (32, 128, 512):
        te, tg, dg = first_order_var_sum(m0, m1, Fr(1,2), gamma, D, beta_g, m, sig_g)
        print(f"   m={m}: w1={width(te+tg, D, n):.4f}  (eta part {float(te):.5g}, g part {float(tg):.5g}, maxdeg {dg})")
