"""r4 / Route A, claim 1: exact (Fraction) verification of the first-order sandwich of the type coefficient
    [Q^{-1} B Q^{-1}]_{tt} = D^{-2} E[phi^2],  phi = psi_type - gamma^T psi_x,
and of the closed form E[phi^2] = sum_t w_t E_t[ sigma2 (rho^2 + g'V2 g) ] + beta' Omega beta (moments <= 8, A1 per-r identity),
against brute-force enumeration of K ~ Bin(m, r) for discrete risk laws (no simulation).  Also: J_poly vs the production
binomial_factorial_joint_moment, the block-inverse identity Q^{-1} e_t = D^{-1}(-gamma, 1), and the first-order widths of the
three archive worlds at (n, m) = (200, 32/128/512) for later comparison with the production simulation (a2 script).
Environment: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19."""
import json, os, sys
from fractions import Fraction
from math import comb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from route_a_lib import (J_poly, first_order, overlap_D, inverse_generic, beta_moments, pd_margin, sigma2_poly_from_g, pmom)
from sycophancy_phase0.analysis.g6_iv import binomial_factorial_joint_moment

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "a1_exact_check.json")
F = Fraction


def falling(K, j):
    out = 1
    for i in range(j):
        out *= (K - i)
    return out


def U(K, j, m):
    return F(falling(K, j), falling(m, j))


def brute_force(laws, w1, m, beta, n_arm=16):
    """laws[t] = list of (r, prob) with Fractions.  Returns exact Q (4x4), B (4x4) = sum_t w_t E_t[psi psi'] and per-type moments."""
    w = [1 - w1, w1]
    Q = [[F(0)] * 4 for _ in range(4)]
    B = [[F(0)] * 4 for _ in range(4)]
    mus = []
    for t in (0, 1):
        mu = [F(0)] * 9
        for r, pr in laws[t]:
            for j in range(9):
                mu[j] += pr * r ** j
            xs = [F(1), r, r * r, F(t)]
            for a in range(4):
                for b in range(4):
                    Q[a][b] += w[t] * pr * xs[a] * xs[b]
            g = beta[0] + beta[1] * r + beta[2] * r * r
            qp, qm = r + g / 2, r - g / 2
            assert 0 <= qp <= 1 and 0 <= qm <= 1
            s2 = (qp * (1 - qp) + qm * (1 - qm)) / n_arm
            for K in range(m + 1):
                pK = comb(m, K) * r ** K * (1 - r) ** (m - K)
                Us = [U(K, j, m) for j in range(5)]
                u = [Us[0], Us[1], Us[2], F(t)]
                # deterministic-given-K part e of psi (psi = eta * u + e)
                e = [sum(beta[b] * (Us[a] * r ** b - Us[a + b]) for b in range(3)) for a in range(3)]
                e.append(F(t) * sum(beta[b] * (r ** b - Us[b]) for b in range(3)))
                for a in range(4):
                    for c in range(4):
                        B[a][c] += w[t] * pr * pK * (s2 * u[a] * u[c] + e[a] * e[c])
        mus.append(mu)
    return Q, B, mus


def run_instance(name, laws, w1, m, beta, n=200):
    Q, B, mus = brute_force(laws, w1, m, beta)
    Qi = inverse_generic(Q)
    QBQ = [[sum(Qi[a][i] * B[i][j] * Qi[j][c] for i in range(4) for j in range(4)) for c in range(4)] for a in range(4)]
    brute_var_tt = QBQ[3][3]
    fo = first_order(mus[0], mus[1], w1, m, n, beta=beta, exact=True)
    D, gamma = fo["D"], fo["gamma"]
    formula_var_tt = fo["Ephi2"] / (D * D)
    # block inverse identity: Q^{-1} e_4 == (-gamma, 1)/D
    col = [Qi[a][3] for a in range(4)]
    ident = [-gamma[0] / D, -gamma[1] / D, -gamma[2] / D, 1 / D]
    # J_poly vs production joint moment (averaged over the type law)
    jp_ok = True
    for t in (0, 1):
        for j in range(0, 5):
            for k in range(0, 5):
                if j + k > 8:
                    continue
                lhs = pmom(J_poly(m, j, k, exact=True), mus[t])
                rhs = binomial_factorial_joint_moment(mus[t], m, j, k)
                jp_ok &= (lhs == rhs)
    res = dict(instance=name, m=m, w1=str(w1), beta=[str(b) for b in beta],
               brute_force_QinvBQinv_tt=str(brute_var_tt), formula_Ephi2_over_D2=str(formula_var_tt),
               exact_equal=bool(brute_var_tt == formula_var_tt), D=str(D), gamma=[str(g) for g in gamma],
               block_inverse_identity_exact=bool(col == ident), J_poly_matches_production_joint_moment=jp_ok,
               term_eta=str(fo["term_eta"]), term_g=str(fo["term_g"]), Omega=[[str(x) for x in row] for row in fo["Omega"]],
               width1_at_n200=float(2 * 1.959963984540054 * (formula_var_tt / n) ** 0.5))
    return res


