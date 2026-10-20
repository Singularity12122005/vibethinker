"""(1) C1 identity P(R|D) − P(R'|D) = Cov(δ, 1_D)/π and the Cauchy–Schwarz bound, exactly (Fractions) in a toy two-prefix world:
reuse K = K_pilot + K_extra vs fresh K' (same law given r), pilot rule D a function of (t, K_pilot), final event R a function of (t, K).
(2) B2 structural fact: the PD decision of endpoint_contrast_poly_cs depends on (K, t) only — identical for any outcome vector y."""
import sys
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
from fractions import Fraction as Fr
from itertools import product
from math import comb
import numpy as np
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

def binpmf(k, m, r): return Fr(comb(m, k)) * r ** k * (1 - r) ** (m - k)
risks, w = [Fr(3, 10), Fr(3, 5)], [Fr(1, 2), Fr(1, 2)]          # r iid per prefix
mp, me = 2, 3                                                    # pilot draws, extra draws (m = 5)
m = mp + me
def R_event(K): return int(K[0] + K[1] >= 5 and abs(K[0] - K[1]) <= 2)   # any event of the final counts
def D_rule(Kp): return int(Kp[0] + Kp[1] >= 2)                            # any pilot rule
P_R_and_D = P_Rf_and_D = P_D = Fr(0); delta_moments = {}
E_delta = E_delta_D = E_delta2 = Fr(0)
for r in product(range(2), repeat=2):
    pr = w[r[0]] * w[r[1]]; rr = [risks[r[0]], risks[r[1]]]
    for Kp in product(range(mp + 1), repeat=2):
        pKp = pr * binpmf(Kp[0], mp, rr[0]) * binpmf(Kp[1], mp, rr[1])
        # P(R | r, Kp) with reuse, and P(R' | r, Kp) with fresh m-draw counts
        pR = sum(binpmf(e0, me, rr[0]) * binpmf(e1, me, rr[1]) * R_event((Kp[0] + e0, Kp[1] + e1)) for e0 in range(me + 1) for e1 in range(me + 1))
        pRf = sum(binpmf(k0, m, rr[0]) * binpmf(k1, m, rr[1]) * R_event((k0, k1)) for k0 in range(m + 1) for k1 in range(m + 1))
        d = D_rule(Kp)
        P_D += pKp * d; P_R_and_D += pKp * d * pR; P_Rf_and_D += pKp * d * pRf
        delta_moments.setdefault(Kp, [Fr(0), Fr(0), Fr(0)])
        delta_moments[Kp][0] += pKp; delta_moments[Kp][1] += pKp * pR; delta_moments[Kp][2] += pKp * pRf
# δ is a function of (t, K_pilot): δ(Kp) = P(R|Kp) − P(R'|Kp) (marginalising r given Kp)
for Kp, (p, a, b) in delta_moments.items():
    dlt = (a - b) / p
    E_delta += p * dlt; E_delta_D += p * dlt * D_rule(Kp); E_delta2 += p * dlt ** 2
pi = P_D
lhs = P_R_and_D / pi - P_Rf_and_D / pi
rhs = (E_delta_D - E_delta * pi) / pi
var_delta = E_delta2 - E_delta ** 2
bound_sq = var_delta * (1 - pi) / pi
print("E[δ] =", E_delta, "(must be 0)")
print("P(R|D) − P(R'|D) =", lhs, "=", float(lhs), "; Cov(δ,1_D)/π =", rhs, "; equal:", lhs == rhs)
print("Cauchy–Schwarz: |lhs|² ≤ σ_δ²(1−π)/π :", lhs ** 2 <= bound_sq, f"({float(abs(lhs)):.6f} ≤ {float(bound_sq) ** 0.5:.6f})")
# (2) PD decision invariance to y
rng = np.random.default_rng(3); disagree = 0; n_np = 0
for _ in range(300):
    r = np.r_[rng.beta(40.5, 162, 100), rng.beta(50.6, 151.8, 100)]; t = np.r_[np.zeros(100, int), np.ones(100, int)]
    K = rng.binomial(128, r)
    outs = [endpoint_contrast_poly_cs(rng.normal(0, s, 200) + c, K, 128, t, degree=2) for s, c in ((0.1, 0), (1.0, 0.5), (0.01, -3))]
    disagree += len({(o["ok"], round(o["min_eig"], 12)) for o in outs}) > 1; n_np += not outs[0]["ok"]
print(f"PD decision identical across 3 outcome vectors in 300/300 draws: {disagree == 0} (non-PD in {n_np}/300 draws, half-variance world, m=128)")
