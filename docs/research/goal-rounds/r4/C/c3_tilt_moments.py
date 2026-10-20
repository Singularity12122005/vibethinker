"""r4 route C, Proposition 2 (score-level mechanism of reuse), exact moment evaluation.

phi_i = E[psi_i | r_i, K32_i] is the only part of the corrected score that a pilot rule can tilt.  With
  Ut_j(k, r) := E[U_j(K128) | K32 = k, r] = sum_l c_{jl} r^{j-l} U_l(k),  c_{jl} = C(32,l) C(96,j-l) / C(128,j),
phi_{i,a} = g(r_i) Ut_a - sum_b beta_b Ut_{a+b}  (a = 0,1,2; type row = t_i (g - sum_b beta_b Ut_b)),
d_i      = u_i g(r_i) - M_i beta_0   (the measurement-error part of psi_i given the FINAL counts),
psi_i    = u_i eta_i + d_i,   Sigma = Var(psi_i) = E[Var(eta|r) u u^T] + Var(d_i),   Phi = Var(phi_i) <= Var(d_i)  (Loewner).
All expectations are polynomials in the risk moments mu_j (<= order 8 for the quadratic design) and are evaluated EXACTLY with
fractions.Fraction via the A1 identity E[r^s U_j U_k | r] (binomial_factorial_joint_moment on shifted moment lists).
Output: pilot share of the ME variance of U_1 (exactly 32/128) and U_2; and along the population type direction w = A^{-1} e_4:
  kappa = sqrt(w'Phi w / w'Sigma w)  (max standardized mean tilt of the type score at P(D)=1/2 is kappa; at P(D)=pi it is
  kappa*sqrt((1-pi)/pi)),  ME share w'Var(d)w / w'Sigma w, and pilot share within ME.
Var(eta | r) = [2 r (1-r) - g(r)^2 / 2] / 16 (two independent 16-draw arms, q_pm = r pm g/2, no clipping).
Environment: CPU x86_64, python 3.13.16, numpy 2.5.4, scipy 1.18.1, 2026-10-19."""
import json, os, sys
from fractions import Fraction as F
from math import comb
import numpy as np
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import binomial_factorial_joint_moment

HERE = os.path.dirname(os.path.abspath(__file__))
M0, M1 = 32, 128
WORLDS = {"narrow": ((F(20), F(80)), (F(25), F(75))), "halfvar": ((F(81, 2), F(162)), (F(253, 5), F(759, 5))),
          "wide": ((F(2), F(8)), (F(5, 2), F(15, 2)))}
G = {"lin": (F(18, 100), F(-8, 10), F(0)), "quad": (F(26, 100), F(-16, 10), F(2)), "cheb": (F(1, 2), F(-4), F(4))}
ORD = 12   # highest risk moment needed: r^s U_j U_k with s + j + k <= 4 + 2 + 2 + ... keep margin


def beta_moments(a, b, order):
    mu = [F(1)]
    for j in range(order):
        mu.append(mu[-1] * (a + j) / (a + b + j))
    return mu


class Poly:
    """Finite sum  sum coef * r^s U_j(K_m)  as a dict {(s, j): coef}; j = 0 means no U factor."""
    def __init__(self, d=None):
        self.d = dict(d or {})
    def __add__(self, o):
        out = Poly(self.d)
        for k, v in o.d.items():
            out.d[k] = out.d.get(k, F(0)) + v
        return out
    def __sub__(self, o):
        return self + o.scale(F(-1))
    def scale(self, c):
        return Poly({k: v * c for k, v in self.d.items()})
    def times_r(self, s):
        return Poly({(k[0] + s, k[1]): v for k, v in self.d.items()})


def E_prod(p, q, mu, m):
    """E[p * q] for two Poly's in the same count K ~ Bin(m, r): sum coef coef' E[r^{s+s'} U_j U_k]."""
    tot = F(0)
    for (s, j), c in p.d.items():
        for (s2, k), c2 in q.d.items():
            shifted = mu[s + s2:]
            tot += c * c2 * binomial_factorial_joint_moment(shifted, m, j, k)
    return tot


def E_lin(p, mu):
    return sum(c * mu[s + j] for (s, j), c in p.d.items())   # E[r^s U_j] = mu_{s+j}


def U(j):            # U_j(K) as a Poly
    return Poly({(0, j): F(1)})


def Ut(j):           # E[U_j(K128) | K32, r] as a Poly in (r, U_l(K32))
    return Poly({(j - l, l): F(comb(M0, l) * comb(M1 - M0, j - l), comb(M1, j)) for l in range(j + 1)})


def gpoly(g):        # g(r) as Poly with no U factor
    return Poly({(k, 0): c for k, c in enumerate(g) if c != 0})


def mul_g(p, g):     # g(r) * p
    out = Poly()
    for k, c in enumerate(g):
        if c != 0:
            out = out + p.times_r(k).scale(c)
    return out


