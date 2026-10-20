"""Does the sup-over-{|g|<=1} width (with sigma^2 <= r(1-r)/8) bound the first-order width of the PHYSICAL model q_± = clip(r ± g/2)?
Wide world, g* = 1 - 8r + 8r^2 (the claimed maximiser).  Also the clipping rate for the claim's g=0.18-0.8r in each world."""
import sys, numpy as np
from scipy import stats, integrate
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_")
from route_a_lib import beta_moments, first_order, V_poly, overlap_D
WORLDS = {"narrow": ((20, 80), (25, 75)), "halfvar": ((40.5, 162.0), (50.6, 151.8)), "wide": ((2, 8), (2.5, 7.5))}
G = (0.18, -0.8, 0.0)
for wn, (ab0, ab1) in WORLDS.items():
    for ab in (ab0, ab1):
        f = lambda r: G[0] + G[1] * r + G[2] * r * r
        pclip = integrate.quad(lambda r: stats.beta.pdf(r, *ab) * (((r + f(r) / 2) > 1) | ((r - f(r) / 2) < 0)), 0, 1, limit=200)[0]
        print(f"{wn}: Beta{ab}: P(clipping) for g=0.18-0.8r = {pclip:.4f}")
# sup check in the wide world with g* = (1, -8, 8), m = 128, n = 200
ab0, ab1 = WORLDS["wide"]
mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
m, n = 128, 200
fo_sup = first_order(mu0, mu1, 0.5, m, n, sup_g=True)
D, gam = overlap_D(mu0, mu1, 0.5)
gstar = (1.0, -8.0, 8.0)
# eta-term with the TRUE clipped sigma^2 and with the bound r(1-r)/8, by quadrature
V2 = [[np.polynomial.polynomial.Polynomial(V_poly(m, j, l, exact=False)) for l in (1, 2)] for j in (1, 2)]
def weight(r, t):
    rho = t - gam[0] - gam[1] * r - gam[2] * r * r
    gVg = sum(gam[a + 1] * gam[b + 1] * V2[a][b](r) for a in range(2) for b in range(2))
    return rho ** 2 + gVg
def sig_true(r):
    g = gstar[0] + gstar[1] * r + gstar[2] * r * r
    qp, qm = np.clip(r + g / 2, 0, 1), np.clip(r - g / 2, 0, 1)
    return (qp * (1 - qp) + qm * (1 - qm)) / 16
def sig_bound(r): return r * (1 - r) / 8
te_true = te_bound = 0.0
for t, ab in ((0, ab0), (1, ab1)):
    te_true += 0.5 * integrate.quad(lambda r: stats.beta.pdf(r, *ab) * sig_true(r) * weight(r, t), 0, 1, limit=300)[0]
    te_bound += 0.5 * integrate.quad(lambda r: stats.beta.pdf(r, *ab) * sig_bound(r) * weight(r, t), 0, 1, limit=300)[0]
pclip = sum(0.5 * integrate.quad(lambda r: stats.beta.pdf(r, *ab) * ((np.abs(gstar[0] + gstar[1] * r + gstar[2] * r * r) / 2 > np.minimum(r, 1 - r))), 0, 1, limit=300)[0] for ab in (ab0, ab1))
print(f"wide, g*=1-8r+8r^2, m=128: P(clip)={pclip:.3f}; eta-term with sigma^2<=r(1-r)/8 bound = {te_bound:.5e}; eta-term with TRUE clipped sigma^2 = {te_true:.5e}; lib term_eta(sup)={fo_sup['term_eta']:.5e}; g-term(sup)={fo_sup['term_g']:.5e}")
w_sup = 3.92 * np.sqrt((te_bound + fo_sup["term_g"]) / (n * D * D))
w_true = 3.92 * np.sqrt((te_true + fo_sup["term_g"]) / (n * D * D))
print(f"claimed sup width {fo_sup['width1']:.4f} (recomputed {w_sup:.4f}) vs first-order width of the physical clipped model at g* (same g-term): {w_true:.4f}  -> sup is {'NOT ' if w_true > w_sup else ''}an upper bound")
# the mean misspecification under clipping: E[Delta-hat | r] - g*(r)
for r in (0.02, 0.05, 0.1, 0.2):
    g = gstar[0] + gstar[1] * r + gstar[2] * r * r
    print(f"   r={r}: g*={g:+.3f}, E[Delta-hat|r]=clip(q+)-clip(q-)={np.clip(r+g/2,0,1)-np.clip(r-g/2,0,1):+.3f}, sigma2 true={sig_true(r):.5f} bound={sig_bound(r):.5f}")
