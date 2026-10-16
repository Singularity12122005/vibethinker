"""Factorial (u_2, u_3) model and backward induction (plan §8.8, §7.10).

Per prefix i the 3×3 (pilot) or 5×5 (confirmation) table of Y^{A3} counts k/K per (u_2, u_3) gives empirical logits
L = log((k+0.5)/(K−k+0.5)) with Cox–Snell weights w = (k+0.5)(K−k+0.5)/(K+1); WLS of a_i − g_i u_3 − c_i u_2 − κ_i u_2 u_3
(u in multiples of alpha_max).  Precision-weighted random-effects pooling (DerSimonian–Laird), cluster-robust SE by
problem, LRT of Var(c_i) = 0 with the per-prefix sampling variances explicit, empirical-Bayes shrinkage c̃_i, and the
backward-induction MPC-vs-myopic comparison on the observed table.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import optimize, stats


def empirical_logit(k: np.ndarray, K: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    k, K = np.asarray(k, float), np.asarray(K, float)
    L = np.log((k + 0.5) / (K - k + 0.5))
    w = (k + 0.5) * (K - k + 0.5) / (K + 1)
    return L, w


def fit_prefix(u2: np.ndarray, u3: np.ndarray, k: np.ndarray, K: np.ndarray) -> Dict[str, object]:
    """WLS of L ~ a − g u3 − c u2 − κ u2 u3 on one prefix's cells. Returns coefficients (a, g, c, kappa) and their
    sampling covariance (from the weights)."""
    L, w = empirical_logit(k, K)
    X = np.stack([np.ones_like(u2), -np.asarray(u3, float), -np.asarray(u2, float), -np.asarray(u2, float) * np.asarray(u3, float)], 1)
    W = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * W[:, None], L * W, rcond=None)
    XtWX = X.T @ (X * w[:, None])
    cov = np.linalg.pinv(XtWX)                     # Var(L_cell) ≈ 1/w  => Cov(beta) = (XᵀWX)⁻¹
    return dict(a=float(beta[0]), g=float(beta[1]), c=float(beta[2]), kappa=float(beta[3]), cov=cov,
                se=np.sqrt(np.diag(cov)), n_cells=int(len(k)))


def dersimonian_laird(est: np.ndarray, var: np.ndarray) -> Dict[str, float]:
    est, var = np.asarray(est, float), np.asarray(var, float)
    w = 1 / var
    mu_fe = (w * est).sum() / w.sum()
    Q = float((w * (est - mu_fe) ** 2).sum())
    k = len(est)
    C = w.sum() - (w ** 2).sum() / w.sum()
    tau2 = max(0.0, (Q - (k - 1)) / C) if C > 0 else 0.0
    wr = 1 / (var + tau2)
    mu = (wr * est).sum() / wr.sum()
    return dict(mu=float(mu), se=float(np.sqrt(1 / wr.sum())), tau2=float(tau2), Q=Q, df=k - 1,
                p_Q=float(stats.chi2.sf(Q, k - 1)) if k > 1 else float("nan"))


def cluster_robust_mean(est: np.ndarray, var: np.ndarray, cluster: np.ndarray, tau2: float = 0.0) -> Dict[str, float]:
    """Precision-weighted mean with a cluster-robust SE (problems as clusters)."""
    est, var, cluster = np.asarray(est, float), np.asarray(var, float), np.asarray(cluster)
    w = 1 / (var + tau2)
    mu = (w * est).sum() / w.sum()
    ups = np.unique(cluster)
    G = len(ups)
    s = np.array([(w[cluster == c] * (est[cluster == c] - mu)).sum() for c in ups])
    se = np.sqrt((s ** 2).sum() * G / max(G - 1, 1)) / w.sum()
    return dict(mu=float(mu), se_cluster=float(se), n_clusters=int(G))


def lrt_random_effect(est: np.ndarray, var: np.ndarray) -> Dict[str, float]:
    """LRT of τ² = 0 for c_i ~ N(c, τ²) observed with known sampling variances var_i; p from the ½χ²₀ + ½χ²₁ mixture."""
    est, var = np.asarray(est, float), np.asarray(var, float)

    def nll(params):
        mu, log_tau2 = params
        v = var + np.exp(log_tau2)
        return 0.5 * (np.log(2 * np.pi * v) + (est - mu) ** 2 / v).sum()
    w = 1 / var
    mu0 = (w * est).sum() / w.sum()
    ll0 = -0.5 * (np.log(2 * np.pi * var) + (est - mu0) ** 2 / var).sum()
    best = None
    for start in (-6.0, -3.0, -1.0, 0.0):
        r = optimize.minimize(nll, x0=[mu0, start], method="Nelder-Mead", options=dict(xatol=1e-8, fatol=1e-10, maxiter=4000))
        if best is None or r.fun < best.fun:
            best = r
    ll1 = -best.fun
    lr = max(0.0, 2 * (ll1 - ll0))
    p = 0.5 * stats.chi2.sf(lr, 1) if lr > 0 else 1.0
    return dict(LR=float(lr), p=float(p), tau2=float(np.exp(best.x[1])), mu=float(best.x[0]))


def eb_shrink(est: np.ndarray, var: np.ndarray, mu: float, tau2: float) -> np.ndarray:
    est, var = np.asarray(est, float), np.asarray(var, float)
    B = tau2 / (tau2 + var)
    return mu + B * (est - mu)


# ---------------------------------------------------------------- backward induction on the table
def backward_induction(table_p: np.ndarray, p_e2: np.ndarray, u_grid: Sequence[float], lam: float, alpha_max_units: bool = True
                       ) -> Dict[str, object]:
    """table_p[i, j] = P̂(Y^{A3} | u2 = u_grid[i], u3 = u_grid[j]); p_e2[i] = P̂(e_2 | u2 = u_grid[i]); cost c(u) = |u|
    (u in multiples of alpha_max).  Total cost(u2, u3) = p_e2[u2] + λ|u2| + table_p[u2, u3] + λ|u3|.
    MPC (oracle-in-sample): first action of the min-total-cost sequence; myopic: u2* = argmin p_e2 + λ|u2| then u3*
    given u2*.  Returns both plans and the gain."""
    U = np.asarray(u_grid, float)
    cost_u = lam * np.abs(U)
    total = p_e2[:, None] + cost_u[:, None] + table_p + cost_u[None, :]
    i_mpc, j_mpc = np.unravel_index(np.argmin(total), total.shape)
    i_my = int(np.argmin(p_e2 + cost_u))
    j_my = int(np.argmin(table_p[i_my] + cost_u))
    return dict(mpc=(float(U[i_mpc]), float(U[j_mpc])), myopic=(float(U[i_my]), float(U[j_my])),
                cost_mpc=float(total[i_mpc, j_mpc]), cost_myopic=float(total[i_my, j_my]),
                gain=float(total[i_my, j_my] - total[i_mpc, j_mpc]), disagree=bool(i_mpc != i_my))


def mpc_vs_myopic(tables: Sequence[np.ndarray], p_e2s: Sequence[np.ndarray], u_grid: Sequence[float], lams: Sequence[float]) -> Dict[float, Dict[str, object]]:
    out = {}
    for lam in lams:
        res = [backward_induction(t, p, u_grid, lam) for t, p in zip(tables, p_e2s)]
        gains = np.array([r["gain"] for r in res])
        out[float(lam)] = dict(disagree_rate=float(np.mean([r["disagree"] for r in res])), mean_gain=float(gains.mean()),
                               gains=gains.tolist(), mpc_first=[r["mpc"][0] for r in res])
    return out


# ---------------------------------------------------------------- G5 primary statistic
def G_statistic(Y: Dict[Tuple[str, float, float], np.ndarray], u3_star: float, alpha_max: float = 1.0, w_a3: float = 0.8, w_c: float = 0.2) -> float:
    """Y[(script, u2, u3)] = per-trajectory Y^S outcomes (eval half).  G = 0.8[Ȳ^{A3}(0,u3*) − Ȳ^{A3}(−1,u3*)] − 0.2[Ȳ^C(−1,u3*) − Ȳ^C(0,u3*)]
    (u in multiples of alpha_max: −1 == −alpha_max)."""
    a0, a1 = Y[("A3", 0.0, u3_star)].mean(), Y[("A3", -1.0, u3_star)].mean()
    c0, c1 = Y[("C", 0.0, u3_star)].mean(), Y[("C", -1.0, u3_star)].mean()
    return float(w_a3 * (a0 - a1) - w_c * (c1 - c0))


def select_u3_star(Y_sel: Dict[Tuple[str, float, float], np.ndarray], u_grid: Sequence[float], lam: float) -> float:
    """argmin_u [Ȳ^{A3}(0, u) + λ|u|] on the selection half (plan §7.10), frozen afterwards."""
    best, best_v = None, np.inf
    for u in u_grid:
        v = Y_sel[("A3", 0.0, float(u))].mean() + lam * abs(u)
        if v < best_v:
            best, best_v = float(u), v
    return best
