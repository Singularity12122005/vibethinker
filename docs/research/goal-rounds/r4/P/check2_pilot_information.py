"""r4 problem-phase cheap check 2: how much does the G6 pilot (100 h_3 prefixes per type, m_pilot = 32 sel continuations)
say about the degree-1 and degree-2 identification quantities?

(a) Unbiased pilot estimators from the 32-counts (U-statistics, A1 identities):  V = Var_w(r)  and  H_w = Cov_w[(r, r^2)]
    (entries mu_{a+b} - mu_a mu_b, estimated by  mean_i U_{a+b}(K_i) - mean_{i != j} U_a(K_i) U_b(K_j)).  Report the sampling
    distribution over 5000 pilots: P(V_hat <= 0), P(lambda_min(H_hat_w) <= 0), quantiles.
(b) Le Cam two-point information: Hellinger affinity between the m=32 count laws of neighbouring risk distributions
    (same mean, different spread), raised to n_t = 100, giving a LOWER bound on the sum of the two error probabilities of ANY
    pilot-based rule that tries to tell them apart:  err_I + err_II >= 1 - sqrt(1 - rho^(2 n_t)).
Environment: CPU, python3 / numpy 2.5.3 / scipy 1.18.1, 2026-10-19."""
import json, sys
import numpy as np
from scipy import stats
from scipy.special import betaln, gammaln

OUT = "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/problem/check2_pilot_information.json"
M, N_T, PILOTS = 32, 100, 5000


def U(K, j, m):
    out = np.ones_like(K, float)
    for i in range(j):
        out *= (K - i) / (m - i)
    return out


def unbiased_Hw(K, m, p=2):
    """Unbiased estimate of Cov_w[(r,...,r^p)] from counts of ONE type: mean U_{a+b} - mean_{i!=j} U_a(K_i)U_b(K_j)."""
    n = K.size
    Us = [U(K, j, m) for j in range(2 * p + 1)]
    H = np.zeros((p, p))
    for a in range(1, p + 1):
        for b in range(1, p + 1):
            cross = (Us[a].sum() * Us[b].sum() - (Us[a] * Us[b]).sum()) / (n * (n - 1))
            H[a - 1, b - 1] = Us[a + b].mean() - cross
    return H


def true_Hw(a, b, p=2):
    mu = [1.0] + [np.exp(betaln(a + j, b) - betaln(a, b)) for j in range(1, 2 * p + 1)]
    return np.array([[mu[i + j] - mu[i] * mu[j] for j in range(1, p + 1)] for i in range(1, p + 1)]), mu


def betabinom_pmf(m, a, b):
    k = np.arange(m + 1)
    return np.exp(gammaln(m + 1) - gammaln(k + 1) - gammaln(m - k + 1) + betaln(k + a, m - k + b) - betaln(a, b))


def lecam(p, q, n):
    rho = float(np.sum(np.sqrt(p * q)))              # Hellinger affinity of one count
    tv1 = 0.5 * float(np.abs(p - q).sum())
    tv_n_upper = float(np.sqrt(max(0.0, 1 - rho ** (2 * n))))   # TV(P^n, Q^n) <= sqrt(1 - rho^{2n})
    return dict(affinity_1=rho, tv_1=tv1, tv_n_upper=tv_n_upper, min_sum_of_errors=1 - tv_n_upper)


if __name__ == "__main__":
    rng = np.random.default_rng(4)
    out = {}
    for name, (a, b) in {"narrow_t0": (20, 80), "narrow_t1": (25, 75), "wide_t0": (2, 8)}.items():
        Hw, mu = true_Hw(a, b)
        V = Hw[0, 0]
        s32 = (mu[1] - mu[2]) / M
        Vh, lmin, lmin_rel = [], [], []
        for _ in range(PILOTS):
            r = rng.beta(a, b, N_T)
            K = rng.binomial(M, r)
            H = unbiased_Hw(K, M)
            Vh.append(H[0, 0]); lmin.append(np.linalg.eigvalsh(H)[0])
        Vh, lmin = np.array(Vh), np.array(lmin)
        out[name] = dict(V_true=float(V), lambda_min_Hw_true=float(np.linalg.eigvalsh(Hw)[0]), Hw_true=Hw.tolist(),
                         noise_s_m32=float(s32), reliability_w_m32=float(V / (V + s32)),
                         reliability_w_m128=float(V / (V + s32 * 32 / 128)),
                         Vhat_mean=float(Vh.mean()), Vhat_sd=float(Vh.std()), P_Vhat_le_0=float((Vh <= 0).mean()),
                         Vhat_q05_50_95=[float(np.percentile(Vh, p)) for p in (5, 50, 95)],
                         lmin_hat_mean=float(lmin.mean()), P_lmin_hat_le_0=float((lmin <= 0).mean()),
                         lmin_hat_q05_50_95=[float(np.percentile(lmin, p)) for p in (5, 50, 95)])
        print(name, json.dumps(out[name]), flush=True)
    # (b) Le Cam two-point bounds at m = 32, n_t = 100: narrow Beta(20,80) vs neighbours with the same mean 0.2
    p_ref = betabinom_pmf(M, 20, 80)
    lc = {}
    for lab, ab in {"point_mass_0.2": None, "half_var_Beta(40.5,162)": (40.5, 162.0), "double_var_Beta(9.5,38)": (9.5, 38.0),
                          "Beta(10,40)": (10, 40), "Beta(5,20)": (5, 20)}.items():
        a2, b2 = (None, None) if ab is None else ab
        q = stats.binom.pmf(np.arange(M + 1), M, 0.2) if a2 is None else betabinom_pmf(M, a2, b2)
        res = lecam(p_ref, q, N_T)
        if a2 is not None:
            Hq, _ = true_Hw(a2, b2); res["V_alt"] = float(Hq[0, 0]); res["lambda_min_alt"] = float(np.linalg.eigvalsh(Hq)[0])
        else:
            res["V_alt"] = 0.0; res["lambda_min_alt"] = 0.0
        lc[lab] = res
        print("LeCam vs", lab, json.dumps(res), flush=True)
    out["lecam_vs_narrow_Beta(20,80)"] = lc
    json.dump(out, open(OUT, "w"), indent=1)
