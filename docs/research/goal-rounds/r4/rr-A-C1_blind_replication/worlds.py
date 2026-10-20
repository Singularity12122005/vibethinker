import sys
from fractions import Fraction as Fr
import numpy as np
sys.path.insert(0, '/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/rereview_A-C1_blind_replication')
import cf

W = {'narrow': ((20, 80), (25, 75)), 'half': ((Fr(81, 2), 162), (Fr(253, 5), Fr(759, 5))), 'wide': ((2, 8), (Fr(5, 2), Fr(15, 2)))}
w = {0: Fr(1, 2), 1: Fr(1, 2)}
n = 200
beta = (Fr(18, 100), Fr(-8, 10), Fr(0))
for name, (p0, p1) in W.items():
    moms = {0: cf.beta_moms(*p0), 1: cf.beta_moms(*p1)}
    gam, D = cf.setup(moms, w)
    out = [name, 'D=%.4f' % float(D), 'gam=' + str([round(float(x), 4) for x in gam])]
    for m in (32, 64, 128, 4096, 10 ** 7):
        Wv, _ = cf.W1(moms, w, m, beta, cf.sig2_arms(beta), n)
        out.append('m%d:W1=%.4f' % (m, Wv))
    # oracle
    sig = cf.sig2_arms(beta)
    orc = sum(w[t] * cf.pexp(cf.pmul(sig, cf.pmul([Fr(t) - gam[0], -gam[1], -gam[2]], [Fr(t) - gam[0], -gam[1], -gam[2]])), moms[t]) for t in (0, 1))
    out.append('oracle=%.4f' % (float(cf.Z2) * float(orc / D ** 2 / n) ** 0.5))
    print(' '.join(out))
    m = 128
    for lab, s2 in (('r(1-r)/8', [Fr(0), Fr(1, 8), Fr(-1, 8)]), ('1/32', [Fr(1, 32)])):
        Te, Om = cf.Ephi2_parts(moms, w, m, s2, gam)
        Omf = np.array([[float(x) for x in row] for row in Om])
        ev = np.linalg.eigvalsh(Omf)
        # scan directions: max of 4 u'Om u / osc(u)^2
        rr = np.linspace(0, 1, 20001)
        best = (-1, None); bestc2 = (-1, None)
        for th in np.linspace(0, np.pi, 200001)[:-1]:
            u = np.array([np.cos(th), np.sin(th)])
            p = u[0] * rr + u[1] * rr ** 2
            osc = p.max() - p.min()
            s = 2 / osc
            bvec = u * s
            val = bvec @ Omf @ bvec
            if val > best[0]: best = (val, bvec)
            # c2: scale limited also by |b|<=2
            s2c = min(s, 2 / max(abs(u[0]), 1e-300), 2 / max(abs(u[1]), 1e-300))
            bc = u * s2c; vc = bc @ Omf @ bc
            if vc > bestc2[0]: bestc2 = (vc, bc)
        bstar = np.array([-8., 8.])
        vstar = bstar @ Omf @ bstar
        WB = float(cf.Z2) * ((float(Te) + vstar) / float(D) ** 2 / n) ** 0.5
        WBscan = float(cf.Z2) * ((float(Te) + best[0]) / float(D) ** 2 / n) ** 0.5
        WC2 = float(cf.Z2) * ((float(Te) + bestc2[0]) / float(D) ** 2 / n) ** 0.5
        print('  m=128 sigma2<=%s eigOm=%s argmax=%s val=%.6g vstar=%.6g Wbar=%.4f (scan %.4f) c2 argmax=%s Wc2=%.4f' % (
            lab, ev, np.round(best[1], 3), best[0], vstar, WB, WBscan, np.round(bestc2[1], 3), WC2))
    if name == 'narrow':
        for bb in [(1, -8, 8), (Fr(-2, 5), 2, 0)]:
            bb = tuple(Fr(x) for x in bb)
            print('  g=', bb, 'W1 m=128 = %.4f' % cf.W1(moms, w, 128, bb, cf.sig2_arms(bb), n)[0])
