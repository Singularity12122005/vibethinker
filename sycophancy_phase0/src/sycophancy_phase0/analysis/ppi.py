"""Judge-error correction by prediction-powered difference estimation (plan §8.7).

For an outcome o (e.g. e_4 = 1[stance = USER]) measured by the judge on the full sample and by humans on a stratified
subset: per arm a and stratum s (judge label), bias_{a,s} = mean_{human subset ∩ a ∩ s}(o_judge − o_human); the
arm's judge mean is corrected by Σ_s π_{a,s} bias_{a,s} with π the stratum shares in the arm's full sample;
τ̂_PPI = τ̂_judge − (bias_arm1 − bias_arm0).  SE by a joint bootstrap over the full sample (clustered) and the human
subset.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np


def arm_bias(judge_o_full: np.ndarray, strata_full: np.ndarray, judge_o_h: np.ndarray, human_o_h: np.ndarray, strata_h: np.ndarray) -> float:
    strata_full, strata_h = np.asarray(strata_full), np.asarray(strata_h)
    total = 0.0
    for s in np.unique(strata_full):
        pi = float((strata_full == s).mean())
        m = strata_h == s
        if m.sum() == 0:
            continue
        total += pi * float((np.asarray(judge_o_h)[m] - np.asarray(human_o_h)[m]).mean())
    return total


def ppi_difference(full: Dict[str, dict], human: Dict[str, dict], n_boot: int = 2000, seed: int = 0) -> Dict[str, float]:
    """full[arm] = {o_judge, strata, cluster}; human[arm] = {o_judge, o_human, strata}.  Arms: 'arm1' (treated), 'arm0'."""
    rng = np.random.default_rng(seed)

    def est(fa, ha):
        tau_j = fa["arm1"]["o_judge"].mean() - fa["arm0"]["o_judge"].mean()
        b1 = arm_bias(fa["arm1"]["o_judge"], fa["arm1"]["strata"], ha["arm1"]["o_judge"], ha["arm1"]["o_human"], ha["arm1"]["strata"])
        b0 = arm_bias(fa["arm0"]["o_judge"], fa["arm0"]["strata"], ha["arm0"]["o_judge"], ha["arm0"]["o_human"], ha["arm0"]["strata"])
        return tau_j, tau_j - (b1 - b0), b1, b0
    F = {a: {k: np.asarray(v) for k, v in d.items()} for a, d in full.items()}
    H = {a: {k: np.asarray(v) for k, v in d.items()} for a, d in human.items()}
    tau_j, tau_ppi, b1, b0 = est(F, H)
    bs = np.empty(n_boot)
    for b in range(n_boot):
        Fb, Hb = {}, {}
        for a in ("arm1", "arm0"):
            cl = F[a]["cluster"]; ups = np.unique(cl)
            pick = ups[rng.integers(0, len(ups), len(ups))]
            ii = np.concatenate([np.where(cl == c)[0] for c in pick])
            Fb[a] = {k: v[ii] for k, v in F[a].items()}
            hb = rng.integers(0, len(H[a]["o_judge"]), len(H[a]["o_judge"]))
            Hb[a] = {k: v[hb] for k, v in H[a].items()}
        bs[b] = est(Fb, Hb)[1]
    return dict(tau_judge=float(tau_j), tau_ppi=float(tau_ppi), bias_arm1=float(b1), bias_arm0=float(b0),
                se_ppi=float(bs.std(ddof=1)), ci95_ppi=(float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))))


def specificity_sensitivity(human: Sequence[str], judge: Sequence[str], positive: str = "USER") -> Dict[str, object]:
    """Per-arm-type sensitivity/specificity with Wilson 95% CIs (plan §6.2 human validation)."""
    from scipy import stats
    h, j = np.asarray(human), np.asarray(judge)

    def wilson(k, n, z=1.959964):
        if n == 0:
            return (float("nan"), float("nan"), float("nan"))
        p = k / n
        den = 1 + z * z / n
        c = (p + z * z / (2 * n)) / den
        hw = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
        return (float(p), float(c - hw), float(c + hw))
    pos, neg = h == positive, h != positive
    return dict(sensitivity=wilson(int((j[pos] == positive).sum()), int(pos.sum())),
                specificity=wilson(int((j[neg] != positive).sum()), int(neg.sum())), n=int(len(h)))
