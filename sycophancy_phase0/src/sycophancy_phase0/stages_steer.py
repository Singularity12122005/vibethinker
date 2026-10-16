"""Stage glue for the HF-dependent gates: G0, G3, G4-0, G4-1, G2′-b, G4-2, G5, G6 (plan §7.1, §7.5–§7.11).

These stages need a GPU context (``Context.from_config``) for activations, steering and gradients; with the fake
context only the rollout/estimator plumbing runs (activations are supplied by the caller or skipped).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .constants import ACTION_GRID
from .gates import g0 as G0
from .gates import g2b as G2B
from .gates import g3 as G3
from .gates import g40 as G40
from .gates import g41 as G41
from .gates import g42 as G42
from .gates import g5 as G5
from .gates import g6 as G6
from .gates import g15 as G15
from .run import Context, record_deviation, write_summary
from .stages import gate_entry, load_folds, load_pools, load_prefix_bank, load_problems, run_specs, sizes
from .trajectory import read_jsonl

DIRECTION_LAYERS = (12, 16, 20, 24, 28, 32, 36)


def _steer_params(ctx: Context, direction: str) -> dict:
    """Frozen (direction, layer, alpha_max) from configs/alpha_max.json written by G4-1."""
    p = os.path.join(ctx.run_path, "configs", "alpha_max.json")
    if not os.path.exists(p):
        raise RuntimeError("G4-1 has not written configs/alpha_max.json")
    am = json.load(open(p, encoding="utf-8"))
    e = am[direction]
    return dict(direction=direction, layer=int(e["layer"]), alpha_max=float(e["alpha_max"]))


# ---------------------------------------------------------------- G3 (§7.5)
def stage_g3(ctx: Context, features: Optional[Dict[str, np.ndarray]] = None, think_result: Optional[str] = None) -> dict:
    """features (aligned with G3.targets rows): logits_top50 [n,50], suffix_ratio [n], z {"R1_L8": [n,D], ...}; in a GPU
    run they come from hf_engine.confidence_features / extract_z on the bank's h_2 ids."""
    bank = load_problems(ctx)
    pres = load_prefix_bank(ctx)
    t = G3.targets(pres)
    rho_sh = G3.reliability(t)
    text = G3.text_features(pres, {pid: p.distractor for pid, p in bank.items()})
    if features is None:
        n = len(t["y"])
        features = dict(logits_top50=np.zeros((n, 1)), suffix_ratio=np.zeros(n), z={})
    res = G3.run_ladder(t, features["logits_top50"], features["suffix_ratio"], text, features.get("z", {}), n_boot=ctx.config.get("n_boot", 1000),
                        n_perm=ctx.config.get("n_perm", 100))
    results, dec = G3.g3_gate(res, rho_sh, "nothink")
    final, path = G3.combine_paths(dec, think_result)
    pc = G3.positive_control(features["z"], t["script"], t["question"]) if features.get("z") else float("nan")
    summary = dict(levels=res["levels"], rho_sh=rho_sh, positive_control_auroc=pc, perm_null=res.get("perm_null"), decision=final, path=path, n=len(t["y"]))
    write_summary(ctx.run_path, "G3", summary)
    gate_entry(ctx, "G3", "可解码性", f"{len(t['y'])} h_2 (A3/B); ρ_sh={rho_sh:.3f}", results, final, f"path={path}")
    if path == "think":
        record_deviation(ctx.run_path, "主模型改为 M_hybrid 思考模式", "非思考探针未过 G3 判据而思考臂通过", "G4–G7")
    return dict(decision=final, rho_sh=rho_sh)


