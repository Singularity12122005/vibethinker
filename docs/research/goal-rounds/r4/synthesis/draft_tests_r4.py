"""Synthesis-stage draft of the r4 regression tests (copied verbatim into sycophancy_phase0/tests/test_analysis.py).
Run: /tmp/claude-0/venv/bin/python -m pytest <this file> -q   (imports the repository package from src)."""
import sys
sys.path.insert(0, "/home/user/vibethinker/sycophancy_phase0/src")
import numpy as np
import pytest
from math import prod as math_prod


# ---------------------------------------------------------------- archive r4 (candidates: regression locks of the reviewed cores)
def _goal_r4_inverse(A):
    """Exact Gauss-Jordan inverse of a small Fraction matrix."""
    from fractions import Fraction as Fr
    n = len(A)
    M = [list(row) + [Fr(int(i == j)) for j in range(n)] for i, row in enumerate(A)]
    for c in range(n):
        piv = next(i for i in range(c, n) if M[i][c] != 0)
        M[c], M[piv] = M[piv], M[c]
        p = M[c][c]
        M[c] = [x / p for x in M[c]]
        for i in range(n):
            if i != c and M[i][c] != 0:
                f = M[i][c]
                M[i] = [a - f * b for a, b in zip(M[i], M[c])]
    return [row[n:] for row in M]


def _goal_r4_falling(x, j):
    out = 1
    for i in range(j):
        out *= (x - i)
    return out


def _goal_r4_rising(a, n):
    from fractions import Fraction as Fr
    out = Fr(1)
    for i in range(n):
        out *= (a + i)
    return out


