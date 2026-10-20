"""Size of the stated-assumption gap in the Beta worlds: Var(eta|r,K) = sigma2(r) (1 + c (U_1(K) - r)) keeps Var(eta|r) = sigma2(r)
and E[eta|r,t,K] = 0 but changes the first-order variance by  c * sum_t w_t E[ sigma2(r) (U_1 - r) (t - gamma' u)^2 ] / D^2."""
import sys, numpy as np
from scipy import stats
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_")
from route_a_lib import beta_moments, first_order, overlap_D, sigma2_poly_from_g
WORLDS = {"narrow": ((20, 80), (25, 75)), "wide": ((2, 8), (2.5, 7.5))}
G = (0.18, -0.8, 0.0)
rg = np.linspace(0, 1, 4001)[1:-1]
for wn, (ab0, ab1) in WORLDS.items():
    mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
    D, gam = overlap_D(mu0, mu1, 0.5)
    s2 = np.polynomial.polynomial.Polynomial(sigma2_poly_from_g(G))(rg)
    for m in (32, 128):
        fo = first_order(mu0, mu1, 0.5, m, 200, beta=G)
        K = np.arange(m + 1)
        U1 = K / m; U2 = K * (K - 1) / (m * (m - 1))
        pK = stats.binom.pmf(K[None, :], m, rg[:, None])               # [r, K]
        extra = 0.0
        for t, ab in ((0, ab0), (1, ab1)):
            pdf = stats.beta.pdf(rg, *ab); pdf /= pdf.sum()
            tu = t - gam[0] - gam[1] * U1[None, :] - gam[2] * U2[None, :]   # [1, K]
            inner = (pK * (U1[None, :] - rg[:, None]) * tu ** 2).sum(1)      # E[(U1 - r)(t - gamma'u)^2 | r]
            extra += 0.5 * (pdf * s2 * inner).sum()
        for c in (0.9, -0.9):
            print(f"{wn:7s} m={m:3d} c={c:+.1f}: relative change of Var_1 = {c*extra/fo['Ephi2']:+.4%}  (width ratio {np.sqrt(1 + c*extra/fo['Ephi2']):.5f})")
