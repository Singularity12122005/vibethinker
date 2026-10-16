import numpy as np

from sycophancy_phase0.scoring.human_validation import agreement_report, candidate_rows, cohen_kappa, stratified_sample
from sycophancy_phase0.trajectory import Arm, Trajectory, TurnRecord


def _traj(i, script, steered, stances, explicits):
    arm = Arm(u=[0, 0, -1, 0], direction="v", layer=20, alpha_max=0.5, scope="S_gen", fold_version=0) if steered else Arm.null()
    turns = [TurnRecord(t=t, user_text="x", ids_len_before=10, user_span=[1, 2], assistant_ids=[5, 151645], think_ids=None, assistant_text=f"y{t}",
                        finish_reason="stop", ended_with_endoftext=False, n_new_tokens=2, stance=st, explicit=ex,
                        judge=(dict(model="J1", raw="{}", parse_error=False, stance=st, explicit=ex) if t in (2, 3) else None))
             for t, (st, ex) in enumerate(zip(stances, explicits), start=1)]
    return Trajectory(traj_id=f"t{i}", run_id="r", config_sha256="", model="M", regime="r", problem_id=f"p{i % 7}", family="F2", script=script,
                      prefix_id="pf", block="est", trajectory_idx=i, subsplit=0, arm=arm, seeds=[1, 2, 3, 4], turns=turns)


def test_sampling_and_agreement():
    rng = np.random.default_rng(0)
    trajs = []
    for i in range(400):
        st = [rng.choice(["USER", "ORIG", "OTHER", "NONE"], p=[0.3, 0.5, 0.1, 0.1]) for _ in range(4)]
        ex = [rng.choice(["EXPLICIT", "HEDGED", "EVASIVE"], p=[0.8, 0.1, 0.1]) for _ in range(4)]
        trajs.append(_traj(i, rng.choice(["A3", "B", "D"]), i % 2 == 1, st, ex))
    rows = candidate_rows(trajs)
    assert len(rows) == 800 and all(r["turn"] in (2, 3) for r in rows)
    sample = stratified_sample(rows, n_per_arm_type=100)
    assert 150 <= len(sample) <= 260
    hedged_share_pool = np.mean([r["explicit"] in ("HEDGED", "EVASIVE") for r in rows])
    hedged_share_sample = np.mean([r["explicit"] in ("HEDGED", "EVASIVE") for r in sample])
    assert hedged_share_sample > hedged_share_pool                    # over-sampled
    assert abs(sum(r["steered"] for r in sample) - sum(not r["steered"] for r in sample)) < 40
    judge = [r["stance"] for r in sample]
    h1 = [s if rng.random() < 0.9 else "OTHER" for s in judge]
    h2 = [s if rng.random() < 0.9 else "OTHER" for s in judge]
    rep = agreement_report(sample, h1, h2)
    assert rep["n"] == len(sample) and 0.5 < rep["kappa_overall"] <= 1.0 and rep["ppi_switch"] is not None
    assert "steered" in rep["by_arm"] and rep["by_arm"]["steered"]["specificity"][0] > 0.8
    assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0 and abs(cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"])) < 1e-12
