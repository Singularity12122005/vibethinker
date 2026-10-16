"""Stage glue: one function per pipeline stage, reading/writing only under runs/<run_id>/ (plan §2.4, §10).

Artifacts (relative to the run directory):
  data/F1.jsonl F2.jsonl F3.jsonl               bank records (data stage)
  data/mining.json  data/pools.json  data/folds.json   §5.2–§5.6 (mine stage)
  trajectories/<stage>.jsonl                     one JSONL per stage; resumable by traj_id
  data/prefixes/prefix_bank.jsonl                §7.2b
  tables/<gate>_summary.json, GATES.md           per gate
Sizes come from ``ctx.config["sizes"]`` (defaults = plan values; tests shrink them).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Dict, List, Optional, Sequence

import numpy as np

from .data.common import read_bank
from .data.pools import SingleTurnSample, assign_pools, d_prefill_y1, exclusion_rate, make_folds, mine, needs_batch2
from .gates import g0 as G0
from .gates import g1 as G1
from .gates import g15 as G15
from .gates import g2 as G2
from .gates import g2a as G2A
from .rollout import BankProblem, RolloutSpec, run_rollouts
from .run import Context, record_deviation, write_summary
from .scripts.builders import user_turns
from .trajectory import Arm, JsonlWriter, Trajectory, existing_traj_ids, read_jsonl

DEFAULT_SIZES = dict(mining_n=64, g1_n=64, g1_subset_n=32, g15_n=64, g15_k_pref=4, g2_n_h2=50, g2_n_cont=50, g2a_n_prefix=40, g2a_N=128,
                     g2a_M=16, g2a_n_h3=50, g2a_Ms=128, g2a_m=8, g40_n_per_fold=12, g40_n=32, g41_n_h3=40, g41_n=16, g2b_n_y2=32,
                     g2b_n=16, g42_n=32, g5_problems=15, g5_per_problem=3, g5_K=16, g6_n_h3=200, g6_n=32)


def sizes(ctx: Context) -> dict:
    return {**DEFAULT_SIZES, **ctx.config.get("sizes", {})}


# ---------------------------------------------------------------- helpers
def load_bank(ctx: Context) -> Dict[str, BankProblem]:
    bank: Dict[str, BankProblem] = {}
    for fam in ("F1", "F2", "F3"):
        p = os.path.join(ctx.run_path, "data", f"{fam}.jsonl")
        if not os.path.exists(p):
            continue
        for r in read_bank(p):
            if not r.statement_zh:
                continue
            bank[r.problem_id] = BankProblem(problem_id=r.problem_id, family=r.family, statement_zh=r.statement_zh, gold=r.gold, gold_type=r.gold_type,
                                             modified_statement_zh=r.modified_statement_zh, modified_gold=r.modified_gold,
                                             modification_note=r.modification_note)
    return bank


def _attach_distractors(bank: Dict[str, BankProblem], mining: dict) -> None:
    for pid, m in mining.items():
        if pid in bank:
            bank[pid].distractor = m["distractor"]
            bank[pid].distractor2 = m["distractor2"]


def run_specs(ctx: Context, specs: Sequence[RolloutSpec], stage: str, *, z_fn=None, z_turns=(2, 3), judge=True, batch: int = 4096) -> List[Trajectory]:
    """Resumable: skips specs whose traj_id already exists in trajectories/<stage>.jsonl; returns all trajectories."""
    path = os.path.join(ctx.run_path, "trajectories", f"{stage}.jsonl")
    done = existing_traj_ids([path])
    from .rollout import spec_traj_id
    todo = [sp for sp in specs if not done or spec_traj_id(sp, ctx.builder, ctx.first_turn_ids, ctx.decode) not in done]
    if todo:
        with JsonlWriter(path) as w:
            for s in range(0, len(todo), batch):
                run_rollouts(todo[s:s + batch], builder=ctx.builder, router=ctx.router, first_turn_ids=ctx.first_turn_ids, decode=ctx.decode,
                             judge=ctx.judge if judge else None, judge2=ctx.judge2 if judge else None, z_fn=z_fn, z_turns=z_turns, writer=w,
                             zstore=ctx.extra.get("zstore"))
    return list(read_jsonl(path))


def budget_snapshot(ctx: Context, stage: str) -> dict:
    """Append the engines' token counters to tables/budget.json (plan §7.13 budget tracking)."""
    engines = {"steered": getattr(ctx.router, "steered", None), "null": getattr(ctx.router, "null", None)}
    snap = {k: dict(generated=getattr(e, "n_generated_tokens", 0), prompt=getattr(e, "n_prompt_tokens", 0), name=getattr(e, "name", None))
            for k, e in engines.items() if e is not None}
    path = os.path.join(ctx.run_path, "tables", "budget.json")
    cur = _json(path) if os.path.exists(path) else {}
    cur[stage] = snap
    _json(path, cur)
    return snap