if __name__ == "__main__":
    out = {"exact_instances": []}
    # Instance 1: two-point / three-point laws, modest g
    laws1 = [[(F(1, 5), F(1, 2)), (F(3, 10), F(1, 2))], [(F(1, 4), F(1, 3)), (F(2, 5), F(1, 3)), (F(1, 2), F(1, 3))]]
    out["exact_instances"].append(run_instance("discrete_2pt/3pt, g=0.18-0.8r+0.3r^2, m=8", laws1, F(1, 2), 8, [F(9, 50), F(-4, 5), F(3, 10)]))
    # Instance 2: strongly curved g, unequal type proportions, m = 10
    laws2 = [[(F(1, 10), F(1, 4)), (F(1, 5), F(1, 2)), (F(3, 10), F(1, 4))], [(F(1, 4), F(1, 2)), (F(9, 20), F(1, 2))]]
    out["exact_instances"].append(run_instance("discrete_3pt/2pt, g=0.1-r+2r^2, w1=2/5, m=10", laws2, F(2, 5), 10, [F(1, 10), F(-1), F(2)]))
    # Instance 3: m = 4 (= 2p, the minimum), V4 has truncated sums (j+k-m terms)
    laws3 = [[(F(1, 5), F(1, 2)), (F(2, 5), F(1, 2))], [(F(3, 10), F(1, 2)), (F(1, 2), F(1, 2))]]
    out["exact_instances"].append(run_instance("discrete, m=4 (=2p), g=0.1-0.2r", laws3, F(1, 2), 4, [F(1, 10), F(-1, 5), F(0)]))
    for r in out["exact_instances"]:
        print(json.dumps(r, indent=None)[:600], "...", flush=True)
    assert all(r["exact_equal"] and r["block_inverse_identity_exact"] and r["J_poly_matches_production_joint_moment"] for r in out["exact_instances"])

    # ---- first-order widths of the archive worlds (n = 200, 100 per type), g linear (0.18, -0.8, 0) and quad as in check1
    worlds = {"narrow": ((20, 80), (25, 75)), "halfvar": ((40.5, 162.0), (50.6, 151.8)), "wide": ((2, 8), (2.5, 7.5)),
              "doublevar": ((9.5, 38.0), (12.0, 36.0))}
    gs = {"linear": (0.18, -0.8, 0.0), "quad_narrow": (0.26, -1.6, 2.0), "quad_wide": (0.30, -1.2, 0.8)}
    tab = {}
    for wn, (ab0, ab1) in worlds.items():
        mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
        D, gamma = overlap_D(mu0, mu1, 0.5)
        tab[wn] = dict(D=float(D), gamma=[float(x) for x in gamma], Hw_lmin=pd_margin(mu0, mu1, 0.5, 32, 100, 100)["lmin_Hw"])
        for m in (32, 128, 512):
            for gn, g in gs.items():
                fo = first_order(mu0, mu1, 0.5, m, 200, beta=g)
                fs = first_order(mu0, mu1, 0.5, m, 200, sup_g=True)
                pm = pd_margin(mu0, mu1, 0.5, m, 100, 100)
                tab[wn]["m=%d|g=%s" % (m, gn)] = dict(width1=fo["width1"], width_oracle=fo["width_oracle"],
                                                      term_eta=fo["term_eta"], term_g=fo["term_g"],
                                                      width1_sup_g=fs["width1"], beta_star_sup=[float(b) for b in fs["beta_star"]],
                                                      kappa=pm["kappa"], lmin_ES=pm["lmin_ES"])
        print(wn, "D=%.4f gamma=%s lmin(Hw)=%.2e" % (tab[wn]["D"], np.round(tab[wn]["gamma"], 3), tab[wn]["Hw_lmin"]))
        for m in (32, 128, 512):
            d = tab[wn]["m=%d|g=linear" % m]
            print("   m=%4d  width1(linear g)=%.4f  oracle=%.4f  [eta-term %.3e, g-term %.3e]  width1 sup_g=%.4f (b*=%s)  kappa=%.3f lminES=%.2e"
                  % (m, d["width1"], d["width_oracle"], d["term_eta"], d["term_g"], d["width1_sup_g"], np.round(d["beta_star_sup"], 2), d["kappa"], d["lmin_ES"]))
    out["first_order_table"] = tab
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT)
