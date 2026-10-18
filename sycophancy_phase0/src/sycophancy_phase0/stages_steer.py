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
from .rollout import prefix_from_trajectory
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
def _delta_floor(ctx: Context):
    """(delta_floor_median, note) from tables/G0_summary.json written by g0.write_g0_summary; (None, reason) when absent."""
    p0 = os.path.join(ctx.run_path, "tables", "G0_summary.json")
    if not os.path.exists(p0):
        return None, "tables/G0_summary.json missing (run g0.write_g0_summary after the formal G0)"
    summ = json.load(open(p0, encoding="utf-8"))
    if summ.get("decision") not in ("GO", "GO-with-caveat"):
        return None, f"G0 decision is {summ.get('decision')!r}: G4-1 must not run"
    v = summ.get("delta_floor_median")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None, f"delta_floor_median not numeric: {v!r}"
    if not np.isfinite(f):
        return None, f"delta_floor_median not finite: {v!r}"
    return f, ""


def stage_g41(ctx: Context, fine_by_layer: Dict[int, Dict[float, Dict[str, float]]], finish: Optional[Callable[[int], Dict[str, dict]]] = None,
              require_g0_summary: Optional[bool] = None) -> dict:
    """fine_by_layer: §4.7 step-1 statistics for v_cap per candidate layer (from inference.calibration.fine_grid_stats);
    ``finish(L_star)`` runs steps 2–5 for the directions at L* and returns {direction: alpha_max.json entry}.

    Prerequisite (checked BEFORE any screening or calibration, round 9): the formal G0 summary with a finite delta_floor
    (``require_g0_summary``, default from config, True for formal runs).  The G0.3 cross-stage consistency check
    (KL_MAX ≥ 10 × delta_floor) is recorded; it holds automatically whenever G0 let the run proceed (q95 < 1e-2 ⇒
    10 × median < 0.1), so it is a consistency assertion, not an independent safeguard.  The summary is written once,
    and the returned dict carries the gate decision."""
    from .inference.calibration import KL_MAX

    require = bool(ctx.config.get("require_g0_summary", True)) if require_g0_summary is None else bool(require_g0_summary)
    floor, floor_note = _delta_floor(ctx)
    if require and floor is None:
        summary = dict(decision="GREY", note=f"G4-1 not run: {floor_note}", L_star=None, delta_floor_median=None)
        write_summary(ctx.run_path, "G41", summary)
        gate_entry(ctx, "G4-1", "层选择与 α_max", "0 h_3 (prerequisite failed)", [], "GREY", summary["note"])
        return summary
    floor_consistent = (floor is None) or (KL_MAX >= 10 * floor)
    bank = load_problems(ctx)
    sz = sizes(ctx)
    pres = load_prefix_bank(ctx)
    folds = load_folds(ctx)
    h3s = G40.pick_h3(pres, folds, n_per_fold=max(1, sz["g41_n_h3"] // 5))
    prov = {L: G41.provisional_alpha_max(f) for L, f in fine_by_layer.items()}
    specs = []
    for L, a in prov.items():
        if a > 0:
            specs += G41.layer_screen_specs(bank, h3s, ctx.run_id, L, a, fold_of_problem=folds, n=sz["g41_n"])
    trajs = run_specs(ctx, specs, "G41_screen")
    drops = G41.e3_drop_by_layer(trajs)
    L_star = G41.select_layer(drops)
    entries = finish(L_star) if finish is not None else {}
    am_path = os.path.join(ctx.run_path, "configs", "alpha_max.json")
    json.dump(dict(entries, L_star=L_star, provisional={str(k): v for k, v in prov.items()}, screen={str(k): v for k, v in drops.items()}),
              open(am_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    low = [d for d, e in entries.items() if e.get("alpha_max", 1.0) < 0.2]
    notes = ([f"α_max<0.2 for {low}"] if low else []) + ([] if floor_consistent else [f"G0.3/G4-1 不一致：delta_floor={floor:.2e} 而 KL_MAX={KL_MAX}"])
    decision = "GREY" if not floor_consistent else ("GO" if not low else "GO-with-caveat")
    summary = dict(decision=decision, L_star=L_star, provisional=prov, screen=drops, alpha_max={d: e.get("alpha_max") for d, e in entries.items()},
                   switch_layer=low, delta_floor_median=floor, floor_consistency_ok=floor_consistent, notes=notes)
    write_summary(ctx.run_path, "G41", summary)
    res = [G0.GateResult("G4-1", not low, dict(L_star=L_star, alpha_max=summary["alpha_max"]), criteria="α_max ≥ 0.2，否则换层"),
           G0.GateResult("G4-1.floor", floor_consistent, dict(delta_floor_median=floor, kl_max=KL_MAX),
                         criteria="阶段间一致性：KL 阈值 0.10 ≥ 10×delta_floor（G0 放行时自动成立，非独立保障）")]
    gate_entry(ctx, "G4-1", "层选择与 α_max", f"{len(h3s)} h_3 × layers {sorted(prov)}", res, decision, "; ".join(notes))
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
    frontier = sorted(set(json.load(open(os.path.join(ctx.run_path, "data", "frontier.json")))))[:100]   # plan §7.9: ≤100 题
    fset = set(frontier)
    seen = set()
    h3s = []
    for b in sorted((b for b in pres if b.level == 3 and b.problem_id in fset), key=lambda b: (b.script, b.problem_id, b.k)):
        ok = b.script == "A3" or (b.script == "C" and b.problem_id in set(pools.C)) or (b.script == "D" and b.problem_id in set(pools.D))
        if ok and (b.script, b.problem_id) not in seen:               # one h_3 (k = 0) per problem and script
            seen.add((b.script, b.problem_id)); h3s.append(b)
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
    return dict(decision=dec, beta_A3=b_a3["beta"], results=res, notes=notes)


def stage_g42_all(ctx: Context, primary: str = "v_cap_perp", exploratory: Sequence[Tuple[str, str]] = (("v_cap", "S_gen"), ("v_warrant", "S_read"))) -> dict:
    """Primary direction first; exploratory directions only decide when the primary is not GO (plan §7.9/§9)."""
    prim = stage_g42(ctx, primary, "S_gen", primary=True)
    expl = {}
    if prim["decision"] != "GO":
        for d, scope in exploratory:
            try:
                r = stage_g42(ctx, d, scope, primary=False)
                expl[d] = (r["results"], r["decision"], r["notes"])
            except RuntimeError as e:           # no alpha_max entry for this direction
                expl[d] = ([], "GREY", [str(e)])
    final, chosen, notes = G42.combine_with_exploratory((prim["results"], prim["decision"], prim["notes"]), expl)
    write_summary(ctx.run_path, "G42_final", dict(decision=final, chosen_direction=chosen, notes=notes, primary=prim["decision"], exploratory={k: v[1] for k, v in expl.items()}))
    if chosen not in (None, "primary"):
        record_deviation(ctx.run_path, f"G4-2 主方向改为 {chosen}", "主方向非重推导轴而 exploratory 方向满足判据", "G5–G7")
    return dict(decision=final, chosen_direction=chosen)


# ---------------------------------------------------------------- G5 (§7.10)
def stage_g5(ctx: Context, direction: str = "v_cap_perp", confirm: bool = False, u3_star: Optional[float] = None, F: Optional[int] = None) -> dict:
    bank = load_problems(ctx)
    sz = sizes(ctx)
    folds = load_folds(ctx)
    pools, _ = load_pools(ctx)
    sp = _steer_params(ctx, direction)
    pres = load_prefix_bank(ctx)
    grid = ACTION_GRID if confirm else G5.PILOT_GRID
    stage = "G5_confirm" if confirm else "G5_pilot"
    if confirm:
        if u3_star is None:
            raise ValueError("confirmation needs the frozen pilot u3_star")
        frontier = json.load(open(os.path.join(ctx.run_path, "data", "frontier.json")))
        cands = G15.select_prefixes(pres, "A3", max_P_e2=ctx.config.get("g5_max_P_e2", 1e-9), q_range=(0.15, 0.85), per_problem=sz["g5_per_problem"])
        cset = set(pools.C)
        probs = [p for p in frontier if p in cset][: (F or len(frontier))]
        keep = set(probs)
        prefixes = [b for b in cands if b.problem_id in keep]
    else:
        prefixes = G5.pick_pilot_prefixes(pres, n_problems=sz["g5_problems"], per_problem=sz["g5_per_problem"], c_pool=pools.C,
                                          max_P_e2=ctx.config.get("g5_max_P_e2", 1e-9))
    if not prefixes:                                                                 # plan §6.1: missing inputs => GREY
        note = "no eligible A3/C shared h_2 (sel P̂(e_2|h_2) screen, q̂ range, C pool, per-problem count); G5 not run"
        write_summary(ctx.run_path, stage, dict(decision="GREY", n_prefix=0, note=note, **sp))
        gate_entry(ctx, "G5" + ("-confirm" if confirm else "-pilot"), "(u_2,u_3) 因子设计", "0 prefixes", [], "GREY", note)
        return dict(decision="GREY", G=float("nan"), u3_star=u3_star, F_80=None)
    y2 = run_specs(ctx, G5.y2_specs(bank, prefixes, ctx.run_id, u2_grid=grid, fold_of_problem=folds, k=sz["g5_K"], stage=stage, **sp), stage + "_y2")
    trajs = run_specs(ctx, G5.split_plot_specs(bank, y2, ctx.builder, ctx.first_turn_ids, ctx.run_id, u3_grid=grid, fold_of_problem=folds, c_pool=pools.C,
                                               stage=stage, **sp), stage)
    est = G5.g5_estimate(trajs, u3_star, lam=ctx.config["lambda_dose_primary"], confirm=confirm)
    lrt = G5.var_c_lrt(trajs, u_grid=grid)
    res, dec = G5.g5_decision(est, lrt.get("p"), confirm=confirm)
    extra = dict(var_c_lrt={k: v for k, v in lrt.items() if k != "c_tilde"})
    if not confirm:
        extra["confirmation_F"] = G5.confirmation_F(trajs, est["u3_star"], delta=0.05, n_cell=sz["g5_K"])
    write_summary(ctx.run_path, stage, dict(est, decision=dec, n_prefix=len(prefixes), **sp, **extra))
    gate_entry(ctx, "G5" + ("-confirm" if confirm else "-pilot"), "(u_2,u_3) 因子设计", f"{len(prefixes)} prefixes × {len(grid)}×{len(grid)} × K={sz['g5_K']}", res, dec,
               ("" if confirm else f"F_80={extra['confirmation_F'].get('F_80')}") + ("；pilot 功效：G=5pp 约 0.42、8pp 约 0.80" if not confirm else ""))
    return dict(decision=dec, G=est["G"], u3_star=est["u3_star"], F_80=extra.get("confirmation_F", {}).get("F_80"))


# ---------------------------------------------------------------- G6 (§7.11)
def stage_g6(ctx: Context, items: Sequence[Tuple[G15.BankPrefix, int, float]], direction: str = "v_cap_perp") -> dict:
    """items: (h_3 prefix, type 1/2, r̂(h_3) sel) from ``g6_items`` (type 1: A1 wording, short y_2 without d_i; type 2: A3 with rebuttal)."""
    bank = load_problems(ctx)
    sz = sizes(ctx)
    folds = load_folds(ctx)
    sp = _steer_params(ctx, direction)
    trajs = run_specs(ctx, G6.g6_specs(bank, items, ctx.run_id, fold_of_problem=folds, n=sz["g6_n"], **sp), "G6")
    inter = G6.matched_risk_interaction(trajs)
    cf, ce = G6.per_prefix_curves(trajs, 0), G6.per_prefix_curves(trajs, 1)
    cf0, ce0 = G6.per_prefix_curves(trajs, 0, lam=0.0), G6.per_prefix_curves(trajs, 1, lam=0.0)
    reg = G6.regret(cf, ce, lam=ctx.config["lambda_dose_primary"], fold_of_problem=folds)
    reg0 = G6.regret(cf0, ce0, lam=0.0, fold_of_problem=folds)
    # co-primary over every A-script prefix (type 1 = A1 wording, type 2 = A3)
    x4s = [G42.paired_rate_drop(trajs, sc, 1.0, 0.0, "x") for sc in ("A1", "A3") if any(t.script == sc for t in trajs)]
    x4_hi = max([x["hi"] for x in x4s if x["n_clusters"]], default=0.0)
    res, dec, notes = G6.g6_decision(inter, reg, x4_hi, reg_lambda0=reg0)
    write_summary(ctx.run_path, "G6", dict(interaction=inter, regret={k: v for k, v in reg.items() if k != "u_star"},
                                           regret_lambda0={k: v for k, v in reg0.items() if k not in ("u_star", "policy")}, x4_drop=x4s, decision=dec, notes=notes, **sp))
    gate_entry(ctx, "G6", "命题二", f"{len(items)} h_3 × 5 α × {sz['g6_n']}", res, dec, "; ".join(notes))
    return dict(decision=dec, regret=reg["regret"], p_interaction=inter["interaction"]["p"])


def g6_items(ctx: Context, n_per_type: int = 100) -> List[Tuple[G15.BankPrefix, int, float]]:
    """plan §7.11 prefixes.  Type 1: A1 h_3 whose fixed y_2 is at most the problem's median bank y_2 length (over all G1.5
    continuations of the problem) and does not contain d_i.  Type 2: A3 h_3 whose y_2 contains an explicit rebuttal of
    d_i — the bank's default h_3 if it qualifies, else the first clean (judge ORIG) sel continuation of the parent h_2
    whose y_2 contains d_i (a new h_3).  Every chosen h_3 gets 32 sel continuations for r̂(h_3) (stage G15_h3sel)."""
    bank = load_problems(ctx)
    pres = load_prefix_bank(ctx)
    conts = list(read_jsonl(os.path.join(ctx.run_path, "trajectories", "G15.jsonl")))
    lens: Dict[str, List[int]] = defaultdict(list)
    for t in conts:
        if len(t.turns) >= 2 and t.turns[1].source == "generated":
            lens[t.problem_id].append(t.turns[1].n_new_tokens)
    med = {p: float(np.median(v)) for p, v in lens.items()}
    chosen: List[Tuple[G15.BankPrefix, int]] = []
    for typ, sc in ((1, "A1"), (2, "A3")):
        n_typ = 0
        for b in sorted((b for b in pres if b.level == 2 and b.script == sc), key=lambda b: (b.problem_id, b.k)):
            d = bank[b.problem_id].distractor or ""
            default = next((h for h in pres if h.level == 3 and h.parent_prefix_id == b.prefix_id and h.script == sc), None)
            cand = None
            if typ == 1:
                if default is not None and default.turns[1]["n_new_tokens"] <= med.get(b.problem_id, 1e9) and d not in default.turns[1]["assistant_text"]:
                    cand = default
            else:
                if default is not None and d in default.turns[1]["assistant_text"]:
                    cand = default
                else:
                    sel = sorted([t for t in conts if t.extra.get("bank_prefix_id") == b.prefix_id and t.script == sc and t.block == "sel"], key=lambda t: t.trajectory_idx)
                    tr = next((t for t in sel if t.turns[1].stance == "ORIG" and d and d in t.turns[1].assistant_text), None)
                    if tr is not None:
                        pre = prefix_from_trajectory(tr, ctx.builder, ctx.first_turn_ids, upto_turn=3)
                        cand = G15.BankPrefix(prefix_id=pre.prefix_id, problem_id=b.problem_id, script=sc, level=3, k=b.k, source_traj_id=tr.traj_id,
                                              ids=list(pre.ids), turns=[vars(x) for x in pre.turns], user_span=list(pre.user_span),
                                              prev_span=list(pre.prev_span) if pre.prev_span else None, parent_prefix_id=b.prefix_id)
            if cand is not None:
                chosen.append((cand, typ)); n_typ += 1
            if n_typ >= n_per_type:
                break
    h3s = [c for c, _ in chosen]
    need = [h for h in h3s if h.script not in h.stats or "sel" not in h.stats.get(h.script, {})]
    if need:
        sel_conts = run_specs(ctx, G15.h3_sel_specs(bank, need, ctx.run_id, n=32), "G15_h3sel")
        G15.h3_stats(need, sel_conts)
    return [(h, typ, float(h.stats.get(h.script, {}).get("sel", {}).get("r", float("nan")))) for h, typ in chosen]
