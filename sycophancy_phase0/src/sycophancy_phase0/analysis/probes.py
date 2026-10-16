"""Probe ladder with leave-one-question-out ridge regression (plan §8.5, §7.5).

Levels are nested feature sets: (0) problem fixed effects [predicts 0 on problem-demeaned targets], (1) first-token
top-50 logits, (2) forced-suffix log-prob ratio, (3) P̂(e_2 | h_2) (sel), (4) text features, (5) z probes.  For every
level the ridge penalty is chosen by inner K-fold CV (by question) inside each outer LOQO fold; the LOQO predictions
give R², ΔR² over the previous level, a question-level bootstrap CI of ΔR², a Gaussian LRT approximation, a
shuffled-label null for the probe level, and AUROC on the raw target binarised at 0.5.  Ridge is solved in the dual
(kernel) form so that D = 2048 features with n ≈ 1200 prefixes cost one eigendecomposition per fold.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

LAMBDA_GRID = tuple(float(x) for x in np.logspace(-2, 4, 13))


def _standardise(Xtr: np.ndarray, Xte: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    return (Xtr - mu) / sd, (Xte - mu) / sd


def ridge_predict_all_lambdas(Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray, lambdas: Sequence[float]) -> np.ndarray:
    """Dual ridge: ŷ_te(λ) = K_te (K + λI)⁻¹ (y − ȳ) + ȳ via one eigendecomposition of K. Returns [n_te, n_lambda]."""
    Xtr, Xte = _standardise(Xtr, Xte)
    ybar = ytr.mean()
    yc = ytr - ybar
    K = Xtr @ Xtr.T
    evals, evecs = np.linalg.eigh(K)
    evals = np.clip(evals, 0, None)
    Kte = Xte @ Xtr.T
    proj = evecs.T @ yc
    out = np.empty((Xte.shape[0], len(lambdas)))
    for j, lam in enumerate(lambdas):
        alpha = evecs @ (proj / (evals + lam))
        out[:, j] = Kte @ alpha + ybar
    return out


def loqo_predictions(X: np.ndarray, y: np.ndarray, question: np.ndarray, lambdas: Sequence[float] = LAMBDA_GRID,
                     inner_folds: int = 5, seed: int = 0) -> Dict[str, object]:
    """Leave-one-question-out predictions with the penalty chosen per outer fold by inner CV (by question)."""
    X, y, question = np.asarray(X, float), np.asarray(y, float), np.asarray(question)
    qs = np.unique(question)
    rng = np.random.default_rng(seed)
    pred = np.empty_like(y)
    chosen = {}
    for q in qs:
        te = question == q
        tr = ~te
        trq = question[tr]
        uq = np.unique(trq)
        perm = rng.permutation(len(uq))
        fold_of = {uq[i]: perm[i] % inner_folds for i in range(len(uq))}
        inner_f = np.array([fold_of[t] for t in trq])
        sse = np.zeros(len(lambdas))
        Xtr, ytr = X[tr], y[tr]
        for f in range(inner_folds):
            ite = inner_f == f
            if ite.sum() == 0 or (~ite).sum() < 2:
                continue
            p = ridge_predict_all_lambdas(Xtr[~ite], ytr[~ite], Xtr[ite], lambdas)
            sse += ((p - ytr[ite][:, None]) ** 2).sum(0)
        j = int(np.argmin(sse))
        chosen[str(q)] = float(lambdas[j])
        pred[te] = ridge_predict_all_lambdas(Xtr, ytr, X[te], [lambdas[j]])[:, 0]
    return dict(pred=pred, lambda_by_question=chosen)


def r2(y: np.ndarray, pred: np.ndarray) -> float:
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    sst = ((y - y.mean()) ** 2).sum()
    return float(1 - ((y - pred) ** 2).sum() / sst) if sst > 0 else float("nan")


def auroc(y_bin: np.ndarray, score: np.ndarray) -> float:
    from scipy import stats
    y_bin, score = np.asarray(y_bin, bool), np.asarray(score, float)
    n1, n0 = y_bin.sum(), (~y_bin).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    ranks = stats.rankdata(score)
    return float((ranks[y_bin].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def spearman_brown(half0: np.ndarray, half1: np.ndarray) -> float:
    r = np.corrcoef(half0, half1)[0, 1]
    return float(2 * r / (1 + r)) if np.isfinite(r) and r > -1 else float("nan")


def ladder(levels: Sequence[Tuple[str, Optional[np.ndarray]]], y: np.ndarray, question: np.ndarray, raw_target: Optional[np.ndarray] = None,
           n_boot: int = 1000, n_perm: int = 100, perm_level: Optional[str] = None, seed: int = 0, lambdas: Sequence[float] = LAMBDA_GRID,
           inner_folds: int = 5) -> Dict[str, object]:
    """levels: [(name, X or None)], nested cumulatively; level 0 (None) predicts 0 (problem FE on demeaned targets).
    y: problem-demeaned target.  Returns per-level R², ΔR² with question-bootstrap CI (97.5% lower bound per §7.5),
    Gaussian LRT approximation, AUROC (raw_target > 0.5), and a shuffled-label null for ``perm_level``."""
    y, question = np.asarray(y, float), np.asarray(question)
    qs = np.unique(question)
    rng = np.random.default_rng(seed)
    preds: Dict[str, np.ndarray] = {}
    feats: List[np.ndarray] = []
    rows = []
    prev_name = None
    for name, X in levels:
        if X is None:
            pred = np.zeros_like(y)
        else:
            feats.append(np.asarray(X, float).reshape(len(y), -1))
            Xc = np.concatenate(feats, 1)
            pred = loqo_predictions(Xc, y, question, lambdas, inner_folds, seed)["pred"]
        preds[name] = pred
        R2 = r2(y, pred)
        d = dict(level=name, R2=R2, n_features=int(sum(f.shape[1] for f in feats)))
        if prev_name is not None:
            d["delta_R2"] = R2 - r2(y, preds[prev_name])
            sse_prev, sse = ((y - preds[prev_name]) ** 2).sum(), ((y - pred) ** 2).sum()
            n = len(y)
            d["lrt_stat"] = float(n * np.log(sse_prev / sse)) if sse > 0 and sse_prev > 0 else float("nan")
            # question-level bootstrap of ΔR²
            idx = {q: np.where(question == q)[0] for q in qs}
            bs = np.empty(n_boot)
            for b in range(n_boot):
                pick = qs[rng.integers(0, len(qs), len(qs))]
                ii = np.concatenate([idx[q] for q in pick])
                bs[b] = r2(y[ii], pred[ii]) - r2(y[ii], preds[prev_name][ii])
            d["delta_R2_lb975"] = float(np.quantile(bs, 0.025))
            d["delta_R2_ci95"] = (float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975)))
        if raw_target is not None:
            d["auroc"] = auroc(np.asarray(raw_target) > 0.5, pred)
        rows.append(d)
        prev_name = name
    out: Dict[str, object] = dict(levels=rows, preds=preds)
    if perm_level is not None:
        names = [n for n, _ in levels]
        k = names.index(perm_level)
        base_feats = [np.asarray(X, float).reshape(len(y), -1) for _, X in levels[:k] if X is not None]
        full_feats = base_feats + [np.asarray(levels[k][1], float).reshape(len(y), -1)]
        null = np.empty(n_perm)
        for p in range(n_perm):
            yp = y[rng.permutation(len(y))]
            pb = loqo_predictions(np.concatenate(base_feats, 1), yp, question, lambdas, inner_folds, seed + p)["pred"] if base_feats else np.zeros_like(y)
            pf = loqo_predictions(np.concatenate(full_feats, 1), yp, question, lambdas, inner_folds, seed + p)["pred"]
            null[p] = r2(yp, pf) - r2(yp, pb)
        obs = next(r["delta_R2"] for r in rows if r["level"] == perm_level)
        out["perm_null"] = dict(level=perm_level, null=null.tolist(), p=float((np.sum(null >= obs) + 1) / (n_perm + 1)), observed=obs)
    return out


def g3_decision(delta_R2: float, lb975: float, rho_sh: float, min_frac: float = 0.2) -> str:
    """plan §7.5: ΔR² 97.5% lower bound > 0 and point estimate >= 0.2·ρ_sh => GO."""
    return "GO" if (lb975 > 0 and delta_R2 >= min_frac * rho_sh) else "KILL"
