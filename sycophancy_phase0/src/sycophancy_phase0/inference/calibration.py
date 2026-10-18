"""alpha_max calibration (plan §4.7) and kappa_1.

Step 1 (teacher-forced, cheap): for alpha in ±{0.05, …, 2.00} on 200 script-B turn-2 prompt+response pairs (out of
fold): mean next-token KL(P^0 || P^alpha) over response positions and the route-flip fraction over MoE layers > L.
Per |alpha| the worse of the two signs is kept.
Step 2 (generation, coarse grid ±{0.25, …, 2.0}) on the external GSM8K calibration set: explicit-answer rate x_2(alpha)
(script B turn 2, 2 samples per problem) and single-turn accuracy acc(alpha) (2 samples per problem); isotonic
(non-increasing in |alpha|) fits with one-sided 95% lower bounds from a problem-level bootstrap.
Step 3: alpha_max = largest grid alpha such that every grid point in [0.05, alpha] satisfies KL <= 0.10, flip <= 0.05,
x_2 lower bound >= x_2(0) − 0.03 and acc lower bound >= acc(0) − 0.03 (coarse-grid quantities linearly interpolated).
Step 4: kappa_1 = E_{y ~ P^{alpha_max}} [ Σ_k KL(P^{alpha_max}_k || P^0_k) ] over steered samples (nats, whole response).
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..constants import TEMPERATURE

FINE_GRID = tuple(round(0.05 * k, 2) for k in range(1, 41))          # 0.05 … 2.00
COARSE_GRID = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
KL_MAX, FLIP_MAX, X2_DROP, ACC_DROP = 0.10, 0.05, 0.03, 0.03


# ---------------------------------------------------------------- step 1
def fine_grid_stats(model, steer, items: Sequence[Tuple[Sequence[int], Sequence[int]]], alphas: Sequence[float] = FINE_GRID,
                    top_k: int = 8, scope: str = "S_gen", pos_masks: Optional[Sequence] = None,
                    temperature: float = TEMPERATURE) -> Dict[float, Dict[str, float]]:
    """items: (prompt_ids, response_ids).  Returns {|alpha|: {kl_pos, kl_neg, kl, flip_pos, flip_neg, flip}}; KL between the
    T-tempered next-token distributions (plan §4.7 step 1)."""
    import torch

    from .hf_engine import next_token_kl, router_topk_sets

    out: Dict[float, Dict[str, float]] = {}
    with torch.no_grad():
        base_sets = [router_topk_sets(model, list(p) + list(r), len(p), steer, 0.0, top_k=top_k) for p, r in items]
        for a in alphas:
            rec: Dict[str, float] = {}
            for sign, tag in ((1.0, "pos"), (-1.0, "neg")):
                kls, flips = [], []
                for i, (p, r) in enumerate(items):
                    pm = None if pos_masks is None else pos_masks[i]
                    kl = next_token_kl(model, list(p) + list(r), len(p), steer, sign * a, scope, pos_mask=pm, temperature=temperature)
                    kls.append(float(kl.mean()))
                    sets_a = router_topk_sets(model, list(p) + list(r), len(p), steer, sign * a, top_k=top_k, scope=scope, pos_mask=pm)
                    flips.append(_flip_from_sets(base_sets[i], sets_a, steer.layer, top_k))
                rec[f"kl_{tag}"] = float(np.mean(kls)); rec[f"flip_{tag}"] = float(np.mean(flips))
            rec["kl"] = max(rec["kl_pos"], rec["kl_neg"]); rec["flip"] = max(rec["flip_pos"], rec["flip_neg"])
            out[float(a)] = rec
    return out


def _flip_from_sets(sets0: Dict[int, np.ndarray], sets_a: Dict[int, np.ndarray], layer: int, top_k: int) -> float:
    """1 − |S0 ∩ Sα|/k averaged over (layer > L, response position)."""
    vals = []
    for ell in sorted(sets0):
        if ell <= layer:
            continue
        s0, sa = sets0[ell], sets_a[ell]                        # [n_pos, k] expert ids
        inter = np.array([len(set(x) & set(y)) for x, y in zip(s0, sa)], float)
        vals.append(1.0 - inter / top_k)
    return float(np.mean(np.concatenate(vals))) if vals else 0.0


# ---------------------------------------------------------------- step 2
def coarse_grid_rates(x2_obs: Dict[float, List[Tuple[str, float]]], acc_obs: Dict[float, List[Tuple[str, float]]],
                      n_boot: int = 1000, seed: int = 0) -> Dict[str, object]:
    """x2_obs/acc_obs: {alpha (incl. 0.0): [(problem_id, 0/1), ...]} pooled over both signs per |alpha| (the worse sign is
    taken per grid point).  Returns isotonic (non-increasing in |alpha|) fits and 95% lower bounds on the grid."""
    from ..analysis.isotonic import isotonic_lower_bound

    def table(obs):
        grid = sorted(obs)
        vals, cl, gi = [], [], []
        for g, a in enumerate(grid):
            for pid, v in obs[a]:
                vals.append(v); cl.append(pid); gi.append(g)
        r = isotonic_lower_bound(np.array(vals), np.array(cl), np.array(gi), len(grid), increasing=False, n_boot=n_boot, seed=seed)
        return dict(grid=grid, fit=r["fit"].tolist(), lower=r["lower"].tolist(), raw={a: float(np.mean([v for _, v in obs[a]])) for a in grid})
    return dict(x2=table(x2_obs), acc=table(acc_obs))


def worse_sign(obs_pos: Dict[float, List[Tuple[str, float]]], obs_neg: Dict[float, List[Tuple[str, float]]]) -> Dict[float, List[Tuple[str, float]]]:
    """Per |alpha| keep the sign with the lower mean rate (plan: 正负 α 取两者较差); alpha=0 is shared."""
    out = {}
    for a in sorted(set(obs_pos) | set(obs_neg)):
        if a == 0.0:
            out[0.0] = obs_pos.get(0.0, obs_neg.get(0.0))
            continue
        cands = [o[a] for o in (obs_pos, obs_neg) if a in o]
        out[a] = min(cands, key=lambda lst: np.mean([v for _, v in lst]))
    return out


# ---------------------------------------------------------------- step 3
def alpha_max_from_curves(fine: Dict[float, Dict[str, float]], coarse: Dict[str, object], *, kl_max: float = KL_MAX,
                          flip_max: float = FLIP_MAX, x2_drop: float = X2_DROP, acc_drop: float = ACC_DROP) -> Dict[str, object]:
    grid = sorted(fine)
    cx, ca = coarse["x2"], coarse["acc"]
    x2_0 = cx["fit"][cx["grid"].index(0.0)] if 0.0 in cx["grid"] else cx["raw"][0.0]
    acc_0 = ca["fit"][ca["grid"].index(0.0)] if 0.0 in ca["grid"] else ca["raw"][0.0]

    def interp(tbl, a):
        g, lo = np.array(tbl["grid"], float), np.array(tbl["lower"], float)
        ok = ~np.isnan(lo)
        return float(np.interp(a, g[ok], lo[ok]))

    reasons: Dict[float, List[str]] = {}
    alpha_max = 0.0
    for a in grid:
        fails = []
        if fine[a]["kl"] > kl_max:
            fails.append("kl")
        if fine[a]["flip"] > flip_max:
            fails.append("flip")
        if interp(cx, a) < x2_0 - x2_drop:
            fails.append("x2")
        if interp(ca, a) < acc_0 - acc_drop:
            fails.append("acc")
        reasons[a] = fails
        if fails:
            break
        alpha_max = a
    return dict(alpha_max=alpha_max, x2_0=x2_0, acc_0=acc_0, first_failure={a: f for a, f in reasons.items() if f},
                switch_layer=alpha_max < 0.2)


# ---------------------------------------------------------------- step 4
def kappa1(model, steer, items: Sequence[Tuple[Sequence[int], Sequence[int]]], alpha: float, scope: str = "S_gen",
           temperature: float = TEMPERATURE) -> Dict[str, float]:
    """items: (prompt_ids, steered_response_ids) sampled under alpha.  Σ_k KL(P^alpha_k || P^0_k) per response (T-tempered
    distributions), averaged."""
    import torch

    from .hf_engine import next_token_kl
    tot = []
    with torch.no_grad():
        for p, r in items:
            kl = next_token_kl(model, list(p) + list(r), len(p), steer, alpha, scope, direction="alpha_to_zero", temperature=temperature)
            tot.append(float(kl.sum()))
    return dict(kappa1=float(np.mean(tot)), se=float(np.std(tot, ddof=1) / np.sqrt(len(tot))) if len(tot) > 1 else float("nan"),
                n=len(tot), per_token=float(np.mean([t / max(1, len(r)) for t, (_, r) in zip(tot, items)])))


def write_alpha_max(path: str, entries: Dict[str, dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
