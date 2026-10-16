import json
import os

import numpy as np

from chain_fixture import build_chain
from fake_tok import encode
from sycophancy_phase0.gates.g0 import g0_4, g0_8
from sycophancy_phase0.gates.g0_runner import cross_stack, g04_inputs, g04_phase1, g04_phase2
from sycophancy_phase0.gates.g15 import continuation_specs
from sycophancy_phase0.stages import load_prefix_bank, load_problems


def test_g04_and_g08_plumbing(tmp_path):
    ctx, info = build_chain(str(tmp_path), run_id="G0X", n_problems=3)
    bank = load_problems(ctx)
    pres = [b for b in load_prefix_bank(ctx) if b.level == 2 and b.script == "A3"][:2]
    h2 = [(bank[b.problem_id], b.to_prefix()) for b in pres]
    p1 = g04_phase1(ctx, h2, n_y2=2, n_cont=4)
    assert len(p1["y2"]) == 2 * 2 * 2 and all(len(t.turns) == 2 and not t.arm.is_null for t in p1["y2"]) and len(p1["conts"]) == 8 * 4
    def text_path(msgs):
        t = ""
        for m in msgs:
            t += f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
        return encode(t + "<|im_start|>assistant\n")
    p2 = g04_phase2(ctx, h2, p1["y2"], text_path_ids=text_path, n_cont=4)
    assert p2["text_path_mismatch_rate"] == 0.0 and len(p2["conts"]) == 8 * 4
    inp = g04_inputs(p1, p2)
    assert inp["ids_identical"] and inp["greedy_identical"] and inp["e3_same_process"].shape == (32,) and len(set(inp["h2_cluster"])) == 2
    assert np.array_equal(inp["e3_same_process"], inp["e3_rebuilt"])        # fake engine is deterministic given ids+seed
    assert g0_4(**inp).passed
    specs = continuation_specs(bank, [b for b in load_prefix_bank(ctx) if b.level == 3][:2], ctx.run_id, n=6, idx0=64, block="est", scripts_for_a3=("A3",))
    ea, eb, cl = cross_stack(ctx, ctx, specs)
    assert ea.shape == eb.shape and np.array_equal(ea, eb) and g0_8(ea, eb, cl).passed
    budget = json.load(open(os.path.join(ctx.run_path, "tables", "budget.json"), encoding="utf-8"))
    assert "G1" in budget and budget["G1"]["null"]["generated"] > 0
