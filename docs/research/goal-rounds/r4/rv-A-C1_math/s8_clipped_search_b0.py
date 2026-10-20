"""Extended search: physical clipped eta-term + g-term over (b0, b1, b2) with |g| <= 1, b0 over its admissible range; wide world."""
import sys, numpy as np
from scipy import stats
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_")
from route_a_lib import beta_moments, first_order, V_poly, overlap_D
ab0, ab1 = (2, 8), (2.5, 7.5)
mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
n = 200
D, gam = overlap_D(mu0, mu1, 0.5)
rg = np.linspace(0, 1, 4001)[1:-1]
pdf0, pdf1 = stats.beta.pdf(rg, *ab0), stats.beta.pdf(rg, *ab1); pdf0 /= pdf0.sum(); pdf1 /= pdf1.sum()
for m in (32, 128):
    fo = first_order(mu0, mu1, 0.5, m, n, sup_g=True)
    Om = np.array(fo["Omega"], float)
    V2 = [[np.polynomial.polynomial.Polynomial(V_poly(m, j, l, exact=False))(rg) for l in (1, 2)] for j in (1, 2)]
    gVg = sum(gam[a + 1] * gam[b + 1] * V2[a][b] for a in range(2) for b in range(2))
    W = [((t - gam[0] - gam[1] * rg - gam[2] * rg ** 2) ** 2 + gVg) for t in (0, 1)]
    wts = 0.5 * pdf0 * W[0] + 0.5 * pdf1 * W[1]
    best = (-1, None); best_eta = (-1, None)
    for b1 in np.linspace(-8, 8, 81):
        for b2 in np.linspace(-8, 8, 81):
            p = b1 * rg + b2 * rg ** 2
            lo, hi = -1 - p.min(), 1 - p.max()
            if hi < lo: continue
            tg = b1 * b1 * Om[0, 0] + 2 * b1 * b2 * Om[0, 1] + b2 * b2 * Om[1, 1]
            for b0 in np.linspace(lo, hi, 9):
                g = b0 + p
                qp, qm = np.clip(rg + g / 2, 0, 1), np.clip(rg - g / 2, 0, 1)
                te = float((wts * (qp * (1 - qp) + qm * (1 - qm)) / 16).sum())
                if te > best_eta[0]: best_eta = (te, (b0, b1, b2))
                if te + tg > best[0]: best = (te + tg, (b0, b1, b2, te, tg))
    print(f"wide m={m:3d}: claimed sup E[phi^2]={fo['Ephi2']:.5e} (eta-bound {fo['term_eta']:.3e}); physical max={best[0]:.5e} at (b0,b1,b2,eta,g)={tuple(round(x,3) for x in best[1])}; "
          f"physical max eta-term alone={best_eta[0]:.3e} at {tuple(round(x,2) for x in best_eta[1])}  -> eta-bound {'HOLDS' if best_eta[0] <= fo['term_eta'] else 'FAILS'}")
