"""(i) polynomial degree of the g-term and eta-term; (ii) search over the admissible class osc(b1 r + b2 r^2) <= 2 for the PHYSICAL
clipped model's first-order eta-term (true sigma^2 with clipping) + g-term vs the claimed sup (bound sigma^2 <= r(1-r)/8), wide world."""
import sys, numpy as np
from scipy import stats
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_")
from route_a_lib import beta_moments, first_order, V_poly, overlap_D, pmul, padd, pscale, monomial, J_poly
# (i) degree
m = 128
for j, l in ((4, 4), (2, 2), (2, 4)):
    V = V_poly(m, j, l, exact=True)
    print(f"deg V_{j}{l} = {max(i for i, c in enumerate(V) if c != 0)}")
print("alpha_{2,4}^2 V_44 has degree 8, alpha_{2,2}^2 V_22 (alpha_{2,2} = -(t-g0) - g2 r^2) has degree 4+4 = 8  -> g-term degree 8 (derivation 1.6 says <=7)")
# (ii) search, wide world
ab0, ab1 = (2, 8), (2.5, 7.5)
mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
n = 200
D, gam = overlap_D(mu0, mu1, 0.5)
rg = np.linspace(0, 1, 20001)[1:-1]
pdf0, pdf1 = stats.beta.pdf(rg, *ab0), stats.beta.pdf(rg, *ab1)
pdf0 /= pdf0.sum(); pdf1 /= pdf1.sum()
for m in (32, 128, 512):
    fo = first_order(mu0, mu1, 0.5, m, n, sup_g=True)
    Om = np.array(fo["Omega"], float)
    V2 = [[np.polynomial.polynomial.Polynomial(V_poly(m, j, l, exact=False))(rg) for l in (1, 2)] for j in (1, 2)]
    gVg = sum(gam[a + 1] * gam[b + 1] * V2[a][b] for a in range(2) for b in range(2))
    W = [((t - gam[0] - gam[1] * rg - gam[2] * rg ** 2) ** 2 + gVg) for t in (0, 1)]
    wts = 0.5 * pdf0 * W[0] + 0.5 * pdf1 * W[1]
    te_bound = float((wts * rg * (1 - rg) / 8).sum())
    best = (-1, None)
    # grid on boundary + interior over angle and radius
    th = np.linspace(0, np.pi, 720, endpoint=False)
    for c, s in zip(np.cos(th), np.sin(th)):
        v0, v1 = 0.0, c + s
        vals = [v0, v1]
        if s != 0:
            rv = -c / (2 * s)
            if 0 < rv < 1: vals.append(c * rv + s * rv * rv)
        osc = max(vals) - min(vals)
        R = 2.0 / osc
        for frac in (0.25, 0.5, 0.75, 1.0):
            b1, b2 = c * R * frac, s * R * frac
            # choose b0 so that |g| <= 1: center the range
            p = b1 * rg + b2 * rg ** 2
            b0 = -(p.max() + p.min()) / 2
            g = b0 + p
            qp, qm = np.clip(rg + g / 2, 0, 1), np.clip(rg - g / 2, 0, 1)
            s2 = (qp * (1 - qp) + qm * (1 - qm)) / 16
            te_true = float((wts * s2).sum())
            tg = b1 * b1 * Om[0, 0] + 2 * b1 * b2 * Om[0, 1] + b2 * b2 * Om[1, 1]
            tot = te_true + tg
            if tot > best[0]: best = (tot, (b0, b1, b2, te_true, tg))
    sup_claim = fo["term_eta"] + fo["term_g"]
    b0, b1, b2, te_true, tg = best[1]
    print(f"wide m={m:3d}: claimed sup E[phi^2] = {sup_claim:.5e} (eta {fo['term_eta']:.3e} + g {fo['term_g']:.3e}; width {fo['width1']:.4f});  "
          f"max over physical clipped class = {best[0]:.5e} at g=({b0:+.2f},{b1:+.2f},{b2:+.2f}) (eta_true {te_true:.3e} + g {tg:.3e}; width {3.92*np.sqrt(best[0]/(n*D*D)):.4f});  te_bound(grid)={te_bound:.3e}")
