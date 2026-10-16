"""GPU-side glue that the stage functions take as callables (plan §4.5–§4.8, §7.5–§7.7): activation extraction for
directions and probes, r_L calibration, the §4.7 fine/coarse grids and kappa_1, and alpha_max.json entries.

Everything here needs ``ctx.model`` (an HF model on GPU) and, for generation, ``ctx.extra["hf_engine"]``; the tiny-model
tests exercise the same code paths on CPU.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .constants import Z_LAYERS
from .inference.calibration import COARSE_GRID, FINE_GRID, alpha_max_from_curves, coarse_grid_rates, fine_grid_stats, kappa1, worse_sign
from .inference.directions import FIRST_K, first_k_token_means, load_direction
from .inference.engine import GenRequest
from .inference.hf_engine import confidence_features, extract_z, residual_norm_median
from .inference.sampling import derive_seed
from .inference.steering import Steer
from .inference.templates import TurnBuilder
from .scoring.parse import canonical, classify_final, is_hedged, parse_final_answer, values_equal
from .scripts.builders import user_turns
from .run import Context

DIRECTION_LAYERS = (12, 16, 20, 24, 28, 32, 36)


# ---------------------------------------------------------------- r_L (§4.6)
def calibrate_r_L(ctx: Context, prompts: Sequence[Sequence[int]], layers: Sequence[int] = tuple(range(0, 48, 4)), min_pos: int = 8) -> Dict[int, float]:
    """Median per-position residual norm of hidden_states[L+1] at positions >= 8 over 200 clean A3 turn-2 prompts."""
    out = {int(L): residual_norm_median(ctx.model, [list(p) for p in prompts], int(L), min_pos=min_pos) for L in layers}
    os.makedirs(os.path.join(ctx.run_path, "configs"), exist_ok=True)
    json.dump(out, open(os.path.join(ctx.run_path, "configs", "r_L.json"), "w"), indent=1)
    return out


def load_r_L(ctx: Context) -> Dict[int, float]:
    return {int(k): float(v) for k, v in json.load(open(os.path.join(ctx.run_path, "configs", "r_L.json"))).items()}


# ---------------------------------------------------------------- z_t extraction for the rollout loop (§4.5)
def z_fn_for(ctx: Context, layers: Sequence[int] = Z_LAYERS, batch_size: int = 8) -> Callable:
    """run_rollouts(z_fn=...): clean-forward R1/R2/R3 rows per (prompt ids, user_span, prev_assistant_span); the ZStore in
    ``ctx.extra["zstore"]`` persists them (fp16 unless overflow)."""
    def z_fn(ids_list, user_spans, prev_spans):
        rows = []
        for s in range(0, len(ids_list), batch_size):
            z = extract_z(ctx.model, [list(x) for x in ids_list[s:s + batch_size]], layers, [tuple(u) for u in user_spans[s:s + batch_size]],
                          [tuple(p) if p else None for p in prev_spans[s:s + batch_size]])
            n = len(ids_list[s:s + batch_size])
            for b in range(n):
                rows.append({pos: {int(L): z[pos][L][b].numpy() for L in layers if L in z[pos]} for pos in ("R1", "R2", "R3") if z[pos]})
        return rows
    return z_fn


# ---------------------------------------------------------------- activations
def acts_fn_for(ctx: Context, layers: Sequence[int] = DIRECTION_LAYERS, k: int = FIRST_K, batch_size: int = 16) -> Callable:
    """stage_g40(acts_fn=...): first-16-token means per layer for (h_3 ids, y_3 ids) items."""
    return lambda items: first_k_token_means(ctx.model, items, layers, k=k, batch_size=batch_size)


def g3_features_for(ctx: Context, prefixes, distractor_of: Dict[str, str], gold_of: Dict[str, str], layers: Sequence[int] = Z_LAYERS,
                    batch_size: int = 8) -> Dict[str, np.ndarray]:
    """stage_g3(features=...): for the A3/B h_2 rows (in gates.g3.targets order): top-50 logits of the last prompt token,
    forced-suffix log-prob ratio log P(d_i) − log P(g_i) (§4.5), and z_2 = R1/R2/R3 × layers from a clean forward."""
    rows = [bp for bp in prefixes if bp.level == 2 and bp.script in ("A3", "B") and bp.script in bp.stats and bp.stats[bp.script]["est"].get("n", 0) > 0]
    enc = ctx.builder.encode
    top, ratio, z_acc = [], [], defaultdict(list)
    for s in range(0, len(rows), batch_size):
        chunk = rows[s:s + batch_size]
        seqs = [list(bp.ids) for bp in chunk]
        suf = [[enc("最终答案：" + str(distractor_of[bp.problem_id])), enc("最终答案：" + str(gold_of[bp.problem_id]))] for bp in chunk]
        cf = confidence_features(ctx.model, seqs, suf)
        top.append(cf["top_logits"]); ratio.append(cf["suffix_logp"][:, 0] - cf["suffix_logp"][:, 1])
        z = extract_z(ctx.model, seqs, layers, [tuple(bp.user_span) for bp in chunk], [tuple(bp.prev_span) if bp.prev_span else None for bp in chunk])
        for pos in ("R1", "R2", "R3"):
            for L in layers:
                if L in z[pos]:
                    z_acc[f"{pos}_L{L}"].append(z[pos][L].numpy())
    return dict(logits_top50=np.concatenate(top), suffix_ratio=np.concatenate(ratio), z={k: np.concatenate(v) for k, v in z_acc.items()})


# ---------------------------------------------------------------- §4.7 fine grid for G4-1 step 1
def fine_grid_for(ctx: Context, items: Sequence[Tuple[Sequence[int], Sequence[int]]], direction: str, layers: Sequence[int], r_L: Dict[int, float],
                  fold: int = 0, alphas: Sequence[float] = FINE_GRID, top_k: int = 8) -> Dict[int, Dict[float, Dict[str, float]]]:
    """items: 200 out-of-fold script-B turn-2 (prompt, response) pairs; one Steer per layer (removed afterwards)."""
    out = {}
    for L in layers:
        v = load_direction(os.path.join(ctx.run_path, "configs", "directions"), direction, int(L), fold)
        import torch
        st = Steer(ctx.model, int(L), torch.as_tensor(v), r_L[int(L)])
        try:
            out[int(L)] = fine_grid_stats(ctx.model, st, items, alphas=alphas, top_k=top_k)
        finally:
            st.remove()
    return out


# ---------------------------------------------------------------- §4.7 coarse grid (generation on the calibration set)
def coarse_grid_for(ctx: Context, direction: str, layer: int, r_L: Dict[int, float], calib: Sequence, *, fold: int = 0,
                    alphas: Sequence[float] = COARSE_GRID, n_per: int = 2, scope: str = "S_gen", n_boot: int = 1000) -> Dict[str, object]:
    """calib: BankProblem-like records of the 400 external GSM8K problems (statement_zh, gold).  For each |alpha| and sign:
    x_2(alpha) = explicit-answer rate of script-B turn 2 (built on a correct single-turn y_1 sampled at alpha = 0), and
    acc(alpha) = single-turn accuracy; 2 samples each per problem.  The worse sign per |alpha| is kept (plan §4.7)."""
    import torch
    hf = ctx.extra["hf_engine"]
    v = load_direction(os.path.join(ctx.run_path, "configs", "directions"), direction, int(layer), fold)
    st = Steer(ctx.model, int(layer), torch.as_tensor(v), r_L[int(layer)])
    hf.steer = st
    try:
        obs_x2 = {+1: defaultdict(list), -1: defaultdict(list)}
        obs_acc = {+1: defaultdict(list), -1: defaultdict(list)}
        # alpha = 0 baseline y_1 (one per problem per sample) and turn-2 prompts
        base_reqs, meta = [], []
        for p in calib:
            xs = user_turns("B", S=p.statement_zh)
            ids_1 = ctx.first_turn_ids(xs[0])
            for j in range(n_per):
                base_reqs.append(GenRequest(ids_1, derive_seed(ctx.run_id, p.problem_id, "calib", "null", j, 1), 0.0))
                meta.append((p, j, ids_1, xs))
        base = hf.generate(base_reqs)
        prompts2 = []
        for (p, j, ids_1, xs), res in zip(meta, base):
            norm = ctx.builder.normalize(res.ids, res.finish_reason)
            txt = ctx.decode(norm.ids[:-1])
            ok = values_equal(canonical(parse_final_answer(txt), p.kind), p.gold, p.kind)
            if ok:
                ids_2, _ = ctx.builder.next_turn(ids_1, norm.ids, xs[1])
                prompts2.append((p, j, ids_2))
        for sign in (+1, -1):
            for a in alphas:
                alpha = sign * a
                reqs = [GenRequest(ids_2, derive_seed(ctx.run_id, p.problem_id, "calib", f"x2;a={alpha:g}", j, 2), alpha) for p, j, ids_2 in prompts2]
                for (p, j, _), res in zip(prompts2, hf.generate(reqs)):
                    norm = ctx.builder.normalize(res.ids, res.finish_reason)
                    txt = ctx.decode(norm.ids[:-1])
                    explicit = parse_final_answer(txt) is not None and canonical(parse_final_answer(txt), p.kind) is not None and not is_hedged(txt)
                    obs_x2[sign][float(a)].append((p.problem_id, float(explicit)))
                reqs = [GenRequest(ids_1, derive_seed(ctx.run_id, p.problem_id, "calib", f"acc;a={alpha:g}", j, 1), alpha) for p, j, ids_1, xs in meta]
                for (p, j, _, _), res in zip(meta, hf.generate(reqs)):
                    norm = ctx.builder.normalize(res.ids, res.finish_reason)
                    txt = ctx.decode(norm.ids[:-1])
                    obs_acc[sign][float(a)].append((p.problem_id, float(values_equal(canonical(parse_final_answer(txt), p.kind), p.gold, p.kind))))
        # alpha = 0 rows for both tables (shared by the two signs)
        for (p, j, _, _), res in zip(meta, base):
            norm = ctx.builder.normalize(res.ids, res.finish_reason); txt = ctx.decode(norm.ids[:-1])
            obs_acc[+1][0.0].append((p.problem_id, float(values_equal(canonical(parse_final_answer(txt), p.kind), p.gold, p.kind))))
        reqs0 = [GenRequest(ids_2, derive_seed(ctx.run_id, p.problem_id, "calib", "x2;a=0", j, 2), 0.0) for p, j, ids_2 in prompts2]
        for (p, j, _), res in zip(prompts2, hf.generate(reqs0)):
            norm = ctx.builder.normalize(res.ids, res.finish_reason); txt = ctx.decode(norm.ids[:-1])
            explicit = parse_final_answer(txt) is not None and canonical(parse_final_answer(txt), p.kind) is not None and not is_hedged(txt)
            obs_x2[+1][0.0].append((p.problem_id, float(explicit)))
        x2 = worse_sign(dict(obs_x2[+1]), dict(obs_x2[-1]))
        acc = worse_sign(dict(obs_acc[+1]), dict(obs_acc[-1]))
        return coarse_grid_rates(x2, acc, n_boot=n_boot)
    finally:
        hf.steer = None
        st.remove()


def finish_for(ctx: Context, fine_by_layer: Dict[int, Dict[float, Dict[str, float]]], r_L: Dict[int, float], calib: Sequence,
               kappa_items_fn: Callable[[str, int, float], Sequence[Tuple[Sequence[int], Sequence[int]]]], directions_at_lstar=("v_cap_perp", "v_warrant"),
               fold: int = 0) -> Callable[[int], Dict[str, dict]]:
    """stage_g41(finish=...): steps 2–5 for v_cap at L*, L*±4 and for the read-side/⊥ directions at L*; kappa_1 from
    ``kappa_items_fn(direction, layer, alpha_max)`` returning steered (prompt, response) samples at alpha_max."""
    from .gates.g41 import alpha_max_entry
    import torch

    def finish(L_star: int) -> Dict[str, dict]:
        entries = {}
        for direction, layer, scope in [("v_cap", L_star, "S_gen"), ("v_cap", L_star - 4, "S_gen"), ("v_cap", L_star + 4, "S_gen")] + \
                                       [(d, L_star, "S_read" if d == "v_warrant" else "S_gen") for d in directions_at_lstar]:
            if layer not in fine_by_layer and direction == "v_cap":
                continue
            fine = fine_by_layer.get(layer) if direction == "v_cap" else None
            if fine is None:
                v = load_direction(os.path.join(ctx.run_path, "configs", "directions"), direction, layer, fold)
                st = Steer(ctx.model, layer, torch.as_tensor(v), r_L[layer])
                try:
                    fine = fine_grid_stats(ctx.model, st, kappa_items_fn("__fine__", layer, 0.0), scope=scope)
                finally:
                    st.remove()
            coarse = coarse_grid_for(ctx, direction, layer, r_L, calib, fold=fold, scope=scope)
            sel = alpha_max_from_curves(fine, coarse)
            k1 = None
            if sel["alpha_max"] > 0:
                v = load_direction(os.path.join(ctx.run_path, "configs", "directions"), direction, layer, fold)
                st = Steer(ctx.model, layer, torch.as_tensor(v), r_L[layer])
                try:
                    k1 = kappa1(ctx.model, st, kappa_items_fn(direction, layer, sel["alpha_max"]), sel["alpha_max"], scope=scope)["kappa1"]
                finally:
                    st.remove()
            key = direction if layer == L_star else f"{direction}@L{layer}"
            entries[key] = alpha_max_entry(direction, layer, fold, sel["alpha_max"], k1, fine, coarse, dict(selection=sel, scope=scope))
        return entries
    return finish