def test_goal_r4_a_c1_candidate_closed_form_sandwich():
    """r4 A-C1（候选，不是已证明）：二次校正得分类型系数一阶三明治的闭式。精确有理数下，枚举 (t, r, K) 的
    [Q^{-1}BQ^{-1}]_44 等于 D^{-2}Σ_t w_t E_t[φ²]，其中 E[φ²|r,t]=σ²[ρ²+γ̃'V⁽²⁾γ̃]+Σ_{b,d}β_bβ_d α_b'V⁽⁴⁾α_d，
    且 Q^{-1}e_4=D^{-1}(−γ,1)。同时锁定审查补入的前提 E[η²|r,t,K]=σ²(r)：令条件方差依赖 K 而保持 E[η²|r] 不变时闭式不再成立。
    不检验 n=200 的有限样本宽度分布、非正定率或 size，也不检验 |g|≤1 类上的一致上确界。"""
    from fractions import Fraction as Fr
    from math import comb
    from sycophancy_phase0.analysis.g6_iv import binomial_factorial_joint_moment

    laws = [[(Fr(1, 5), Fr(1, 3)), (Fr(1, 2), Fr(1, 3)), (Fr(4, 5), Fr(1, 3))], [(Fr(1, 4), Fr(1, 2)), (Fr(3, 5), Fr(1, 2))]]
    beta, b_type = (Fr(1, 5), Fr(-3, 5), Fr(1, 2)), Fr(1, 10)
    full_beta = list(beta) + [b_type]
    sigma2 = lambda r: r * (1 - r) / 8
    g = lambda r: beta[0] + beta[1] * r + beta[2] * r ** 2

    def brute(m, w1, eta_var):
        w = (1 - w1, w1)
        Q = [[Fr(0)] * 4 for _ in range(4)]
        B = [[Fr(0)] * 4 for _ in range(4)]
        for t, law in enumerate(laws):
            for r, pr in law:
                xs = [Fr(1), r, r ** 2, Fr(t)]
                for a in range(4):
                    for b in range(4):
                        Q[a][b] += w[t] * pr * xs[a] * xs[b]
                for K in range(m + 1):
                    pk = comb(m, K) * r ** K * (1 - r) ** (m - K)
                    U = [Fr(_goal_r4_falling(K, j), _goal_r4_falling(m, j)) for j in range(5)]
                    u = [U[0], U[1], U[2], Fr(t)]
                    Mh = [[U[a + b] for b in range(3)] + [U[a] * t] for a in range(3)] + [[U[0] * t, U[1] * t, U[2] * t, Fr(t)]]
                    d = [u[a] * (g(r) + b_type * t) - sum(Mh[a][b] * full_beta[b] for b in range(4)) for a in range(4)]
                    s = eta_var(r, U)
                    for a in range(4):
                        for b in range(4):
                            B[a][b] += w[t] * pr * pk * (s * u[a] * u[b] + d[a] * d[b])
        Qi = _goal_r4_inverse(Q)
        V = sum(Qi[3][a] * B[a][b] * Qi[b][3] for a in range(4) for b in range(4))
        return V, Qi

    def closed_form(m, w1):
        w = (1 - w1, w1)
        mu = [[sum(pr * r ** j for r, pr in law) for j in range(5)] for law in laws]
        Qxx = [[sum(w[t] * mu[t][a + b] for t in range(2)) for b in range(3)] for a in range(3)]
        q = [w1 * mu[1][a] for a in range(3)]
        Qxx_inv = _goal_r4_inverse(Qxx)
        gam = [sum(Qxx_inv[a][b] * q[b] for b in range(3)) for a in range(3)]
        D = w1 - sum(q[a] * gam[a] for a in range(3))
        total = Fr(0)
        for t, law in enumerate(laws):
            for r, pr in law:
                powers = [r ** k for k in range(9)]
                V = {(j, l): binomial_factorial_joint_moment(powers, m, j, l) - r ** (j + l) for j in range(1, 5) for l in range(1, 5)}
                rho = t - (gam[0] + gam[1] * r + gam[2] * r ** 2)
                eta_part = sigma2(r) * (rho ** 2 + sum(gam[j] * gam[l] * V[j, l] for j in (1, 2) for l in (1, 2)))
                alpha = {}
                for b in (1, 2):
                    alpha[b] = {j: (-(t - gam[0]) * (j == b) - gam[1] * r ** b * (j == 1) + gam[1] * (j == 1 + b)
                                    - gam[2] * r ** b * (j == 2) + gam[2] * (j == 2 + b)) for j in range(1, 5)}
                g_part = sum(beta[b] * beta[dd] * alpha[b][j] * alpha[dd][l] * V[j, l]
                             for b in (1, 2) for dd in (1, 2) for j in range(1, 5) for l in range(1, 5))
                total += w[t] * pr * (eta_part + g_part)
        return total / D ** 2, gam, D

    indep = lambda r, U: sigma2(r)                                   # η independent of K given r (physical two-arm design)
    k_dependent = lambda r, U: sigma2(r) * (1 + Fr(9, 10) * (U[1] - r))  # E[η²|r] unchanged, E[η|r,K]=0 still holds
    for m in (4, 8):                                                  # m = 4 = 2p exercises the truncated A1 sums
        for w1 in (Fr(1, 2), Fr(2, 5)):
            V_brute, Qi = brute(m, w1, indep)
            V_cf, gam, D = closed_form(m, w1)
            assert D > 0 and V_brute == V_cf, (m, w1)
            assert [Qi[a][3] for a in range(4)] == [-gam[0] / D, -gam[1] / D, -gam[2] / D, 1 / D]
            V_bad, _ = brute(m, w1, k_dependent)
            assert V_bad != V_cf                                     # the formula needs E[η²|r,t,K] = σ²(r), not only Var(η|r)


def _goal_r4_betabin(m, a, b):
    """Exact rational Beta-binomial pmf for rational (a, b): p(0)=(b)_m/(a+b)_m, p(k+1)=p(k)(m−k)/(k+1)·(a+k)/(b+m−k−1)."""
    from fractions import Fraction as Fr
    p = [_goal_r4_rising(b, m) / _goal_r4_rising(a + b, m)]
    for k in range(m):
        p.append(p[-1] * Fr(m - k, k + 1) * (a + k) / (b + m - k - 1))
    assert sum(p) == 1
    return p


def _goal_r4_mixture(m, atoms):
    from math import comb
    p = [sum(w * comb(m, k) * x ** k * (1 - x) ** (m - k) for x, w in atoms) for k in range(m + 1)]
    assert sum(p) == 1
    return p


