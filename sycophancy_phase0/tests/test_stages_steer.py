"""Plumbing of the steering-dependent stages on the fake context (activations/calibration supplied synthetically)."""
import json
import os

import numpy as np

from chain_fixture import build_chain
from sycophancy_phase0.gates.g41 import alpha_max_entry
from sycophancy_phase0.stages import load_prefix_bank, stage_g2a
from sycophancy_phase0.stages_steer import g6_items, stage_g2b, stage_g3, stage_g40, stage_g41, stage_g42, stage_g5, stage_g6


def test_steer_stages(tmp_path):
    ctx, info = build_chain(str(tmp_path), run_id="STEER")
    rng = np.random.default_rng(0)
    D = 8
    # G3 with synthetic features aligned to the bank rows
    pres = load_prefix_bank(ctx)
    n = sum(1 for b in pres if b.level == 2 and b.script in ("A3", "B") and b.script in b.stats and b.stats[b.script]["est"].get("n", 0) > 0)
    feats = dict(logits_top50=rng.normal(size=(n, 5)), suffix_ratio=rng.normal(size=n), z={"R1_L8": rng.normal(size=(n, D))})
    ctx.config["n_boot"], ctx.config["n_perm"] = 50, 5
    g3 = stage_g3(ctx, features=feats)
    assert g3["decision"] in ("GO", "GO-with-caveat", "KILL") and os.path.exists(os.path.join(ctx.run_path, "tables", "G3_summary.json"))
    # G4-0 with a synthetic activation function (stance-separated)
    def acts_fn(items):
        return {20: np.stack([rng.normal(size=D) for _ in items])}
    g40 = stage_g40(ctx, acts_fn=acts_fn)
    assert g40["n_trajs"] > 0 and os.path.isdir(os.path.join(ctx.run_path, "configs", "directions"))
    # G4-1 with synthetic fine-grid statistics and a finish() stub
    fine = {L: {a: dict(kl=0.02 * a, flip=0.01 * a) for a in (0.5, 1.0, 1.5, 2.0)} for L in (16, 20)}
    finish = lambda L: {d: alpha_max_entry(d, L, 0, 1.0, 12.0, fine[L], None, dict(stub=True)) for d in ("v_cap", "v_cap_perp", "v_warrant")}
    g41 = stage_g41(ctx, fine, finish=finish)
    assert g41["L_star"] in (16, 20) and os.path.exists(os.path.join(ctx.run_path, "configs", "alpha_max.json"))
    # G2'-a y_2 are needed by G2'-b; the smoke bank has 4 sel draws per h_2, so loosen the P̂(e_2) screen (plan default 0.1)
    ctx.config["g2a_max_P_e2"] = 0.3
    assert stage_g2a(ctx)["n_prefix"] > 0
    g2b = stage_g2b(ctx)
    assert g2b["decision"] in ("GO", "KILL")
    g42 = stage_g42(ctx)
    assert g42["decision"] in ("GO", "GO-with-caveat", "GREY") and np.isfinite(g42["beta_A3"])
    ctx.config["g5_max_P_e2"] = 0.3                                   # smoke bank: 4 sel draws per h_2 (plan default 0/32)
    g5 = stage_g5(ctx)
    assert g5["decision"] in ("GO", "KILL", "GREY") and g5["u3_star"] in (-1.0, 0.0, 1.0)
    g5c = stage_g5(ctx, confirm=True, u3_star=g5["u3_star"], F=2)
    assert g5c["decision"] in ("GO", "KILL", "GREY")
    items = g6_items(ctx, n_per_type=2)
    if items:
        g6 = stage_g6(ctx, items)
        assert g6["decision"] in ("GO", "GO-with-caveat", "GREY")
    gates_md = open(os.path.join(ctx.run_path, "GATES.md"), encoding="utf-8").read()
    for g in ("## G3 —", "## G4-0 —", "## G4-1 —", "## G2′-b —", "## G4-2 —", "## G5-pilot —", "## G5-confirm —"):
        assert g in gates_md
