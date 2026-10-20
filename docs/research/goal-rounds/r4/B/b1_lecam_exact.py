"""r4 route B, claim B1: exact Le Cam two-point lower bounds for the G6 h_3 pilot (100 type-0 + 100 type-1 prefixes, m `sel`
counts each) between the narrow Beta world F_a = Beta(20,80)/Beta(25,75) and explicit failing worlds, at m in {32,128,512}.

Mathematics (derivation in b_derivation.md):
  * count law of one prefix of type t: p_F(k) = C(m,k) int r^k (1-r)^(m-k) dF_t(r);  for Beta(a,b) with rational a,b this is
    exactly rational: p(0) = (b)_m / (a+b)_m, p(k+1) = p(k) * (m-k)/(k+1) * (a+k)/(b+m-k-1)   (rising factorials);
    for a discrete F (atoms x_j, weights w_j) it is sum_j w_j Bin(k; m, x_j), exactly rational for rational atoms/weights.
  * Hellinger affinity rho(P,Q) = sum_k sqrt(p_k q_k) tensorises: rho(P^{(x)n0} (x) Q^{(x)n1}) = rho_0^n0 rho_1^n1.
  * TV(P,Q) <= sqrt(1 - rho^2)  (Cauchy-Schwarz);  for every randomized rule phi: E_a[1-phi] + E_b[phi] >= 1 - TV,
    with equality for the likelihood-ratio test phi = 1{p_a > p_b}.  Hence
        err_I + err_II  >=  1 - TV_exact  >=  1 - sqrt(1 - (rho_0^100 rho_1^100)^2).
  * Corollary: any rule with P_b(certify) <= gamma has P_a(certify) <= TV + gamma.
Exact arithmetic: pmfs as fractions.Fraction; affinities with mpmath at 60 significant digits from the exact fractions
(sqrt is the only irrational step).  The exact minimal error sum 1 - TV of the product law is estimated by Monte Carlo of the
likelihood-ratio statistic under both worlds (200000 pilots each side; SE reported).
Environment tag: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, mpmath 1.3.0, 4 cores, 2026-10-19.
Scratch only; nothing in the repository is modified."""
import json, sys, time
from fractions import Fraction as Fr
from math import comb
import numpy as np
import mpmath as mp

mp.mp.dps = 60
HERE = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/B__Le_Cam_two-point_impossibility_for_the_32-pilot_and_explicit_failing_worlds_inside_the_compatible_set__lower_bound__necessity_direction_"
OUT = HERE + "/b1_lecam_exact.json"
N_T = 100            # prefixes per type in the pilot
SEED = 20261019


# ----------------------------------------------------------------------------------------------------------- exact count laws
def rf(x: Fr, k: int) -> Fr:
    out = Fr(1)
    for i in range(k):
        out *= (x + i)
    return out


def betabinom_exact(m: int, a: Fr, b: Fr):
    """Exact rational Beta-binomial pmf via the ratio recursion; checked against the direct rising-factorial formula at k=0,m."""
    p = [Fr(0)] * (m + 1)
    p[0] = rf(b, m) / rf(a + b, m)
    for k in range(m):
        p[k + 1] = p[k] * Fr(m - k, k + 1) * (a + k) / (b + m - k - 1)
    assert sum(p) == 1, "pmf must sum to one exactly"
    assert p[m] == rf(a, m) / rf(a + b, m)
    return p


def mixture_exact(m: int, atoms, weights):
    p = [Fr(0)] * (m + 1)
    for x, w in zip(atoms, weights):
        for k in range(m + 1):
            p[k] += w * comb(m, k) * x ** k * (1 - x) ** (m - k)
    assert sum(p) == 1
    return p


def moments_exact(atoms, weights, order):
    return [sum(w * x ** j for x, w in zip(atoms, weights)) for j in range(order + 1)]


def beta_moments_exact(a: Fr, b: Fr, order):
    return [rf(a, j) / rf(a + b, j) for j in range(order + 1)]


