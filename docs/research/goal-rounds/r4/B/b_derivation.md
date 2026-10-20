# Route B (r4): Le Cam two-point impossibility for the 32-pilot, with explicit failing worlds inside the compatible set

Attacker 2, research round r4. Lower-bound / necessity direction of the obstacle. All scripts in this directory; run with
`/tmp/claude-0/venv/bin/python`. Environment tag for every number below: CPU, python 3.13.16 x86_64, numpy 2.5.4 (the venv's
version; the problem-phase checks were tagged 2.5.3), scipy 1.18.1, mpmath 1.3.0, 4 cores, 2026-10-19.

Notation follows `g6_iv.py` and archive §4: prefix $i$, true risk $r_i$, type $t_i\in\{0,1\}$ ($n_t=100$ each), pilot counts
$K_i\mid r_i\sim\mathrm{Bin}(m,r_i)$, $U_j(K)=K^{(j)}/m^{(j)}$ with $E[U_j\mid r]=r^j$, endpoint contrast
$\hat\Delta_i=g(r_i)+b_{\rm type}t_i+\eta_i$, $g(r)=c+b_1r+b_2r^2$, $\eta_i$ the difference of two independent 16-draw binomial
means with $q_\pm(r)=\mathrm{clip}(r\pm g(r)/2,0,1)$, $E[\eta\mid r,t,K]=0$. The production estimator is
`endpoint_contrast_poly_cs(degree=2)` with $A=\sum_i\hat M_i$, PD rule $\lambda_{\min}(A)>10^{-9}\max(1,\lambda_{\max}(A))$,
HC1 sandwich by default and CR1 when a cluster vector is given.

Worlds (per type $t=0,1$; means $0.20/0.25$ throughout):

| name | type 0 | type 1 | role |
|---|---|---|---|
| $F_a$ | Beta(20,80) | Beta(25,75) | narrow archive world (passes at 128, check1/check1b) |
| $F_b$ | Beta(40.5,162) | Beta(50.6,151.8) | problem-phase anchor, $V\approx V_a/2$ |
| $F_\theta$ | Beta$(\mu s,(1-\mu)s)$, $s=101/\theta-1$ | same | variance scale $V=\theta V_a$, $\theta\in\{0.5,\dots,0.9\}$ |
| $F_c$ | $\delta_{0.20}$ | $\delta_{0.25}$ | literal §7.11 example, $D=0$ |
| $F_{c2}$ | $\tfrac{101}{201}\delta_{81/505}+\tfrac{100}{201}\delta_{6/25}$ | $\tfrac{1616}{3491}\delta_{329/1616}+\tfrac{1875}{3491}\delta_{29/100}$ | exact two-point, same $(\mu,V)$ as $F_a$ |
| $F_{lp}$ | 3 atoms (b3 LP) | 3 atoms | DKW-compatible, $E[S_w(128)]$ not PD |

## B1. Le Cam two-point bound for the actual pilot (both types), exact constants

**Assumptions.** (A1) Given the risks, the pilot counts are independent across prefixes and $K_i\mid r_i\sim\mathrm{Bin}(m,r_i)$
(design: selection on $y_2$ text and $e_2=0$ only; §7.2b D4). (A2) Within type $t$, $r_i\stackrel{iid}{\sim}F_t$ (template model
class; question clustering acts only through $r$ and is ignored here — see scope). (A3) The decision rule is any measurable,
possibly randomized, function of the 200 pilot counts (pre-experiment: $\hat\Delta$ does not exist yet; reuse of the 32 inside
the 128 does not add information to the pilot-stage rule).

**Count law.** For one prefix of type $t$: $p_{F_t}(k)=\binom mk\int_0^1r^k(1-r)^{m-k}\,dF_t(r)$. For $F_t=\mathrm{Beta}(a,b)$,
$p(k)=\binom mk\frac{(a)_k(b)_{m-k}}{(a+b)_m}$ (rising factorials), hence
$p(0)=\frac{(b)_m}{(a+b)_m}$ and $p(k+1)=p(k)\cdot\frac{m-k}{k+1}\cdot\frac{a+k}{b+m-k-1}$ — exactly rational for rational $a,b$
(`betabinom_exact`, asserts $\sum_kp(k)=1$ and the closed form at $k=m$). For a discrete $F=\sum_jw_j\delta_{x_j}$ with rational
atoms and weights, $p(k)=\sum_jw_j\binom mkx_j^k(1-x_j)^{m-k}$ is exactly rational (`mixture_exact`).

