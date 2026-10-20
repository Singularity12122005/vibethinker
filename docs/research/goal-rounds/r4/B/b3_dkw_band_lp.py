"""r4 route B, claim B3: the stated compatible set C_gamma^DKW of a narrow pilot (100 type-t counts at m=32; DKW-Massart band
sup_k |G_hat_t(k) - G_F,t(k)| <= eps_n(gamma) = sqrt(ln(2/gamma)/(2n)), valid for any F incl. discrete) contains the failing
worlds with high probability, and an LP over grid mixtures inside the band exhibits a compatible F whose A1 Schur mean
E[S_w(128)] is NOT positive definite (margin < 0 in the weak direction) -- a lower bound on the sup of the failure over
C_gamma, not a claim that the extreme point is attained.
(a) Monte Carlo over 5000 narrow pilots: inclusion frequency of F_b (half-var), F_c (point mass), F_c2 (two-point), F_d
    (double-var) and of F_a itself (coverage) at gamma in {0.05, 0.10, 0.28}.
(b) For one seeded pilot: LP  min_w  v' E[S_t(128)] v  over w in simplex on the grid x_j = j/400, with the DKW band and the
    pilot's (or the true) first two moments fixed (so the objective is affine in (mu_3, mu_4), hence linear in w);
    v = eigenvector of lambda_min of the pooled E[S_w(128)] at F_a.  Also the LP range of the within-type variance
    V = mu_2 - mu_1^2 over the band with mu_1 fixed (the pilot's confidence interval for V in the DKW sense).
(c) Production test (endpoint_contrast_poly_cs, degree 2, HC1 / CR1) at the LP world, m in {128, 512}, archive linear g,
    2000 reps, via b2_failing_worlds_gclass.run_cell; plus the exact-form Le Cam affinity of the LP world vs F_a.
Environment tag: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19.  Scratch only."""
import json, sys, time
from fractions import Fraction as Fr
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from scipy import stats
from scipy.optimize import linprog
from sycophancy_phase0.analysis.g6_iv import binomial_factorial_joint_moment, corrected_schur_mean

HERE = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/B__Le_Cam_two-point_impossibility_for_the_32-pilot_and_explicit_failing_worlds_inside_the_compatible_set__lower_bound__necessity_direction_"
sys.path.insert(0, HERE)
import b2_failing_worlds_gclass as b2

OUT = HERE + "/b3_dkw_band_lp.json"
M_PILOT, N_T, SEED, N_PILOTS = 32, 100, 777, 5000
GAMMAS = (0.05, 0.10, 0.28)


def eps_dkw(n, gamma):
    return float(np.sqrt(np.log(2.0 / gamma) / (2.0 * n)))


def count_pmf(world, t, m):
    """float64 count law of one prefix (Beta-binomial or grid mixture); exact-form checks are in b1."""
    k = np.arange(m + 1)
    if world["kind"] == "beta":
        a, b = world["p"][t]
        return stats.betabinom.pmf(k, m, a, b)
    at, w = world["p"][t]
    w = np.asarray(w, float) / np.sum(w)
    return np.array([np.sum(w * stats.binom.pmf(kk, m, np.asarray(at, float))) for kk in k])


def U(K, j, m):
    out = np.ones_like(K, float)
    for i in range(j):
        out *= (K - i) / (m - i)
    return out


def pilot_moment_estimates(K, m, order=4):
    """Unbiased U-statistic estimates mu_j = mean_i U_j(K_i) (A1 / P2(b))."""
    return [1.0] + [float(U(K, j, m).mean()) for j in range(1, order + 1)]


# ----------------------------------------------------------------------------------------------------------- (a) inclusion MC
def inclusion_mc(rng):
    worlds = {"F_a (coverage)": b2.WORLDS["F_a"], "F_b half-var": b2.WORLDS["F_b"], "F_c2 two-point": b2.WORLDS["F_c2"],
              "F_c point mass": b2.disc_w("point mass", (0.2,), (1.0,), (0.25,), (1.0,)), "F_d double-var": b2.beta_w(9.5, 38.0, 12.0, 36.0),
              "F_theta0.7": b2.WORLDS["F_theta0.7"], "F_theta0.8": b2.WORLDS["F_theta0.8"]}
    cdfs = {name: [np.cumsum(count_pmf(w, t, M_PILOT)) for t in (0, 1)] for name, w in worlds.items()}
    ks = np.arange(M_PILOT + 1)
    sup = {name: np.zeros((N_PILOTS, 2)) for name in worlds}
    for i in range(N_PILOTS):
        for t in (0, 1):
            r = b2.draw_r(rng, b2.WORLDS["F_a"], t)
            K = rng.binomial(M_PILOT, r)
            Ghat = np.cumsum(np.bincount(K, minlength=M_PILOT + 1)) / N_T
            for name in worlds:
                sup[name][i, t] = np.max(np.abs(Ghat - cdfs[name][t]))
    out = {}
    for name in worlds:
        d = {}
        for g in GAMMAS:
            e = eps_dkw(N_T, g)
            inc = (sup[name] <= e).all(1)
            d[f"gamma={g}"] = dict(eps=e, P_in_band_both_types=float(inc.mean()), P_in_band_type0=float((sup[name][:, 0] <= e).mean()))
        d["sup_dist_true_count_cdfs_vs_F_a"] = [float(np.max(np.abs(cdfs[name][t] - cdfs["F_a (coverage)"][t]))) for t in (0, 1)]
        out[name] = d
    return out


