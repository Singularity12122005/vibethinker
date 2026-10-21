"""只验证实现，不作为研究数据或现象证据。"""
from copy import deepcopy
from itertools import product
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[2] / "tests"))
from common import Blocked, clean_second, require_scored, require_generation_quality
from analyze import exact_allocation, matched_comparison, phase_a1
from phase_a import h3_from_clean
from rescore import rescore_batch
from test_rollout import PROB, FT, decode, make_router
from fake_tok import encode, is_ws
from sycophancy_phase0.inference.templates import TurnBuilder
from sycophancy_phase0.rollout import RolloutSpec, run_rollouts
from sycophancy_phase0.trajectory import Arm


def fixture_rows():
    router, _ = make_router(lambda t, a, s: "最终答案：40" if t in (1, 4) else "答案是 60")
    return run_rollouts([RolloutSpec("test", PROB, sc, Arm.null(), j) for sc in ("A3", "B") for j in range(4)],
                        builder=TurnBuilder(encode, "instruct", is_ws), router=router, first_turn_ids=FT, decode=decode)


def mark_scored(rows):
    for tr in rows:
        tr.extra.pop("labels_provisional", None)
        for t in tr.turns[1:3]:
            t.judge = dict(model="test_judge", parse_error=False)
    return rows


def test_q1_joint_denominator_excludes_hedging_and_early_failure():
    rows = mark_scored(fixture_rows())
    for i, tr in enumerate(rows):
        tr.outcomes["e"] = [0, 0, 1, 0] if tr.script == "A3" else [0, 0, 0, 0]
        tr.outcomes["E_max"] = max(tr.outcomes["e"])
        tr.turns[1].stance, tr.turns[1].explicit = "ORIG", "EXPLICIT"
    rows[0].turns[1].explicit = "HEDGED"
    rows[1].turns[1].stance = "USER"
    rows[1].outcomes["e"][1] = 1
    result = phase_a1(rows, {PROB.problem_id: PROB}, 20)
    assert result["joint_late_failure"] == {"A3": .5, "B": 0.}
    assert result["n_kept"] == 8
    assert result["decision"] == "STOP"  # 单题不能通过前沿题数门槛。
    rows[0].extra["labels_provisional"] = True
    with pytest.raises(Blocked):
        phase_a1(rows, {PROB.problem_id: PROB}, 20)


def test_dynamic_program_matches_exhaustive_search_even_and_odd():
    for risk in ([.05, .2, .8, .95], [.15, .5, .9]):
        doses, p = exact_allocation(risk, 2.5)
        n = len(risk)
        brute = min(sum(p[i, d] for i, d in enumerate(ds)) for ds in product(range(3), repeat=n) if sum(ds) == n)
        assert doses.mean() == .5
        assert np.isclose(p[np.arange(n), (2 * doses).astype(int)].sum(), brute)


def test_matched_control_removes_distribution_only_gain():
    # 各状态完全一样，但非线性使 0/1 分配优于固定半剂量。
    p = np.tile([.9, .8, .4], (4, 1))
    r = matched_comparison(p, [0, 0, 1, 1], [0, 1, 2, 3], 30)
    assert r["gain"] == pytest.approx(0)
    assert p[:, 1].mean() - r["assigned"] == pytest.approx(.15)
    # 仅依赖剂量的加性误报会精确抵消。
    p = np.array([[.8, .6, .1], [.1, .1, .1]])
    before = matched_comparison(p, [1, 0], [0, 1], 20)["gain"]
    after = matched_comparison(p + [.01, .02, .03], [1, 0], [0, 1], 20)["gain"]
    assert before == pytest.approx(after)


def test_rescore_blind_items_and_outcomes_replace_provisional():
    rows = fixture_rows()
    with pytest.raises(Blocked):
        require_scored(rows)
    seen = []
    def judge(items):
        seen.extend(items)
        return [dict(model="test_judge", stance="ORIG", explicit="HEDGED", final_number="40", parse_error=False) for it in items]
    rescore_batch(rows, {PROB.problem_id: PROB}, judge)
    require_scored(rows)
    assert all(set(it) == {"S", "G_eff", "X", "G_orig", "Y", "kind", "no_think_close"} for it in seen)
    assert all(tr.outcomes["e"] == [0, 0, 0, 0] and tr.outcomes["CE"][1] == 0 for tr in rows)
    assert all(not clean_second(tr) for tr in rows)


def test_h3_selection_skips_earlier_hedged_answer():
    rows = mark_scored(fixture_rows())[:3]
    for tr in rows:
        tr.turns[1].stance, tr.turns[1].explicit = "ORIG", "EXPLICIT"
    rows[0].turns[1].explicit = "HEDGED"
    bp = SimpleNamespace(prefix_id=rows[0].prefix_id, problem_id=PROB.problem_id, k=0)
    ctx = SimpleNamespace(builder=TurnBuilder(encode, "instruct", is_ws), first_turn_ids=FT)
    h3 = h3_from_clean(ctx, bp, rows)
    assert h3.source_traj_id == rows[2].traj_id  # idx=1 属于估计块，不能拿来选前缀。


def test_truncated_generation_stops_without_removing_rows():
    rows = fixture_rows()
    for t in rows[0].turns:
        t.truncated = True
    with pytest.raises(Blocked):
        require_generation_quality(rows)
    assert len(rows) == 8 and sum(t.truncated for r in rows for t in r.turns) == 4


def test_authorized_fraction_parser_is_strict_and_string_safe(monkeypatch):
    from fractions import Fraction
    from parsing import normalize_number
    from sycophancy_phase0.scoring import parse
    monkeypatch.setattr(parse, "normalize_number", normalize_number)
    assert parse.canonical(r"$\frac{1}{2}$") == "1/2"
    assert parse.canonical(r"\frac{−3}{-4}") == "3/4"
    assert normalize_number("0.5") == Fraction(1, 2)
    for bad in (r"\frac{1}{2} 或 40", r"大概\frac{1}{2}", r"\frac{1}{2}+1", r"\frac{1}{0}",
                r"\frac{1.0}{2}", r"\frac{\frac{1}{2}}{3}", r"\frac{1}{2}%"):
        assert parse.canonical(bad) is None
    assert parse.canonical(r"\frac{1}{2}", "string") == r"\frac{1}{2}"


def test_mining_does_not_require_a_preexisting_wrong_answer(monkeypatch, tmp_path):
    import phase_a
    problem = deepcopy(PROB)
    problem.distractor = None
    monkeypatch.setattr(phase_a, "load_bank", lambda ctx: {problem.problem_id: problem})
    router, _ = make_router(lambda t, a, s: "最终答案：40")
    def gen(ctx, specs, stage, batch_size):
        return run_rollouts(specs, builder=TurnBuilder(encode, "instruct", is_ws), router=router,
                            first_turn_ids=FT, decode=decode)
    monkeypatch.setattr(phase_a, "generate", gen)
    ctx = SimpleNamespace(run_id="test", run_path=str(tmp_path), config={"sizes": {"mining_n": 2}})
    result = phase_a.mining(ctx, 2)
    assert result["n_main"] == 0 and result["n_candidates"] == 1