**Pilot law.** $P_F=(P_{F_0})^{\otimes n_0}\otimes(P_{F_1})^{\otimes n_1}$ with $n_0=n_1=100$ (A1, A2).

**Lemma 1 (affinity tensorizes).** $\rho(P,Q):=\sum_k\sqrt{p_kq_k}$. For products,
$\rho(\otimes_iP_i,\otimes_iQ_i)=\sum_{k_1..k_n}\prod_i\sqrt{p_i(k_i)q_i(k_i)}=\prod_i\sum_{k}\sqrt{p_i(k)q_i(k)}=\prod_i\rho(P_i,Q_i)$.
Hence $\rho_{\rm pilot}=\rho_0^{100}\rho_1^{100}$ with $\rho_t=\rho(P_{F_{a,t}},P_{F_{b,t}})$.

**Lemma 2 (TV vs affinity).** $\mathrm{TV}(P,Q)=\tfrac12\sum|p-q|=\tfrac12\sum|\sqrt p-\sqrt q|(\sqrt p+\sqrt q)
\le\tfrac12\sqrt{\sum(\sqrt p-\sqrt q)^2}\sqrt{\sum(\sqrt p+\sqrt q)^2}=\tfrac12\sqrt{2(1-\rho)}\sqrt{2(1+\rho)}=\sqrt{1-\rho^2}$
(Cauchy–Schwarz).

**Lemma 3 (Le Cam / Neyman–Pearson).** For any randomized rule $\varphi:\mathcal K\to[0,1]$ ("certify" with probability
$\varphi$), $E_a[1-\varphi]+E_b[\varphi]=1-\sum_k\varphi(k)(p_a(k)-p_b(k))\ge1-\sum_{k:p_a>p_b}(p_a-p_b)=1-\mathrm{TV}(P_a,P_b)$,
with equality for $\varphi=\mathbf 1\{p_a>p_b\}$ (the likelihood-ratio test). So
$$\min_\varphi\big[\mathrm{err}_I+\mathrm{err}_{II}\big]=1-\mathrm{TV}(P_a,P_b)\;\ge\;1-\sqrt{1-\rho_0^{200}\rho_1^{200}}.$$

**Corollary 4 (availability of any valid certificate).** If a rule has false-certification probability
$P_b(\text{certify})\le\gamma$ in a world $F_b$ where the (200,128) test fails, then in the passing world
$P_a(\text{certify})\le\mathrm{TV}(P_a,P_b)+\gamma$ (because $P_a(\varphi)-P_b(\varphi)\le\mathrm{TV}$ for every $\varphi$).
With $\mathrm{TV}$ replaced by $\sqrt{1-\rho_{\rm pilot}^2}$ this is a closed-form bound in the moments of nothing but the two count
laws; the exact value uses $\mathrm{TV}$ of the product law, estimated by MC of the LR statistic (b1, b1b).

**Numbers (b1_lecam_exact.py → b1_lecam_exact.out / .json; seed 20261019; affinities at 60 digits from exact rational pmfs).**
"type-0 only" is the quantity the problem phase reported (check2c); "both types" is the actual pilot.