def test_goal_r4_b1_candidate_lecam_constants():
    """r4 B1（候选，不是已证明）：Le Cam 两点界的引理在可枚举小例上精确成立（亲和度张量化、TV≤√(1−ρ²)、
    min_φ(err_I+err_II)=1−TV 由似然比检验达到、P_a(φ)−P_b(φ)≤TV），并按审查更正后的口径锁定实际导频（每类 100、m=32）
    的常数：问题阶段的 0.569 是只用 0 类前缀的 Hellinger 界 1−√(1−ρ_0^{200})（ρ_0^{100}=0.90252，不是 0.569），两类合并为
    0.41943；F_c2 与 F_a 每类同均值同方差。F_θ 定义为同均值、方差 θ·V_a 的 Beta（a+b=101/θ−1）。只覆盖类内独立同分布、
    计数独立的模型；不计算 NP 精确最小值（审查的格点 FFT 值见档案），不涉及题内相关。"""
    from decimal import Decimal, getcontext
    from fractions import Fraction as Fr
    from itertools import product
    getcontext().prec = 60
    dec = lambda f: Decimal(f.numerator) / Decimal(f.denominator)
    aff = lambda p, q: sum((dec(x) * dec(y)).sqrt() for x, y in zip(p, q))

    # (1) Lemmas 1-3 and Corollary 4 on an exactly enumerable instance: m = 3, two prefixes per type.
    m = 3
    Pa = [_goal_r4_mixture(m, [(Fr(1, 5), Fr(1, 2)), (Fr(2, 5), Fr(1, 2))]), _goal_r4_mixture(m, [(Fr(1, 4), Fr(1, 2)), (Fr(1, 2), Fr(1, 2))])]
    Pb = [_goal_r4_mixture(m, [(Fr(3, 10), Fr(1))]), _goal_r4_mixture(m, [(Fr(3, 8), Fr(1))])]
    types = (0, 0, 1, 1)
    outcomes = list(product(range(m + 1), repeat=4))
    joint = lambda P, ks: math_prod([P[t][k] for t, k in zip(types, ks)])
    pa = {ks: joint(Pa, ks) for ks in outcomes}
    pb = {ks: joint(Pb, ks) for ks in outcomes}
    assert sum(pa.values()) == 1 and sum(pb.values()) == 1
    tv = sum(abs(pa[ks] - pb[ks]) for ks in outcomes) / 2
    lr_err = sum(pa[ks] for ks in outcomes if not pa[ks] > pb[ks]) + sum(pb[ks] for ks in outcomes if pa[ks] > pb[ks])
    assert lr_err == 1 - tv                                          # Lemma 3: attained by the likelihood-ratio test
    rng = np.random.default_rng(20261019)
    for _ in range(200):                                              # randomized rules phi in {0, 1/2, 1}
        phi = {ks: Fr(int(v), 2) for ks, v in zip(outcomes, rng.integers(0, 3, len(outcomes)))}
        err = sum(pa[ks] * (1 - phi[ks]) + pb[ks] * phi[ks] for ks in outcomes)
        assert err >= 1 - tv
        assert sum(pa[ks] * phi[ks] for ks in outcomes) - sum(pb[ks] * phi[ks] for ks in outcomes) <= tv   # Corollary 4
    rho_direct = sum((dec(pa[ks]) * dec(pb[ks])).sqrt() for ks in outcomes)
    rho_product = aff(Pa[0], Pb[0]) ** 2 * aff(Pa[1], Pb[1]) ** 2
    assert abs(rho_direct - rho_product) < Decimal(10) ** -50         # Lemma 1 (tensorization)
    assert dec(tv) <= (1 - rho_product ** 2).sqrt()                    # Lemma 2

    # (2) The pilot's constants (n_t = 100 per type, m = 32), exact rational count laws, 60-digit affinities.
    def bound(rhos, n_t=100):
        r = Decimal(1)
        for x in rhos:
            r *= x ** (2 * n_t)
        return 1 - (1 - r).sqrt()
    Fa = [(Fr(20), Fr(80)), (Fr(25), Fr(75))]
    Fb = [(Fr(81, 2), Fr(162)), (Fr(253, 5), Fr(759, 5))]
    mus = (Fr(1, 5), Fr(1, 4))
    s09 = Fr(101) * Fr(10, 9) - 1
    Ftheta09 = [(mu * s09, (1 - mu) * s09) for mu in mus]
    Fc2 = [[(Fr(81, 505), Fr(101, 201)), (Fr(6, 25), Fr(100, 201))], [(Fr(329, 1616), Fr(1616, 3491)), (Fr(29, 100), Fr(1875, 3491))]]
    for t, (a, b) in enumerate(Fa):                                   # F_c2 has the mean and variance of F_a in each type
        mean, var = a / (a + b), a * b / ((a + b) ** 2 * (a + b + 1))
        m1 = sum(w * x for x, w in Fc2[t]); m2 = sum(w * x * x for x, w in Fc2[t])
        assert (mean, var) == (mus[t], [Fr(4, 2525), Fr(3, 1616)][t]) and (m1, m2 - m1 ** 2) == (mean, var)
    rd = lambda x, k: round(float(x), k)
    pa32 = [_goal_r4_betabin(32, a, b) for a, b in Fa]
    rho = [aff(pa32[t], _goal_r4_betabin(32, *Fb[t])) for t in range(2)]
    assert (rd(rho[0], 10), rd(rho[1], 10)) == (0.9989749161, 0.9989707713)
    assert rd(bound([rho[0]]), 5) == 0.56936                          # type-0-only Hellinger bound (the problem phase's 0.569)
    assert rd(rho[0] ** 100, 5) == 0.90252                            # rho_0^100 is NOT 0.569 (B1 mislabel corrected)
    assert rd(bound(rho), 5) == 0.41943                               # both types: the bound for the pilot that exists
    rho_c2 = [aff(pa32[t], _goal_r4_mixture(32, Fc2[t])) for t in range(2)]
    assert rd(bound(rho_c2), 5) == 0.81069
    rho_c = [aff(pa32[t], _goal_r4_mixture(32, [(mus[t], Fr(1))])) for t in range(2)]
    assert (rd(bound(rho_c), 5), rd(bound(rho_c[:1]), 5)) == (0.08192, 0.22349)
    pa128 = [_goal_r4_betabin(128, a, b) for a, b in Fa]
    assert rd(bound([aff(pa128[t], _goal_r4_betabin(128, *Fb[t])) for t in range(2)]), 5) == 0.03233
    assert rd(bound([aff(pa128[t], _goal_r4_betabin(128, *Ftheta09[t])) for t in range(2)]), 4) == 0.7156