def score_components(g, beta, Ufun):
    """Rows a=0,1,2 of  u_a g(r) - sum_b beta_b U_{a+b}  with U replaced by Ufun (U for d_i, Ut for phi_i); plus the row
    (g - sum_b beta_b U_b) that multiplies t_i."""
    rows = []
    for a in range(3):
        p = mul_g(Ufun(a), g)
        for b in range(3):
            if beta[b] != 0:
                p = p - Ufun(a + b).scale(beta[b])
        rows.append(p)
    p = gpoly(g)
    for b in range(3):
        if beta[b] != 0:
            p = p - Ufun(b).scale(beta[b])
    rows.append(p)
    return rows


def cov_matrix(rows, mu_t, m, with_type):
    """E[rows rows^T] per type (mean zero given r, so this is the covariance); the last row carries factor t."""
    k = 4
    C = [[F(0)] * k for _ in range(k)]
    for a in range(k):
        for b in range(k):
            fac = (1 if (a < 3 and b < 3) else (with_type))   # t^2 = t = 1 for type 1, 0 for type 0 on the type row/col
            if fac:
                C[a][b] = E_prod(rows[a], rows[b], mu_t, m)
    return C


def main():
    out = {}
    for wname, (ab0, ab1) in WORLDS.items():
        mus = [beta_moments(*ab0, ORD), beta_moments(*ab1, ORD)]
        # (i) pilot share of the ME variance of U_j(K128), j = 1, 2 (pooled over types)
        shares = {}
        for j in (1, 2):
            num = sum(E_prod(Ut(j), Ut(j), mu, M0) - mu[2 * j] for mu in mus) / 2
            den = sum(binomial_factorial_joint_moment(mu, M1, j, j) - mu[2 * j] for mu in mus) / 2
            shares[f"U{j}"] = dict(var_pilot_part=float(num), var_ME_total=float(den), share=float(num / den), share_exact=str(num / den))
        res = dict(pilot_share_of_ME_variance=shares)
        # (ii) along the population type direction
        A = np.zeros((4, 4))
        for a in range(3):
            for b in range(3):
                A[a, b] = float((mus[0][a + b] + mus[1][a + b]) / 2)
            A[a, 3] = A[3, a] = float(mus[1][a] / 2)
        A[3, 3] = 0.5
        w = np.linalg.solve(A, np.eye(4)[3])
        for gname, g in G.items():
            beta = g
            Phi = np.zeros((4, 4)); Vd = np.zeros((4, 4)); Veta = np.zeros((4, 4))
            v_eta = Poly({(1, 0): F(2, 16), (2, 0): F(-2, 16)}) - mul_g(gpoly(g), g).scale(F(1, 32))  # [2r(1-r) - g^2/2]/16
            for t, mu in enumerate(mus):
                rows_phi = score_components(g, beta, Ut); rows_d = score_components(g, beta, U)
                Cphi = cov_matrix(rows_phi, mu, M0, t); Cd = cov_matrix(rows_d, mu, M1, t)
                for a in range(4):
                    for b in range(4):
                        Phi[a, b] += float(Cphi[a][b]) / 2; Vd[a, b] += float(Cd[a][b]) / 2
                        ua = U(a) if a < 3 else Poly({(0, 0): F(t)}); ub = U(b) if b < 3 else Poly({(0, 0): F(t)})
                        # E[Var(eta|r) u_a u_b]: expand v_eta * u_a * u_b  -> use E_prod on (v_eta * u_a, u_b)
                        va = Poly()
                        for (s, jj), c in ua.d.items():
                            for (s2, _), c2 in v_eta.d.items():
                                va = va + Poly({(s + s2, jj): c * c2})
                        Veta[a, b] += float(E_prod(va, ub, mu, M1)) / 2
            Sigma = Veta + Vd
            wPw, wSw, wDw = w @ Phi @ w, w @ Sigma @ w, w @ Vd @ w
            kappa = float(np.sqrt(wPw / wSw))
            from scipy.stats import norm
            res[gname] = dict(kappa_tilt_ratio=kappa, ME_share_type_dir=float(wDw / wSw), pilot_share_within_ME_type_dir=float(wPw / wDw),
                              tilt_bound_sd_units={str(p): kappa * float(np.sqrt((1 - p) / p)) for p in (0.5, 0.25, 0.1)},
                              first_order_size_at_mean_shift_kappa=float(norm.cdf(-1.96 - kappa) + norm.cdf(-1.96 + kappa)),
                              var_eta_mean=float((E_lin(v_eta, mus[0]) + E_lin(v_eta, mus[1])) / 2),
                              Phi_diag=np.diag(Phi).tolist(), Vd_diag=np.diag(Vd).tolist(), Veta_diag=np.diag(Veta).tolist())
        out[wname] = res
        print(wname, json.dumps({k: (v if k == "pilot_share_of_ME_variance" else {kk: v[kk] for kk in ("kappa_tilt_ratio", "ME_share_type_dir", "pilot_share_within_ME_type_dir", "first_order_size_at_mean_shift_kappa")}) for k, v in res.items()}, indent=None), flush=True)
    json.dump(out, open(os.path.join(HERE, "c3_tilt_moments.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
