"""Scope review of A-C1: recompute w_1 under preconditions the real pipeline does not guarantee."""
import sys, json, glob
import numpy as np
R4 = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4"
sys.path.insert(0, glob.glob(R4 + "/A__*")[0])
from route_a_lib import first_order, beta_moments, sup_quadratic_over_bounded_g, overlap_D, V_poly, pmom, pmul, padd, pscale, monomial
Z = 1.959963984540054
n, w1 = 200, 0.5
worlds = {"narrow": ((20, 80), (25, 75)), "halfvar": ((40.5, 162), (50.6, 151.8)), "wide": ((2, 8), (2.5, 7.5))}
beta_lin = (0.18, -0.8, 0.0)
out = {}
for name, (ab0, ab1) in worlds.items():
    mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
    res = {}
    for m in (32, 128, 512):
        base = first_order(mu0, mu1, w1, m, n, beta=beta_lin)
        supA = first_order(mu0, mu1, w1, m, n, sup_g=True)       # author's class, sigma2 <= r(1-r)/8
        # (i) sigma2 <= 1/32 uniformly (asymmetric arms allowed by the plan): eta-term with constant sigma2
        s32 = first_order(mu0, mu1, w1, m, n, beta=beta_lin, sigma2=[1.0 / 32])
        Om = np.array(s32["Omega"])
        g_full, _ = sup_quadratic_over_bounded_g(Om)
        g_c2, _ = sup_quadratic_over_bounded_g(Om, coef_bound=2.0)
        D = s32["D"]
        def width(term_eta, term_g):
            return 2 * Z * np.sqrt((term_eta + term_g) / (n * D * D))
        # author's numbers (sigma2 <= r(1-r)/8)
        wA_full = width(supA["term_eta"], g_full)
        wA_c2 = width(supA["term_eta"], g_c2)
        # sigma2 = 1/32
        w32_full = width(s32["term_eta"], g_full)
        w32_c2 = width(s32["term_eta"], g_c2)
        w32_lin = s32["width1"]
        res[m] = dict(w1_lin=base["width1"], oracle=base["width_oracle"], D=D,
                      author_sup_full=wA_full, author_sup_c2=wA_c2,
                      s32_lin=w32_lin, s32_sup_full=w32_full, s32_sup_c2=w32_c2,
                      term_eta_author=supA["term_eta"], term_eta_s32=s32["term_eta"], term_g_full=g_full, term_g_c2=g_c2)
    out[name] = res
    print(name, "D=%.4f" % res[128]["D"])
    for m in (32, 128, 512):
        r = res[m]
        print("  m=%4d  w1(lin)=%.4f oracle=%.4f | author sup full/c2 = %.4f/%.4f | sigma2=1/32: lin=%.4f sup full/c2 = %.4f/%.4f"
              % (m, r["w1_lin"], r["oracle"], r["author_sup_full"], r["author_sup_c2"], r["s32_lin"], r["s32_sup_full"], r["s32_sup_c2"]))

# (ii) |g| <= 1 only on the risk support [a, b] (what the pipeline actually forces: |Delta| <= 1 where r lives)
def osc_on(c, s, a, b):
    vals = [c * a + s * a * a, c * b + s * b * b]
    if s != 0:
        rs = -c / (2 * s)
        if a < rs < b:
            vals.append(c * rs + s * rs * rs)
    return max(vals) - min(vals)
print("\n(ii) sup over {|g|<=1 on supp} with supp = central 99% of the mixture, sigma2 author bound, m=128")
from scipy.stats import beta as Beta
for name, (ab0, ab1) in worlds.items():
    mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
    a = min(Beta.ppf(0.005, *ab0), Beta.ppf(0.005, *ab1)); b = max(Beta.ppf(0.995, *ab0), Beta.ppf(0.995, *ab1))
    supA = first_order(mu0, mu1, w1, 128, n, sup_g=True)
    Om = np.array(supA["Omega"]); D = supA["D"]
    best = 0; bb = None
    for th in np.linspace(0, np.pi, 3600, endpoint=False):
        c, s = np.cos(th), np.sin(th)
        o = osc_on(c, s, a, b)
        if o <= 0: continue
        rad = 2.0 / o
        v = np.array([c * rad, s * rad])
        val = v @ Om @ v
        if val > best: best, bb = val, v
    wsup = 2 * Z * np.sqrt((supA["term_eta"] + best) / (n * D * D))
    print("  %s supp=[%.3f,%.3f] beta*=(%.1f,%.1f) sup w1 = %.4f (author on [0,1]: %.4f)" % (name, a, b, bb[0], bb[1], wsup, out[name][128]["author_sup_full"]))

# (iii) question effect in Delta beyond r: CR1 first-order factor under two cluster layouts
print("\n(iii) CR1 first-order variance with an additive question effect a_q in eta, Var(a_q)=tau2, m=128, g linear")
for name, (ab0, ab1) in worlds.items():
    mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
    D, gam = overlap_D(mu0, mu1, w1)
    base = first_order(mu0, mu1, w1, 128, n, beta=beta_lin)
    # E[rho | t] for each type: rho = t - g0 - g1 r - g2 r^2
    e1 = 1 - gam[0] - gam[1] * mu1[1] - gam[2] * mu1[2]
    e0 = 0 - gam[0] - gam[1] * mu0[1] - gam[2] * mu0[2]
    for tau2 in (0.0025, 0.01):   # sd 5pp / 10pp question-level shift of Delta
        # layout A: each question has 2 type-0 + 2 type-1 (shared questions, as in the author's simulation)
        crossA = (2 * e0 * e0 + 2 * e1 * e1 + 8 * e0 * e1) * tau2 / 4      # ordered pairs i!=j per cluster, per prefix
        # layout B: each question has 4 prefixes of one type (types from disjoint questions)
        crossB = (12 * (e0 * e0) * 0.5 + 12 * (e1 * e1) * 0.5) * tau2 / 4
        for lab, cross in (("A shared-question", crossA), ("B disjoint-question", crossB)):
            Ephi2 = base["Ephi2"] + cross
            w = 2 * Z * np.sqrt(Ephi2 / (n * D * D))
            print("  %-8s tau=%.2f layout %-20s E[rho|t=1]=%.3f  w1(indep)=%.4f -> w1(CR1)=%.4f (ratio %.3f)"
                  % (name, np.sqrt(tau2), lab, e1, base["width1"], w, w / base["width1"]))
json.dump({k: {str(m): v for m, v in d.items()} for k, d in out.items()}, open(R4 + "/review_A-C1_scope/s1_scope_numbers.json", "w"), indent=1, default=float)
