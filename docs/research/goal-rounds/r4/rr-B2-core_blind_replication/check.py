import sys, numpy as np
from fractions import Fraction
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs as f, PD_RTOL
print("numpy", np.__version__)

def ff(x, j):
    o = Fraction(1)
    for i in range(j): o *= (x - i)
    return o
def exactA(K, t, m, p):
    k = p + 2
    A = [[Fraction(0)]*k for _ in range(k)]
    for Ki, ti in zip(K, t):
        Ki = Fraction(int(Ki)); ti = Fraction(ti)
        U = [ff(Ki, j)/ff(Fraction(m), j) for j in range(2*p+1)]
        for a in range(p+1):
            for b in range(p+1): A[a][b] += U[a+b]
            A[a][k-1] += U[a]*ti; A[k-1][a] += U[a]*ti
        A[k-1][k-1] += ti
    return A

rng = np.random.default_rng(2024)
def draw(m, n0=100, n1=100):
    r = np.r_[rng.beta(40.5, 162, n0), rng.beta(50.6, 151.8, n1)]
    t = np.r_[np.zeros(n0), np.ones(n1)]
    K = rng.binomial(m, r)
    return r, t, K
cluster = np.repeat(np.arange(50), 2); cluster = np.r_[cluster, cluster]  # 50 questions, 2+2

# (1) exact formula check + invariance across delta laws/SE
for m in (128, 512):
    p = 2
    ndraw = 300
    nonpd = 0; mism = 0; exact_mis = 0; calls = 0
    for d in range(ndraw):
        r, t, K = draw(m)
        outs = set()
        for g in range(10):
            for law in range(4):
                mu = (g-5)*0.1*r + 0.3*r**2*(g%3) + 0.05*t*g
                if law == 0: eta = rng.normal(0, np.sqrt(r*(1-r)/16*2), r.size)
                elif law == 1: eta = rng.normal(0, np.sqrt(r*(1-r)/32*2), r.size)
                elif law == 2: eta = 0
                else: eta = rng.standard_cauchy(r.size)*1e6
                y = mu + eta
                for cl in (None, cluster):
                    o = f(y, K, m, t, degree=p, cluster=cl); calls += 1
                    outs.add((o["ok"], o["min_eig"]))
        # extra: nan / inf delta (PD decision only)
        for y in (np.full(r.size, np.nan), np.full(r.size, np.inf), np.zeros(r.size)):
            try:
                o = f(y, K, m, t, degree=p); outs.add((o["ok"], o["min_eig"])) if not np.isnan(y).any() and not np.isinf(y).any() else None
                okpd = o["min_eig"]
            except Exception as e: print("exc", type(e), e)
        if len(outs) != 1: mism += 1
        ok, me = next(iter(outs))
        # independent PD decision from exact A
        A = exactA(K, t, m, p)
        Af = np.array([[float(x) for x in row] for row in A])
        ev = np.linalg.eigvalsh(Af)
        mypd = ev[0] > PD_RTOL*max(1.0, abs(ev[-1]))
        if mypd != ok or abs(ev[0]-me) > 1e-9*max(1, abs(ev[-1])): exact_mis += 1
        nonpd += (not ok)
    print(f"m={m} draws={ndraw} calls={calls} draws_with_nonidentical(ok,min_eig)={mism} nonPD={nonpd} exactA_disagree={exact_mis}")
