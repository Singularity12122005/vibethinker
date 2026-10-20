# Exact enumeration (Fractions) of the C1-atom identity under G6-like premise variations.
# One prefix, small binomials (m0=2 pilot, m1=3 extension, m=5 final) so everything is exact.
# Case A: eta law depends on a latent theta=(r,g) beyond (r,t)  -> identity should still hold.
# Case B: extension drawn at r+eps (e.g. max_new_tokens 512->768 switch, serving drift) -> E[delta] != 0.
# Case C: D depends on extra pre-G6 data W correlated with r (h_2-bank draws) -> D not in sigma(t,K32).
from fractions import Fraction as F
from math import comb
import itertools

def binpmf(m, p):
    return [comb(m, k) * p**k * (1 - p)**(m - k) for k in range(m + 1)]

m0, m1 = 2, 3
m = m0 + m1
thetas = [((F(1, 5), 0), F(1, 2)), ((F(1, 5), 1), F(1, 4)), ((F(3, 5), 0), F(1, 8)), ((F(3, 5), 1), F(1, 8))]  # ((r,g), prob)

def eta_pmf(r, g):  # eta in {0,1}; law depends on g (not a function of r alone)
    p = F(1, 10) + F(7, 10) * g + F(1, 10) * r
    return {0: 1 - p, 1: p}

def f(K, eta):  # arbitrary {0,1} statistic of final count and outcome noise
    return 1 if (K + 2 * eta) in (2, 3, 6) else 0

def run(eps=F(0), use_W=False):
    # joint over (theta, W, K32, K96, Kp, eta)
    num = {}  # keys: conditioning value c -> [P(c), P(R,c), P(R',c)]
    PR = PRp = F(0)
    for (theta, pth) in thetas:
        r, g = theta
        pW = binpmf(1, r) if use_W else [F(1)]
        for w, pw in enumerate(pW):
            for k0, p0 in enumerate(binpmf(m0, r)):
                for k1, p1 in enumerate(binpmf(m1, r + eps)):
                    for kp, pp in enumerate(binpmf(m, r + eps)):   # fresh 128 run under the *new* config
                        for e, pe in eta_pmf(r, g).items():
                            pr = pth * pw * p0 * p1 * pp * pe
                            c = (k0, w)
                            a = num.setdefault(c, [F(0), F(0), F(0)])
                            a[0] += pr; a[1] += pr * f(k0 + k1, e); a[2] += pr * f(kp, e)
                            PR += pr * f(k0 + k1, e); PRp += pr * f(kp, e)
    return num, PR, PRp

def report(name, num, PR, PRp, D_keys):
    Edelta = sum(a[0] * (a[1] / a[0] - a[2] / a[0]) for a in num.values())
    pi = sum(num[c][0] for c in D_keys)
    lhs = sum(num[c][1] for c in D_keys) / pi - sum(num[c][2] for c in D_keys) / pi
    # covariance of delta with 1_D, delta defined on sigma(K32) only (the proposition's delta)
    byk = {}
    for (k0, w), a in num.items():
        b = byk.setdefault(k0, [F(0), F(0), F(0)])
        for j in range(3): b[j] += a[j]
    Ed = sum(b[1] - b[2] for b in byk.values())
    print(f"{name}: E[delta]={float(Edelta):+.6f} (exact {Edelta}); P(R)-P(R')={float(PR-PRp):+.6f}; "
          f"P(R|D)-P(R'|D)={float(lhs):+.6f}")
    return lhs, byk, pi

# Case A
num, PR, PRp = run()
D = [c for c in num if c[0] == 2]
lhs, byk, pi = report("A latent-eta", num, PR, PRp, D)
cov = sum((b[1] - b[2]) * (1 if k == 2 else 0) for k, b in byk.items()) - 0  # E[delta 1_D]
print("   Cov(delta,1_D)/pi =", float(cov / pi), " identity holds:", cov / pi == lhs)
# Case B
num, PR, PRp = run(eps=F(1, 20))
D = [c for c in num if c[0] == 2]
report("B drift eps=0.05", num, PR, PRp, D)
# Case C: D uses W (one extra Bernoulli(r) draw, e.g. the h_2-bank trajectory through h_3)
num, PR, PRp = run(use_W=True)
D = [c for c in num if c[0] + c[1] >= 2]
lhs, byk, pi = report("C D uses W", num, PR, PRp, D)
deltaK = {k: (b[1] - b[2]) / b[0] for k, b in byk.items()}
cov_K = sum(num[c][0] * deltaK[c[0]] for c in D)
print("   prop's Cov(delta_K32,1_D)/pi =", float(cov_K / pi), " equals lhs:", cov_K / pi == lhs)
