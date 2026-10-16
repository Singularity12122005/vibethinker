"""G4-0 / G4-1 / G2′-b / G4-2 / G5 / G6 orchestration and estimators on fake-engine trajectories."""
import numpy as np

from fake_tok import encode, first_turn_ids, is_ws
from sycophancy_phase0.constants import ACTION_GRID, IM_END, SYSTEM_PROMPT
from sycophancy_phase0.data.pools import Pools
from sycophancy_phase0.gates.g1 import g1_specs
from sycophancy_phase0.gates.g15 import bank_stats, continuation_specs, h2_prefixes, select_h3
from sycophancy_phase0.gates.g2a import pick_prefixes, y2_specs
from sycophancy_phase0.gates.g2b import g2b_estimate, g2b_gate, g2b_specs, quarter_table
from sycophancy_phase0.gates.g40 import estimate_directions, persist, pick_h3, read_side_directions, turn3_specs
from sycophancy_phase0.gates.g41 import e3_drop_by_layer, layer_screen_specs, provisional_alpha_max, select_layer
from sycophancy_phase0.gates.g42 import beta_endpoints, dose_response_table, dose_specs, g42_decision, paired_rate_drop
from sycophancy_phase0.gates.g5 import g5_decision, g5_estimate, pick_pilot_prefixes, split_plot_specs
from sycophancy_phase0.gates.g5 import y2_specs as g5_y2_specs
from sycophancy_phase0.gates.g6 import g6_decision, g6_specs, matched_risk_interaction, per_prefix_curves, regret
from sycophancy_phase0.inference.engine import EngineRouter, FakeEngine
from sycophancy_phase0.inference.templates import TurnBuilder
from sycophancy_phase0.rollout import BankProblem, run_rollouts


def decode(ids):
    return "".join(chr(i - 1000) if i >= 1000 else ("\n\n" if i == 271 else "") for i in ids)


FT = lambda x: first_turn_ids(SYSTEM_PROMPT, x, "instruct")
IM_START = encode("<|im_start|>")[0]
USER = encode("user")
BUILDER = TurnBuilder(encode, "instruct", is_ws)
FOLDS = {f"F2-p{i:02d}": i % 5 for i in range(6)}


def make_bank(n=6):
    return {f"F2-p{i:02d}": BankProblem(problem_id=f"F2-p{i:02d}", family="F2", statement_zh=f"题{i}", gold="40", gold_type="integer",
                                        distractor="60", distractor2="50", modified_statement_zh=f"题{i}改", modified_gold="70",
                                        modification_note="改") for i in range(n)}


def responder(ids, seed, alpha, mnt):
    """Concession probability 0.45 at alpha = 0; negative alpha (anti-concession) lowers it, positive raises it;
    turn 1 correct; C updates; D accepts.  Lock-in after a concession."""
    n_user = sum(1 for i in range(len(ids)) if ids[i] == IM_START and ids[i + 1:i + 1 + len(USER)] == USER)
    txt = decode(ids)
    r = np.random.default_rng(seed)
    if n_user == 1:
        return encode(f"思路{seed % 997}\n最终答案：40") + [IM_END]
    if "修改一下题目条件" in txt:
        out = "最终答案：70" if n_user == 4 else "你说得对，答案是 70"
    elif "我认为应该是 40" in txt:
        out = "最终答案：40" if n_user == 4 else "你说得对，答案是 40"
    else:
        pc = float(np.clip(0.45 + 0.35 * alpha, 0.02, 0.98))
        conceded = "你说得对，答案是 60" in txt or r.random() < pc
        out = ("最终答案：60" if conceded else "最终答案：40") if n_user == 4 else ("你说得对，答案是 60" if conceded else f"答案仍然是 40（{seed % 97}）")
    return encode(out) + [IM_END]


def run(specs):
    eng = FakeEngine(responder)
    return run_rollouts(specs, builder=BUILDER, router=EngineRouter(eng, eng), first_turn_ids=FT, decode=decode)


def setup():
    bank = make_bank(6)
    pools = Pools(main=sorted(bank), D=[], D_nat=[], C=sorted(bank), excluded={})
    g1 = run(g1_specs(bank, pools, "r"))
    pres = h2_prefixes(bank, sorted(bank), g1, BUILDER, FT)
    conts = run(continuation_specs(bank, pres, "r", n=16, scripts_for_a3=("A3",)))
    bank_stats(pres, conts)
    h3 = [h for h in (select_h3(bp, conts, BUILDER, FT) for bp in pres if bp.script == "A3") if h is not None]
    return bank, pres, conts, h3


def test_g40_g41():
    bank, pres, conts, h3 = setup()
    picks = pick_h3(h3, FOLDS, n_per_fold=2)
    assert picks and all(p.level == 3 for p in picks)
    t3 = run(turn3_specs(bank, picks, "r", n=12))
    assert all(len(t.turns) == 3 for t in t3)
    rng = np.random.default_rng(0)
    D = 6
    true = rng.normal(size=D)
    acts = {20: np.array([(2 * true if t.turns[2].stance == "USER" else 0 * true) + 0.1 * rng.normal(size=D) for t in t3])}
    dirs = estimate_directions(acts, t3, FOLDS, n_folds=5, min_per_class=1)
    v = dirs["v_cap"][20][0]["v"]
    assert abs(v @ true / np.linalg.norm(true)) > 0.95 and set(dirs["v_cap_perp"][20]) == set(range(5))
    assert abs(dirs["v_cap_perp"][20][0]["v"] @ dirs["d_agree"][20][0]["v"]) < 1e-9
    rs = read_side_directions({"A3": (np.ones((3, D)), ["F2-p00", "F2-p01", "F2-p02"]), "B": (np.zeros((3, D)), ["F2-p00", "F2-p01", "F2-p02"])},
                              {"A3": (np.ones((3, D)), ["F2-p00", "F2-p01", "F2-p02"]), "D": ([], [])}, FOLDS)
    assert set(rs["v_press"]) == set(range(5)) and rs["v_warrant"] == {}
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        meta = persist(d, dirs)
        assert "v_cap_L20" in meta
    fine = {a: dict(kl=0.03 * a, flip=0.01 * a) for a in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)}
    assert provisional_alpha_max(fine) == 3.0
    screen = run(layer_screen_specs(bank, picks, "r", layer=20, alpha_max_L=1.0, n=8) + layer_screen_specs(bank, picks, "r", layer=24, alpha_max_L=0.2, n=8))
    drops = e3_drop_by_layer(screen, n_boot=100)
    assert set(drops) == {20, 24} and drops[20]["drop"] > drops[24]["drop"] and select_layer(drops) == 20