def affinity(p, q) -> mp.mpf:
    return mp.fsum(mp.sqrt(mp.mpf(pi.numerator) / pi.denominator * (mp.mpf(qi.numerator) / qi.denominator)) for pi, qi in zip(p, q))


def tv1(p, q) -> Fr:
    return sum(abs(pi - qi) for pi, qi in zip(p, q)) / 2


def bound_from_rho(rho_total: mp.mpf):
    tv_upper = mp.sqrt(max(mp.mpf(0), 1 - rho_total ** 2))
    return tv_upper, 1 - tv_upper


# ----------------------------------------------------------------------------------------------------------- worlds
def beta_world(a0, b0, a1, b1):
    return dict(kind="beta", params=((Fr(a0), Fr(b0)), (Fr(a1), Fr(b1))))


def discrete_world(atoms0, w0, atoms1, w1):
    return dict(kind="discrete", params=(([Fr(x) for x in atoms0], [Fr(w) for w in w0]), ([Fr(x) for x in atoms1], [Fr(w) for w in w1])))


def pmf_of(world, t, m):
    if world["kind"] == "beta":
        a, b = world["params"][t]
        return betabinom_exact(m, a, b)
    atoms, w = world["params"][t]
    return mixture_exact(m, atoms, w)


def describe(world):
    if world["kind"] == "beta":
        return [f"Beta({float(a):g},{float(b):g})" for a, b in world["params"]]
    return [f"atoms {[str(x) for x in at]} weights {[str(x) for x in w]}" for at, w in world["params"]]


def theta_world(theta: Fr):
    """Same means 0.2 / 0.25 as F_a, within-type variance theta * V_a:  a+b+1 = 101/theta."""
    s = Fr(101) / theta - 1
    return beta_world(s / 5, 4 * s / 5, s / 4, 3 * s / 4)


F_A = beta_world(20, 80, 25, 75)
# two-point worlds with EXACTLY the mean and variance of F_a per type (derivation b_derivation.md, B3)
#   type 0: mu = 1/5, V = 4/2525 = (mu - x1)(x2 - mu) with x2 - mu = 1/25  ->  x1 = 81/505, w1 = 101/201
#   type 1: mu = 1/4, V = 3/1616, x2 - mu = 1/25 -> x1 = 329/1616, w1 = 1616/3491
F_C2 = discrete_world([Fr(81, 505), Fr(6, 25)], [Fr(101, 201), Fr(100, 201)],
                      [Fr(329, 1616), Fr(29, 100)], [Fr(1616, 3491), Fr(1875, 3491)])
WORLDS = {
    "F_b half-var Beta(40.5,162)/(50.6,151.8) [problem-phase anchor]": beta_world(Fr(81, 2), 162, Fr(253, 5), Fr(759, 5)),
    "F_c point mass 0.20/0.25 [literal 7.11 example]": discrete_world([Fr(1, 5)], [1], [Fr(1, 4)], [1]),
    "F_d double-var Beta(9.5,38)/(12,36)": beta_world(Fr(19, 2), 38, 12, 36),
    "F_c2 two-point, same (mu, V) as F_a per type": F_C2,
}
for th in (Fr(1, 2), Fr(3, 5), Fr(7, 10), Fr(4, 5), Fr(9, 10)):
    WORLDS[f"F_theta variance-scale theta={th} Beta(mu s,(1-mu)s), s=101/theta-1"] = theta_world(th)


# ----------------------------------------------------------------------------------------------------------- MC of the exact TV
def lr_test_error_sum(pa, pb, n_t, reps, rng):
    """Monte Carlo of the error sum of the likelihood-ratio test  phi = 1{sum log(p_a/p_b) > 0}  (both types, n_t each),
    which equals 1 - TV(P_a, P_b) up to ties (ties counted as 'not certify', giving an upper bound on the minimum)."""
    out = {}
    lr = [np.log(np.array([float(x) for x in pa[t]])) - np.log(np.array([float(x) for x in pb[t]])) for t in (0, 1)]
    def stat(world):
        s = np.zeros(reps)
        for t in (0, 1):
            pm = np.array([float(x) for x in world[t]])
            pm = pm / pm.sum()
            K = rng.choice(pm.size, size=(reps, n_t), p=pm)
            s += lr[t][K].sum(1)
        return s
    sa, sb = stat(pa), stat(pb)
    errI = float((sa <= 0).mean()); errII = float((sb > 0).mean())
    se = float(np.sqrt(errI * (1 - errI) / reps + errII * (1 - errII) / reps))
    return dict(reps=reps, err_I_LR=errI, err_II_LR=errII, err_sum_LR=errI + errII, mc_se=se,
                tv_exact_mc=1 - (errI + errII))


