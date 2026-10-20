"""Re-check scope-lens s1(iii): CR1 first-order width under an additive question effect a_q in eta.
The scope lens added only the off-diagonal cross term to the tau-free base; the diagonal tau2*E[rho^2+g~'V2 g~] is missing.
Also a production MC at large n (endpoint_contrast_poly_cs, CR1) to arbitrate."""
import sys, glob
import numpy as np
R4 = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4"
sys.path.insert(0, glob.glob(R4 + "/A__*")[0])
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
from route_a_lib import first_order, beta_moments, overlap_D
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs
Z = 1.959963984540054
n, w1 = 200, 0.5
worlds = {"narrow": ((20, 80), (25, 75)), "wide": ((2, 8), (2.5, 7.5))}
bl = (0.18, -0.8, 0.0)
for name, (ab0, ab1) in worlds.items():
    mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
    D, gam = overlap_D(mu0, mu1, w1)
    base = first_order(mu0, mu1, w1, 128, n, beta=bl)
    e1 = 1 - gam[0] - gam[1] * mu1[1] - gam[2] * mu1[2]
    e0 = 0 - gam[0] - gam[1] * mu0[1] - gam[2] * mu0[2]
    for tau2 in (0.0025, 0.01):
        own = first_order(mu0, mu1, w1, 128, n, beta=(0, 0, 0), sigma2=[tau2])["Ephi2"]
        crossA = (2 * e0 * e0 + 2 * e1 * e1 + 8 * e0 * e1) * tau2 / 4
        crossB = (12 * e0 * e0 * 0.5 + 12 * e1 * e1 * 0.5) * tau2 / 4
        f = lambda E: 2 * Z * np.sqrt(E / (n * D * D))
        print("%s tau=%.2f W1=%.4f | scope-lens A=%.4f B=%.4f | with diagonal: HC1=%.4f CR1_A=%.4f CR1_B=%.4f"
              % (name, tau2 ** .5, base["width1"], f(base["Ephi2"] + crossA), f(base["Ephi2"] + crossB),
                 f(base["Ephi2"] + own), f(base["Ephi2"] + own + crossA), f(base["Ephi2"] + own + crossB)))

# production MC, narrow, layout A (2 type-0 + 2 type-1 per question), tau=0.10, m=128, clipped 16-draw arms
rng = np.random.default_rng(20261020)
N, reps, m, tau = 8000, 300, 128, 0.10
nq = N // 4
est = []
for rep in range(reps):
    t = np.tile([0, 0, 1, 1], nq)
    q = np.repeat(np.arange(nq), 4)
    r = np.where(t == 1, rng.beta(25, 75, N), rng.beta(20, 80, N))
    g = bl[0] + bl[1] * r
    a = rng.normal(0, tau, nq)[q]
    qp = np.clip(r + g / 2 + a / 2, 0, 1); qm = np.clip(r - g / 2 - a / 2, 0, 1)
    y = rng.binomial(16, qp) / 16 - rng.binomial(16, qm) / 16
    K = rng.binomial(m, r)
    res = endpoint_contrast_poly_cs(y, K, m, t, degree=2, cluster=q)
    if res["ok"]:
        est.append((res["beta"][-1], res["se"][-1]))
est = np.array(est)
sd = est[:, 0].std(ddof=1); 
print("MC narrow layout A tau=0.10 N=%d ok=%d: sampling sd -> width at n=200: %.4f ; mean CR1 se -> width: %.4f"
      % (N, len(est), 2 * Z * sd * np.sqrt(N / 200), 2 * Z * est[:, 1].mean() * np.sqrt(N / 200)))
