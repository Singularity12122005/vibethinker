"""第一阶段：真实题目、错误答案挖掘、施压轨迹与固定前缀库。"""
from __future__ import annotations

from collections import defaultdict
import random
from pathlib import Path
from common import Blocked, cli, context, generate, load, parser, save, trajectories, clean_second

from sycophancy_phase0.data.common import read_bank, write_bank
from sycophancy_phase0.data.pools import SingleTurnSample, mine, needs_batch2, assign_pools
from sycophancy_phase0.gates import g1 as G1, g15 as G15
from sycophancy_phase0.rollout import RolloutSpec, prefix_from_trajectory
from sycophancy_phase0.run import stage_data
from sycophancy_phase0.stages import load_bank, load_problems, load_pools
from sycophancy_phase0.trajectory import Arm


def data(ctx):
    d = Path(ctx.run_path) / "data"
    if (d / "selected.json").exists():
        return load(d / "selected.json")
    stage_data(ctx)
    rng = random.Random(20261020)
    chosen = {}
    for fam in ("F2", "F3"):
        rows = read_bank(str(d / f"{fam}.jsonl"))
        kept = rng.sample(rows, 1 if ctx.config["smoke"] else 32)
        write_bank(kept, str(d / f"{fam}.jsonl"))
        chosen[fam] = [p.problem_id for p in kept]
    save(d / "selected.json", chosen)
    return chosen


def mining(ctx, batch_size):
    """沿用 stage_mine 的定义；逐批落盘，避免长生成结束前丢失整批。"""
    bank = load_bank(ctx)
    n = ctx.config["sizes"]["mining_n"]
    samples = defaultdict(list)
    for batch, temp in ((1, None), (2, 1.0)):
        pids = list(bank) if batch == 1 else [p for p in bank if needs_batch2(samples[p], bank[p].gold, bank[p].kind)]
        if not pids:
            continue
        # 第一轮各脚本相同；挖掘发生在错误答案已知之前，须用不要求 D 的 B。
        specs = [RolloutSpec(ctx.run_id, bank[p], "B", Arm.null(), j, stop_after=1,
                            temperature=temp, extra={"batch": batch}) for p in pids for j in range(n)]
        for tr in generate(ctx, specs, f"P_mine_{batch}", batch_size):
            t = tr.turns[0]
            samples[tr.problem_id].append(SingleTurnSample(tr.trajectory_idx, batch, t.parsed, t.assistant_text, t.assistant_ids))
    results = {p: mine(p, b.gold, b.kind, samples[p], 3) for p, b in bank.items()}
    pools = assign_pools({p: dict(family=b.family, gold=b.gold, gold_type=b.gold_type, modified_gold=b.modified_gold)
                          for p, b in bank.items()}, results, samples, .9, .3)
    d = Path(ctx.run_path) / "data"
    save(d / "mining.json", {p: x.to_json() for p, x in results.items()})
    save(d / "pools.json", dict(main=pools.main, D=pools.D, D_nat=pools.D_nat, C=pools.C,
                                excluded=pools.excluded, d_prefill={}))
    pids = sorted(pools.main)
    random.Random(20261020).shuffle(pids)
    halves = {p: int(i >= (len(pids) + 1) // 2) for i, p in enumerate(pids)}
    if (d / "halves.json").exists() and load(d / "halves.json") != halves:
        raise Blocked("题目两半已存在且与当前题库不一致，禁止静默改变")
    save(d / "halves.json", halves)
    return dict(n_main=len(pools.main), n_candidates=len(bank), note="只有首批样本进入正确率")


def a1(ctx, batch_size):
    bank = load_problems(ctx)
    pools, _ = load_pools(ctx)
    pools.main = sorted(pools.main)[:48]
    if ctx.config["smoke"]:
        # 两题小检查只检验真实生成链路，不据此选主池或判定研究结论。
        pools.main = sorted(bank)[:2]
        for p in bank.values():
            p.distractor = p.distractor or ("错误输出" if p.kind == "string" else str(float(p.gold) + 1))
        mining_path = Path(ctx.run_path) / "data/mining.json"
        info = load(mining_path)
        for p in bank.values():
            info[p.problem_id]["distractor"] = p.distractor
        save(mining_path, info)
    specs = [s for s in G1.g1_specs(bank, pools, ctx.run_id)
             if s.script in ("A3", "B") and s.trajectory_idx < (2 if ctx.config["smoke"] else (16 if s.script == "A3" else 8))]
    rows = generate(ctx, specs, "P_A1", batch_size)
    return dict(n=len(rows), next="卸载主模型后运行 rescore.py；未经评审不得作 Q1 判定")


def h3_from_clean(ctx, bp, conts):
    rows = sorted((t for t in conts if t.prefix_id == bp.prefix_id and t.script == "A3" and t.block == "sel" and clean_second(t)),
                  key=lambda t: t.trajectory_idx)
    if not rows:
        return None
    tr = rows[0]
    pre = prefix_from_trajectory(tr, ctx.builder, ctx.first_turn_ids, 3)
    return G15.BankPrefix(pre.prefix_id, bp.problem_id, "A3", 3, bp.k, tr.traj_id, pre.ids,
                          [vars(t) for t in pre.turns], list(pre.user_span), list(pre.prev_span), bp.prefix_id)


def a2(ctx, batch_size, finalize=False):
    d = Path(ctx.run_path)
    summary = load(d / "tables" / "phase_a1.json")
    if summary["decision"] != "CONTINUE":
        raise Blocked("Q1 未通过，不能生成下一阶段数据")
    bank = load_problems(ctx)
    rows = trajectories(ctx, "P_A1", scored=True)
    pres, seen = [], set()
    for pid in summary["frontier"][:24]:
        b = bank[pid]
        for k, tr in enumerate(G15.select_y1_sources(rows, pid, b.gold, b.kind, 4)):
            bp = G15.build_h2(b, tr, "A3", k, ctx.builder, ctx.first_turn_ids)
            if bp.prefix_id not in seen:
                pres.append(bp)
                seen.add(bp.prefix_id)
    if finalize:
        conts = trajectories(ctx, "P_A2", scored=True)
        G15.bank_stats(pres, conts)
        h3s = [h for bp in pres if (h := h3_from_clean(ctx, bp, conts)) is not None]
        G15.write_bank(pres + h3s, str(d / "data/prefixes/prefix_bank.jsonl"))
        return dict(n_h2=len(pres), n_clean_h3=len(h3s))
    specs = G15.continuation_specs(bank, pres, ctx.run_id, n=2 if ctx.config["smoke"] else 32, c_pool=(), stage="P_A2")
    rows = generate(ctx, specs, "P_A2", batch_size)
    return dict(n=len(rows), next="真实评审后运行 a2-bank")


def main():
    ap = parser(__doc__)
    ap.add_argument("stage", choices=("data", "mine", "a1", "a2", "a2-bank"))
    args = ap.parse_args()
    ctx = context(args, gpu=args.stage in ("mine", "a1", "a2"), tokenizer=args.stage == "a2-bank")
    if args.stage == "data":
        result = data(ctx)
    elif args.stage == "mine":
        result = mining(ctx, args.batch_size)
    elif args.stage == "a1":
        result = a1(ctx, args.batch_size)
    else:
        result = a2(ctx, args.batch_size, args.stage == "a2-bank")
    print(result, flush=True)


if __name__ == "__main__":
    cli(main)
