"""Direct coverage of G5 confirmation_F (plan §8.6 / §7.10): the F_80 formula receives (σ²_f,UB80, σ²_p, P, n, δ, p̄)."""
import numpy as np
import pytest

from sycophancy_phase0.analysis.power import F_required
from sycophancy_phase0.gates.g5 import confirmation_F
from sycophancy_phase0.trajectory import Arm, Trajectory


def _traj(i, pid, pre, u2, u3, ce3, ce4):
    return Trajectory(traj_id=f"t{i}", run_id="r", config_sha256="", model="M", regime="r", problem_id=pid, family="F2", script="A3",
                      prefix_id=pre, block="est", trajectory_idx=64 + i, subsplit=i % 2, arm=Arm.null(), seeds=[1, 2, 3, 4],
                      outcomes=dict(e=[0, 0, 1 - ce3, 1 - ce4], CE=[1, 1, ce3, ce4]), extra=dict(u2=u2, u3=u3, bank_prefix_id=pre))


def test_confirmation_F_formula_path():
    rng = np.random.default_rng(0)
    trajs, i = [], 0
    for pid in ("p0", "p1", "p2", "p3"):
        for pre in ("a", "b", "c"):
            p0 = 0.6 + 0.1 * rng.random()
            for u2 in (0.0, -1.0):
                p = p0 if u2 == 0.0 else p0 - 0.1
                for _ in range(16):
                    ce = int(rng.random() < p)
                    trajs.append(_traj(i, pid, pid + pre, u2, 1.0, ce, ce)); i += 1
    r = confirmation_F(trajs, u3_star=1.0, delta=0.05, n_cell=16)
    assert r["F_80"] is not None and np.isfinite(r["F_80"]) and r["F_80"] > 3 and r["P"] == 3 and r["n_problems_pilot"] == 4
    assert set(r["components"]) >= {"sigma_f2_ub80", "sigma_p2", "MS_f", "MS_p", "se2_tau"} and 0 < r["pbar"] < 1
    c = r["components"]
    assert r["F_80"] == pytest.approx(F_required(c["sigma_f2_ub80"], c["sigma_p2"], 3, 16, 0.05, r["pbar"]))      # exact argument order
    assert c["sigma_f2_ub80"] > c["sigma_f2"] and r["F_80"] != pytest.approx(F_required(c["sigma_f2"], c["sigma_p2"], 3, 16, 0.05, r["pbar"]))
    assert r["F_80"] != pytest.approx(F_required(c["sigma_p2"], c["sigma_f2_ub80"], 3, 16, 0.05, r["pbar"]))       # swapped variances differ
    # too few paired prefixes per problem => explicitly undefined
    assert confirmation_F([t for t in trajs if t.extra["bank_prefix_id"].endswith("a")], 1.0)["F_80"] is None
