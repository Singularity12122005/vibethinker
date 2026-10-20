from formula import *
from fractions import Fraction as Fr
import numpy as np
KMAX = 12
worlds = {
    'narrow':   (beta_moments(20, 80, KMAX), beta_moments(25, 75, KMAX)),
    'halfvar~': (beta_moments(Fr(202,5), Fr(808,5), KMAX), beta_moments(Fr(101,2), Fr(303,2), KMAX)),
    'wide':     (beta_moments(2, 8, KMAX), beta_moments(Fr(5, 2), Fr(15, 2), KMAX)),
}
n = 200
sigB = sigma2_bound()

def osc(b1, b2):
    vals = [0.0, b1 + b2]
    if b2 != 0:
        rv = -b1 / (2 * b2)
        if 0 < rv < 1:
            vals.append(b1 * rv + b2 * rv * rv)
    return max(vals) - min(vals)

def Om_world(m0, m1, w1, gamma, m):
    Om = np.zeros((2, 2))
    for t, mom, w in ((0, m0, 1 - w1), (1, m1, w1)):
        O = Omega(t, gamma, m)
        for i in range(2):
            for j in range(2):
                Om[i, j] += float(w * pexpect(O[i][j], mom))
    return Om

def eta_bound(m0, m1, w1, gamma, m):
    tot = Fr(0)
    for t, mom, w in ((0, m0, 1 - w1), (1, m1, w1)):
        e, g = Ephi2_poly(t, gamma, (0, 0), m, sigB)
        tot += w * pexpect(e, mom)
    return float(tot)

def sup_full(Om):
    best = (-1, None)
    for th in np.linspace(0, np.pi, 200001)[:-1]:
        c, s = np.cos(th), np.sin(th)
        o = osc(c, s)
        sc = 2.0 / o
        b = np.array([c * sc, s * sc])
        v = b @ Om @ b
        if v > best[0]:
            best = (v, b)
    return best

def sup_box(Om):
    verts = [(2, 0), (0, 2), (-2, 2), (-2, 0), (0, -2), (2, -2)]
    best = (-1, None)
    for b in verts:
        b = np.array(b, float); v = b @ Om @ b
        if v > best[0]: best = (v, b)
    return best

def budget(m0, m1, w1, gamma, D, kind, grid):
    beta_g = (Fr(-4, 5), Fr(0)); sig_g = sigma2_arms(Fr(9, 50), Fr(-4, 5), Fr(0))
    out = []
    for m in grid:
        if kind == 'g':
            te, tg, _ = first_order_var_sum(m0, m1, w1, gamma, D, beta_g, m, sig_g); S = float(te + tg)
        else:
            Om = Om_world(m0, m1, w1, gamma, m); eb = eta_bound(m0, m1, w1, gamma, m)
            S = eb + (sup_box(Om)[0] if kind == 'c2' else sup_full(Om)[0])
        out.append((m, width(S, D, n)))
    return out

grid = [8, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024]
for name, (m0, m1) in worlds.items():
    Qxx, q, gamma, D = overlap(m0, m1, Fr(1, 2))
    Om = Om_world(m0, m1, Fr(1, 2), gamma, 128)
    eb = eta_bound(m0, m1, Fr(1, 2), gamma, 128)
    vf, bf = sup_full(Om); vb, bb = sup_box(Om)
    print(f"== {name}: Omega(m=128)={Om.tolist()} eig={np.linalg.eigvalsh(Om)}")
    print(f"   sup full: width={width(eb+vf, D, n):.4f} at beta*={bf.round(3)} (osc={osc(*bf):.4f}); cheb (-8,8) value={np.array([-8,8])@Om@np.array([-8,8]):.6g} vs max {vf:.6g}")
    print(f"   sup box : width={width(eb+vb, D, n):.4f} at beta*={bb}")
    for kind in ('g', 'c2', 'full'):
        res = budget(m0, m1, Fr(1, 2), gamma, D, kind, grid)
        first = next((m for m, w in res if w <= 0.15), None)
        print(f"   budget[{kind}]: first grid m with w1<=0.15 -> {first}; " + " ".join(f"{m}:{w:.4f}" for m, w in res))
