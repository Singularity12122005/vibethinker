import sys, numpy as np, warnings
from fractions import Fraction
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src")
from sycophancy_phase0.analysis import g6_iv as g
warnings.simplefilter("ignore")
rec = {}
orig_eig = np.linalg.eigvalsh; orig_solve = np.linalg.solve
def eig(A): rec['A'] = A.copy(); return orig_eig(A)
def solve(A, b):
    rec['solveA'] = A.copy(); rec['b'] = b.copy()
    try: r = orig_solve(A, b); rec['solve_err']=False; return r
    except np.linalg.LinAlgError: rec['solve_err']=True; raise
g.np.linalg.eigvalsh = eig; g.np.linalg.solve = solve

def exactA(K, t, m, p):
    k = p + 2
    def ff(x, j):
        o = Fraction(1)
        for i in range(j): o *= (x - i)
        return o
    A = [[Fraction(0)]*k for _ in range(k)]
    for Ki, ti in zip(K, t):
        U = [ff(Ki, j)/ff(m, j) for j in range(2*p+1)]
        for a in range(p+1):
            for b in range(p+1): A[a][b] += U[a+b]
            A[a][k-1] += U[a]*ti; A[k-1][a] += U[a]*ti
        A[k-1][k-1] += ti
    return A

rng = np.random.default_rng(1)
bad = 0; ntrial = 0; nsolveerr = 0
specials = [np.nan, np.inf, -np.inf, 1e308, 0.0]
for trial in range(3000):
    m = int(rng.integers(2, 13)); p = int(rng.integers(1, m//2 + 1)); n = int(rng.integers(1, 9))
    K = rng.integers(0, m+1, n); t = rng.integers(0, 2, n)
    if trial % 5 == 0:  # concentrated counts to hit singular states
        K = rng.choice([0, m, m//2], n)
    outs = []
    for v in range(6):
        if v == 0: y = rng.normal(size=n)
        elif v == 1: y = np.full(n, np.nan)
        elif v == 2: y = rng.normal(size=n); y[0] = np.inf
        elif v == 3: y = rng.normal(size=n)*1e300
        elif v == 4: y = rng.choice(specials, n)
        else: y = np.zeros(n); y[-1] = -np.inf
        cl = None if v % 2 == 0 else rng.integers(0, 3, n)
        rec.clear()
        r = g.endpoint_contrast_poly_cs(y, K, m, t, degree=p, cluster=cl)
        outs.append((rec['A'], r['min_eig'], r['ok'], r.get('reason'), 'solveA' in rec, rec.get('solve_err')))
    A0 = outs[0][0]
    EA = exactA(list(map(int,K)), list(map(int,t)), m, p)
    if not all(float(EA[i][j]) == A0[i, j] for i in range(p+2) for j in range(p+2)):
        # allow rounding
        if not np.allclose(np.array([[float(x) for x in row] for row in EA]), A0, rtol=1e-12, atol=0): print("exact mismatch", K, t, m, p)
    ntrial += 1
    for o in outs[1:]:
        if not (np.array_equal(o[0], A0) and (o[1] == outs[0][1]) and o[4] == outs[0][4] and o[5] == outs[0][5]
                and (o[3] == outs[0][3] if not o[2] else True)):
            bad += 1; print("DIFF", K, t, m, p, outs[0][1:], o[1:]); break
    if outs[0][5]: nsolveerr += 1
print("trials", ntrial, "bad", bad, "solve-error cases", nsolveerr)

# exact singular example from comment: m=4,p=2, counts (4,4)/(0,4)?
for K, t in [([4, 0], [1, 0]), ([4, 4, 0, 4], [1, 1, 0, 0]), ([0,4],[1,0])]:
    for y in ([1.0]*len(K), [np.nan]*len(K), [np.inf]+[0.0]*(len(K)-1)):
        rec.clear(); r = g.endpoint_contrast_poly_cs(y, K, 4, t, degree=2)
        print(K, t, y[:1], r['ok'], r['min_eig'], r.get('reason'), rec.get('solve_err'))

# solve directly: singular-passing matrices with nan b
S = np.array([[1.0, 1.0], [1.0, 1.0 + 1e-17]])
for b in ([1, 2], [np.nan, 1], [np.inf, -np.inf]):
    try: orig_solve(S, np.array(b, float)); print("no err", b)
    except np.linalg.LinAlgError: print("LinAlgError", b)
N = np.array([[2.0, 1.0], [1.0, 3.0]])
for b in ([1, 2], [np.nan, 1], [np.inf, -np.inf], [1e308, -1e308]):
    try: print("ok", b, orig_solve(N, np.array(b, float)))
    except np.linalg.LinAlgError: print("LinAlgError", b)

# length mismatch: K,t of length 1, delta_hat of length 5
for y in ([1.0], [1.0]*5):
    rec.clear()
    try:
        r = g.endpoint_contrast_poly_cs(y, [2], 4, [1], degree=1); print("len(y)=", len(y), "min_eig", r['min_eig'], r['ok'], r.get('reason'))
    except Exception as e: print("len(y)=", len(y), type(e).__name__, e)
try: g.endpoint_contrast_poly_cs([1.0, 2.0], [2, 3, 1], 4, [1, 0, 1]); print("no error")
except Exception as e: print("len2 vs 3:", type(e).__name__, e)