| pair | m | $\rho_0$ | $\rho_1$ | type-0-only bound (n=100) | **both-types bound (n=200)** | NP-exact err sum (LR-test MC, SE) |
|---|---|---|---|---|---|---|
| $F_a$ vs $F_b$ | 32 | 0.998974916 | 0.998970771 | 0.56936 (= check2c 0.569) | **0.41943** | 0.5233 (0.0014) |
| | 128 | 0.993141039 | 0.993132009 | 0.13539 | **0.03233** | 0.0967 (0.0007) |
| | 512 | 0.981370949 | 0.981399246 | 0.011699 | **0.00027** | 0.0060 (0.0002) |
| $F_a$ vs $F_{c2}$ | 32 | 0.999917421 | 0.9999001 | 0.87201 | **0.81069** | 0.8517 (0.0016) |
| | 128 | 0.995340465 | 0.995031773 | 0.22086 | **0.07540** | 0.1656 (0.0009) |
| | 512 | 0.930459763 | 0.928747305 | 2.7e-7 | **1.0e-13** | 0.0000 |
| $F_a$ vs $F_c$ (point mass) | 32 | 0.995391996 | 0.995375927 | 0.22349 (= check2 0.223) | **0.08192** | b1b |
| | 128 | 0.959890915 | 0.959822404 | 1.4e-4 | **3.8e-8** | — |
| $F_a$ vs $F_d$ (double var) | 32 | 0.996652554 | 0.996743071 | 0.301 | **0.14345** | — |
| $F_a$ vs $F_{0.9}$ | 32 / 128 / 512 | | | 0.9145 / 0.7969 / 0.6946 | **0.8792 / 0.7156 / 0.5783** | b1b |
| $F_a$ vs $F_{0.8}$ | 32 / 128 / 512 | | | 0.8280 / 0.5957 / 0.4095 | **0.7583 / 0.4518 / 0.2412** | b1b |
| $F_a$ vs $F_{0.7}$ | 32 / 128 / 512 | | | 0.7415 / 0.4105 / 0.1908 | **0.6401 / 0.2419 / 0.0615** | b1b |
| $F_a$ vs $F_{0.6}$ | 32 / 128 / 512 | | | 0.6559 / 0.2552 / 0.0631 | **0.5274 / 0.1044 / 0.0075** | b1b |
| $F_a$ vs $F_{0.5}$ | 32 / 128 / 512 | | | 0.5724 / 0.1389 / 0.0126 | **0.4230 / 0.0339 / 0.0003** | — |

Reading: the problem-phase constant 0.569 is the type-0 factor only; for the pilot actually available (200 counts) the
Hellinger bound is 0.419 and the exact minimum over all rules (NP) is 0.523 ± 0.0014. The exact two-point world
$F_{c2}$ is far less separable (0.852 ± 0.002 at m=32, 0.166 at m=128).

**Scope.** Holds for iid-within-type risks, independent binomial counts, any pre-experiment rule (randomized allowed), any
stated compatible-set construction, and is one-sided: a small bound does not prove separability (the NP column is the exact
value for these pairs). **Does not claim**: that the bound is tight for rules restricted to a class (it is attained by the LR
test only); anything about rules that use the steered-arm outcomes; anything under question-level dependence of $r$ (with
positive within-question dependence the effective pilot is smaller, which can only make an iid-based information argument
more pessimistic for the certificate, but the two-point constants would change).

## B2. The failure at $F_b$ is a property of the count design: $g$-free PD event, grid over the bounded $g$-class, both SEs

**Score decomposition (exact).** Under $b_{\rm type}=0$, $\beta=(c,b_1,b_2,0)$, $x^*=(1,r,r^2,t)$. The production
$\hat m_i=(U_0y_i,U_1y_i,U_2y_i,t_iy_i)$ and $(\hat M_i\beta)_a=cU_a+b_1U_{a+1}+b_2U_{a+2}$ for $a=0,1,2$,
$(\hat M_i\beta)_3=t_i(c+b_1U_1+b_2U_2)$. With $y_i=c+b_1r_i+b_2r_i^2+\eta_i$:
$$\psi_{i,a}=b_1\,(U_ar_i-U_{a+1})+b_2\,(U_ar_i^2-U_{a+2})+U_a\eta_i,\quad a=0,1,2;\qquad
\psi_{i,3}=t_i\big[b_1(r_i-U_1)+b_2(r_i^2-U_2)+\eta_i\big].$$
So $c$ cancels exactly, $E[\psi_i\mid r_i]=0$, and $\mathrm{Cov}(\psi_i\mid r_i)=\Sigma_{\rm meas}(b_1,b_2;r_i,m)+\mathrm{Var}(\eta_i\mid r_i)\,E[\hat x_i\hat x_i^\top\mid r_i]$
(the cross term vanishes since $E[\eta\mid K,r]=0$). The matrix $A=\sum_i\hat M_i$ is a function of $(K,t)$ alone.

**Proposition 5 (PD event is $g$-, $\eta$- and SE-free).** The event $\{\texttt{ok}=\texttt{True}\}$ of
`endpoint_contrast_poly_cs` depends only on $(K,t,m,\text{degree})$; it is the same for every $g$ in any class, every
$\mathrm{Var}(\eta\mid r)$ (16- or 32-draw arms, or $\eta\equiv0$) and for HC1 vs CR1. *Proof*: the function evaluates the PD rule on
$A$ before touching $y$ or the cluster vector. Checked bit-for-bit on 300 draws × 10 $g$ × 3 $\eta$-laws × 2 SEs = 18 000
production calls (b2b_pd_event_invariance.py → .out: identical `ok` and `min_eig` in all draws).