def gate_entry(ctx: Context, gate: str, title: str, inputs: str, results, decision: str, notes: str = "") -> None:
    budget_snapshot(ctx, gate)
    G0.write_gates_md(results, os.path.join(ctx.run_path, "GATES.md"), ctx.run_id, inputs=inputs, notes=notes, gate=gate, title=title, decision=decision)


def _json(path: str, obj=None):
    if obj is None:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else (vars(o) if hasattr(o, "__dict__") else str(o)))


# ---------------------------------------------------------------- mine (§5.2–§5.6)
def stage_mine(ctx: Context) -> dict:
    bank = load_bank(ctx)
    sz = sizes(ctx)
    specs = [RolloutSpec(run_id=ctx.run_id, problem=p, script="A3", arm=Arm.null(), trajectory_idx=j, stop_after=1, extra=dict(batch=1))
             for p in bank.values() for j in range(sz["mining_n"])]
    # script A3 is only used for its x_1 (identical for every script); the distractor placeholder is not needed at turn 1
    for sp in specs:
        sp.problem.distractor = sp.problem.distractor or "?"
    t1 = run_specs(ctx, specs, "mine_batch1", judge=False)
    samples: Dict[str, List[SingleTurnSample]] = defaultdict(list)
    for tr in t1:
        samples[tr.problem_id].append(SingleTurnSample(tr.trajectory_idx, 1, tr.turns[0].parsed, tr.turns[0].assistant_text, tr.turns[0].assistant_ids))
    need2 = [pid for pid in bank if needs_batch2(samples[pid], bank[pid].gold, bank[pid].kind)]
    if need2:
        specs2 = [RolloutSpec(run_id=ctx.run_id, problem=bank[pid], script="A3", arm=Arm.null(), trajectory_idx=j, stop_after=1, temperature=1.0,
                              extra=dict(batch=2)) for pid in need2 for j in range(sz["mining_n"])]
        for tr in run_specs(ctx, specs2, "mine_batch2", judge=False):
            samples[tr.problem_id].append(SingleTurnSample(tr.trajectory_idx, 2, tr.turns[0].parsed, tr.turns[0].assistant_text, tr.turns[0].assistant_ids))
    mining = {pid: mine(pid, bank[pid].gold, bank[pid].kind, samples[pid], ctx.config["pools"]["distractor_min_freq"]) for pid in bank}
    bank_dicts = {pid: dict(family=p.family, gold=p.gold, gold_type=p.gold_type, modified_gold=p.modified_gold) for pid, p in bank.items()}
    pools = assign_pools(bank_dicts, mining, samples, ctx.config["pools"]["p0_main"], ctx.config["pools"]["p0_dnat"])
    folds = make_folds(list(bank), seed=ctx.config["seeds"]["folds"])
    dpre = {}
    for pid in pools.D:
        s = d_prefill_y1(samples[pid], mining[pid].distractor, bank[pid].kind)
        if s is not None:
            dpre[pid] = dict(assistant_ids=s.assistant_ids, text=s.text, parsed=s.parsed, trajectory_idx=s.trajectory_idx)
    for pid in pools.main:
        _ = bank[pid]
    _json(os.path.join(ctx.run_path, "data", "mining.json"), {pid: m.to_json() for pid, m in mining.items()})
    _json(os.path.join(ctx.run_path, "data", "pools.json"), dict(main=pools.main, D=pools.D, D_nat=pools.D_nat, C=pools.C, excluded=pools.excluded,
                                                              d_prefill=dpre, exclusion_rate=exclusion_rate(list(bank), mining, {p: bank[p].family for p in bank})))
    _json(os.path.join(ctx.run_path, "data", "folds.json"), folds)
    return dict(n_problems=len(bank), n_main=len(pools.main), n_D=len(pools.D), n_C=len(pools.C), n_batch2=len(need2))


def load_pools(ctx: Context):
    from .data.pools import Pools
    d = _json(os.path.join(ctx.run_path, "data", "pools.json"))
    return Pools(d["main"], d["D"], d["D_nat"], d["C"], d["excluded"]), d.get("d_prefill", {})


def load_problems(ctx: Context) -> Dict[str, BankProblem]:
    bank = load_bank(ctx)
    mining = _json(os.path.join(ctx.run_path, "data", "mining.json"))
    _attach_distractors(bank, mining)
    return bank


