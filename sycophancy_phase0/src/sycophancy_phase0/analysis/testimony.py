"""Testimony-model check (plan §8.9, §7.4 (ii)).

For each A3 h_3: M_s = 128 alpha = 0 y_3 with judge stance (+ = USER, − = ORIG; OTHER/NONE excluded, share reported),
each with m = 8 alpha = 0 y_4 giving q̄_j = P̂(e_4 | y_3).  On the risk scale, judge misclassification is inverted
with PPV/NPV from the human-labelled, unsteered A3 turn-3 stratum:
    μ_+ = [NPV q̄_+ − (1 − PPV) q̄_−] / (PPV + NPV − 1),   μ_− = [PPV q̄_− − (1 − NPV) q̄_+] / (PPV + NPV − 1),
then LOR = logit μ_+ − logit μ_−, λ_m/τ = LOR/2.  Uncertainty: joint bootstrap over the human subset (PPV/NPV) and
the y_3 groups within prefix (optionally prefixes too).  Also: prefix-FE logistic regression e_4 ~ stance +
stance × risk stratum (cluster-robust by prefix) and the same-stance ICC with a within-prefix permutation test.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .glm import logit_fit, wald
from .varcomp import u_stat_var


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return float(np.log(p / (1 - p)))


def corrected_means(q_plus: float, q_minus: float, ppv: float, npv: float) -> Tuple[float, float]:
    d = ppv + npv - 1
    if d <= 0:
        return float("nan"), float("nan")
    mu_p = (npv * q_plus - (1 - ppv) * q_minus) / d
    mu_m = (ppv * q_minus - (1 - npv) * q_plus) / d
    return float(np.clip(mu_p, 0, 1)), float(np.clip(mu_m, 0, 1))


def ppv_npv(human: Sequence[str], judge: Sequence[str], positive: str = "USER") -> Dict[str, float]:
    """PPV = P(human=+ | judge=+), NPV = P(human=− | judge=−) on the calibration stratum (judge ORIG counted as −)."""
    h, j = np.asarray(human), np.asarray(judge)
    jp, jn = j == positive, j != positive
    return dict(PPV=float((h[jp] == positive).mean()) if jp.any() else float("nan"),
                NPV=float((h[jn] != positive).mean()) if jn.any() else float("nan"), n=int(len(h)))


def testimony_point(prefix: np.ndarray, stance: np.ndarray, qbar: np.ndarray, ppv: float, npv: float) -> Dict[str, float]:
    """prefix, stance ('USER'/'ORIG'/other), qbar = per-y_3 P̂(e_4) (from m continuations).  Prefix-level means of q̄
    per stance, averaged over prefixes with both classes, then corrected and converted to LOR."""
    prefix, stance, qbar = np.asarray(prefix), np.asarray(stance), np.asarray(qbar, float)
    qp, qm, used = [], [], 0
    for p in np.unique(prefix):
        m = prefix == p
        a, b = qbar[m & (stance == "USER")], qbar[m & (stance == "ORIG")]
        if len(a) and len(b):
            qp.append(a.mean()); qm.append(b.mean()); used += 1
    if used == 0:
        return dict(LOR=float("nan"), lambda_m_over_tau=float("nan"), n_prefix=0)
    q_plus, q_minus = float(np.mean(qp)), float(np.mean(qm))
    mu_p, mu_m = corrected_means(q_plus, q_minus, ppv, npv)
    lor = _logit(mu_p) - _logit(mu_m)
    return dict(q_plus=q_plus, q_minus=q_minus, mu_plus=mu_p, mu_minus=mu_m, LOR=lor, lambda_m_over_tau=lor / 2, n_prefix=used,
                excluded_share=float(np.mean(~np.isin(stance, ["USER", "ORIG"]))))


def testimony_bootstrap(prefix, stance, qbar, human: Sequence[str], judge: Sequence[str], n_boot: int = 2000, seed: int = 0,
                        resample_prefixes: bool = False) -> Dict[str, float]:
    rng = np.random.default_rng(seed)
    prefix, stance, qbar = np.asarray(prefix), np.asarray(stance), np.asarray(qbar, float)
    human, judge = np.asarray(human), np.asarray(judge)
    cal = ppv_npv(human, judge)
    est = testimony_point(prefix, stance, qbar, cal["PPV"], cal["NPV"])
    ups = np.unique(prefix)
    idx = {p: np.where(prefix == p)[0] for p in ups}
    bs = np.empty(n_boot)
    for b in range(n_boot):
        hb = rng.integers(0, len(human), len(human))
        c = ppv_npv(human[hb], judge[hb])
        picks = ups[rng.integers(0, len(ups), len(ups))] if resample_prefixes else ups
        ii, pp = [], []
        for k, p in enumerate(picks):
            r = idx[p][rng.integers(0, len(idx[p]), len(idx[p]))]
            ii.append(r); pp.append(np.full(len(r), k))
        ii, pp = np.concatenate(ii), np.concatenate(pp)
        bs[b] = testimony_point(pp, stance[ii], qbar[ii], c["PPV"], c["NPV"])["LOR"]
    bs = bs[np.isfinite(bs)]
    return dict(**est, PPV=cal["PPV"], NPV=cal["NPV"], LOR_ci95=(float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))) if bs.size else (float("nan"),) * 2,
                LOR_se=float(bs.std(ddof=1)) if bs.size > 1 else float("nan"))


def fe_logit_stance_by_stratum(prefix: np.ndarray, stance: np.ndarray, stratum: np.ndarray, e4: np.ndarray) -> Dict[str, object]:
    """Prefix fixed effects + stance + stance × risk-stratum dummies (rows = y_4 continuations, or y_3 with e4 = q̄
    as fractional outcome); cluster-robust by prefix.  Reports the stance LOR per stratum and a homogeneity Wald test."""
    prefix, stance, stratum, e4 = np.asarray(prefix), np.asarray(stance), np.asarray(stratum), np.asarray(e4, float)
    keep = np.isin(stance, ["USER", "ORIG"])
    prefix, stance, stratum, e4 = prefix[keep], stance[keep], stratum[keep], e4[keep]
    ups = np.unique(prefix); strata = np.unique(stratum)
    s_ind = (stance == "USER").astype(float)
    cols = [np.where(prefix == p, 1.0, 0.0) for p in ups]
    cols.append(s_ind)
    names = [f"fe_{p}" for p in ups] + ["stance"]
    for st in strata[1:]:
        cols.append(s_ind * (stratum == st)); names.append(f"stance_x_{st}")
    X = np.stack(cols, 1)
    fit = logit_fit(X, e4, cluster=prefix)
    base = names.index("stance")
    per_stratum = {}
    for st in strata:
        c = np.zeros(len(names)); c[base] = 1
        if st != strata[0]:
            c[names.index(f"stance_x_{st}")] = 1
        per_stratum[str(st)] = wald(fit["beta"], fit["cov_robust"], c)
    inter_idx = [i for i, n in enumerate(names) if n.startswith("stance_x_")]
    if inter_idx:
        C = np.zeros((len(inter_idx), len(names)))
        for r, i in enumerate(inter_idx):
            C[r, i] = 1
        b = C @ fit["beta"]; V = C @ fit["cov_robust"] @ C.T
        from scipy import stats
        chi2 = float(b @ np.linalg.solve(V, b)); p_hom = float(stats.chi2.sf(chi2, len(inter_idx)))
    else:
        chi2, p_hom = float("nan"), float("nan")
    return dict(per_stratum_LOR=per_stratum, homogeneity_chi2=chi2, homogeneity_p=p_hom, n=int(len(e4)), n_prefix=int(len(ups)))


def same_stance_icc(prefix: np.ndarray, stance: np.ndarray, K: np.ndarray, m: int, n_perm: int = 500, seed: int = 0) -> Dict[str, object]:
    """Within each prefix and stance class: Var_j(q_j) U-statistic over the y_3 of that class (K_j = e_4 count of its
    m continuations); pooled over prefixes (equal weights); permutation null by shuffling stance labels within prefix."""
    prefix, stance, K = np.asarray(prefix), np.asarray(stance), np.asarray(K, float)
    rng = np.random.default_rng(seed)

    def stat(st):
        vals = {"USER": [], "ORIG": []}
        for p in np.unique(prefix):
            for s in vals:
                mm = (prefix == p) & (st == s)
                if mm.sum() >= 2:
                    vals[s].append(u_stat_var(K[mm], m))
        return {s: (float(np.mean(v)) if v else float("nan")) for s, v in vals.items()}
    obs = stat(stance)
    null = {"USER": [], "ORIG": []}
    for _ in range(n_perm):
        stp = stance.copy()
        for p in np.unique(prefix):
            mm = np.where(prefix == p)[0]
            stp[mm] = stance[mm][rng.permutation(len(mm))]
        r = stat(stp)
        for s in null:
            null[s].append(r[s])
    out = dict(observed=obs)
    for s in null:
        nn = np.array([v for v in null[s] if np.isfinite(v)])
        out[f"perm_p_{s}"] = float((np.sum(nn >= obs[s]) + 1) / (len(nn) + 1)) if nn.size and np.isfinite(obs[s]) else float("nan")
    return out
