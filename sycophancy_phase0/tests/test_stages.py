"""End-to-end plumbing of the stage glue on the fake context with shrunk sizes."""
import json
import os

import numpy as np

from chain_fixture import build_chain
from sycophancy_phase0.stages import load_prefix_bank, stage_g1, stage_g2, stage_g2a
from sycophancy_phase0.trajectory import read_jsonl


def test_stage_chain(tmp_path):
    ctx, info = build_chain(str(tmp_path))
    assert info["mine"]["n_problems"] == 4 and info["mine"]["n_main"] >= 2
    mining = json.load(open(os.path.join(ctx.run_path, "data", "mining.json"), encoding="utf-8"))
    assert all(v["distractor"] in ("WRONG", None) for v in mining.values())
    assert set(info["pools"]["C"]) <= set(info["pools"]["main"])
    assert info["g1"]["n_trajs"] > 0 and os.path.exists(os.path.join(ctx.run_path, "tables", "G1_summary.json"))
    gates_md = open(os.path.join(ctx.run_path, "GATES.md"), encoding="utf-8").read()
    assert "## G1 — 校准 pilot" in gates_md and "Decision:" in gates_md and "## G1.5 — 前缀库" in gates_md
    n_before = sum(1 for _ in read_jsonl(os.path.join(ctx.run_path, "trajectories", "G1.jsonl")))
    stage_g1(ctx)                                                            # resume: nothing re-generated
    assert sum(1 for _ in read_jsonl(os.path.join(ctx.run_path, "trajectories", "G1.jsonl"))) == n_before
    bank = load_prefix_bank(ctx)
    assert info["g15"]["n_h2"] > 0 and any(b.level == 3 for b in bank) and all(b.stats for b in bank if b.level == 2)
    g2 = stage_g2(ctx, prebunk_texts={b.prefix_id: "GOLD 才对。WRONG 是错的。" for b in bank if b.script == "A3" and b.level == 2})
    assert g2["decision"] in ("GO", "GO-with-caveat")
    g2a = stage_g2a(ctx)
    assert g2a["decision"] in ("GO", "GO-with-caveat", "KILL") and np.isfinite(g2a["J"])
    s = json.load(open(os.path.join(ctx.run_path, "tables", "G2a_summary.json"), encoding="utf-8"))
    assert s["kappa1_is_placeholder"] and "testimony_uncorrected" in s
