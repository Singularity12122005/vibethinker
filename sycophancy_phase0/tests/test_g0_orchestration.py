import json
import os

import numpy as np

from chain_fixture import build_chain
from fake_tok import encode
from sycophancy_phase0.gates.g0 import g0_4, g0_8
from sycophancy_phase0.gates.g0_runner import cross_stack, g04_inputs, g04_phase1, g04_phase2
from sycophancy_phase0.gates.g15 import continuation_specs
from sycophancy_phase0.stages import load_prefix_bank, load_problems
from sycophancy_phase0.trajectory import read_jsonl


def test_g04_and_g08_plumbing(tmp_path):
    ctx, info = build_chain(str(tmp_path), run_id="G0X", n_problems=3)
    bank = load_problems(ctx)
    pres = [b for b in load_prefix_bank(ctx) if b.level == 2 and b.script == "A3"][:2]
    h2 = [(bank[b.problem_id], b.to_prefix()) for b in pres]
    logits_fn = lambda ids: np.array([len(ids), sum(ids) % 97, ids[-1]], dtype=np.float32)      # deterministic in ids
    p1 = g04_phase1(ctx, h2, n_y2=2, n_cont=4, logits_fn=logits_fn)
    assert p1["in_memory"] and p1["hook_present"] is None and len(p1["first_logits"]) == 8 and all(t.next_ids is not None for t in p1["y2"])
    assert len(p1["y2"]) == 2 * 2 * 2 and all(len(t.turns) == 2 and not t.arm.is_null for t in p1["y2"]) and len(p1["conts"]) == 8 * 4
    def text_path(msgs):
        t = ""
        for m in msgs:
            t += f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
        return encode(t + "<|im_start|>assistant\n")
    y2_jsonl = [t for t in read_jsonl(os.path.join(ctx.run_path, "trajectories", "G04_phase1_y2.jsonl"))]
    assert len(y2_jsonl) == 8 and all(t.next_ids is None for t in y2_jsonl)                   # phase 2 works from the JSONL only
    p2 = g04_phase2(ctx, h2, y2_jsonl, text_path_ids=text_path, n_cont=4, logits_fn=logits_fn)
    hf_reqs = [r for call in ctx.router.steered.calls for r in call if r.engine == "hf"]
    assert len(hf_reqs) >= 2 * (8 * 4 + 8) and all(r.alpha == 0.0 for r in hf_reqs)           # both paths forced onto the HF engine at alpha 0
    assert p2["text_path_mismatch_rate"] == 0.0 and len(p2["conts"]) == 8 * 4
    inp = g04_inputs(p1, p2)
    assert inp["ids_identical"] and inp["greedy_identical"] and inp["e3_same_process"].shape == (32,) and len(set(inp["h2_cluster"])) == 2
    assert inp["design_ok"] and inp["design_notes"] == "" and inp["first_logit_maxdiff"] == 0.0
    inp_nolog = g04_inputs(p1, dict(p2, first_logits={}))
    assert not inp_nolog["design_ok"] and "logits" in inp_nolog["design_notes"] and not g0_4(**inp_nolog).passed
    # v1.4 G0.4 design note: phase-2 continuations sample a DISJOINT trajectory_idx range (seeds differ), so e_3 is a fresh
    # draw from the same process rather than a replay; only ids/greedy are required to be bitwise identical.
    assert {t.trajectory_idx for t in p1["conts"]} == set(range(64, 68)) and {t.trajectory_idx for t in p2["conts"]} == set(range(96, 100))
    assert len({t.traj_id for t in p1["conts"]} & {t.traj_id for t in p2["conts"]}) == 0
    r = g0_4(**inp)
    assert r.details["ids_identical"] and r.details["greedy_identical"] and r.details["text_path_mismatch_rate"] == 0.0 and r.details["first_logits_measured"]
    specs = continuation_specs(bank, [b for b in load_prefix_bank(ctx) if b.level == 3][:2], ctx.run_id, n=6, idx0=64, block="est", scripts_for_a3=("A3",))
    ea, eb, cl = cross_stack(ctx, ctx, specs)
    assert ea.shape == eb.shape and np.array_equal(ea, eb) and g0_8(ea, eb, cl).passed
    budget = json.load(open(os.path.join(ctx.run_path, "tables", "budget.json"), encoding="utf-8"))
    assert "G1" in budget and budget["G1"]["null"]["generated"] > 0
