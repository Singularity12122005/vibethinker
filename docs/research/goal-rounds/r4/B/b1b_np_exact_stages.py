"""r4 route B, claim B1 supplement: exact (Neyman-Pearson) minimal error sums 1 - TV(P_a, P_b) of the two-type pilot by Monte
Carlo of the likelihood-ratio test, for the pairs that matter at each stage:
  32-stage : F_a vs F_b (anchor), F_c (point mass), F_c2 (two-point), F_lp (LP world of b3), F_theta 0.6..0.9;
  128-stage: F_a vs F_theta 0.6..0.9 and F_c2 at m=128;   512-stage: F_a vs F_theta 0.7..0.9 at m=512.
Also the availability bound TV + gamma (sup of P_a(certify) over rules with P_b(certify) <= gamma).  pmfs float64 (exact-form
Hellinger bounds for the Beta/rational worlds are in b1_lecam_exact.py).  200000 pilots per side; SE reported.
Environment tag: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19.  Scratch only."""
import json, sys, time
import numpy as np
from scipy import stats

HERE = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/B__Le_Cam_two-point_impossibility_for_the_32-pilot_and_explicit_failing_worlds_inside_the_compatible_set__lower_bound__necessity_direction_"
sys.path.insert(0, HERE)
import b2_failing_worlds_gclass as b2
from b3_dkw_band_lp import count_pmf

N_T, REPS, SEED = 100, 200000, 20261020
lw = json.load(open(HERE + "/b3_dkw_band_lp.json"))["lp_world"]["atoms_weights"]
WORLDS = {"F_b": b2.WORLDS["F_b"], "F_c point mass": b2.disc_w("pm", (0.2,), (1.0,), (0.25,), (1.0,)), "F_c2": b2.WORLDS["F_c2"],
          "F_lp": b2.disc_w("lp", tuple(lw[0][0]), tuple(lw[0][1]), tuple(lw[1][0]), tuple(lw[1][1])),
          "F_theta0.6": b2.WORLDS["F_theta0.6"], "F_theta0.7": b2.WORLDS["F_theta0.7"], "F_theta0.8": b2.WORLDS["F_theta0.8"], "F_theta0.9": b2.WORLDS["F_theta0.9"]}
PLAN = {32: list(WORLDS), 128: ["F_b", "F_c2", "F_lp", "F_theta0.6", "F_theta0.7", "F_theta0.8", "F_theta0.9"], 512: ["F_theta0.7", "F_theta0.8", "F_theta0.9"]}


def lr_mc(pa, pb, rng):
    lr = [np.log(pa[t]) - np.log(pb[t]) for t in (0, 1)]
    def stat(world):
        s = np.zeros(REPS)
        for t in (0, 1):
            K = rng.choice(world[t].size, size=(REPS, N_T), p=world[t] / world[t].sum())
            s += lr[t][K].sum(1)
        return s
    sa, sb = stat(pa), stat(pb)
    eI, eII = float((sa <= 0).mean()), float((sb > 0).mean())
    return dict(err_I=eI, err_II=eII, err_sum_NP=eI + eII, tv_exact=1 - eI - eII, mc_se=float(np.sqrt(eI * (1 - eI) / REPS + eII * (1 - eII) / REPS)))


if __name__ == "__main__":
    t0 = time.time(); rng = np.random.default_rng(SEED); out = dict(seed=SEED, reps=REPS, results={})
    for m, names in PLAN.items():
        pa = [count_pmf(b2.WORLDS["F_a"], t, m) for t in (0, 1)]
        for name in names:
            pb = [count_pmf(WORLDS[name], t, m) for t in (0, 1)]
            rho = [float(np.sum(np.sqrt(pa[t] * pb[t]))) for t in (0, 1)]
            rp = rho[0] ** N_T * rho[1] ** N_T
            r = lr_mc(pa, pb, rng)
            r["hellinger_err_sum_lower"] = float(1 - np.sqrt(max(0.0, 1 - rp ** 2)))
            r["availability_upper_TV_plus_gamma"] = {f"gamma={g}": min(1.0, r["tv_exact"] + g) for g in (0.05, 0.10, 0.28)}
            out["results"][f"F_a vs {name} | m={m}"] = r
            print(f"m={m:4d} F_a vs {name:16s}: Hellinger err_sum>={r['hellinger_err_sum_lower']:.4f}  NP err_sum={r['err_sum_NP']:.4f} (SE {r['mc_se']:.4f})  "
                  f"TV_exact={r['tv_exact']:.4f}  availability<=TV+0.05={r['availability_upper_TV_plus_gamma']['gamma=0.05']:.3f}", flush=True)
    out["elapsed_s"] = time.time() - t0
    json.dump(out, open(HERE + "/b1b_np_exact_stages.json", "w"), indent=1)
    print("elapsed", out["elapsed_s"])