# ---------------------------------------------------------------- G4-0 (§7.6)
def stage_g40(ctx: Context, acts_fn: Optional[Callable[[List[Tuple[List[int], List[int]]]], Dict[int, np.ndarray]]] = None) -> dict:
    bank = load_problems(ctx)
    sz = sizes(ctx)
    folds = load_folds(ctx)
    pres = load_prefix_bank(ctx)
    h3_a3 = G40.pick_h3(pres, folds, n_per_fold=sz["g40_n_per_fold"])
    by_problem_d = {bp.problem_id: bp for bp in pres if bp.script == "D" and bp.level == 3}
    h3_d = [by_problem_d[b.problem_id] for b in h3_a3 if b.problem_id in by_problem_d]
    trajs = run_specs(ctx, G40.turn3_specs(bank, h3_a3 + h3_d, ctx.run_id, n=sz["g40_n"]), "G40")
    prefix_ids = {bp.prefix_id: bp.ids for bp in h3_a3 + h3_d}
    summary = dict(n_h3_A3=len(h3_a3), n_h3_D=len(h3_d), n_trajs=len(trajs))
    if acts_fn is not None:
        items = G40.activation_items(trajs, prefix_ids)
        acts = acts_fn(items)
        dirs = G40.estimate_directions(acts, trajs, folds, min_per_class=int(ctx.config.get("g40_min_per_class", 3)))
        meta = G40.persist(os.path.join(ctx.run_path, "configs", "directions"), dirs)
        summary["directions"] = meta
    write_summary(ctx.run_path, "G40", summary)
    gate_entry(ctx, "G4-0", "方向数据", f"{len(h3_a3)} A3 h_3 + {len(h3_d)} D h_3 × {sz['g40_n']}", [G0.GateResult("G4-0", True, summary, criteria="方向估计（无判据）")], "GO")
    return summary


