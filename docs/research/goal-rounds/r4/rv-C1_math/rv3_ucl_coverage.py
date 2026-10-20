"""Reviewer: coverage of the outer-bootstrap 95% percentile UCL for sigma_delta^2 in a synthetic trinomial model calibrated
to the narrow-lin HC1 cell (P(y != 0) ~ 0.056, sigma_delta^2 ~ 2e-5 and ~ 4e-5), N_out = 1000, N_in = 200."""
import numpy as np
rng = np.random.default_rng(5)
n_out, n_in, B, reps = 1000, 200, 500, 600
for true_sd in (0.0045, 0.0064):
    cover = 0; ests = []
    for _ in range(reps):
        # heteroskedastic delta: skewed (gamma-shaped) outer effect, mean zero
        g = rng.gamma(0.5, 1.0, n_out); delta = (g - 0.5) / np.sqrt(0.5) * true_sd
        base = rng.uniform(0.02, 0.036, n_out)           # discordance rate varies across outer units
        p1, p2 = base + delta / 2, base - delta / 2
        p1 = np.clip(p1, 0, 1); p2 = np.clip(p2, 0, 1)
        c = np.stack([rng.multinomial(n_in, [a, b, 1 - a - b]) for a, b in zip(p1, p2)])
        n1, n2 = c[:, 0], c[:, 1]
        yb = (n1 - n2) / n_in; ey2 = (n1 + n2) / n_in
        s2 = (ey2 - yb ** 2) * n_in / (n_in - 1)
        truth = np.var(delta, ddof=0)  # finite-population realised var approx; use the model value instead
        truth = true_sd ** 2
        est = yb.var(ddof=1) - s2.mean() / n_in; ests.append(est)
        idx = rng.integers(0, n_out, (B, n_out))
        ybb, s2b = yb[idx], s2[idx]
        boots = ybb.var(1, ddof=1) - s2b.mean(1) / n_in
        cover += np.percentile(boots, 95) >= truth
    print(f"true sd {true_sd}: mean est {np.mean(ests):.3e} (truth {true_sd**2:.3e}), UCL95 coverage {cover/reps:.3f}")
