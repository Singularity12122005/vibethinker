"""kappa achievable by (t,K32)-measurable rules: Var(E[w'phi | K32, t]) vs w'Phi w."""
import exact as E
from fractions import Fraction as F
from math import comb
import sympy
def ut_poly(j, k):
    # Ut_j(k, r) polynomial in r
    p = {}
    for l in range(j + 1):
        p = E.padd(p, {j - l: F(comb(j, l) * E.ff(k, l) * E.ff(96, j - l), E.ff(128, j))})
    return p
for world in E.WORLDS:
    for gname, g in E.GS.items():
        A, Sig, SME, Phi = E.mats(world, g)
        w = sympy.Matrix(A).inv()[3, :].T
        ws = (w.T * sympy.Matrix(Sig) * w)[0]; wp = (w.T * sympy.Matrix(Phi) * w)[0]
        gp = {i: c for i, c in enumerate(g) if c != 0}
        tot = 0
        for tval, (a, b) in zip((0, 1), E.WORLDS[world]):
            mom = E.beta_moments(a, b, 80)
            for k in range(33):
                # w'phi(k,r) = sum_a w_a phi_a + w_t * t*phi_0
                Ut = [ut_poly(j, k) for j in range(5)]
                ph = []
                for aa in range(3):
                    p = E.pmul(gp, Ut[aa])
                    for bb in range(3):
                        if g[bb] != 0: p = E.padd(p, E.pscale(Ut[aa + bb], -g[bb]))
                    ph.append(p)
                wphi = {}
                for aa in range(3): wphi = E.padd(wphi, E.pscale(ph[aa], F(w[aa])))
                if tval: wphi = E.padd(wphi, E.pscale(ph[0], F(w[3])))
                lik = E.pmul({kk: F(comb(32, k) * comb(32 - k, kk - k) * (-1) ** (kk - k)) for kk in range(k, 33)}, {0: F(1)})
                pk = E.integ(lik, mom)
                num = E.integ(E.pmul(lik, wphi), mom)
                tot += F(1, 2) * num * num / pk
        print(world, gname, 'kappa(Phi)=%.4f' % float(sympy.sqrt(wp / ws)), 'kappa(achievable)=%.4f' % float(sympy.sqrt(tot / ws)))