# ---------------------------------------------------------------- G4-1 (§7.7)
def stage_g41(ctx: Context, fine_by_layer: Dict[int, Dict[float, Dict[str, float]]], finish: Optional[Callable[[int], Dict[str, dict]]] = None) -> dict:
    """fine_by_layer: §4.7 step-1 statistics for v_cap per candidate layer (from inference.calibration.fine_grid_stats);
    ``finish(L_star)`` runs steps 2–5 for the directions at L* and returns {direction: alpha_max.json entry}."""
    bank = load_problems(ctx)
    sz = sizes(ctx)
    pres = load_prefix_bank(ctx)
    folds = load_folds(ctx)
    h3s = G40.pick_h3(pres, folds, n_per_fold=max(1, sz["g41_n_h3"] // 5))
    prov = {L: G41.provisional_alpha_max(f) for L, f in fine_by_layer.items()}
    specs = []
    for L, a in prov.items():
        if a > 0:
            specs += G41.layer_screen_specs(bank, h3s, ctx.run_id, L, a, n=sz["g41_n"])
    trajs = run_specs(ctx, specs, "G41_screen")
    drops = G41.e3_drop_by_layer(trajs)
    L_star = G41.select_layer(drops)
    entries = finish(L_star) if finish is not None else {}
    am_path = os.path.join(ctx.run_path, "configs", "alpha_max.json")
    json.dump(dict(entries, L_star=L_star, provisional={str(k): v for k, v in prov.items()}, screen={str(k): v for k, v in drops.items()}),
              open(am_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    low = [d for d, e in entries.items() if e.get("alpha_max", 1.0) < 0.2]
    summary = dict(L_star=L_star, provisional=prov, screen=drops, alpha_max={d: e.get("alpha_max") for d, e in entries.items()}, switch_layer=low)
    write_summary(ctx.run_path, "G41", summary)
    res = [G0.GateResult("G4-1", not low, dict(L_star=L_star, alpha_max=summary["alpha_max"]), criteria="α_max ≥ 0.2，否则换层")]
    gate_entry(ctx, "G4-1", "层选择与 α_max", f"{len(h3s)} h_3 × layers {sorted(prov)}", res, "GO" if not low else "GO-with-caveat",
               f"α_max<0.2 for {low}" if low else "")
    return summary


# ---------------------------------------------------------------- G2′-b (§7.8)
def stage_g2b(ctx: Context, direction: str = "v_cap_perp") -> dict:
    bank = load_problems(ctx)
    sz = sizes(ctx)
    folds = load_folds(ctx)
    sp = _steer_params(ctx, direction)
    y2 = list(read_jsonl(os.path.join(ctx.run_path, "trajectories", "G2a_y2.jsonl")))
    specs = G2B.g2b_specs(bank, y2, ctx.builder, ctx.first_turn_ids, ctx.run_id, fold_of_problem=folds, n_y2=sz["g2b_n_y2"], n_per_arm=sz["g2b_n"], **sp)
    trajs = run_specs(ctx, specs, "G2b")
    est = G2B.g2b_estimate(trajs, lam=ctx.config["lambda_dose_primary"])
    res, dec = G2B.g2b_gate(est)
    write_summary(ctx.run_path, "G2b", dict(est, decision=dec, **sp))
    gate_entry(ctx, "G2′-b", "steering 类 Var(V_3)", f"{est['n_prefix']} prefixes × {est['n_y2'] // max(1, est['n_prefix'])} y_2 × 5 arms × {sz['g2b_n']}", res, dec)
    return dict(decision=dec, cov=est["est"])


# ---------------------------------------------------------------- G4-2 (§7.9)
def stage_g42(ctx: Context, direction: str = "v_cap_perp", scope: str = "S_gen", primary: bool = True) -> dict:
    bank = load_problems(ctx)
    sz = sizes(ctx)
    folds = load_folds(ctx)
    pools, _ = load_pools(ctx)
    sp = _steer_params(ctx, direction)
    pres = load_prefix_bank(ctx)
    frontier = set(json.load(open(os.path.join(ctx.run_path, "data", "frontier.json"))))
    h3s = [b for b in pres if b.level == 3 and b.problem_id in frontier and
           (b.script == "A3" or (b.script == "C" and b.problem_id in set(pools.C)) or (b.script == "D" and b.problem_id in set(pools.D)))]
    specs = G42.dose_specs(bank, h3s, ctx.run_id, scope=scope, fold_of_problem=folds, n=sz["g42_n"], **sp)
    trajs = run_specs(ctx, specs, f"G42_{direction}")
    b_a3 = G42.beta_endpoints(trajs, "A3")
    b_d = G42.beta_endpoints(trajs, "D") if any(t.script == "D" for t in trajs) else None
    c_drop = G42.paired_rate_drop(trajs, "C", 1.0, 0.0, "c") if any(t.script == "C" for t in trajs) else None
    x4 = G42.paired_rate_drop(trajs, "A3", 1.0, 0.0, "x")
    res, dec, notes = G42.g42_decision(b_a3, b_d, c_drop, x4, primary=primary)
    summary = dict(beta_A3=b_a3, beta_D=b_d, c_drop=c_drop, x4_drop=x4, tables={s: G42.dose_response_table(trajs, s) for s in ("A3", "C", "D") if any(t.script == s for t in trajs)},
                   decision=dec, notes=notes, **sp)
    write_summary(ctx.run_path, f"G42_{direction}", summary)
    gate_entry(ctx, "G4-2", f"剂量-响应（{direction}）", f"{len(h3s)} h_3 × 5 α × {sz['g42_n']}", res, dec, "; ".join(notes))
    return dict(decision=dec, beta_A3=b_a3["beta"])


# ---------------------------------------------------------------- G5 (§7.10)
def stage_g5(ctx: Context, direction: str = "v_cap_perp", confirm: bool = False, u3_star: Optional[float] = None, F: Optional[int] = None) -> dict:
    bank = load_problems(ctx)
    sz = sizes(ctx)
    folds = load_folds(ctx)
    pools, _ = load_pools(ctx)
    sp = _steer_params(ctx, direction)
    pres = load_prefix_bank(ctx)
    grid = ACTION_GRID if confirm else G5.PILOT_GRID
    if confirm:
        frontier = json.load(open(os.path.join(ctx.run_path, "data", "frontier.json")))
        cands = G15.select_prefixes(pres, "A3", max_P_e2=1e-9, q_range=(0.15, 0.85), per_problem=sz["g5_per_problem"])
        keep = set(frontier[: (F or len(frontier))])
        prefixes = [b for b in cands if b.problem_id in keep]
    else:
        prefixes = G5.pick_pilot_prefixes(pres, n_problems=sz["g5_problems"], per_problem=sz["g5_per_problem"])
    y2 = run_specs(ctx, G5.y2_specs(bank, prefixes, ctx.run_id, u2_grid=grid, fold_of_problem=folds, k=sz["g5_K"], **sp), f"G5_{'confirm' if confirm else 'pilot'}_y2")
    trajs = run_specs(ctx, G5.split_plot_specs(bank, y2, ctx.builder, ctx.first_turn_ids, ctx.run_id, u3_grid=grid, fold_of_problem=folds, c_pool=pools.C, **sp),
                      f"G5_{'confirm' if confirm else 'pilot'}")
    est = G5.g5_estimate(trajs, u3_star, lam=ctx.config["lambda_dose_primary"], confirm=confirm)
    lrt_p = None
    res, dec = G5.g5_decision(est, lrt_p, confirm=confirm)
    write_summary(ctx.run_path, "G5_confirm" if confirm else "G5_pilot", dict(est, decision=dec, n_prefix=len(prefixes), **sp))
    gate_entry(ctx, "G5" + ("-confirm" if confirm else "-pilot"), "(u_2,u_3) 因子设计", f"{len(prefixes)} prefixes × {len(grid)}×{len(grid)} × K={sz['g5_K']}", res, dec)
    return dict(decision=dec, G=est["G"], u3_star=est["u3_star"])


# ---------------------------------------------------------------- G6 (§7.11)
def stage_g6(ctx: Context, items: Sequence[Tuple[G15.BankPrefix, int, float]], direction: str = "v_cap_perp") -> dict:
    """items: (h_3 prefix, type 1/2, r̂^sel) chosen per §7.11 (type 1: A1 wording, short y_2 without d_i; type 2: A3 with rebuttal)."""
    bank = load_problems(ctx)
    sz = sizes(ctx)
    folds = load_folds(ctx)
    sp = _steer_params(ctx, direction)
    trajs = run_specs(ctx, G6.g6_specs(bank, items, ctx.run_id, fold_of_problem=folds, n=sz["g6_n"], **sp), "G6")
    inter = G6.matched_risk_interaction(trajs)
    cf, ce = G6.per_prefix_curves(trajs, 0), G6.per_prefix_curves(trajs, 1)
    reg = G6.regret(cf, ce, lam=ctx.config["lambda_dose_primary"])
    x4 = G42.paired_rate_drop([t for t in trajs], "A3", 1.0, 0.0, "x") if any(t.script == "A3" for t in trajs) else dict(hi=0.0)
    res, dec = G6.g6_decision(inter, reg, x4.get("hi", 0.0))
    write_summary(ctx.run_path, "G6", dict(interaction=inter, regret={k: v for k, v in reg.items() if k != "u_star"}, x4_drop=x4, decision=dec, **sp))
    gate_entry(ctx, "G6", "命题二", f"{len(items)} h_3 × 5 α × {sz['g6_n']}", res, dec)
    return dict(decision=dec, regret=reg["regret"], p_interaction=inter["interaction"]["p"])


def g6_items(ctx: Context, n_per_type: int = 100) -> List[Tuple[G15.BankPrefix, int, float]]:
    """Type 1: A1 h_3 whose fixed y_2 is at most the problem's median y_2 length and does not contain d_i; type 2: A3 h_3
    whose y_2 contains d_i.  r̂^sel from the bank (sel continuations of the parent h_2 as a proxy when h_3 has none)."""
    bank = load_problems(ctx)
    pres = load_prefix_bank(ctx)
    by_id = {b.prefix_id: b for b in pres}
    med: Dict[str, float] = {}
    lens: Dict[str, List[int]] = defaultdict(list)
    for b in pres:
        if b.level == 3:
            lens[b.problem_id].append(b.turns[1]["n_new_tokens"])
    med = {p: float(np.median(v)) for p, v in lens.items()}
    out = []
    for typ, sc in ((1, "A1"), (2, "A3")):
        for b in pres:
            if b.level != 3 or b.script != sc:
                continue
            d = bank[b.problem_id].distractor or ""
            y2 = b.turns[1]["assistant_text"]
            ok = (b.turns[1]["n_new_tokens"] <= med.get(b.problem_id, 1e9) and d not in y2) if typ == 1 else (d in y2)
            if not ok:
                continue
            parent = by_id.get(b.parent_prefix_id)
            r_sel = (parent.stats.get(parent.script, {}).get("sel", {}).get("r", 0.5) if parent else 0.5)
            out.append((b, typ, float(r_sel)))
            if sum(1 for _, t, _ in out if t == typ) >= n_per_type:
                break
    return out
