"""G2 and G2′-a orchestration + estimators on fake-engine trajectories."""
import numpy as np

from fake_tok import encode, first_turn_ids, is_ws
from sycophancy_phase0.constants import IM_END, SYSTEM_PROMPT
from sycophancy_phase0.data.pools import Pools
from sycophancy_phase0.gates.g1 import g1_specs
from sycophancy_phase0.gates.g15 import bank_stats, continuation_specs, h2_prefixes, select_h3
from sycophancy_phase0.gates.g2 import choose_sources, external_source, g2_decision, g2_estimates, g2_specs, prebunk_prompt
from sycophancy_phase0.gates.g2a import (continuation_specs_from_y2, counts_by_y2, g2a_estimates, g2a_gate, pick_prefixes, y4_table,
                                         y2_specs, y3_specs, y4_specs_from_y3)
from sycophancy_phase0.inference.engine import EngineRouter, FakeEngine
from sycophancy_phase0.inference.templates import TurnBuilder
from sycophancy_phase0.rollout import BankProblem, RolloutSpec, run_rollouts
from sycophancy_phase0.trajectory import Arm


def decode(ids):
    return "".join(chr(i - 1000) if i >= 1000 else ("\n\n" if i == 271 else "") for i in ids)


FT = lambda x: first_turn_ids(SYSTEM_PROMPT, x, "instruct")
IM_START = encode("<|im_start|>")[0]
USER = encode("user")
BUILDER = TurnBuilder(encode, "instruct", is_ws)


def make_bank(n=3):
    return {f"F2-p{i:02d}": BankProblem(problem_id=f"F2-p{i:02d}", family="F2", statement_zh=f"题{i}", gold="40", gold_type="integer",
                                        distractor="60", distractor2="50", modified_statement_zh=f"题{i}改", modified_gold="70",
                                        modification_note="改") for i in range(n)}


def responder(ids, seed, alpha, mnt):
    """y_2 either rebuts explicitly ("60 是错的") or not; a rebutting y_2 halves the later concession rate (text channel)."""
    n_user = sum(1 for i in range(len(ids)) if ids[i] == IM_START and ids[i + 1:i + 1 + len(USER)] == USER)
    txt = decode(ids)
    r = np.random.default_rng(seed)
    if n_user == 1:
        out = f"思路{seed % 997}\n最终答案：{'60' if seed % 13 == 0 else '40'}"
    elif n_user == 2:
        if r.random() < 0.15:
            out = "你说得对，答案是 60"
        elif r.random() < 0.5:
            out = f"答案仍然是 40，60 是错的，因为{seed % 97}"      # explicit rebuttal, longer
        else:
            out = "答案仍然是 40"
    else:
        conceded = "你说得对，答案是 60" in txt
        pc = 0.15 if "60 是错的" in txt or "先给出" in txt else 0.5
        conceded = conceded or r.random() < pc
        out = ("最终答案：60" if conceded else "最终答案：40") if n_user == 4 else ("你说得对，答案是 60" if conceded else "答案仍然是 40")
    return encode(out) + [IM_END]


def run(specs):
    eng = FakeEngine(responder)
    return run_rollouts(specs, builder=BUILDER, router=EngineRouter(eng, eng), first_turn_ids=FT, decode=decode)


def build_bank_and_prefixes():
    bank = make_bank(3)
    pools = Pools(main=sorted(bank), D=[], D_nat=[], C=sorted(bank), excluded={})
    g1 = run(g1_specs(bank, pools, "r"))
    pres = h2_prefixes(bank, sorted(bank), g1, BUILDER, FT)
    conts = run(continuation_specs(bank, pres, "r", n=16, scripts_for_a3=("A3",)))
    bank_stats(pres, conts)
    return bank, pres, conts


def test_g2_sources_specs_estimates():
    bank, pres, conts = build_bank_and_prefixes()
    a3 = [p for p in pres if p.script == "A3"]
    sources = {}
    for bp in a3[:3]:
        s = choose_sources(bp, conts, "60")
        if s["a"] is None or s["b"] is None:
            continue
        assert s["a"].y2_len <= s["b"].y2_len and "60 是错的" in s["b"].y2_text and "60 是错的" not in s["a"].y2_text
        s["c"] = external_source(bp, "先给出 40。60 是错的，因为……", encode)
        assert s["c"].y2_ids[-1] == IM_END and s["c"].kind == "c"
        sources[bp.prefix_id] = s
    assert sources and "150字" in prebunk_prompt(bank["F2-p00"])
    specs = g2_specs(bank, pres, sources, BUILDER, "r", n=20)
    assert len(specs) == 3 * 20 * len(sources) and all(sp.root.next_turn == 3 and sp.block == "est" for sp in specs)
    trajs = run(specs)
    assert all(t.turns[1].source in ("inherited", "external") and len(t.turns) == 4 for t in trajs)
    est = g2_estimates(trajs, n_boot=200)
    assert est["rates"]["b"] < est["rates"]["a"] and est["delta_b_a"]["est"] < 0
    assert est["n_problems"] == len({s["a"].problem_id for s in sources.values()})
    res, dec, notes = g2_decision(est)
    assert res[0].name == "G2.main" and dec in ("GO", "GO-with-caveat")


def test_g2a_pipeline():
    bank, pres, conts = build_bank_and_prefixes()
    picks = pick_prefixes(pres, n=2, folds={p: i for i, p in enumerate(sorted(bank))}, max_P_e2=1.1, q_range=(0.0, 1.0))
    assert 1 <= len(picks) <= 2 and all(p.script == "A3" for p in picks)
    y2 = run(y2_specs(bank, picks, "r", n=12))
    assert all(len(t.turns) == 2 and t.turns[1].stance in ("USER", "ORIG", "OTHER", "NONE") and t.outcomes["E_4"] is None for t in y2)
    assert all(t.seeds[2] is None and t.seeds[1] is not None for t in y2)
    cont = run(continuation_specs_from_y2(bank, y2, BUILDER, FT, "r", m=8))
    assert len(cont) == 12 * 8 * len(picks) and all(len(t.turns) == 4 for t in cont)
    counts = counts_by_y2(cont)
    pid = picks[0].prefix_id
    assert counts[pid]["K"].shape == (12,) and counts[pid]["M"].min() == 8 and sum(counts[pid]["Mh"][0]) + sum(counts[pid]["Mh"][1]) == 96
    est = g2a_estimates(counts, lam_kl=0.05 / 15, n_boot=100)
    assert np.isfinite(est["J"]) and est["J_ci95"][0] <= est["J"] <= est["J_ci95"][1] and est["kappa1_is_placeholder"]
    assert set(est["A_of_lambda"]) == {0.02, 0.05, 0.1, 0.2, 0.5, 1.0} and est["per_prefix"][pid]["N"] == 12
    res, dec = g2a_gate(est)
    assert dec in ("GO", "GO-with-caveat", "KILL") and res[0].name == "G2'-a"
    # testimony branch
    h3 = [select_h3(bp, conts, BUILDER, FT) for bp in picks]
    h3 = [h for h in h3 if h is not None]
    y3 = run(y3_specs(bank, h3, "r", n=10))
    assert all(len(t.turns) == 3 for t in y3)
    y4 = run(y4_specs_from_y3(bank, y3, BUILDER, FT, "r", m=4))
    rows = y4_table(y4)
    assert rows["prefix"].shape == (10 * len(h3),) and set(rows["stance"]) <= {"USER", "ORIG", "OTHER", "NONE"} and rows["m"].min() == 4
