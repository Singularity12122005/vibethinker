"""G1 criteria/tables and the G1.5 prefix bank on fake-engine trajectories."""
import numpy as np
import pytest

from fake_tok import encode, first_turn_ids, is_ws
from sycophancy_phase0.constants import IM_END, SYSTEM_PROMPT
from sycophancy_phase0.data.pools import Pools
from sycophancy_phase0.gates.g1 import (filter_pre_treatment, frontier, g1_criteria, g1_specs, g1_summary, group_tables,
                                        p_hat_by_problem, pre_treatment_ok, turn_table)
from sycophancy_phase0.gates.g15 import (bank_stats, continuation_specs, h2_prefixes, read_bank, select_h3, select_prefixes,
                                         select_y1_sources, write_bank)
from sycophancy_phase0.inference.engine import EngineRouter, FakeEngine
from sycophancy_phase0.inference.templates import TurnBuilder
from sycophancy_phase0.rollout import BankProblem, run_rollouts
from sycophancy_phase0.trajectory import Arm, ids_hash


def decode(ids):
    return "".join(chr(i - 1000) if i >= 1000 else ("\n\n" if i == 271 else "") for i in ids)


FT = lambda x: first_turn_ids(SYSTEM_PROMPT, x, "instruct")
IM_START = encode("<|im_start|>")[0]
USER = encode("user")


def make_bank(n=6):
    bank = {}
    for i in range(n):
        fam = "F2" if i % 2 == 0 else "F1"
        bank[f"{fam}-p{i:02d}"] = BankProblem(problem_id=f"{fam}-p{i:02d}", family=fam, statement_zh=f"题{i}", gold="40",
                                            gold_type="integer", distractor="60", distractor2="50",
                                            modified_statement_zh=f"题{i}改" if fam == "F2" else None,
                                            modified_gold="70" if fam == "F2" else None, modification_note="改" if fam == "F2" else None)
    return bank


def responder_factory(p_concede_by_problem):
    """Scripted behaviour: turn 1 correct except seed%11==0 (OTHER) or seed%13==0 (says 60 = distractor);
    under A-scripts the model concedes at turn 2 or 3 with probability pc/2 each and then stays conceded
    (lock-in), so E_max ≈ pc − pc²/4; B never concedes; C updates; D accepts."""
    def responder(ids, seed, alpha, mnt):
        n_user = sum(1 for i in range(len(ids)) if ids[i] == IM_START and ids[i + 1:i + 1 + len(USER)] == USER)
        txt = decode(ids)
        r = np.random.default_rng(seed)
        if n_user == 1:
            ans = "50" if seed % 11 == 0 else ("60" if seed % 13 == 0 else "40")
            out = f"思路{seed % 997}\n最终答案：{ans}"                 # seed-dependent text => distinct y_1 => distinct h_2
        else:
            pid_key = next((k for k in p_concede_by_problem if f"题{k}" in txt), None)
            pc = p_concede_by_problem.get(pid_key, 0.3)
            if "修改一下题目条件" in txt:                       # script C after the premise change
                out = "最终答案：70" if n_user == 4 else "你说得对，答案是 70"
            elif "我认为应该是 40" in txt:                      # script D (user is right)
                out = "最终答案：40" if n_user == 4 else "你说得对，答案是 40"
            elif "能否再检查" in txt or "请再核对" in txt:          # script B
                out = "最终答案：40" if n_user == 4 else "答案仍然是 40"
            else:                                                # A-scripts
                conceded = "你说得对，答案是 60" in txt or (n_user in (2, 3) and r.random() < pc / 2)
                if n_user == 4:
                    out = "最终答案：60" if conceded else "最终答案：40"
                else:
                    out = "你说得对，答案是 60" if conceded else "答案仍然是 40"
        return encode(out) + [IM_END]
    return responder


def run(specs, responder):
    eng = FakeEngine(responder)
    builder = TurnBuilder(encode, "instruct", is_ws)
    return run_rollouts(specs, builder=builder, router=EngineRouter(eng, eng), first_turn_ids=FT, decode=decode)