**Consequence.** Under $F_b$ at $(200,128)$ the pooled non-PD rate over the 10 $g$-cells is $0.1235$, exact 95% CI
$[0.1190,0.1281]$ (20 000 reps, b2b .json) — above the 2% tolerance for the entire bounded class and both SEs. Therefore
"$F_b$ fails at 128" needs no assumption on $g$ or on $\mathrm{Var}(\eta\mid r)$; only the width/size parts of the verdict depend on $g$.

**Grid over the class (b2_failing_worlds_gclass.py → .out/.json; base seed 4242, 2000 reps per cell, 50 question clusters of 2+2).**
$g$-grid: $g_0\equiv0$; $g_1=0.18-0.8r$; $g_2=0.26-1.6r+2r^2$; $g_3=0.30-1.2r+0.8r^2$; $g_4=-0.2+1.2r$; $g_5=-r+r^2$;
$g_6=0.02+1.5r-1.5r^2$; $g_7=-0.02-1.5r+1.5r^2$; $g_8=1.5r^2$; $g_9=-1.5r^2$; all have $\max_{[0,1]}|g|\le1$ (exact vertex check)
and clip rates $\le6.1\times10^{-4}$ (reported per cell).

| world, m | non-PD (pooled, exact CI) | size HC1 range | size CR1 range | width q90 given ok, HC1 (range over g) | q90 with ∞ for non-PD | verdict |
|---|---|---|---|---|---|---|
| $F_a$, 128 | 0.0056 [0.0046, 0.0067] | 0.042–0.0535 | 0.0465–0.060 | 0.135–0.149 | 0.136–0.150 (HC1), 0.139–0.153 (CR1) | pass for all g under HC1; CR1 fails width only for $g_4$ (0.153) |
| $F_a$, 512 | 0 [0, 0.00018] | 0.046–0.0615 | 0.0535–0.0645 | 0.103–0.110 | ≤0.115 | pass |
| $F_b$, 128 | 0.1235 [0.1190, 0.1281] | 0.0185–0.026 | 0.0215–0.0305 | 0.43–0.64 | ∞ | fail (non-PD, width; size on the low side) for all g, both SEs |
| $F_b$, 512 | 0 [0, 0.00018] | 0.0455–0.062 | 0.0505–0.067 | 0.127–0.136 | ≤0.141 | pass for all g, both SEs |
| $F_{c2}$, 128 | 0.1153 [0.1074, 0.1237] | 0.0285–0.0315 | 0.028–0.033 | 0.277–0.284 | ∞ | fail |
| $F_{c2}$, 512 | 0 [0, 0.0006] | 0.0485–0.052 | 0.0495–0.0565 | 0.110–0.111 | ≤0.115 | pass |
| $F_{0.9}$, 128 ($g_1$) | 0.012 [0.0077, 0.0178] | 0.037 | 0.046 | 0.155 | 0.158 / 0.163 | fail width (marginal) |
| $F_{0.8}$, 128 ($g_1$) | 0.023 [0.0169, 0.0306] | 0.0385 | 0.0415 | 0.177 | 0.188 / 0.192 | fail non-PD (marginal), width |
| $F_{0.7}$, 128 ($g_1$) | 0.0415 [0.033, 0.051] | 0.039 | 0.0465 | 0.233 | 0.315 / 0.319 | fail |
| $F_{0.6}$, 128 ($g_1$) | 0.075 [0.064, 0.087] | 0.028 | 0.0295 | 0.359 | 1.75 / 1.73 | fail |
| $F_{\theta}$, 512 ($g_1$), θ=0.6–0.9 | 0 | 0.049–0.0635 | 0.052–0.065 | 0.112–0.127 | ≤0.131 | pass |

