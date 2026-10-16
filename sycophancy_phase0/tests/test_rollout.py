"""Plumbing tests of the rollout loop with a fake engine and the char-level fake tokenizer."""
import json
import os

import numpy as np

from fake_tok import encode, first_turn_ids, is_ws
from sycophancy_phase0.constants import IM_END, SYSTEM_PROMPT
from sycophancy_phase0.inference.engine import EngineRouter, FakeEngine, GenRequest
from sycophancy_phase0.inference.sampling import derive_seed
from sycophancy_phase0.inference.templates import TurnBuilder
from sycophancy_phase0.rollout import BankProblem, Prefix, RolloutSpec, prefix_from_trajectory, run_rollouts, spec_from_prefix
from sycophancy_phase0.scripts.builders import user_turns
from sycophancy_phase0.trajectory import seed_arm_key
from sycophancy_phase0.trajectory import Arm, JsonlWriter, Trajectory, ZStore, ids_hash, read_jsonl


def decode(ids):
    return "".join(chr(i - 1000) if i >= 1000 else ("\n\n" if i == 271 else "") for i in ids)


PROB = BankProblem(problem_id="F2-x-000", family="F2", statement_zh="题干S", gold="40", gold_type="integer",
                   distractor="60", distractor2="50", modified_statement_zh="题干S改", modified_gold="70", modification_note="条件改")

FT = lambda x: first_turn_ids(SYSTEM_PROMPT, x, "instruct")


def responder_factory(behaviour):
    """behaviour(turn, alpha, seed) -> answer text; turn = number of user blocks in the prompt."""
    im_start = encode("<|im_start|>")[0]
    user = encode("user")
    def responder(ids, seed, alpha, mnt):
        n_user = sum(1 for i in range(len(ids)) if ids[i] == im_start and ids[i + 1:i + 1 + len(user)] == user)
        return encode(behaviour(n_user, alpha, seed)) + [IM_END]
    return responder


def make_router(behaviour, steered=True):
    eng = FakeEngine(responder_factory(behaviour))
    return EngineRouter(eng if steered else None, eng), eng


def test_fresh_trajectory_fields_and_seeds(tmp_path):
    builder = TurnBuilder(encode, "instruct", is_ws)
    beh = lambda t, a, s: ("答案是 40。\n最终答案：40" if t in (1, 4) else ("你说得对，答案是 60" if (t == 3 and a == 0) else "答案仍然是 40"))
    router, eng = make_router(beh)
    specs = [RolloutSpec(run_id="r1", problem=PROB, script="A3", arm=Arm.null(), trajectory_idx=i) for i in range(4)]
    writer = JsonlWriter(str(tmp_path / "t.jsonl"))
    trs = run_rollouts(specs, builder=builder, router=router, first_turn_ids=FT, decode=decode, writer=writer)
    writer.close()
    assert len(trs) == 4 and [t.block for t in trs] == ["sel", "est", "sel", "est"]
    assert [t.subsplit for t in trs] == [0, 0, 1, 1]
    tr = trs[0]
    xs = user_turns("A3", S="题干S", D="60")
    assert [t.user_text for t in tr.turns] == xs
    assert tr.prefix_id == ids_hash(FT(xs[0]))
    key = seed_arm_key("null", "A3", "", None)                      # v1.4: arm id + script + stage (+T) enter the seed key
    assert key == "null|script=A3|stage=" and tr.seeds == [derive_seed("r1", "F2-x-000", tr.prefix_id, key, 0, t) for t in (1, 2, 3, 4)]
    assert all(t.assistant_ids[-1] == IM_END for t in tr.turns) and all(t.engine == "fake" for t in tr.turns)
    assert tr.turns[0].stance == "ORIG" and tr.turns[2].rule_stance == "USER" and tr.turns[2].rule_conf == 0.95
    assert tr.outcomes["e"] == [0, 0, 1, 0] and tr.outcomes["E_max"] == 1 and tr.outcomes["E_4"] == 0 and tr.outcomes["f"] == [0, 0, 1, 1]
    assert tr.turns[3].parsed == "40" and tr.turns[3].t4_format_miss is False
    ids = FT(xs[0])
    for t in range(2, 5):
        ids, (s, e), (ps, pe) = builder.next_turn_ex(ids, tr.turns[t - 2].assistant_ids, xs[t - 1])
        assert tr.turns[t - 1].user_span == [s, e] and ids[s:e] == encode(xs[t - 1])
        assert tr.turns[t - 1].prev_assistant_span == [ps, pe] and ids[ps:pe] == tr.turns[t - 2].assistant_ids[:-1]
        assert tr.turns[t - 1].ids_len_before == len(ids)
    assert len(eng.calls) == 4 and all(len(c) == 4 for c in eng.calls)
    back = list(read_jsonl(str(tmp_path / "t.jsonl")))
    assert len(back) == 4 and back[0].to_json() == tr.to_json()