def test_g2b_and_g42():
    bank, pres, conts, h3 = setup()
    picks = pick_prefixes(pres, n=3, max_P_e2=1.1, q_range=(0.0, 1.0))
    y2 = run(y2_specs(bank, picks, "r", n=6))
    specs = g2b_specs(bank, y2, BUILDER, FT, "r", direction="v_cap_perp", layer=20, alpha_max=1.0, fold_of_problem=FOLDS, n_y2=4, n_per_arm=8)
    assert len(specs) == len(picks) * 4 * 5 * 8
    trajs = run(specs)
    p_hat, cost, prefix, _ = quarter_table(trajs)
    assert p_hat.shape[1:] == (5, 4) and not np.isnan(p_hat).any() and list(cost) == [1, 0.5, 0, 0.5, 1]
    est = g2b_estimate(trajs, n_boot=100)
    res, dec = g2b_gate(est)
    assert est["n_y2"] == len(picks) * 4 and dec in ("GO", "KILL")
    # G4-2 dose response: negative u (d = +1) lowers concession -> CE_4 higher at d = 1 than d = −1
    d42 = run(dose_specs(bank, h3[:4], "r", direction="v_cap_perp", layer=20, alpha_max=1.0, scope="S_gen", fold_of_problem=FOLDS, n=16))
    ba3 = beta_endpoints(d42, "A3", n_boot=200)
    assert ba3["beta"] > 0 and ba3["n_problems"] >= 1
    tab = dose_response_table(d42, "A3")
    assert set(tab) == {-1.0, -0.5, 0.0, 0.5, 1.0} and tab[1.0]["rate"] > tab[-1.0]["rate"]
    x4 = paired_rate_drop(d42, "A3", 1.0, 0.0, "x", n_boot=100)
    res, dec, notes = g42_decision(ba3, None, None, x4)
    assert res[0].name == "G4-2.axis" and dec in ("GO", "GREY") and abs(x4["est"]) < 1e-9


def test_g5_and_g6():
    bank, pres, conts, h3 = setup()
    pilot = pick_pilot_prefixes(pres, n_problems=2, per_problem=2)
    assert len(pilot) in (0, 2, 4)
    if not pilot:
        pilot = [p for p in pres if p.script == "A3"][:4]
    y2 = run(g5_y2_specs(bank, pilot, "r", u2_grid=(-1.0, 0.0, 1.0), direction="v", layer=20, alpha_max=1.0, fold_of_problem=FOLDS, k=8))
    assert all(len(t.turns) == 2 for t in y2) and {t.extra["u2"] for t in y2} == {-1.0, 0.0, 1.0}
    sp = split_plot_specs(bank, y2, BUILDER, FT, "r", u3_grid=(-1.0, 0.0, 1.0), direction="v", layer=20, alpha_max=1.0, fold_of_problem=FOLDS, c_pool=sorted(bank))
    assert len(sp) == len(y2) * 3 * 2
    trajs = run(sp)
    assert all(len(t.turns) == 4 for t in trajs) and {t.script for t in trajs} == {"A3", "C"}
    est = g5_estimate(trajs, None, n_boot=100)
    assert est["u3_star"] in (-1.0, 0.0, 1.0) and np.isfinite(est["G"]) and est["n_problems"] >= 1
    res, dec = g5_decision(est, var_c_lrt_p=0.5)
    assert dec in ("GO", "KILL", "GREY") and res[0].name == "G5.G"
    est_c = g5_estimate(trajs, est["u3_star"], n_boot=50, confirm=True)
    assert g5_decision(est_c, None, confirm=True)[1] in ("GO", "KILL", "GREY")
    # G6
    items = [(h, 1 if i % 2 == 0 else 2, 0.3 + 0.1 * (i % 3)) for i, h in enumerate(h3[:6])]
    g6 = run(g6_specs(bank, items, "r", direction="v", layer=20, alpha_max=1.0, fold_of_problem=FOLDS, n=16))
    inter = matched_risk_interaction(g6)
    assert "d1_x_type2" in inter["coef"] and 0 <= inter["interaction"]["p"] <= 1
    cf, ce = per_prefix_curves(g6, 0), per_prefix_curves(g6, 1)
    assert set(cf) == set(ce) and all(set(c["J"]) == {-1.0, -0.5, 0.0, 0.5, 1.0} for c in cf.values())
    reg = regret(cf, ce, n_boot=100)
    assert np.isfinite(reg["regret"]) and reg["n_prefix"] == len(items) and set(reg["u_star"]) == set(cf)
    res, dec, notes = g6_decision(inter, reg, x4_drop_hi=0.0)
    assert dec in ("GO", "KILL", "GREY") and len(res) == 3 and isinstance(notes, list)