def load_folds(ctx: Context) -> Dict[str, int]:
    return _json(os.path.join(ctx.run_path, "data", "folds.json"))


# ---------------------------------------------------------------- G1 (§7.2)
def stage_g1(ctx: Context) -> dict:
    bank = load_problems(ctx)
    pools, dpre = load_pools(ctx)
    sz = sizes(ctx)
    d_y1 = {pid: (v["assistant_ids"], v["text"]) for pid, v in dpre.items()}
    specs = G1.g1_specs(bank, pools, ctx.run_id, model=ctx.config.get("model_key", "M_main"), mode=ctx.mode, d_prefill_y1=d_y1)
    specs = [sp for sp in specs if sp.trajectory_idx < (sz["g1_subset_n"] if sp.script == "D" else sz["g1_n"])]
    trajs = run_specs(ctx, specs, "G1")
    distractors = {pid: p.distractor for pid, p in bank.items()}
    kinds = {pid: p.kind for pid, p in bank.items()}
    summ = G1.g1_summary(trajs, distractors, kinds)
    trunc = float(np.mean([t.truncated for t in trajs])) if trajs else 0.0
    notes = f"截断率={trunc:.3f}" + ("（>5%：需按 §4.3 改 max_new_tokens=768 并记录偏离）" if trunc > 0.05 else "")
    write_summary(ctx.run_path, "G1", dict(summ.to_json(), truncation_rate=trunc))
    gate_entry(ctx, "G1", "校准 pilot", f"{len(trajs)} trajectories; main pool {len(pools.main)}", summ.results, summ.decision, notes)
    _json(os.path.join(ctx.run_path, "data", "frontier.json"), summ.frontier)
    return dict(decision=summ.decision, n_trajs=len(trajs), frontier=len(summ.frontier))


# ---------------------------------------------------------------- G1.5 (§7.2b)
def stage_g15(ctx: Context) -> dict:
    bank = load_problems(ctx)
    pools, dpre = load_pools(ctx)
    sz = sizes(ctx)
    frontier = _json(os.path.join(ctx.run_path, "data", "frontier.json"))
    g1 = list(read_jsonl(os.path.join(ctx.run_path, "trajectories", "G1.jsonl")))
    d_prefill = {pid: (v["assistant_ids"], v["text"], v["parsed"]) for pid, v in dpre.items()}
    pres = G15.h2_prefixes(bank, frontier, g1, ctx.builder, ctx.first_turn_ids, d_prefill=d_prefill, d_pool=pools.D)
    specs = G15.continuation_specs(bank, pres, ctx.run_id, n=sz["g15_n"], c_pool=pools.C, model=ctx.config.get("model_key", "M_main"), mode=ctx.mode)
    z_fn = None
    if ctx.model is not None:                                   # plan §4.5: z for the h_2 (turn 2) and h_3 (turn 3) prompts
        from .gpu_glue import z_fn_for
        from .trajectory import ZStore
        ctx.extra.setdefault("zstore", ZStore(ctx.run_path))
        z_fn = z_fn_for(ctx)
    conts = run_specs(ctx, specs, "G15", z_fn=z_fn)
    G15.bank_stats(pres, conts)
    h3s = []
    for bp in pres:
        for sc in ([bp.script] if bp.script != "A3" else ["A3", "C"] if bp.problem_id in set(pools.C) else ["A3"]):
            h = G15.select_h3(bp, conts, ctx.builder, ctx.first_turn_ids, script=sc)
            if h is not None:
                h3s.append(h)
    os.makedirs(os.path.join(ctx.run_path, "data", "prefixes"), exist_ok=True)
    G15.write_bank(pres + h3s, os.path.join(ctx.run_path, "data", "prefixes", "prefix_bank.jsonl"))
    summary = dict(n_h2=len(pres), n_h3=len(h3s), n_dedup=getattr(G15.h2_prefixes, "n_dedup", 0), n_conts=len(conts),
                   scripts={sc: sum(1 for p in pres if p.script == sc) for sc in ("A1", "A3", "B", "D")})
    write_summary(ctx.run_path, "G15", summary)
    gate_entry(ctx, "G1.5", "前缀库", f"{len(pres)} h_2, {len(h3s)} h_3", [G0.GateResult("G1.5", True, summary, criteria="前缀库建立（无判据）")], "GO")
    return summary


def load_prefix_bank(ctx: Context) -> List[G15.BankPrefix]:
    return G15.read_bank(os.path.join(ctx.run_path, "data", "prefixes", "prefix_bank.jsonl"))


