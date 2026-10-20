import numpy as np
from fractions import Fraction as Fr
from formula import *
from supclass import worlds, Om_world, sup_full, osc, n
from mc import gen, estimate, form
# (i) sup over class with sigma^2 <= 1/32 (valid under clipping) instead of r(1-r)/8
sig32 = pconst(Fr(1, 32))
print("sup over {|g|<=1} at m=128, eta-part with sigma^2 = 1/32 (clipping-valid bound) vs r(1-r)/8:")
for name, (m0, m1) in worlds.items():
    Qxx, q, gamma, D = overlap(m0, m1, Fr(1, 2))
    Om = Om_world(m0, m1, Fr(1, 2), gamma, 128); vf, bf = sup_full(Om)
    e32 = sum(w * pexpect(Ephi2_poly(t, gamma, (0, 0), 128, sig32)[0], mom) for t, mom, w in ((0, m0, Fr(1,2)), (1, m1, Fr(1,2))))
    e8 = sum(w * pexpect(Ephi2_poly(t, gamma, (0, 0), 128, sigma2_bound())[0], mom) for t, mom, w in ((0, m0, Fr(1,2)), (1, m1, Fr(1,2))))
    print(f"  {name}: width(1/32)={width(float(e32)+vf, D, n):.4f}  width(r(1-r)/8)={width(float(e8)+vf, D, n):.4f}")
# (ii) n=200 finite-sample width vs w1 around the budget cells, more reps
np.random.seed(5)
print("\nn=200, 4000 reps, g=0.18-0.8r, Bernoulli arms (clipped): realised 3.92*se_HC1")
for name, ms in (('halfvar~', (128, 192, 256)), ('narrow', (32, 48, 64, 128))):
    for m in ms:
        ws = []; npd = 0
        for rep in range(4000):
            r, t, y = gen(name, 200, 'bern'); beta, se, pd = estimate(r, t, y, m)
            ws.append(3.92 * se); npd += (not pd)
        ws = np.array(ws)
        (a0, c0), (a1, c1) = __import__('mc').worlds[name]
        m0 = beta_moments(Fr(a0), Fr(c0), 12); m1 = beta_moments(Fr(a1), Fr(c1), 12)
        Qxx, q, gamma, D = overlap(m0, m1, Fr(1, 2))
        te, tg, _ = first_order_var_sum(m0, m1, Fr(1, 2), gamma, D, (Fr(-4, 5), Fr(0)), m, sigma2_arms(Fr(9, 50), Fr(-4, 5), Fr(0)))
        w1 = width(te + tg, D, 200)
        print(f"  {name:9s} m={m:3d}: w1={w1:.4f} median={np.median(ws):.4f} q75={np.quantile(ws,.75):.4f} q90={np.quantile(ws,.9):.4f} P(width<=0.15)={np.mean(ws<=0.15):.3f} nonPD={npd/4000:.3f}")
