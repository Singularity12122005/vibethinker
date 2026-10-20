"""r4 route C (sequential internal pilot 32 -> 128 -> re-assess; validity under reuse): shared helpers.
Everything that produces a size / width number calls the PRODUCTION estimator endpoint_contrast_poly_cs
(degree 2, PD rule lambda_min > 1e-9*max(1, lambda_max), HC1 default, CR1 when cluster given).
Environment tag: CPU x86_64, python 3.13.16, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19.
Scratch only; nothing in the repository is modified."""
import sys
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs, binomial_factorial_joint_moment  # noqa: E402

N_T = 100                      # prefixes per type (n = 200)
N_ARM = 16                     # draws per steered arm (plan §7.11: 32 per prefix x alpha, split fit/eval 16/16)
TYPES_VEC = np.repeat([0, 1], N_T)
# question clusters: 50 questions x 4 prefixes, 2 of each type in every question (same as problem-phase check1)
CLUSTER = np.concatenate([np.repeat(np.arange(N_T // 2), 2), np.repeat(np.arange(N_T // 2), 2)])

WORLDS = {
    "narrow": ((20.0, 80.0), (25.0, 75.0)),              # archive r3 A2 narrow cell; §7.11 example type (0.20 / 0.25)
    "halfvar": ((40.5, 162.0), (50.6, 151.8)),           # same means, half the within-type variance (check1b / check2c Le Cam pair)
    "wide": ((2.0, 8.0), (2.5, 7.5)),                    # archive r3 A2 wide cell
}
G_CLASS = {
    "lin": (0.18, -0.8, 0.0),                            # archive linear world
    "quad": (0.26, -1.6, 2.0),                           # problem-phase check1 quadratic
    "cheb": (0.5, -4.0, 4.0),                            # 0.5*(1 - 8r + 8r^2): extreme member of {|g| <= 1/2}, slope -2.4 at r=0.2
}
W0 = 0.15                                                # proposed q90 width tolerance (user decision)
SIG2_ETA_MAX = 1.0 / 32.0                                # sup_r Var(eta | r) for two 16-draw arms: 2 * (1/4) / 16


def U_stat(K, j, m):
    """U_j(K) = K^{(j)} / m^{(j)} (falling factorials); unbiased for r^j given K ~ Bin(m, r)."""
    out = np.ones_like(K, dtype=float)
    for i in range(j):
        out = out * (K - i) / (m - i)
    return out


def draw_outer_counts(rng, types, m):
    """Pilot counts K_i ~ BetaBin(m, a_t, b_t) for 100 prefixes per type (r integrated out)."""
    r = np.concatenate([rng.beta(*types[0], N_T), rng.beta(*types[1], N_T)])
    return rng.binomial(m, r)


def draw_r_posterior(rng, types, K, m):
    """r_i | K_i ~ Beta(a_t + K_i, b_t + m - K_i): the exact conditional law of the risk given the pilot in a Beta world."""
    a = np.where(TYPES_VEC == 0, types[0][0], types[1][0]); b = np.where(TYPES_VEC == 0, types[0][1], types[1][1])
    return rng.beta(a + K, b + m - K)


def draw_dhat(rng, r, g, n_arm=N_ARM):
    """Endpoint contrast: difference of two independent n_arm-draw binomial means with q_pm = clip(r pm g(r)/2, 0, 1)."""
    c0, b1, b2 = g
    delta = c0 + b1 * r + b2 * r ** 2
    qp, qm = r + delta / 2, r - delta / 2
    clipped = float(np.mean((qp > 1) | (qm < 0)))
    qp, qm = np.clip(qp, 0, 1), np.clip(qm, 0, 1)
    return rng.binomial(n_arm, qp) / n_arm - rng.binomial(n_arm, qm) / n_arm, clipped


def run_test(dhat, K, m, cluster=None):
    """Production degree-2 corrected-score type test. Returns (ok, reject at |t|>1.96, full 95% CI width; inf when not ok)."""
    res = endpoint_contrast_poly_cs(dhat, K, m, TYPES_VEC, degree=2, cluster=cluster)
    if not res["ok"]:
        return False, False, np.inf
    tt = res["t_type"]
    return True, bool(np.isfinite(tt) and abs(tt) > 1.96), float(2 * 1.96 * res["se"][-1])


# ------------------------------------------------------------------------------------------------ pilot-measurable statistics
def pd_flag(K, m):
    """Deterministic PD flag of the corrected degree-2 matrix (production rule) at this m -- a function of the counts only."""
    y0 = np.zeros(K.size)
    return bool(endpoint_contrast_poly_cs(y0, K, m, TYPES_VEC, degree=2)["ok"])


def vhat_pooled(K, m):
    """Pooled unbiased within-type Var(r): mean_i U_2 - mean_{i != j} U_1(K_i) U_1(K_j), averaged over the two types."""
    v = []
    for k in (0, 1):
        Kk = K[TYPES_VEC == k]; n = Kk.size
        u1, u2 = U_stat(Kk, 1, m), U_stat(Kk, 2, m)
        v.append(u2.mean() - (u1.sum() ** 2 - (u1 ** 2).sum()) / (n * (n - 1)))
    return 0.5 * (v[0] + v[1])


def unbiased_moments(K, m, order):
    """Unbiased per-type raw moments mu_j, j = 0..order (needs order <= m) and the U-statistic products mu_a mu_b (a, b <= order/2)."""
    out = []
    for k in (0, 1):
        Kk = K[TYPES_VEC == k]; n = Kk.size
        Us = [U_stat(Kk, j, m) for j in range(order + 1)]
        mu = np.array([u.mean() for u in Us])
        prod = np.zeros((order // 2 + 1, order // 2 + 1))
        for a in range(order // 2 + 1):
            for b in range(order // 2 + 1):
                prod[a, b] = (Us[a].sum() * Us[b].sum() - (Us[a] * Us[b]).sum()) / (n * (n - 1))
        out.append((mu, prod))
    return out


def pd_margin_hat(K, m_pilot, m_target, p=2):
    """Pilot estimate of the PD margin of the expected Schur complement at m_target (A1):
    lambda_min( sum_t w_t [ H_w,t - C_t^{(m_target)} / n_t ] ),  H_w,t[a,b] = mu_{a+b,t} - mu_{a,t} mu_{b,t},
    C_t[a,b] = J_ab^{(m_target)}(mu_t) - mu_{a,t} mu_{b,t}; all moments (<= 2p = 4) unbiased from the pilot counts."""
    S = np.zeros((p, p))
    for k, (mu, prod) in enumerate(unbiased_moments(K, m_pilot, 2 * p)):
        n_t = N_T
        for a in range(1, p + 1):
            for b in range(1, p + 1):
                J = float(binomial_factorial_joint_moment([float(x) for x in mu], m_target, a, b))
                C = J - prod[a, b]
                S[a - 1, b - 1] += 0.5 * (mu[a + b] - prod[a, b] - C / n_t)
    return float(np.linalg.eigvalsh(S)[0])


def width_predictor(K, m, sig2_eta, p=2):
    """Pre-experiment width proxy: 2*1.96*sqrt( sig2_eta * n/(n-k) * [A^{-1} G A^{-1}]_{type,type} ),
    A = sum_i M_i (corrected design, the matrix the final test will use), G = sum_i u_i u_i^T with u_i = (1, U_1, U_2, t_i).
    It is the outcome-noise part of the HC1 sandwich with Var(eta|r) replaced by the constant sig2_eta; the measurement-error
    part of B is omitted. Returns nan when A is not PD by the production rule."""
    n = K.size; k = p + 2
    U = [U_stat(K, j, m) for j in range(2 * p + 1)]
    M = np.zeros((n, k, k)); u = np.zeros((n, k))
    for a in range(p + 1):
        for b in range(p + 1):
            M[:, a, b] = U[a + b]
        M[:, a, k - 1] = M[:, k - 1, a] = U[a] * TYPES_VEC
        u[:, a] = U[a]
    M[:, k - 1, k - 1] = TYPES_VEC; u[:, k - 1] = TYPES_VEC
    A = M.sum(0)
    eig = np.linalg.eigvalsh(A)
    if not (eig[0] > 1e-9 * max(1.0, abs(eig[-1]))):
        return float("nan")
    Ai = np.linalg.inv(A)
    G = u.T @ u
    v = (Ai @ G @ Ai)[k - 1, k - 1] * sig2_eta * n / (n - k)
    return float(2 * 1.96 * np.sqrt(max(v, 0.0)))


# ------------------------------------------------------------------------------------------------ nested-ANOVA machinery
def between_variance_component(y):
    """y: (N_out, N_in) array of inner outcomes. Unbiased estimate of Var_o(E[y | o]) =
    sample variance of the outer means  minus  mean inner sample variance / N_in (one-way random-effects ANOVA)."""
    n_out, n_in = y.shape
    ybar = y.mean(1)
    s2_in = y.var(1, ddof=1)
    return float(ybar.var(ddof=1) - s2_in.mean() / n_in)


def bootstrap_outer(stat, arrays, rng, B=2000):
    """Percentile bootstrap over OUTER units of a statistic stat(*arrays_resampled)."""
    n_out = arrays[0].shape[0]
    vals = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n_out, n_out)
        vals[b] = stat(*[a[idx] for a in arrays])
    return vals


def exact_binom_ci(k, n, alpha=0.05):
    from scipy.stats import beta
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return [lo, hi]