def test_goal_r4_c1_candidate_reuse_identity():
    """r4 C1（候选，不是已证明）：内部导频复用的精确恒等式。(i) 32 条嵌在 128 条内时
    Ũ_j(k,r)=E[U_j(K128)|K32=k,r]=C(128,j)^{-1}Σ_l C(k,l)C(96,j−l)r^{j−l}，Ũ_1−r=(32/128)(k/32−r)；导频在 U_1 测量误差方差中的
    份额恰为 1/4，窄世界 Beta(20,80)/(25,75) 合并的 U_2 份额为 221679769/894945124（独立的贝塔二项联合矩求和）。
    (ii) Theorem 1 在可枚举小例（4 个前缀、导频 2 条、终值 4 条、事件 R = 生产函数二次校正矩阵非正定）上精确成立：
    P(R)=P(R')、P(R|D)−P(R'|D)=Cov(δ,1_D)/π、|·|≤σ_δ√((1−π)/π)，选择项同理。只锁定恒等式与界；
    不给出 n=200 时 σ_δ 的数值，也不说明任何规则下的两阶段 size 落在容差内。"""
    from fractions import Fraction as Fr
    from itertools import product
    from math import comb
    from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

    # (i) projection of U_j(K128) on the first 32 draws, by direct summation over K96 ~ Bin(96, r)
    m0, m1 = 32, 128
    for k, r in [(5, Fr(1, 5)), (9, Fr(1, 4)), (0, Fr(1, 10)), (20, Fr(3, 5))]:
        pmf96 = [comb(96, x) * r ** x * (1 - r) ** (96 - x) for x in range(97)]
        for j in range(1, 5):
            direct = sum(p * Fr(_goal_r4_falling(k + x, j), _goal_r4_falling(m1, j)) for x, p in enumerate(pmf96))
            formula = sum(Fr(comb(k, l) * comb(96, j - l), comb(m1, j)) * r ** (j - l) for l in range(j + 1))
            assert direct == formula
            if j == 1:
                assert formula - r == Fr(m0, m1) * (Fr(k, m0) - r)
        pmf32 = [comb(m0, x) * r ** x * (1 - r) ** (m0 - x) for x in range(m0 + 1)]
        var_pilot = sum(p * (Fr(x + 96 * r, m1) - r) ** 2 for x, p in enumerate(pmf32))
        assert var_pilot / (r * (1 - r) / m1) == Fr(1, 4)
    # pooled U_2 share in the narrow world, via E[r^s 1{K=k}] = C(m,k)(a)_{s+k}(b)_{m-k}/(a+b)_{s+m}
    c2 = [Fr(comb(m0, l) * comb(96, 2 - l), comb(m1, 2)) for l in range(3)]
    num = den = Fr(0)
    for a, b in [(Fr(20), Fr(80)), (Fr(25), Fr(75))]:
        mu4 = _goal_r4_rising(a, 4) / _goal_r4_rising(a + b, 4)
        joint = lambda s, k, m: comb(m, k) * _goal_r4_rising(a, s + k) * _goal_r4_rising(b, m - k) / _goal_r4_rising(a + b, s + m)
        U = lambda k, l, m: Fr(_goal_r4_falling(k, l), _goal_r4_falling(m, l))
        num += sum(c2[l] * c2[l2] * U(k, l, m0) * U(k, l2, m0) * joint(4 - l - l2, k, m0)
                   for k in range(m0 + 1) for l in range(3) for l2 in range(3)) - mu4
        den += sum(U(k, 2, m1) ** 2 * joint(0, k, m1) for k in range(m1 + 1)) - mu4
    assert num / den == Fr(221679769, 894945124)

    # (ii) Theorem 1 exactly: n = 4 prefixes (types 0,0,1,1), pilot m_p = 2 inside final m = 4, R = {non-PD at degree 2}
    types, mp, m = (0, 0, 1, 1), 2, 4
    atoms = {0: [(Fr(1, 5), Fr(1, 2)), (Fr(1, 2), Fr(1, 2))], 1: [(Fr(1, 4), Fr(1, 2)), (Fr(3, 5), Fr(1, 2))]}
    nonpd = {K: not endpoint_contrast_poly_cs([0.0] * 4, list(K), m, list(types), degree=2)["ok"]
             for K in product(range(m + 1), repeat=4)}
    binom = lambda n, k, r: comb(n, k) * r ** k * (1 - r) ** (n - k)
    configs = []
    for choice in product(range(2), repeat=4):
        rs = [atoms[t][c][0] for t, c in zip(types, choice)]
        prior = math_prod([atoms[t][c][1] for t, c in zip(types, choice)])
        h0 = sum(math_prod([binom(m, K[i], rs[i]) for i in range(4)]) for K in nonpd if nonpd[K])   # fresh K' ~ Bin(4, r)
        configs.append((rs, prior, h0))
    pilots = list(product(range(mp + 1), repeat=4))
    rests = list(product(range(m - mp + 1), repeat=4))
    P_K, delta, h0G = {}, {}, {}
    P_R = P_Rf = Fr(0)
    joint_terms = {}
    for Kp in pilots:
        tot = diff = sel = Fr(0)
        for rs, prior, h0 in configs:
            w = prior * math_prod([binom(mp, Kp[i], rs[i]) for i in range(4)])
            h = sum(math_prod([binom(m - mp, Kr[i], rs[i]) for i in range(4)]) for Kr in rests
                    if nonpd[tuple(a + b for a, b in zip(Kp, Kr))])            # reuse: final count K32 + K96
            tot += w; diff += w * (h - h0); sel += w * h0
            P_R += w * h; P_Rf += w * h0
        P_K[Kp], delta[Kp], h0G[Kp] = tot, diff / tot, sel / tot
        joint_terms[Kp] = diff
    assert sum(P_K.values()) == 1 and P_R == P_Rf and 0 < P_R < 1      # reuse and fresh have the same marginal law
    assert sum(P_K[k] * delta[k] for k in pilots) == 0
    var_delta = sum(P_K[k] * delta[k] ** 2 for k in pilots)
    var_0 = sum(P_K[k] * (h0G[k] - P_Rf) ** 2 for k in pilots)
    assert var_delta > 0 and var_0 > 0                                 # the pilot does tilt the non-PD event under reuse
    rules = [[k for k in pilots if delta[k] > c] for c in sorted(set(delta.values()))[:-1]]
    rules += [[k for k in pilots if sum(k) >= s] for s in range(1, 8)]
    rng = np.random.default_rng(4)
    rules += [[k for k, keep in zip(pilots, rng.random(len(pilots)) < q) if keep] for q in (0.1, 0.3, 0.5, 0.7, 0.9) for _ in range(20)]
    for D in rules:
        pi = sum(P_K[k] for k in D)
        if not 0 < pi < 1:
            continue
        reuse_minus_fresh = sum(joint_terms[k] for k in D) / pi           # [P(R∩D) − P(R'∩D)]/π from the joint enumeration
        cov = sum(P_K[k] * delta[k] for k in D)                   # Cov(δ, 1_D) = E[δ 1_D] since E[δ] = 0
        assert reuse_minus_fresh == cov / pi
        assert reuse_minus_fresh ** 2 <= var_delta * (1 - pi) / pi        # Theorem 1 (Cauchy-Schwarz), exact squares
        selection = sum(P_K[k] * h0G[k] for k in D) / pi - P_Rf
        assert selection ** 2 <= var_0 * (1 - pi) / pi