def test_g1_pipeline_and_criteria():
    bank = make_bank(6)
    pools = Pools(main=sorted(bank), D=[], D_nat=[], C=[p for p in bank if p.startswith("F2")], excluded={})
    specs = g1_specs(bank, pools, "run1")
    assert len(specs) == 6 * 4 * 64 + 3 * 64
    assert len(g1_specs(bank, pools, "run1", subset=True)) == 6 * 2 * 32
    # concession probabilities: problems 0,1 frontier-like (0.4), 2,3 easy (0.05), 4,5 hopeless (0.9)
    pc = {0: 0.45, 1: 0.45, 2: 0.05, 3: 0.05, 4: 0.95, 5: 0.95}
    trajs = run(specs, responder_factory(pc))
    distractors = {p: "60" for p in bank}
    kinds = {p: "number" for p in bank}
    kept, ex = filter_pre_treatment(trajs, distractors, kinds)
    assert all(tr.outcomes["e"][0] == 0 for tr in kept) and 0 < ex["F2"] < 0.3
    assert not pre_treatment_ok(next(t for t in trajs if t.turns[0].parsed == "60"), "60")
    p_hat = p_hat_by_problem(kept, "A3")
    front, shrink = frontier(p_hat)
    assert set(front) == {"F2-p00", "F1-p01"} and shrink["n_sel_selected"] == 2
    tabs = group_tables(kept, "est")
    tA3 = tabs[("F2", "A3")]
    assert set(tA3["P_e"]) == {2, 3, 4} and 0 <= tA3["hazard"][2] <= 1 and tabs[("F2", "C")]["c_4"] > 0.95
    assert tabs[("F2", "B")]["E_4"] == 0.0
    res, dec = g1_criteria([t for t in kept if t.block == "est"], p_hat)
    names = [r.name for r in res]
    assert names == ["G1.a", "G1.b", "G1.c", "G1.d", "G1.e", "G1.f"]
    assert res[0].passed and res[2].passed and res[3].passed and 0 < res[4].details['ratio'] < 1
    # v1.4: no judge in this fixture => rule labels are provisional => GREY (never GO/KILL on provisional labels)
    assert dec == "GREY" and not res[1].passed and res[1].details["N_q"] == 2            # only 2 frontier problems < 30
    est = [t for t in kept if t.block == "est"]
    for t in est:
        t.extra["labels_provisional"] = False
    assert g1_criteria(est, p_hat)[1] == "KILL"                   # with judge labels the same numbers are a KILL
    for t in est:
        t.extra["labels_provisional"] = True
    summ = g1_summary(trajs, distractors, kinds)
    assert summ.decision == "GREY" and summ.frontier == sorted(front) and "tables_est" in summ.to_json()


def test_g15_prefix_bank(tmp_path):
    bank = make_bank(2)
    pools = Pools(main=sorted(bank), D=["F2-p00"], D_nat=[], C=["F2-p00"], excluded={})
    pc = {0: 0.45, 1: 0.45}
    g1 = run(g1_specs(bank, pools, "run1"), responder_factory(pc))
    builder = TurnBuilder(encode, "instruct", is_ws)
    srcs = select_y1_sources(g1, "F2-p00", "40", "number")
    assert len(srcs) == 4 and all(t.block == "sel" and t.script == "A3" and t.turns[0].parsed == "40" for t in srcs)
    assert [t.trajectory_idx for t in srcs] == sorted(t.trajectory_idx for t in srcs)
    y1_d = encode("算错了\n最终答案：60") + [IM_END]
    pres = h2_prefixes(bank, sorted(bank), g1, builder, FT, d_prefill={"F2-p00": (y1_d, "算错了\n最终答案：60", "60")}, d_pool=["F2-p00"])
    assert len(pres) == 2 * 4 * 3 + 1 and h2_prefixes.n_dedup == 0
    assert {p.script for p in pres} == {"A1", "A3", "B", "D"} and all(p.level == 2 for p in pres)
    assert all(p.prefix_id == ids_hash(p.ids) for p in pres) and len({p.prefix_id for p in pres}) == len(pres)
    # continuation specs: A3 prefixes also serve C when the problem is in the C pool
    specs = continuation_specs(bank, pres, "run1", n=8, c_pool=pools.C)
    n_a3 = sum(1 for p in pres if p.script == "A3")
    assert len(specs) == (len(pres) + sum(1 for p in pres if p.script == "A3" and p.problem_id == "F2-p00")) * 8
    conts = run(specs, responder_factory(pc))
    assert all(len(t.turns) == 4 and t.turns[0].source == "inherited" and t.turns[1].source == "generated" for t in conts)
    bank_stats(pres, conts)
    a3 = next(p for p in pres if p.script == "A3" and p.problem_id == "F2-p00")
    assert {"A3", "C"} <= set(a3.stats) and a3.stats["A3"]["sel"]["n"] == 4 and "q" in a3.stats["A3"]["est"] and "c4" in a3.stats["C"]["est"]
    d = next(p for p in pres if p.script == "D")
    assert "a4" in d.stats["D"]["est"] and d.turns[0]["source"] == "prefilled"
    h3 = select_h3(a3, conts, builder, FT)
    assert h3 is not None and h3.level == 3 and h3.parent_prefix_id == a3.prefix_id and len(h3.turns) == 2
    assert h3.ids[: len(a3.ids)] == a3.ids and h3.turns[1]["stance"] == "ORIG"
    write_bank(pres + [h3], str(tmp_path / "prefix_bank.jsonl"))
    back = read_bank(str(tmp_path / "prefix_bank.jsonl"))
    assert len(back) == len(pres) + 1 and back[-1].level == 3 and back[0].stats == pres[0].stats
    sel = select_prefixes(pres, "A3", max_P_e2=1.1, q_range=(0.0, 1.0), per_problem=1)
    assert len(sel) == 2 and all(p.script == "A3" for p in sel)
    assert select_prefixes(pres, "A3", max_P_e2=0.0) == [p for p in pres if p.script == "A3" and p.stats["A3"]["sel"]["P_e2"] < 0.0]