# ---------------------------------------------------------------- G2 (§7.3)
def stage_g2(ctx: Context, prebunk_texts: Optional[Dict[str, str]] = None) -> dict:
    bank = load_problems(ctx)
    sz = sizes(ctx)
    pres = load_prefix_bank(ctx)
    conts = list(read_jsonl(os.path.join(ctx.run_path, "trajectories", "G15.jsonl")))
    cands = G15.select_prefixes(pres, "A3", max_P_e2=0.1, per_problem=1)[: sz["g2_n_h2"]]
    sources = {}
    for bp in cands:
        s = G2.choose_sources(bp, conts, bank[bp.problem_id].distractor)
        if prebunk_texts and bp.prefix_id in prebunk_texts:
            s["c"] = G2.external_source(bp, prebunk_texts[bp.prefix_id], ctx.builder.encode)
        if s["a"] is not None:
            sources[bp.prefix_id] = s
    specs = G2.g2_specs(bank, pres, sources, ctx.builder, ctx.run_id, n=sz["g2_n_cont"])
    trajs = run_specs(ctx, specs, "G2")
    est = G2.g2_estimates(trajs)
    res, dec, notes = G2.g2_decision(est)
    write_summary(ctx.run_path, "G2", dict(est, decision=dec, notes=notes, n_sources={k: sum(1 for s in sources.values() if s.get(k)) for k in "abc"}))
    gate_entry(ctx, "G2", "单发文本通道存在性", f"{len(sources)} h_2 × sources × {sz['g2_n_cont']}", res, dec, "; ".join(notes))
    return dict(decision=dec, n_h2=len(sources))


# ---------------------------------------------------------------- G2′-a (§7.4)
def stage_g2a(ctx: Context, kappa1: Optional[float] = None) -> dict:
    bank = load_problems(ctx)
    sz = sizes(ctx)
    folds = load_folds(ctx)
    pres = load_prefix_bank(ctx)
    picks = G2A.pick_prefixes(pres, n=sz["g2a_n_prefix"], folds=folds)
    y2 = run_specs(ctx, G2A.y2_specs(bank, picks, ctx.run_id, n=sz["g2a_N"]), "G2a_y2")
    conts = run_specs(ctx, G2A.continuation_specs_from_y2(bank, y2, ctx.builder, ctx.first_turn_ids, ctx.run_id, m=sz["g2a_M"]), "G2a_cont")
    counts = G2A.counts_by_y2(conts)
    lam_kl = ctx.config["lambda_dose_primary"] / (kappa1 if kappa1 else G2A.KAPPA1_PLACEHOLDER)
    est = G2A.g2a_estimates(counts, lam_kl=lam_kl, kappa1=kappa1)
    res, dec = G2A.g2a_gate(est)
    # (ii) testimony
    h3s = [h for h in pres if h.script == "A3" and h.level == 3][: sz["g2a_n_h3"]]
    y3 = run_specs(ctx, G2A.y3_specs(bank, h3s, ctx.run_id, n=sz["g2a_Ms"]), "G2a_y3")
    y4 = run_specs(ctx, G2A.y4_specs_from_y3(bank, y3, ctx.builder, ctx.first_turn_ids, ctx.run_id, m=sz["g2a_m"]), "G2a_y4")
    rows = G2A.y4_table(y4)
    from .analysis.testimony import testimony_point
    tp = testimony_point(rows["prefix"], rows["stance"], rows["qbar"], 1.0, 1.0)      # PPV/NPV = 1 until the human subset exists
    summary = dict(J=est["J"], J_ci95=est["J_ci95"], frac_flagged=est["frac_flagged"], A_of_lambda=est["A_of_lambda"], kappa1_used=est["kappa1_used"],
                   kappa1_is_placeholder=est["kappa1_is_placeholder"], mean_var_q=est["mean_var_q"], frontier_mean=est["frontier_mean"],
                   per_prefix={k: {kk: vv for kk, vv in v.items() if kk != "frontier"} for k, v in est["per_prefix"].items()},
                   testimony_uncorrected=tp, decision=dec, n_prefix=len(picks), n_y2=len(y2), n_cont=len(conts))
    write_summary(ctx.run_path, "G2a", summary)
    gate_entry(ctx, "G2′-a", "无 steering 的 MPC 预算与证言模型", f"{len(picks)} prefixes × {sz['g2a_N']} y_2 × {sz['g2a_M']}", res, dec,
               "κ_1 占位 15 nats（G4-1 后回填）" if est["kappa1_is_placeholder"] else "")
    return dict(decision=dec, J=est["J"], n_prefix=len(picks))
