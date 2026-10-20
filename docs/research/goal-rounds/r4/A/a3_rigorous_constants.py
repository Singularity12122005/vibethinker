"""r4 / Route A, claim 3: the EXPLICIT-CONSTANT finite-sample branch of the certificate is vacuous at the G6 pilot size
(n_t = 100 prefixes per type, m = 32), in all three worlds, for the natural exact constructions:

(i)  Hoeffding moment box.  U_j(K) in [0,1] so each per-type moment estimate mu_hat_{j,t} (mean of n_t iid bounded terms) satisfies
     P(|mu_hat - mu| >= eps) <= 2 exp(-2 n_t eps^2); Bonferroni over 2 types x 8 orders at gamma = 0.05 gives eps_H.  The box
     contains the two-point-mass moment vector theta* (mu_{j,t} = mu_hat_{1,t}^j) whenever max_{t,j} |mu_hat_{j,t} - mu_hat_{1,t}^j| <= eps_H;
     theta* has Var(r|t) = 0 for both types with distinct means, hence D(theta*) = 0 (type is an exact affine function of r) and
     first-order width = infinity.  So inf_{C_H} D = 0 and sup_{C_H} w_1 = infinity: the exact box certificate can never fire for any
     d_0 > 0 or finite w_0.  Checked on 5000 simulated pilots per world (fraction of pilots whose box contains theta*).
(ii) DKW band on the per-type COUNT CDF (eps_D = sqrt(ln(2/gamma')/(2 n_t)), gamma' = 0.025 per type): numerical search for a
     two-point-per-type world with D = 0 (supports {a, b} / {c, d} with a + b = c + d, so that a quadratic separates the types
     exactly) whose Beta-free binomial-mixture count CDFs lie inside the pilot's DKW bands.  Reported per world on 20 pilots:
     fraction of pilots in whose DKW set a D = 0 world was found (a found world proves inf D = 0 for that pilot; not finding
     one proves nothing).
(iii) Matrix Bernstein for the corrected moment matrix: n needed so that P(||A_bar - Q|| >= lambda_min(Q)) <= 0.02, with the crude
     bound R = 8 and with the exact sigma^2 = ||E(M_hat - Q)^2|| / n from the A1 joint moments (computed by enumeration over K),
     and the whitened version (Q^{-1/2} scaling).  Compared with n = 200.
Environment: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy import stats
from scipy.optimize import minimize
from scipy.special import betaln, gammaln
from route_a_lib import U_matrix, beta_moments, overlap_D, pilot_theta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "a3_rigorous_constants.json")
WORLDS = {"narrow": ((20, 80), (25, 75)), "halfvar": ((40.5, 162.0), (50.6, 151.8)), "wide": ((2, 8), (2.5, 7.5))}
N_T, M, GAMMA = 100, 32, 0.05


def hoeffding_check(rng, types, pilots=5000):
    eps16 = np.sqrt(np.log(2 * 16 / GAMMA) / (2 * N_T))     # 16 moment bounds (2 types x orders 1..8)
    eps4 = np.sqrt(np.log(2 * 4 / GAMMA) / (2 * N_T))       # only orders 1, 2 per type
    inside16, inside4, maxdev = 0, 0, []
    for _ in range(pilots):
        dev = []
        for ab in types:
            K = rng.binomial(M, rng.beta(*ab, N_T))
            Um = U_matrix(K, M, 8).mean(0)
            dev.append(np.abs(Um - Um[0] ** np.arange(1, 9)))
        dev = np.array(dev)
        maxdev.append(dev.max())
        inside16 += dev.max() <= eps16
        inside4 += dev[:, :2].max() <= eps4
    return dict(eps_H_16=float(eps16), eps_H_4=float(eps4), pilots=pilots,
                frac_box16_contains_pointmass_world=inside16 / pilots, frac_box4_contains_pointmass_world=inside4 / pilots,
                max_over_pilots_of_max_dev=float(np.max(maxdev)))


def betabinom_cdf(m, a, b):
    k = np.arange(m + 1)
    pmf = np.exp(gammaln(m + 1) - gammaln(k + 1) - gammaln(m - k + 1) + betaln(k + a, m - k + b) - betaln(a, b))
    return np.cumsum(pmf)


def dkw_search(rng, types, pilots=20, restarts=12):
    """For each pilot: minimise over (a, b, pa, c, pc) with d = a + b - c the max over types of the sup-distance between the
    two-point binomial-mixture count CDF and the empirical count CDF; success if the minimum <= eps_D."""
    eps = np.sqrt(np.log(2 / (GAMMA / 2)) / (2 * N_T))
    ks = np.arange(M + 1)
    found, dists = 0, []
    for _ in range(pilots):
        ecdfs = []
        for ab in types:
            K = rng.binomial(M, rng.beta(*ab, N_T))
            ecdfs.append(np.array([(K <= k).mean() for k in ks]))

        def obj(z):
            a, b, pa, c, pc = z
            d = a + b - c
            if not (0 < a < 1 and 0 < b < 1 and 0 < c < 1 and 0 < d < 1 and 0 < pa < 1 and 0 < pc < 1):
                return 10.0
            cdf0 = pa * stats.binom.cdf(ks, M, a) + (1 - pa) * stats.binom.cdf(ks, M, b)
            cdf1 = pc * stats.binom.cdf(ks, M, c) + (1 - pc) * stats.binom.cdf(ks, M, d)
            return max(np.abs(cdf0 - ecdfs[0]).max(), np.abs(cdf1 - ecdfs[1]).max())

        best = 10.0
        for _ in range(restarts):
            z0 = np.array([rng.uniform(0.02, 0.5), rng.uniform(0.02, 0.6), rng.uniform(0.2, 0.8), rng.uniform(0.02, 0.5), rng.uniform(0.2, 0.8)])
            res = minimize(obj, z0, method="Nelder-Mead", options=dict(maxiter=4000, xatol=1e-6, fatol=1e-7))
            best = min(best, res.fun)
        dists.append(best)
        found += best <= eps
    return dict(eps_DKW_per_type=float(eps), pilots=pilots, frac_pilots_with_D0_world_inside_band=found / pilots,
                min_sup_distance_q0_50_100=[float(np.min(dists)), float(np.median(dists)), float(np.max(dists))])


def matrix_bernstein(types, m, n=200, alpha=0.02):
    """Q = E[x* x*'], E(M_hat - Q)^2 by enumeration over K (exact Beta-binomial weights); n needed for
    P(||A_bar - Q|| >= lambda_min(Q)) <= alpha via  d exp(-(s^2/2)/(sigma_1^2 + R s/3)) with sigma_1^2 = ||E(M-Q)^2||,
    s = lambda_min(Q), in the scale of a single summand (bound for the mean of n terms: d exp(-n (s^2/2)/(sigma_1^2 + R s/3)))."""
    ks = np.arange(m + 1)
    Q = np.zeros((4, 4)); E2 = np.zeros((4, 4)); Rmax = 0.0
    mats = []
    for t, ab in enumerate(types):
        pmf = np.exp(gammaln(m + 1) - gammaln(ks + 1) - gammaln(m - ks + 1) + betaln(ks + ab[0], m - ks + ab[1]) - betaln(*ab))
        U = np.c_[np.ones(m + 1), U_matrix(ks, m, 4)]        # U_0..U_4 for each K
        for i, k in enumerate(ks):
            Mh = np.zeros((4, 4))
            for a in range(3):
                for b in range(3):
                    Mh[a, b] = U[i, a + b]
                Mh[a, 3] = Mh[3, a] = U[i, a] * t
            Mh[3, 3] = t
            mats.append((0.5 * pmf[i], Mh))
    Q = sum(w * Mh for w, Mh in mats)
    for w, Mh in mats:
        Dm = Mh - Q
        E2 += w * Dm @ Dm
        Rmax = max(Rmax, np.linalg.norm(Dm, 2))
    lam = np.linalg.eigvalsh(Q)
    s = lam[0]
    sig2 = np.linalg.norm(E2, 2)
    d = 4

    def n_needed(sig2, R, s):
        return float(np.log(d / alpha) * (sig2 + R * s / 3) / (s ** 2 / 2))

    # whitened version: X = Q^{-1/2} (M - Q) Q^{-1/2}, need ||mean X|| < 1 for PD
    w_, V = np.linalg.eigh(Q)
    Qih = V @ np.diag(w_ ** -0.5) @ V.T
    E2w = np.zeros((4, 4)); Rw = 0.0
    for w, Mh in mats:
        Xw = Qih @ (Mh - Q) @ Qih
        E2w += w * Xw @ Xw
        Rw = max(Rw, np.linalg.norm(Xw, 2))
    return dict(lambda_min_Q=float(s), lambda_max_Q=float(lam[-1]), sigma1_sq=float(sig2), R_exact=float(Rmax),
                n_needed_crude_R8=n_needed(sig2, 8.0, s), n_needed_exact=n_needed(sig2, Rmax, s),
                whitened=dict(sigma1_sq=float(np.linalg.norm(E2w, 2)), R=float(Rw), n_needed=n_needed(float(np.linalg.norm(E2w, 2)), Rw, 1.0)))


if __name__ == "__main__":
    rng = np.random.default_rng(2026)
    out = {}
    for wn, types in WORLDS.items():
        mu0, mu1 = beta_moments(*types[0]), beta_moments(*types[1])
        D, _ = overlap_D(mu0, mu1, 0.5)
        out[wn] = dict(D_true=float(D), hoeffding=hoeffding_check(rng, types), dkw=dkw_search(rng, types),
                       matrix_bernstein={"m=32": matrix_bernstein(types, 32), "m=128": matrix_bernstein(types, 128)})
        print(wn, json.dumps(out[wn]), flush=True)
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT)
