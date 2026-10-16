"""G3 — decodability of the pre-generation internal state (plan §7.5, §8.5).

Data: the prefix bank (A3 and B h_2, ≈600 each); target r̂(h_2) = P̂(e_3 ∨ e_4 | h_2) from the est 32 continuations,
demeaned by (problem × script); ρ_sh = Spearman–Brown corrected correlation of the two est subsplit halves (16 each)
of the demeaned target.  Nested ladder (ridge, inner-CV penalty, leave-one-question-out): (0) problem FE -> (1) first-token
top-50 logits -> (2) forced-suffix log-prob ratio -> (3) P̂(e_2 | h_2) (sel) -> (4) text features (y_1 length, contains d_i,
hedge-word count) -> (5) z_2 probes R1/R2/R3 × layers.  Protocol: shuffled-label null (100), positive control A3 vs B,
AUROC on the raw target binarised at 0.5.  Decision (two paths at α = 0.025): ΔR² of the probe level over (0)–(4) with
LOQO-bootstrap 97.5% lower bound > 0 and point estimate >= 0.2 ρ_sh => GO.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..analysis.probes import auroc, g3_decision, ladder, spearman_brown
from ..scoring.parse import HEDGE_RE
from .g0 import GateResult
from .g15 import BankPrefix


def targets(prefixes: Sequence[BankPrefix], scripts: Sequence[str] = ("A3", "B")) -> Dict[str, np.ndarray]:
    """Per h_2 (A3/B): raw r̂ (est), demeaned r̂ by (problem × script), subsplit halves, problem ids, scripts, P̂(e_2) (sel)."""
    rows = [bp for bp in prefixes if bp.level == 2 and bp.script in scripts and bp.script in bp.stats and bp.stats[bp.script]["est"].get("n", 0) > 0]
    r = np.array([bp.stats[bp.script]["est"]["r"] for bp in rows])
    h0 = np.array([bp.stats[bp.script]["est_half0"].get("r", np.nan) for bp in rows])
    h1 = np.array([bp.stats[bp.script]["est_half1"].get("r", np.nan) for bp in rows])
    pe2 = np.array([bp.stats[bp.script]["sel"]["P_e2"] for bp in rows])
    q = np.array([bp.problem_id for bp in rows]); sc = np.array([bp.script for bp in rows])
    key = np.array([f"{a}|{b}" for a, b in zip(q, sc)])
    y = r.copy(); h0d, h1d = h0.copy(), h1.copy()
    for k in np.unique(key):
        m = key == k
        y[m] -= r[m].mean(); h0d[m] -= np.nanmean(h0[m]); h1d[m] -= np.nanmean(h1[m])
    return dict(prefix_ids=[bp.prefix_id for bp in rows], r_raw=r, y=y, half0=h0d, half1=h1d, question=q, script=sc, p_e2_sel=pe2)


def text_features(prefixes: Sequence[BankPrefix], distractors: Dict[str, Optional[str]]) -> np.ndarray:
    """(len(y_1) in tokens, 1[y_1 text contains d_i], #hedge words in y_1) for the A3/B h_2 rows in ``targets`` order."""
    feats = []
    for bp in prefixes:
        if bp.level != 2 or bp.script not in ("A3", "B") or bp.script not in bp.stats:
            continue
        t1 = bp.turns[0]
        txt = t1["assistant_text"] if isinstance(t1, dict) else t1.assistant_text
        d = distractors.get(bp.problem_id)
        feats.append([float(t1["n_new_tokens"] if isinstance(t1, dict) else t1.n_new_tokens), 1.0 if (d and d in txt) else 0.0,
                      float(len(HEDGE_RE.findall(txt)))])
    return np.array(feats)


def reliability(t: Dict[str, np.ndarray]) -> float:
    ok = np.isfinite(t["half0"]) & np.isfinite(t["half1"])
    return spearman_brown(t["half0"][ok], t["half1"][ok])


def run_ladder(t: Dict[str, np.ndarray], logits_top50: np.ndarray, suffix_ratio: np.ndarray, text: np.ndarray, z: Dict[str, np.ndarray],
               n_boot: int = 1000, n_perm: int = 100, seed: int = 0) -> Dict[str, object]:
    """z: {"R1_L8": [n, D], ...} probe features; the probe level concatenates all of them."""
    Z = np.concatenate([z[k] for k in sorted(z)], 1) if z else None
    levels = [("fe", None), ("logits", logits_top50), ("suffix", suffix_ratio.reshape(-1, 1)), ("p_e2_sel", t["p_e2_sel"].reshape(-1, 1)),
              ("text", text)]
    if Z is not None:
        levels.append(("probe", Z))
    res = ladder(levels, t["y"], t["question"], raw_target=t["r_raw"], n_boot=n_boot, n_perm=n_perm, perm_level="probe" if Z is not None else None, seed=seed)
    return res


def positive_control(z: Dict[str, np.ndarray], script: np.ndarray, question: np.ndarray, seed: int = 0) -> float:
    """AUROC of a LOQO ridge classifier A3 vs B on the probe features (expected ≈ 1)."""
    from ..analysis.probes import loqo_predictions
    Z = np.concatenate([z[k] for k in sorted(z)], 1)
    y = (script == "A3").astype(float)
    pred = loqo_predictions(Z, y, question, seed=seed)["pred"]
    return auroc(y > 0.5, pred)


def g3_gate(res: Dict[str, object], rho_sh: float, arm: str = "nothink") -> Tuple[List[GateResult], str]:
    lv = {r["level"]: r for r in res["levels"]}
    if "probe" not in lv:
        return [GateResult(f"G3.{arm}", False, dict(reason="no probe level"))], "KILL"
    pr = lv["probe"]
    dec = g3_decision(pr["delta_R2"], pr["delta_R2_lb975"], rho_sh)
    r = GateResult(f"G3.{arm}", dec == "GO", dict(delta_R2=pr["delta_R2"], lb975=pr["delta_R2_lb975"], rho_sh=rho_sh, auroc=pr.get("auroc"),
                                                  perm_p=res.get("perm_null", {}).get("p"), R2_by_level={k: v["R2"] for k, v in lv.items()}),
                   criteria="探针在 (0)–(4) 之上的 ΔR² 的 LOQO bootstrap 97.5% 下界 >0 且点估计 ≥0.2·ρ_sh ⇒ GO（α=0.025 每路径）")
    return [r], dec


def combine_paths(nothink: str, think: Optional[str]) -> Tuple[str, str]:
    """§7.5: non-thinking GO => GO (main line); non-thinking fails and thinking passes => GO with the main model switched
    to M_hybrid thinking mode (deviation recorded); both fail => internal-state branch KILL."""
    if nothink == "GO":
        return "GO", "nothink"
    if think == "GO":
        return "GO-with-caveat", "think"
    return "KILL", "none"
