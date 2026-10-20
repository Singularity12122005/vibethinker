from formula import *
from fractions import Fraction as Fr
KMAX = 12
beta_g = (Fr(-4, 5), Fr(0)); sig_g = sigma2_arms(Fr(9, 50), Fr(-4, 5), Fr(0)); n = 200
for s in [202, 203, 204, 205, 206]:
    m0 = beta_moments(Fr(s,5), Fr(4*s,5), KMAX); m1 = beta_moments(Fr(s,4), Fr(3*s,4), KMAX)
    Qxx, q, gamma, D = overlap(m0, m1, Fr(1, 2))
    ws = []
    for m in (32, 128, 512):
        te, tg, dg = first_order_var_sum(m0, m1, Fr(1,2), gamma, D, beta_g, m, sig_g)
        ws.append(width(te+tg, D, n))
    print(f"a+b={s}: D={float(D):.4f} gamma=({float(gamma[0]):.2f},{float(gamma[1]):.2f},{float(gamma[2]):.2f}) w1={ws[0]:.4f}/{ws[1]:.4f}/{ws[2]:.4f}")