# ----------------------------------------------------------------------------------------------------------- (b) LP inside the band
def schur_direction_coeffs(m, n_t):
    """v' E[S(m)] v = sum_ab v_a v_b [mu_{a+b} - mu_a mu_b - (E[U_a U_b] - mu_a mu_b)/n_t];  E[U_a U_b] = sum_j c_abj mu_j (linear).
    Returns c[(a,b)] as arrays over j=0..4 (exact fractions as floats)."""
    c = {}
    for a in (1, 2):
        for b in (1, 2):
            row = np.zeros(5)
            for j in range(5):
                e = [Fr(0)] * 5; e[j] = Fr(1)
                row[j] = float(binomial_factorial_joint_moment(e, m, a, b))
            c[(a, b)] = row
    return c


def lp_min_direction(Ghat, mu1, mu2, v, eps, m_target, n_t, grid):
    """min over w (simplex on grid) of v'E[S(m_target)]v with mu_1, mu_2 fixed, DKW band |CDF_w(k) - Ghat(k)| <= eps at m=32."""
    B = stats.binom.pmf(np.arange(M_PILOT + 1)[:, None], M_PILOT, grid[None, :])     # [k, j]
    C = np.cumsum(B, 0)[:-1]                                                            # CDF at k=0..31
    A_ub = np.vstack([C, -C]); b_ub = np.concatenate([Ghat[:-1] + eps, -(Ghat[:-1] - eps)])
    A_eq = np.vstack([np.ones_like(grid), grid, grid ** 2]); b_eq = np.array([1.0, mu1, mu2])
    coeffs = schur_direction_coeffs(m_target, n_t)
    mu_fixed = {0: 1.0, 1: mu1, 2: mu2}
    # objective: affine in (mu_3, mu_4) -> linear in w via mu_j = sum_j grid^j w
    lin3 = lin4 = const = 0.0
    for a in (1, 2):
        for b in (1, 2):
            vv = v[a - 1] * v[b - 1]
            cab = coeffs[(a, b)]
            # mu_{a+b} term
            if a + b == 3: lin3 += vv
            elif a + b == 4: lin4 += vv
            else: const += vv * mu_fixed[a + b]
            const += -vv * mu_fixed[a] * mu_fixed[b] * (1 - 1.0 / n_t)
            # -(1/n_t) sum_j c_abj mu_j
            for j in range(5):
                term = -vv * cab[j] / n_t
                if j == 3: lin3 += term
                elif j == 4: lin4 += term
                else: const += term * mu_fixed[j]
    cost = lin3 * grid ** 3 + lin4 * grid ** 4
    res = linprog(cost, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=(0, None), method="highs")
    if not res.success:
        return dict(success=False, message=res.message)
    w = res.x
    keep = w > 1e-10
    return dict(success=True, value=float(res.fun + const), atoms=grid[keep].tolist(), weights=(w[keep] / w[keep].sum()).tolist(),
                n_atoms=int(keep.sum()))


def lp_range_V(Ghat, mu1, eps, grid):
    B = stats.binom.pmf(np.arange(M_PILOT + 1)[:, None], M_PILOT, grid[None, :])
    C = np.cumsum(B, 0)[:-1]
    A_ub = np.vstack([C, -C]); b_ub = np.concatenate([Ghat[:-1] + eps, -(Ghat[:-1] - eps)])
    A_eq = np.vstack([np.ones_like(grid), grid]); b_eq = np.array([1.0, mu1])
    out = {}
    for sgn, lab in ((1, "min"), (-1, "max")):
        res = linprog(sgn * grid ** 2, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=(0, None), method="highs")
        out[lab] = float(sgn * res.fun - mu1 ** 2) if res.success else None
    return out