if __name__ == "__main__":
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    res = {"F_a": describe(F_A), "n_per_type": N_T, "seed": SEED,
           "environment": "CPU, python 3.13.16 x86_64, numpy %s, scipy 1.18.1, mpmath %s, 4 cores, 2026-10-19" % (np.__version__, mp.__version__)}
    # exact moments of the worlds (to document what the pairs share)
    mom = {"F_a": [[str(x) for x in beta_moments_exact(*F_A["params"][t], 4)] for t in (0, 1)]}
    for name, w in WORLDS.items():
        if w["kind"] == "beta":
            mom[name] = [[str(x) for x in beta_moments_exact(*w["params"][t], 4)] for t in (0, 1)]
        else:
            mom[name] = [[str(x) for x in moments_exact(*w["params"][t], 4)] for t in (0, 1)]
    res["exact_moments_mu1..mu4_per_type"] = mom
    res["pairs"] = {}
    for name, w in WORLDS.items():
        res["pairs"][name] = {"world": describe(w)}
        for m in (32, 128, 512):
            pa = [pmf_of(F_A, t, m) for t in (0, 1)]
            pb = [pmf_of(w, t, m) for t in (0, 1)]
            rho = [affinity(pa[t], pb[t]) for t in (0, 1)]
            rho_pilot = rho[0] ** N_T * rho[1] ** N_T
            tv_up_pilot, bound_pilot = bound_from_rho(rho_pilot)
            tv_up_t0, bound_t0 = bound_from_rho(rho[0] ** N_T)
            row = dict(m=m, affinity_1_type0=mp.nstr(rho[0], 12), affinity_1_type1=mp.nstr(rho[1], 12),
                       tv_1_type0=float(tv1(pa[0], pb[0])), tv_1_type1=float(tv1(pa[1], pb[1])),
                       rho_pilot_200=mp.nstr(rho_pilot, 12),
                       type0_only_n100=dict(tv_upper=mp.nstr(tv_up_t0, 8), err_sum_lower=mp.nstr(bound_t0, 8)),
                       both_types_n200=dict(tv_upper=mp.nstr(tv_up_pilot, 8), err_sum_lower=mp.nstr(bound_pilot, 8)),
                       availability_upper_TVplusgamma=dict({f"gamma={g}": mp.nstr(min(mp.mpf(1), tv_up_pilot + mp.mpf(g)), 6) for g in ("0.05", "0.10", "0.28")}))
            if (name.startswith("F_b") or name.startswith("F_c2")) and m in (32, 128, 512):
                row["lr_test_mc"] = lr_test_error_sum(pa, pb, N_T, 200000, rng)
            res["pairs"][name][f"m={m}"] = row
            print(f"{name} | m={m}: rho0={mp.nstr(rho[0], 9)} rho1={mp.nstr(rho[1], 9)}  type0-only err_sum>={mp.nstr(bound_t0, 5)}  "
                  f"BOTH TYPES err_sum>={mp.nstr(bound_pilot, 5)}  TV_upper={mp.nstr(tv_up_pilot, 5)}"
                  + (f"  LR-test MC err_sum={row['lr_test_mc']['err_sum_LR']:.4f} (SE {row['lr_test_mc']['mc_se']:.4f})" if "lr_test_mc" in row else ""), flush=True)
    res["elapsed_s"] = time.time() - t0
    json.dump(res, open(OUT, "w"), indent=1)
    print("elapsed", res["elapsed_s"])
