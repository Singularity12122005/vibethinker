"""Direction estimation (plan §4.8) under leave-one-fold-out rotation (§5.6).

Inputs are activation rows already extracted with clean forwards (hidden_states[L+1], plan §3 layer convention):
  * ``first_k_token_means``: mean over the first k = 16 generated tokens of a response (write-side directions);
  * h_2 ``user_span`` means and last-prompt-token rows come from ``hf_engine.extract_z`` (R2 / R1).
All directions are unit vectors; per-fold versions are estimated from the complement of the fold.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

FIRST_K = 16


def first_k_token_means(model, items: Sequence[Tuple[Sequence[int], Sequence[int]]], layers: Sequence[int], k: int = FIRST_K,
                        batch_size: int = 16) -> Dict[int, np.ndarray]:
    """Clean teacher-forced forward on prompt+response; mean of hidden_states[L+1] over the first k response
    content tokens (positions prompt_len .. prompt_len+k-1, excluding the closing <|im_end|>).  Returns {L: [n, D]}."""
    import torch

    from .hf_engine import clean_forward, layer_output
    out: Dict[int, List[np.ndarray]] = {L: [] for L in layers}
    with torch.no_grad():
        for s in range(0, len(items), batch_size):
            chunk = items[s:s + batch_size]
            seqs = [list(p) + list(r) for p, r in chunk]
            res, att = clean_forward(model, seqs, output_hidden_states=True)
            for L in layers:
                h = layer_output(res.hidden_states, L).float()
                for b, (p, r) in enumerate(chunk):
                    n_content = max(1, len(r) - 1)                 # drop the final <|im_end|>
                    a, e = len(p), len(p) + min(k, n_content)
                    out[L].append(h[b, a:e].mean(0).cpu().numpy())
    return {L: np.stack(v) for L, v in out.items()}


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if not np.isfinite(n) or n == 0:
        raise ValueError("zero/non-finite direction")
    return v / n


def v_cap(acts: np.ndarray, stances: Sequence[str], prefix: Sequence[str], min_per_class: int = 3) -> Dict[str, object]:
    """CAA-style write-side direction: per prefix mean(USER) − mean(ORIG) (both classes >= min_per_class), averaged
    over prefixes, unit-normalised.  +v = conceding direction; the controller uses negative alpha."""
    acts, st, pf = np.asarray(acts, float), np.asarray(stances), np.asarray(prefix)
    diffs, used = [], []
    for p in np.unique(pf):
        m = pf == p
        u, o = acts[m & (st == "USER")], acts[m & (st == "ORIG")]
        if len(u) >= min_per_class and len(o) >= min_per_class:
            diffs.append(u.mean(0) - o.mean(0)); used.append(str(p))
    if not diffs:
        raise ValueError("no prefix with both classes >= min_per_class")
    raw = np.mean(diffs, 0)
    return dict(v=_unit(raw), raw_norm=float(np.linalg.norm(raw)), n_prefix=len(used), prefixes=used)


def paired_problem_diff(acts_a: np.ndarray, acts_b: np.ndarray, problems_a: Sequence[str], problems_b: Sequence[str]) -> Dict[str, object]:
    """Read-side directions: per-problem mean(A) − mean(B), averaged over problems present in both, unit-normalised
    (v_press: A3 vs B user_span means of h_2; v_warrant: A3 vs D-prefill last-prompt-token rows of h_2)."""
    pa, pb = np.asarray(problems_a), np.asarray(problems_b)
    common = sorted(set(pa) & set(pb))
    if not common:
        raise ValueError("no common problems")
    diffs = [np.asarray(acts_a)[pa == p].mean(0) - np.asarray(acts_b)[pb == p].mean(0) for p in common]
    raw = np.mean(diffs, 0)
    return dict(v=_unit(raw), raw_norm=float(np.linalg.norm(raw)), n_problem=len(common))


def d_agree(acts_by_script: Dict[str, Tuple[np.ndarray, Sequence[str]]]) -> Dict[str, object]:
    """mean(stance=USER) − mean(stance≠USER) over first-16-token means of turn-3 responses, computed within A3 and
    within D-prefill and averaged over the two (plan §4.8)."""
    diffs = []
    for sc, (acts, st) in acts_by_script.items():
        acts, st = np.asarray(acts, float), np.asarray(st)
        u, o = acts[st == "USER"], acts[st != "USER"]
        if len(u) == 0 or len(o) == 0:
            continue
        diffs.append(u.mean(0) - o.mean(0))
    if not diffs:
        raise ValueError("no script with both classes")
    raw = np.mean(diffs, 0)
    return dict(v=_unit(raw), raw_norm=float(np.linalg.norm(raw)), n_scripts=len(diffs))


def orthogonalise(v: np.ndarray, d: np.ndarray) -> np.ndarray:
    """v_cap⊥ := v − (v·d̂) d̂, unit-normalised."""
    d = _unit(np.asarray(d, float))
    v = np.asarray(v, float)
    return _unit(v - (v @ d) * d)


def lofo(estimator: Callable[[np.ndarray], Dict[str, object]], item_folds: Sequence[int], n_folds: int = 5) -> Dict[int, Dict[str, object]]:
    """estimator(mask) -> result dict with "v"; computes one version per held-out fold (items not in the fold)."""
    f = np.asarray(item_folds)
    out = {}
    for k in range(n_folds):
        out[k] = estimator(f != k)
    return out


def cosine_matrix(vs: Sequence[np.ndarray]) -> np.ndarray:
    V = np.stack([_unit(np.asarray(v, float)) for v in vs])
    return V @ V.T


def save_direction(root: str, name: str, layer: int, fold: int, v: np.ndarray, meta: dict) -> str:
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, f"{name}_L{layer}_fold{fold}.npy")
    np.save(path, np.asarray(v, np.float32))
    with open(path.replace(".npy", ".json"), "w", encoding="utf-8") as f:
        json.dump(dict(name=name, layer=layer, fold=fold, **{k: (v_.tolist() if isinstance(v_, np.ndarray) else v_) for k, v_ in meta.items()}), f, ensure_ascii=False)
    return path


def load_direction(root: str, name: str, layer: int, fold: int) -> np.ndarray:
    return np.load(os.path.join(root, f"{name}_L{layer}_fold{fold}.npy"))
