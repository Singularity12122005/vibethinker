"""Verification harness for r4 claims: null size and CI width of the degree-2 corrected-score type test at (n, m) for a given
pair of risk samplers (one per type), quadratic g, two binomial arms of n_arm draws, question clustering optional (CR1).
Also the within-type population Schur complement H_w = Cov_w[(r, r^2)] from moments <= 4 (reference values for Beta families)."""
import sys, time
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

def beta_moments(a, b, J):
    mu = [1.0]
    for j in range(1, J + 1): mu.append(mu[-1] * (a + j - 1) / (a + b + j - 1))
    return mu
def H_w(mu):   # within-type Cov[(r, r^2)] from moments mu[0..4]
    return np.array([[mu[2] - mu[1] ** 2, mu[3] - mu[1] * mu[2]], [mu[3] - mu[1] * mu[2], mu[4] - mu[2] ** 2]])

def simulate(sampler0, sampler1, n, m, R, g=lambda r: 0.20 - 0.5 * r + 0.3 * r ** 2, n_arm=16, seed=0, cluster_k=None):
    rng = np.random.default_rng(seed)
    n0 = n1 = n // 2
    rej, widths, nonpd = 0, [], 0
    for _ in range(R):
        r = np.concatenate([sampler0(rng, n0), sampler1(rng, n1)])
        typ = np.r_[np.zeros(n0, int), np.ones(n1, int)]
        K = rng.binomial(m, r)
        delta = g(r)
        qp, qm = np.clip(r + delta / 2, 0.02, 0.98), np.clip(r - delta / 2, 0.02, 0.98)
        y = rng.binomial(n_arm, qp) / n_arm - rng.binomial(n_arm, qm) / n_arm
        cl = None if cluster_k is None else np.repeat(np.arange(n // cluster_k), cluster_k)[:n]
        out = endpoint_contrast_poly_cs(y, K, m, typ, degree=2, cluster=cl)
        if not out["ok"]:
            nonpd += 1; continue
        rej += out["p_type"] < 0.05
        widths.append(2 * 1.96 * out["se"][-1])
    ok = R - nonpd
    return dict(size=rej / max(1, ok), median_width=float(np.median(widths)) if widths else float("nan"), nonpd_rate=nonpd / R, n_ok=ok)

if __name__ == "__main__":
    fams = {"narrow Beta(20,80)/(25,75)": ((20, 80), (25, 75)), "mid Beta(3,5)/(5,3)": ((3, 5), (5, 3)), "wide Beta(2,8)/(3,3)": ((2, 8), (3, 3))}
    for name, (ab0, ab1) in fams.items():
        lam = [np.linalg.eigvalsh(H_w(beta_moments(*ab, 4)))[0] for ab in (ab0, ab1)]
        print(f"{name}: lambda_min(H_w) per type = {lam[0]:.2e}, {lam[1]:.2e}")
        for m in (32, 128):
            t0 = time.time()
            res = simulate(lambda rng, k, ab=ab0: rng.beta(*ab, k), lambda rng, k, ab=ab1: rng.beta(*ab, k), 200, m, 400, seed=m)
            print(f"   (n=200, m={m}): null size {res['size']:.3f}, median CI width {res['median_width']:.3f}, non-PD {res['nonpd_rate']:.3f} [{time.time()-t0:.0f}s]")