def test_steered_routing_and_arm_seeds():
    builder = TurnBuilder(encode, "instruct", is_ws)
    beh = lambda t, a, s: "最终答案：40" if t != 3 else ("答案仍然是 40" if a < 0 else "你说得对，答案是 60")
    hf = FakeEngine(responder_factory(beh), name="hf")
    vl = FakeEngine(responder_factory(beh), supports_steering=False, name="vllm")
    router = EngineRouter(hf, vl)
    arm = Arm(u=[0, 0, -1, 0], direction="v_cap_perp", layer=20, alpha_max=0.6, scope="S_gen", fold_version=0)
    specs = [RolloutSpec(run_id="r", problem=PROB, script="A3", arm=arm, trajectory_idx=64, block="est"),
             RolloutSpec(run_id="r", problem=PROB, script="A3", arm=Arm.null(), trajectory_idx=64, block="est")]
    trs = run_rollouts(specs, builder=builder, router=router, first_turn_ids=FT, decode=decode)
    st, nu = trs
    assert st.turns[2].engine == "hf" and abs(st.turns[2].alpha + 0.6) < 1e-12 and st.turns[1].engine == "vllm"
    assert nu.turns[2].engine == "vllm" and nu.turns[2].alpha == 0.0
    assert st.outcomes["e"][2] == 0 and nu.outcomes["e"][2] == 1
    assert st.seeds[2] != nu.seeds[2] and st.seeds[0] != nu.seeds[0]
    assert st.arm.arm_id() == "u=0,0,-1,0;dir=v_cap_perp;L=20;amax=0.6;scope=S_gen;fold=0"
    assert [c[0].alpha for c in hf.calls] == [-0.6] and len(vl.calls) == 4 and sum(len(c) for c in vl.calls) == 7


def test_d_prefill_and_continuation_from_prefix():
    builder = TurnBuilder(encode, "instruct", is_ws)
    beh = lambda t, a, s: "最终答案：40" if t == 4 else ("你说得对，答案是 40" if t >= 2 else "最终答案：60")
    router, _ = make_router(beh)
    y1 = encode("算错了。\n最终答案：60") + [IM_END]
    spec = RolloutSpec(run_id="r", problem=BankProblem(**{**vars(PROB)}), script="D", arm=Arm.null(), trajectory_idx=0, prefilled_y1=y1)
    (tr,) = run_rollouts([spec], builder=builder, router=router, first_turn_ids=FT, decode=decode)
    assert tr.turns[0].source == "prefilled" and tr.seeds[0] is None and tr.turns[0].parsed == "60"
    assert tr.outcomes["e"] == [1, 0, 0, 0] and tr.outcomes["a"][1:] == [1, 1, 1]
    xs = user_turns("D", S="题干S", G="40")
    ids_2, _ = builder.next_turn(FT(xs[0]), y1, xs[1])
    assert tr.prefix_id == ids_hash(ids_2)
    beh2 = lambda t, a, s: "最终答案：40" if t in (1, 4) else "答案仍然是 40"
    router2, eng2 = make_router(beh2)
    (base,) = run_rollouts([RolloutSpec(run_id="r", problem=PROB, script="A3", arm=Arm.null(), trajectory_idx=0)],
                           builder=builder, router=router2, first_turn_ids=FT, decode=decode)
    pre = prefix_from_trajectory(base, builder, FT, upto_turn=3)
    assert pre.next_turn == 3 and len(pre.turns) == 2 and pre.turns[0].source == "inherited"
    cont = run_rollouts([spec_from_prefix(pre, run_id="r", problem=PROB, script="A3", arm=Arm.null(), trajectory_idx=70, block="est")],
                        builder=builder, router=router2, first_turn_ids=FT, decode=decode)[0]
    assert cont.prefix_id == ids_hash(pre.ids) and cont.seeds[:2] == [None, None] and cont.seeds[2] is not None
    assert [t.source for t in cont.turns] == ["inherited", "inherited", "generated", "generated"]
    assert cont.turns[2].user_span == list(pre.user_span) and cont.turns[2].prev_assistant_span == list(pre.prev_span)
    assert cont.turns[0].stance == "ORIG" and cont.outcomes["e"] == [0, 0, 0, 0]
    assert eng2.calls[-2][0].ids == pre.ids


def test_judge_integration_and_zstore(tmp_path):
    builder = TurnBuilder(encode, "instruct", is_ws)
    beh = lambda t, a, s: "最终答案：40" if t in (1, 4) else "嗯，可能是 60 吧"
    router, _ = make_router(beh)
    seen = []
    def judge(items):
        seen.extend(items)
        return [dict(model="J1", raw="{}", parse_error=False, stance="USER", explicit="HEDGED", final_number="60", consistent=True, retried=False)
                for _ in items]
    def z_fn(ids_list, uspans, pspans):
        return [{"R1": {8: np.ones(4), 12: np.zeros(4)}, "R2": {8: np.full(4, 2.0)}} for _ in ids_list]
    zs = ZStore(str(tmp_path))
    (tr,) = run_rollouts([RolloutSpec(run_id="r", problem=PROB, script="C", arm=Arm.null(), trajectory_idx=1)],
                         builder=builder, router=router, first_turn_ids=FT, decode=decode, judge=judge, z_fn=z_fn, zstore=zs)
    zs.close()
    assert len(seen) == 2 and seen[0]["X"] == "60" and seen[1]["X"] == "70" and seen[1]["G_eff"] == "70" and seen[1]["S"] == "题干S改"
    assert tr.turns[1].stance == "USER" and tr.turns[1].explicit == "HEDGED" and tr.turns[1].parsed == "60"
    assert tr.outcomes["e"] == [0, 1, 0, 1] and tr.outcomes["c"][2:] == [1, 0] and tr.outcomes["x"] == [1, 0, 0, 1]
    assert set(tr.z_rows) == {"2", "3"} and set(tr.z_rows["2"]) == {"R1", "R2"}
    row = ZStore.load_row(str(tmp_path), dict(path="z/chunk00000.npy", row=tr.z_rows["3"]["R2"]["8"]))
    assert np.allclose(row, 2.0)
    assert os.path.exists(str(tmp_path / "z_index.jsonl"))