Population quantities for the same worlds (b2 .out "POP"): $D(F)=1/(4+q)$ with $q=\Delta\mu_X^\top\bar H_w^{-1}\Delta\mu_X$
($\bar H_w$ = pooled within-type $\mathrm{Cov}(r,r^2)$; derivation: $\mathrm{Var}(t)=\tfrac14$, $\mathrm{Cov}(t,X)=\Delta\mu_X/4$,
$\mathrm{Var}(X)=\bar H_w+\Delta\mu_X\Delta\mu_X^\top/4$, Sherman–Morrison gives $D=\tfrac14-\tfrac1{16}\cdot\tfrac{4q}{4+q}=\tfrac1{4+q}$):
$D(F_a)=0.1827$, $D(F_b)=0.1437$, $D(F_{c2})=0.1829$, $D(F_{0.8})=0.1712$; A1 pooled $\lambda_{\min}E[S_w(128)]$ (production
`corrected_schur_mean`, $n_t=100$): $F_a$ 7.99e-6, $F_b$ 2.80e-6, $F_{c2}$ 2.92e-6, $F_{0.8}$ 5.66e-6. So $F_{c2}$ has the
same $D$ as $F_a$ and still fails at 128: the failure is the PD margin against the U-statistic noise, not the type coefficient's
population identification strength $D$.

**Scope.** Finite-sample simulation statements at $(n,m)\in\{200\}\times\{128,512\}$, null $b_{\rm type}=0$, 16-draw arms,
HC1 and CR1 with 50 clusters of 2+2, MC SE ≈ 0.005 for sizes and ≈ 0.007 for non-PD at 2000 reps; the non-PD part holds for
the whole $g$-class exactly, the width/size parts on the 10-point grid. **Does not claim**: that width/size are bounded over the
whole class (Chebyshev-extreme $g=8r^2-8r+1$ is in $\{|g|\le1\}$ but violates $q_\pm\in[0,1]$ in the narrow world and was not
run); that $F_a$ passes for every $g$ under CR1 (it fails the 0.15 width at $g_4$ by 0.003); anything about power.

## B3. The compatible set of a narrow pilot contains failing and nearly-unidentified worlds (DKW band + LP)

**Two-point construction (exact).** For a type with mean $\mu$ and variance $V$, a two-point law with atoms
$x_1=\mu-d_1<\mu<x_2=\mu+d_2$ and weights $w_1=d_2/(d_1+d_2)$, $w_2=d_1/(d_1+d_2)$ has mean $\mu$ and variance $d_1d_2$.
Choosing $d_2=1/25$: type 0 ($\mu=1/5$, $V=4/2525$) gives $d_1=4/101$, $x_1=81/505$, $w_1=101/201$; type 1 ($\mu=1/4$,
$V=3/1616$) gives $d_1=75/1616$, $x_1=329/1616$, $w_1=1616/3491$ (checked exactly in b1: moments table in the json). Within each
type $r^2=(x_1+x_2)r-x_1x_2$ on the support, so the within-type partial variance of $r^2$ after $(1,r)$ is zero; the pooled
$\bar H_w$ is still PD because the two types' affine relations differ ($x_1+x_2=0.4004$ vs $0.4936$), which is why $F_{c2}$
passes at 512 but fails at 128 (its $\lambda_{\min}E[S_w(128)]=2.9\times10^{-6}$ is $F_b$'s value, with $F_a$'s $V$ and $D$).

**DKW band as the stated $C_\gamma$.** With $\hat G_t$ the empirical CDF of the 100 counts of type $t$ at $m=32$,
$C_\gamma^{\rm DKW}=\{F:\sup_k|G_{F,t}(k)-\hat G_t(k)|\le\varepsilon_{100}(\gamma)\ \forall t\}$, $\varepsilon_n(\gamma)=\sqrt{\ln(2/\gamma)/(2n)}$
(0.1358 / 0.1224 / 0.0991 at $\gamma$ = 0.05 / 0.10 / 0.28). Massart's DKW inequality holds for every distribution function,
discrete included (the empirical process of $F$ is the image of the uniform one under the quantile map), so each type's band
has coverage $\ge1-\gamma$ (observed 0.9856 per type, 0.970 jointly at $\gamma=0.05$; b3 .out "INCL F_a").

**Inclusion of failing worlds (b3_dkw_band_lp.py → .out/.json; seed 777; 5000 narrow pilots).** $P(F\in C_\gamma^{\rm DKW}$ for both types $\mid F_a)$:

| world | γ=0.05 | γ=0.10 | γ=0.28 | sup-distance of its count CDF to $F_a$'s (type 0 / 1) |
|---|---|---|---|---|
| $F_b$ (fails at 128, passes 512) | 0.962 | 0.916 | 0.736 | 0.0178 / 0.0175 |
| $F_{c2}$ (fails at 128, passes 512) | 0.971 | 0.941 | 0.778 | 0.0039 / 0.0047 |
| $F_{0.8}$ (fails at 128 marginally) | 0.968 | 0.932 | 0.769 | 0.0068 / 0.0067 |
| $F_c$ point mass ($D=0$; non-PD 0.89 at 128, 0.86 at 512, check1b) | 0.921 | 0.852 | 0.616 | 0.0375 / 0.0367 |
| $F_d$ double variance | 0.959 | 0.905 | 0.692 | 0.0323 / 0.0318 |

So with probability ≥ 0.92 the DKW set at γ=0.05 contains a world with $D=0$: the sup over $C_\gamma^{\rm DKW}$ of the
non-PD rate is ≥ 0.89 and of the width is ∞ (unless the certificate restricts to $D\ge d_0$ — and then $F_{c2}$, with
$D=D(F_a)$, is still inside with probability 0.97 and still fails).

**LP (linear in $w$).** On the grid $x_j=j/400$, with $\mu_1,\mu_2$ fixed (true values or the pilot's U-statistic estimates),
the A1 Schur mean $E[S_{ab}(m)]=\mu_{a+b}-\mu_a\mu_b-C_{ab}/n_t$, $C_{ab}=E[U_aU_b]-\mu_a\mu_b$, $E[U_aU_b]=\sum_jc_{ab,j}\mu_j$
(coefficients from the production `binomial_factorial_joint_moment` on unit moment vectors) is affine in $(\mu_3,\mu_4)$,
hence $v^\top E[S_t(128)]v$ is linear in $w$ for a fixed direction $v$ (the $\lambda_{\min}$-eigenvector of the pooled
$E[S_w(128)]$ at $F_a$). Minimizing it over $C_{0.05}^{\rm DKW}$ (per type; HiGHS) gives 3-atom solutions with
$v^\top E[S_t(128)]v=-1.24\times10^{-7}$ / $-1.34\times10^{-7}$ (true moments) and a pooled world $F_{lp}$ with
$\lambda_{\min}E[S_w(128)]=-1.29\times10^{-7}<0$ (production `corrected_schur_mean`), $D(F_{lp})=0.0244$ ($q=37$),
$\lambda_{\min}\bar H_w=7.4\times10^{-9}$. Atoms: type 0 $\{0.18,0.1825,0.285\}$ w $\{0.368,0.452,0.180\}$, type 1
$\{0.1875,0.2775,0.28\}$ w $\{0.322,0.083,0.595\}$ — nearly a common two-point support with type-dependent weights, i.e. a
nearly unidentified type effect. Production test at $F_{lp}$ ($g_1$, seeds 100119/100503): non-PD 0.6445 [0.623, 0.666] at 128
and 0.583 [0.561, 0.605] at 512; width q50 given ok 0.20 / 0.29, q90 2.7 / 5.5; oracle q50 0.255. Le Cam vs $F_a$: both-types
bound 0.592 at m=32 but 0.005 at m=128 (b3 .json "lecam_vs_F_a") — inseparable from the narrow world at 32, separable at 128.
The LP range of $V$ inside the band with $\mu_1$ fixed is $[0,0.039]$ (type 0, true $\mu_1$): the DKW set is a very weak
constraint on $V$; the pilot's U-statistic $\hat V$ (sd 0.00095, check2) is far more informative but no construction can beat
the NP constants of B1.

**Scope.** Existence statements for explicit worlds and one stated confidence construction (DKW, any γ); inclusion
probabilities are MC with SE ≤ 0.007. **Does not claim**: that the LP solution is the extreme point of $C_\gamma$ (concave
minimization was replaced by a fixed direction, so the value is an upper bound on $\min_{C_\gamma}\lambda_{\min}$, i.e. a lower
bound on the severity of the sup); that a multinomial-likelihood region would contain the same worlds with the same
probabilities (its constants are different; the B1 bound applies to every construction).

## What the three claims imply for the obstacle's criterion

* 32-stage: the pilot cannot certify 128 — exact NP minimum error sum 0.523 (vs $F_b$) and 0.852 (vs $F_{c2}$); any
  certificate with ≤ 5% false certification against $F_{c2}$ fires in the narrow world at most $0.148+0.05\approx0.20$ of the
  time; against $F_b$ at most $0.477+0.05=0.527$. Outcome (a) "32 already certified" is unavailable in the narrow regime; the
  DKW compatible set even contains $D=0$ worlds with probability 0.92.
* 128-stage: all examined worlds with $\theta\ge0.5$, $F_b$, $F_{c2}$ pass at 512; the nearly-unidentified $F_{lp}$ and the
  point mass are separable from $F_a$ at m=128 (bounds 0.005 / 4e-8). But the marginal-failure worlds $F_{0.9}$ (q90 width
  0.158–0.163) and $F_{0.8}$ (0.188–0.192, non-PD 2.3%) are not: both-types bounds 0.716 and 0.452 at m=128. So outcome (c)
  "128 certified at the 128-stage" under the proposed tolerances (q90 ≤ 0.15, non-PD ≤ 2%) is obstructed with error sum ≥ 0.72;
  under relaxed tolerances (q90 ≤ 0.20, non-PD ≤ 3%) the obstruction pair becomes $(F_a,F_{0.7})$ with bound 0.242 (NP value in
  b1b). The residual risk carried to the 128-stage is therefore a *tolerance decision*, not a fact about the data.
* The 32-stage impossibility is robust to the tolerance (F_b's non-PD 12.4% and width ∞ fail any reasonable tolerance), robust
  over the bounded g-class and both SEs (B2), and not a Beta artefact (F_c2, F_lp).

## Appendix: exact (Neyman–Pearson) minima per stage (b1b_np_exact_stages.py → .out/.json; seed 20261020; 200 000 pilots per side)

| stage m | pair | Hellinger bound (both types) | **NP-exact err sum (SE)** | TV exact | availability ≤ TV+0.05 |
|---|---|---|---|---|---|
| 32 | $F_a$ vs $F_b$ | 0.4194 | **0.5210 (0.0014)** [b1 seed 20261019: 0.5233] | 0.479 | 0.529 |
| 32 | $F_a$ vs $F_c$ point mass | 0.0819 | **0.1735 (0.0009)** | 0.827 | 0.876 |
| 32 | $F_a$ vs $F_{c2}$ | 0.8107 | **0.8537 (0.0016)** | 0.146 | 0.196 |
| 32 | $F_a$ vs $F_{lp}$ | 0.5920 | **0.6701 (0.0015)** | 0.330 | 0.380 |
| 32 | $F_a$ vs $F_{0.6}$ / $F_{0.7}$ / $F_{0.8}$ / $F_{0.9}$ | 0.527 / 0.640 / 0.758 / 0.879 | **0.616 / 0.710 / 0.807 / 0.902** (≤0.0016) | 0.384 / 0.290 / 0.193 / 0.099 | 0.434 / 0.340 / 0.243 / 0.148 |
| 128 | $F_a$ vs $F_b$ | 0.0323 | **0.0967 (0.0007)** | 0.903 | 0.953 |
| 128 | $F_a$ vs $F_{c2}$ | 0.0754 | **0.1638 (0.0009)** | 0.836 | 0.886 |
| 128 | $F_a$ vs $F_{lp}$ | 0.0051 | **0.0317 (0.0004)** | 0.968 | 1.000 |
| 128 | $F_a$ vs $F_{0.6}$ / $F_{0.7}$ / $F_{0.8}$ / $F_{0.9}$ | 0.104 / 0.242 / 0.452 / 0.716 | **0.204 / 0.355 / 0.550 / 0.772** (≤0.0015) | 0.796 / 0.645 / 0.450 / 0.228 | 0.846 / 0.695 / 0.500 / 0.278 |
| 512 | $F_a$ vs $F_{0.7}$ / $F_{0.8}$ / $F_{0.9}$ | 0.0615 / 0.241 / 0.578 | **0.144 / 0.356 / 0.658** (≤0.0015) | 0.857 / 0.644 / 0.342 | 0.907 / 0.694 / 0.392 |

The LR test between $F_a$ and $F_\theta$ is the optimal rule for that pair, so these NP values are the exact frontier for
the two-point problem; they are still one-sided for the full compatible set (other failing worlds may be closer).