if __name__ == "__main__":
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    res = dict(environment="CPU, python 3.13.16 x86_64, numpy %s, scipy 1.18.1, 4 cores, 2026-10-19" % np.__version__, seed=SEED,
               n_pilots=N_PILOTS, eps_dkw={f"gamma={g}": eps_dkw(N_T, g) for g in GAMMAS})
    res["inclusion"] = inclusion_mc(rng)
    for name, d in res["inclusion"].items():
        print("INCL", name, json.dumps(d), flush=True)
    # ---- (b) one seeded pilot
    grid = np.arange(1, 400) / 400.0
    pilot = {}
    pilots_K = {}
    for t in (0, 1):
        r = b2.draw_r(rng, b2.WORLDS["F_a"], t)
        K = rng.binomial(M_PILOT, r)
        pilots_K[t] = K
        pilot[t] = dict(Ghat=np.cumsum(np.bincount(K, minlength=M_PILOT + 1)) / N_T, mu_hat=pilot_moment_estimates(K, M_PILOT))
    # weak direction: eigenvector of lambda_min of pooled E[S_w(128)] at F_a
    S_a = np.zeros((2, 2))
    for t in (0, 1):
        S_a += 0.5 * np.array(corrected_schur_mean(128, 2, b2.world_moments(b2.WORLDS["F_a"], t, 4), N_T), float)
    ev, V = np.linalg.eigh(S_a)
    v = V[:, 0]
    res["weak_direction_v"] = v.tolist(); res["F_a_pooled_E_S_128_eigs"] = ev.tolist()
    res["lp"] = {}
    for gamma in (0.05, 0.28):
        eps = eps_dkw(N_T, gamma)
        for which in ("pilot_moments", "true_moments"):
            entry = {}
            pooled_val = 0.0
            lp_world_atoms, lp_world_w = [], []
            for t in (0, 1):
                mu_true = b2.world_moments(b2.WORLDS["F_a"], t, 4)
                mu1, mu2 = (pilot[t]["mu_hat"][1], pilot[t]["mu_hat"][2]) if which == "pilot_moments" else (mu_true[1], mu_true[2])
                lp = lp_min_direction(pilot[t]["Ghat"], mu1, mu2, v, eps, 128, N_T, grid)
                vr = lp_range_V(pilot[t]["Ghat"], mu1, eps, grid)
                true_val = float(v @ np.array(corrected_schur_mean(128, 2, mu_true, N_T), float) @ v)
                entry[f"type{t}"] = dict(mu1_used=mu1, mu2_used=mu2, V_used=mu2 - mu1 ** 2, V_true=mu_true[2] - mu_true[1] ** 2,
                                         lp=lp, v_S_v_at_F_a=true_val, V_range_in_band_mu1_fixed=vr)
                if lp["success"]:
                    pooled_val += 0.5 * lp["value"]; lp_world_atoms.append(lp["atoms"]); lp_world_w.append(lp["weights"])
            entry["pooled_v_S_v_min"] = pooled_val
            entry["pooled_v_S_v_at_F_a"] = float(ev[0])
            res["lp"][f"gamma={gamma}|{which}"] = entry
            print(f"LP gamma={gamma} {which}: pooled v'E[S_w(128)]v min = {pooled_val:.3e} (F_a: {ev[0]:.3e});",
                  {f"type{t}": (entry[f'type{t}']['lp'].get('value'), entry[f'type{t}']['lp'].get('n_atoms'), entry[f'type{t}']['V_range_in_band_mu1_fixed']) for t in (0, 1)}, flush=True)
            if which == "true_moments" and gamma == 0.05 and len(lp_world_atoms) == 2:
                # ---- (c) production test at the LP world
                name = "F_lp"
                b2.WORLDS[name] = b2.disc_w("LP world (DKW gamma=0.05, true mu1,mu2, min v'Sv)", tuple(lp_world_atoms[0]), tuple(lp_world_w[0]),
                                            tuple(lp_world_atoms[1]), tuple(lp_world_w[1]))
                pop = dict(D=b2.identification_D(b2.WORLDS[name]), pd_margin={f"m={m}": b2.pd_margin_schur(b2.WORLDS[name], m) for m in (32, 128, 512)})
                # Le Cam affinity vs F_a (float64 pmfs; exact-form bounds for the named worlds are in b1)
                lecam = {}
                for m in (32, 128, 512):
                    rho = [float(np.sum(np.sqrt(count_pmf(b2.WORLDS["F_a"], t, m) * count_pmf(b2.WORLDS[name], t, m)))) for t in (0, 1)]
                    rp = rho[0] ** N_T * rho[1] ** N_T
                    lecam[f"m={m}"] = dict(rho0=rho[0], rho1=rho[1], err_sum_lower_both_types=float(1 - np.sqrt(max(0.0, 1 - rp ** 2))))
                cells = {}
                for m in (128, 512):
                    cells[f"m={m}"] = b2.run_cell((name, "g1 archive linear 0.18-0.8r", m, 99991 + m))
                    c = cells[f"m={m}"]
                    print(f"LP-world test m={m}: nonPD={c['non_pd']:.4f} {c['non_pd_ci95']} HC1 size={c['HC1']['size_uncond']:.4f} w|ok={c['HC1']['width_q10_50_90_given_ok']} "
                          f"q90all={c['HC1']['width_q90_all_inf_for_nonpd']} {c['HC1']['verdict']} | CR1 size={c['CR1']['size_uncond']:.4f} {c['CR1']['verdict']}", flush=True)
                res["lp_world"] = dict(label=b2.WORLDS[name]["label"], atoms_weights=b2.WORLDS[name]["p"], population=pop, lecam_vs_F_a=lecam, cells=cells)
                print("LP-world population", json.dumps(pop), "lecam", json.dumps(lecam), flush=True)
    res["pilot_counts"] = {f"type{t}": pilots_K[t].tolist() for t in (0, 1)}
    res["pilot_mu_hat"] = {f"type{t}": pilot[t]["mu_hat"] for t in (0, 1)}
    res["elapsed_s"] = time.time() - t0
    json.dump(res, open(OUT, "w"), indent=1)
    print("elapsed", res["elapsed_s"])
