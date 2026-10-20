"""r4 route C: runnable checks of the Proposition 2 identities and of the nested-ANOVA estimator.
(1) tilde U_j(k, r) = E[U_j(K32 + K96) | K32 = k, r] = C(128,j)^-1 sum_l C(k,l) C(96,j-l) r^(j-l): Monte Carlo over K96 ~ Bin(96, r)
    at fixed (k, r) vs the formula, j = 1..4 (2e6 draws), plus the exact statement tilde U_1 - r = (32/128)(k/32 - r).
(2) E[phi_i] = 0 (phi_i = g tilde U_a - sum_b beta_b tilde U_{a+b} has conditional mean zero given r) by MC over K32 | r.
(3) ANOVA between-variance component is unbiased: synthetic nested Bernoulli model with known Var_o(delta_o).
Environment: CPU x86_64, python 3.13.16, numpy 2.5.4, scipy 1.18.1, 2026-10-19."""
import json, os, sys
from math import comb
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c_common import U_stat, between_variance_component

rng = np.random.default_rng(4104)
out = {}
# (1)
def tildeU(j, k, r, m0=32, m1=128):
    return sum(comb(k, l) * comb(m1 - m0, j - l) * r ** (j - l) for l in range(j + 1)) / comb(m1, j)
res1 = {}
for (k, r) in ((5, 0.2), (9, 0.25), (0, 0.1), (20, 0.6)):
    K96 = rng.binomial(96, r, 2_000_000)
    for j in (1, 2, 3, 4):
        mc = U_stat(k + K96, j, 128)
        res1[f"k={k},r={r},j={j}"] = dict(formula=tildeU(j, k, r), mc_mean=float(mc.mean()), mc_se=float(mc.std() / np.sqrt(mc.size)))
    res1[f"k={k},r={r},exact_U1"] = dict(lhs=tildeU(1, k, r) - r, rhs=(32 / 128) * (k / 32 - r))
out["projection_formula"] = res1
# (2)
g = (0.18, -0.8, 0.0)
def phi_rows(k, r):
    gr = g[0] + g[1] * r + g[2] * r ** 2
    rows = [gr * tildeU(a, k, r) - sum(g[b] * tildeU(a + b, k, r) for b in range(3)) for a in range(3)]
    rows.append(gr - sum(g[b] * tildeU(b, k, r) for b in range(3)))
    return np.array(rows)
res2 = {}
for r in (0.2, 0.25, 0.5):
    K32 = rng.binomial(32, r, 400_000)
    vals = np.array([phi_rows(k, r) for k in range(33)])       # 33 x 4 table
    w = np.bincount(K32, minlength=33) / K32.size
    exact_pm = np.array([comb(32, k) * r ** k * (1 - r) ** (32 - k) for k in range(33)])
    res2[f"r={r}"] = dict(E_phi_exact_pmf=(exact_pm @ vals).tolist(), E_phi_mc=(w @ vals).tolist(), sd_phi=np.sqrt(exact_pm @ vals ** 2).tolist())
out["E_phi_zero"] = res2
# (3)
n_out, n_in, reps = 400, 50, 4000
true_var = 0.003 ** 2
ests = []
for _ in range(reps):
    delta_o = 0.0 + rng.normal(0, 0.003, n_out)                               # Var = 9e-6
    p_r = 0.05 + delta_o / 2; p_f = 0.05 - delta_o / 2
    y = rng.binomial(1, p_r, (n_in, n_out)).T.astype(float) - rng.binomial(1, p_f, (n_in, n_out)).T.astype(float)
    ests.append(between_variance_component(y))
ests = np.array(ests)
out["anova_unbiasedness"] = dict(true_between_var=true_var, mean_estimate=float(ests.mean()), se_of_mean=float(ests.std() / np.sqrt(reps)),
                                 note="y = 1_R - 1_R' with P(R)=.05+delta/2, P(R')=.05-delta/2 so Var_o(E y|o) = Var(delta)")
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "c4_identity_check.json"), "w"), indent=1)
for k, v in res1.items():
    print(k, v)
for k, v in res2.items():
    print(k, "E_phi exact pmf:", np.round(v["E_phi_exact_pmf"], 12).tolist(), " sd_phi:", np.round(v["sd_phi"], 5).tolist())
print("anova:", out["anova_unbiasedness"])
