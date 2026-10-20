# Route A — overlap-and-PD-margin certificate from pilot U-statistics (r4, attacker 1)

Scratch directory: `.../goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_/`
Scripts: `route_a_lib.py` (library), `a1_exact_check.py` (claim 1, exact), `a2_two_stage_sim.py` + `a2_summarize.py` (claim 2, production
function), `a3_rigorous_constants.py` (claim 3). Environment: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19.
Production object: `endpoint_contrast_poly_cs` (degree 2, PD rule $\lambda_{\min}>10^{-9}\max(1,\lambda_{\max})$, HC1 / CR1), imported from
`sycophancy_phase0/analysis/g6_iv.py`; every size / width number below is produced by that function.

## 0. Setting and assumptions (all used below)

* Prefixes $i=1,\dots,n$, $n=200$; type $t_i\in\{0,1\}$ fixed by design with $n_0=n_1=100$, $w_1=n_1/n=\tfrac12$.
* Risk $r_i\mid t_i\sim F_{t_i}$ i.i.d. within type; $\mu_{j,t}=\mathbb E[r^j\mid t]$. Prefixes independent (the question
  clustering of the design enters only through CR1 and the cluster covariance of the pilot moments; **no question effect in $r$
  or in $\Delta$** — the stated model).
* Counts $K_i\mid r_i\sim\mathrm{Bin}(m,r_i)$, common $m$; $U_j(K)=(K)_{\underline j}/(m)_{\underline j}$, $\mathbb E[U_j\mid r]=r^j$.
* Endpoint $y_i=\hat\Delta_i=g(r_i)+b_{\rm type}t_i+\eta_i$, $g(r)=\beta_0+\beta_1r+\beta_2r^2$, $\mathbb E[\eta_i\mid r_i,t_i,K_i]=0$,
  $\operatorname{Var}(\eta_i\mid r_i)=\sigma^2(r_i)$ (two independent arms of $n_{\rm arm}=16$ draws with
  $q_\pm=r\pm g(r)/2$: $\sigma^2(r)=[q_+(1-q_+)+q_-(1-q_-)]/16=[2r(1-r)-g(r)^2/2]/16$ when $q_\pm\in[0,1]$, so
  $\sigma^2(r)\le r(1-r)/8$; with clipping only the trivial bound $\sigma^2\le1/32$ holds — the clipping rate is reported).
* Null $b_{\rm type}=0$ for size; the first-order width does not depend on $b_{\rm type}$.
* The pilot is INTERNAL: the 32 `sel` counts are the first 32 of the 128 ($K^{128}=K^{32}+K^{96}$), and of the 512.

Notation of the production function: $x^*=(1,r,r^2,t)$; per prefix $\hat M_i$ has entries $U_{a+b}(K_i)$ ($a,b\le2$), $U_a(K_i)t_i$,
$t_i$; $\hat m_i=(U_a(K_i)y_i,\;t_iy_i)$; $\hat\beta=A^{-1}\sum_i\hat m_i$, $A=\sum_i\hat M_i$; score
$\psi_i(\beta)=\hat m_i-\hat M_i\beta$; sandwich $A^{-1}\hat BA^{-1}$ with $\hat B=\frac{n}{n-4}\sum_i\hat\psi_i\hat\psi_i^\top$ (HC1) or
the cluster version (CR1).

## 1. Claim 1 — closed-form first-order sandwich of the type coefficient (proved)

**1.1 Score is conditionally mean-zero.** $\mathbb E[\hat M_i\mid r_i,t_i]=x_i^*x_i^{*\top}$ and
$\mathbb E[\hat m_i\mid r_i,t_i]=x_i^*(g(r_i)+b_{\rm type}t_i)=x_i^*x_i^{*\top}\beta$ (because $\mathbb E[U_j\mid r]=r^j$,
$\mathbb E[\eta\mid r,t,K]=0$, and $U_j$ is a function of $K$ only). Hence $\mathbb E[\psi_i(\beta)\mid r_i,t_i]=0$, and
the $\psi_i$ are independent across $i$ with $\mathbb E\psi_i=0$.

**1.2 Expansion.** $\hat\beta-\beta=A^{-1}\sum_i\psi_i(\beta)$. With $\bar A=A/n\to Q:=\sum_tw_t\mathbb E_t[x^*x^{*\top}]$ (LLN) and
$n^{-1/2}\sum_i\psi_i\Rightarrow N(0,B)$, $B:=\sum_tw_t\mathbb E_t[\psi\psi^\top]$ (Lindeberg CLT, bounded summands when $\hat\Delta\in[-1,1]$),
$\sqrt n(\hat\beta-\beta)\Rightarrow N(0,Q^{-1}BQ^{-1})$. The first-order SE of $\hat b_{\rm type}$ is
$\mathrm{se}_1=\sqrt{[Q^{-1}BQ^{-1}]_{44}/n}$ and the first-order 95% full CI width is $w_1=2\cdot1.96\cdot\mathrm{se}_1$. HC1 and CR1
estimate the same $B$ at first order (under independence given risks the cluster cross terms have zero mean).

**1.3 Block inverse / overlap.** Partition $Q=\begin{pmatrix}Q_{xx}&q\\q^\top&w_1\end{pmatrix}$ with $x=(1,r,r^2)$,
$Q_{xx}=\sum_tw_t\mathbb E_t[xx^\top]$ (entries $\mu_{a+b}=\sum_tw_t\mu_{a+b,t}$, $a,b\le2$), $q=\mathbb E[xt]=w_1(1,\mu_{1,1},\mu_{2,1})^\top$.
Let $\gamma=Q_{xx}^{-1}q$ (population regression of $t$ on $x$) and
$$D(F):=w_1-q^\top Q_{xx}^{-1}q=\min_{c\in\mathbb R^3}\mathbb E[(t-c^\top x)^2],$$
the residual variance of type after $(1,r,r^2)$ — the *overlap* / identification strength of the type coefficient. Then
$Q\binom{-\gamma}{1}=\binom{-Q_{xx}\gamma+q}{-q^\top\gamma+w_1}=\binom{0}{D}$, so $Q^{-1}e_4=D^{-1}\binom{-\gamma}{1}$ and
$$[Q^{-1}BQ^{-1}]_{44}=D^{-2}\,(-\gamma,1)B(-\gamma,1)^\top=D^{-2}\sum_tw_t\mathbb E_t[\varphi^2],\qquad
\varphi:=\psi_4-\gamma^\top\psi_{1:3}.$$
$D$ needs per-type moments $\le4$ only; $D=0$ iff $t$ is a.s. a quadratic function of $r$ (e.g. the point-mass world
$0.20/0.25$), and then $w_1=\infty$. $D$ is a minimum of functions linear in the moments, hence **concave** in the moment vector.

**1.4 The type score in closed form.** Write $\delta_j=U_j-r^j$ ($\delta_0=0$, $\mathbb E[\delta_j\mid r]=0$). From
$\psi_a=U_ay-\sum_bU_{a+b}\beta_b-U_at\,b_{\rm type}$ and $y=\sum_b\beta_br^b+b_{\rm type}t+\eta$:
$$\psi_a=U_a\eta+\sum_{b=0}^2\beta_b\,(U_ar^b-U_{a+b}),\quad a=0,1,2;\qquad
\psi_4=t\eta-t\sum_{b}\beta_b\delta_b .$$
Therefore, with $\rho(r,t):=t-\gamma^\top x$ (population residual of $t$) and $u=(1,U_1,U_2)$,
$$\varphi=\eta\,(t-\gamma^\top u)+Z=\eta\,(\rho-\gamma_1\delta_1-\gamma_2\delta_2)+\beta_1\zeta_1+\beta_2\zeta_2,$$
$$\zeta_b=(t-\gamma_0)(r^b-U_b)-\gamma_1(U_1r^b-U_{1+b})-\gamma_2(U_2r^b-U_{2+b}),\qquad b=1,2$$
($\zeta_0\equiv0$: the intercept of $g$ carries no measurement error). Each $\zeta_b=c_b+\sum_{j=1}^4\alpha_{b,j}U_j$ with
$c_b=(t-\gamma_0)r^b$ and
$$\alpha_{b,j}=-(t-\gamma_0)\mathbf 1[j=b]-\gamma_1r^b\mathbf 1[j=1]+\gamma_1\mathbf 1[j=1+b]-\gamma_2r^b\mathbf 1[j=2]+\gamma_2\mathbf 1[j=2+b],$$
and $\mathbb E[\zeta_b\mid r,t]=0$.

**1.5 Conditional second moment.** Because $\eta$ is independent of $K$ given $(r,t)$ with mean zero, the cross term vanishes and
$$\boxed{\;\mathbb E[\varphi^2\mid r,t]=\sigma^2(r)\big[\rho^2+\tilde\gamma^\top V^{(2)}(r)\tilde\gamma\big]
+\sum_{b,d\in\{1,2\}}\beta_b\beta_d\,\alpha_b(r,t)^\top V^{(4)}(r)\,\alpha_d(r,t)\;}$$
with $\tilde\gamma=(\gamma_1,\gamma_2)$ and $V^{(k)}(r)_{jl}=\operatorname{Cov}(U_j,U_l\mid r)=J_{jl}(r)-r^{j+l}$, $1\le j,l\le k$, where
(A1 identity before averaging over $r$)
$$J_{jl}(r)=\mathbb E[U_jU_l\mid r]=\sum_{\ell=\max(0,j+l-m)}^{\min(j,l)}
\frac{\binom j\ell\binom l\ell\,\ell!\,(m)_{\underline{j+l-\ell}}}{(m)_{\underline j}(m)_{\underline l}}\,r^{\,j+l-\ell}.$$
(For $\zeta_b\zeta_d$: $\mathbb E[\zeta_b\zeta_d\mid r,t]=\sum_{jl}\alpha_{b,j}\alpha_{d,l}J_{jl}-c_bc_d$ and $c_b=-\sum_j\alpha_{b,j}r^j$,
which gives $\sum_{jl}\alpha_{b,j}\alpha_{d,l}(J_{jl}-r^{j+l})$.)

**1.6 Moments.** Every term is a polynomial in $r$ (for polynomial $\sigma^2$) of degree $\le8$: $\sigma^2$ (deg 4) $\times\rho^2$
(deg 4); $\sigma^2\times V^{(2)}_{22}$ (deg $\le3$) ; $\alpha\alpha V^{(4)}$ (deg $\le7$). Averaging over $F_t$,
$$\mathbb E_t[\varphi^2]=\sum_{j\le8}c_{j,t}(\gamma,\beta,m)\,\mu_{j,t},$$
so $w_1=2\cdot1.96\,\sqrt{\sum_tw_t\mathbb E_t[\varphi^2]/(nD^2)}$ is an explicit function of **per-type moments $\le8$, $w_1$, $m$,
$n$, $g$ and $\sigma^2(\cdot)$** (the A1 bound $\min(m,4p)=8$ is attained). As $m\to\infty$, $V^{(k)}\to0$ and
$w_1\to w_{\rm oracle}=2\cdot1.96\sqrt{\mathbb E[\rho^2\sigma^2]/(nD^2)}$, the OLS width with true $r$.

**1.7 Uniform-in-$g$ version.** For $\mathcal G=\{g:|g|\le1\text{ on }[0,1]\}$ and no clipping, $\sigma^2(r)\le r(1-r)/8$ and the $g$-term
is $\beta_{1:2}^\top\Omega\beta_{1:2}$ with $\Omega_{bd}=\sum_tw_t\mathbb E_t[\alpha_b^\top V^{(4)}\alpha_d]\succeq0$. The admissible
$(\beta_1,\beta_2)$ form the compact convex symmetric set $\{\operatorname{osc}_{[0,1]}(\beta_1r+\beta_2r^2)\le2\}$; the sup of the PSD
quadratic is attained on its boundary (radius $2/\operatorname{osc}$ in each direction), found by a 1440-point angular grid plus bounded
refinement; it is attained at the Chebyshev extreme $g=1-8r+8r^2$ in all worlds tested (`a1_exact_check.out`). Coefficient-bounded
classes $\mathcal G_c=\mathcal G\cap\{|\beta_1|,|\beta_2|\le c\}$ use the min of the two radii.

**1.8 Exact check** (`a1_exact_check.py`, Fractions): for three discrete risk laws (2–3 support points per type), $m\in\{4,8,10\}$ ($m=4=2p$
exercises the truncated $\ell$-sums), $w_1\in\{\tfrac12,\tfrac25\}$, rational $g$, the brute-force $[Q^{-1}BQ^{-1}]_{44}$ (enumeration of
$K$, full $4\times4$ $B$, exact inverse) **equals** $D^{-2}\sum_tw_t\mathbb E_t\varphi^2$ as rational numbers (e.g.
$1233198574923483/1630867456000000$), the block-inverse identity holds exactly, and $\mathbb E_t[J_{jk}(r)]$ equals the production
`binomial_factorial_joint_moment` for all $j,k\le4$, $j+k\le8$.

**1.9 Numbers at $(n,m)=(200,\cdot)$, $g=0.18-0.8r$** (`a1_exact_check.json`, `first_order_table`; simulated medians from
`a2_summary.json`):

| world | $D$ | $\gamma$ | $w_1$ m=32 | $w_1$ m=128 | $w_1$ m=512 | oracle | $\sup_{\mathcal G}w_1$ m=128 | $\sup_{\mathcal G_2}$ m=128 |
|---|---|---|---|---|---|---|---|---|
| narrow Beta(20,80)/(25,75) | 0.1827 | (−1.13, 9.23, −8.43) | 0.1444 | 0.1071 | 0.0982 | 0.0952 | 0.1639 | (see json) |
| half-var Beta(40.5,162)/(50.6,151.8) | 0.1437 | (−2.08, 14.57, −13.40) | 0.2360 | 0.1428 | 0.1168 | 0.1075 | 0.2312 | |
| wide Beta(2,8)/(2.5,7.5) | 0.2399 | (0.27, 1.39, −1.16) | 0.0860 | 0.0809 | 0.0796 | 0.0792 | 0.1159 | |

The comparison with the production function's simulated width distribution (median given ok and q90, ratio to $w_1$) is in
`a2_summary.json` → `unconditional.*.ratio_*`. Summary (filled from the run): see §4.

## 2. Claim 2 — the pilot certificate, its availability and its two-stage validity (candidate)

**2.1 Pilot estimators.** From the 32 `sel` counts of type $t$: $\hat\theta_t=n_t^{-1}\sum_iU_{1:8}(K_i)$, unbiased for
$\theta_t=(\mu_{1,t},\dots,\mu_{8,t})$ (needs $m\ge8$); question-cluster covariance $\hat\Sigma_t$ (50 clusters of 2 per type in the
simulated design; $G/(G-1)$ factor). Plug-in $\hat D=D(\hat\theta)$, $\hat w_1^{\sup}(m)$, $\hat\kappa(m)$.

**2.2 Jensen direction (proved, one line).** $D$ is concave in the moment vector (§1.3) and $\hat\theta$ is unbiased, so
$\mathbb E\hat D\le D$: the plug-in overlap is biased downward (conservative for a lower bound in the mean). Simulated: see §4.

**2.3 Delta-method one-sided bounds.** $\mathrm{LCB}(f)=f(\hat\theta)-z_{0.95}\sqrt{\nabla f^\top\hat\Sigma\nabla f}$, $\mathrm{UCB}$ likewise,
gradient by central differences (relative step $10^{-6}$; stable to 0.2% against $10^{-5}$, unstable at $10^{-4}$ in the narrow world —
the functionals are strongly non-linear at the scale of the pilot noise there, see 2.6). Coverage is **asymptotic** ($n_t=100$),
not exact; the certificate is a stated construction at $\gamma=0.05$ one-sided per component.

**2.4 Certificate** $\mathcal C(\text{pilot};m,\mathcal G',d_0,w_0)$ fires iff $\mathrm{LCB}(D)\ge d_0$ and
$\mathrm{UCB}(w_1^{\sup_{\mathcal G'}}(m))\le w_0$; the A1 PD margin
$\kappa(m)=\lambda_{\min}\big(\mathbb E[S_w(m)],\bar N(m)\big)$ (generalised eigenvalue of the Schur-complement mean
$\sum_tw_t[H_t-C_t(m)/n_t]$ against the mean measurement-noise covariance $\bar N(m)=\sum_tw_t\mathbb E_t\operatorname{Cov}((U_1,U_2)\mid r)$,
moments $\le4$) is reported as an optional third condition. What the certificate guarantees **by derivation**: when it fires, the
first-order width is $\le w_0$ for every $F$ in the delta-method confidence set and every $g\in\mathcal G'$, and $D\ge d_0>0$ there, so the
type coefficient is first-order identified. What it does **not** guarantee by derivation: finite-sample size, the non-PD rate, and the
tail (q90) of the realised width — these are assessed by simulation with the production function (2.5) and are the CE-B1-type
quantities that low moments do not determine.

**2.5 Simulation design** (`a2_two_stage_sim.py`): worlds narrow / half-variance / wide, $g$ linear $(0.18,-0.8,0)$ with 4000
replications each, plus quadratic $g$ for narrow $(0.26,-1.6,2)$ and wide $(0.30,-1.2,0.8)$ with 2000; 50 questions × (2 type-0 + 2
type-1); $K^{128}=K^{32}+K^{96}$, $K^{512}=K^{128}+K^{384}$ (reuse) and an independent $K^{\rm fresh,128}$; production calls at
32 (HC1, CR1), 128 reuse (HC1, CR1), 128 fresh (HC1), 512 reuse (HC1); the certificate at the 32-stage (targets 32, 128) and at the
128-stage (targets 128 = self-reuse, 512). Tolerance: $|{\rm size}-0.05|\le0.02$, non-PD $\le2\%$, q90(width) $\le0.15$ with width
$=\infty$ when `ok=False`. Thresholds $d_0=0.05$, $w_0=0.15$ (sensitivity grid in `a2_summary.json`).

**2.6 Why the certificate cannot fire in the narrow regime (mechanism, pre-registered expectation).** $\hat D$ and $\hat w_1$ depend on
$\hat Q_{xx}^{-1}$; in the narrow world $\lambda_{\min}(H_w)\approx8\cdot10^{-6}$, so the direction "$r^2$ after $r$" is below the pilot
noise (check2: $\lambda_{\min}(\hat H_w)\le0$ in 69% of pilots) and $\hat\gamma$, $\hat D$ inherit an unbounded sampling spread
(a single pilot: $\hat D=0.145$, delta-sd 0.12 vs $D=0.18$). This is the pilot-information limit that Route B quantifies; the
certificate's unavailability there is the correct behaviour, not a defect of the construction.

## 3. Claim 3 — the explicit-constant finite-sample branch is vacuous at the pilot size (proved, negative)

(i) **Hoeffding box.** $U_j\in[0,1]$ ⇒ $P(|\hat\mu_{j,t}-\mu_{j,t}|\ge\varepsilon)\le2e^{-2n_t\varepsilon^2}$; Bonferroni over 16
(2 types × orders 1–8) at $\gamma=0.05$: $\varepsilon_H=\sqrt{\ln(640)/200}=0.1797$ (orders 1–2 only: 0.1593). The two-point-mass
vector $\theta^*$ with $\mu_{j,t}=\hat\mu_{1,t}^{\,j}$ lies in the box iff $\max_{t,j}|\hat\mu_{j,t}-\hat\mu_{1,t}^j|\le\varepsilon_H$; at
$\theta^*$ both types are degenerate at distinct means, $t$ is an exact affine function of $r$, $D(\theta^*)=0$ and $w_1=\infty$.
Hence $\inf_{C_H}D=0$, $\sup_{C_H}w_1=\infty$: **no exact box certificate fires for any $d_0>0$ or finite $w_0$.** Checked: the
box contains $\theta^*$ in 5000/5000 pilots in each world (max deviation over pilots 0.0069 narrow; see json for the others).

(ii) **DKW band** on the count CDF ($\varepsilon_D=\sqrt{\ln(80)/200}=0.148$ per type): a two-point-per-type world with supports
$\{a,b\}$, $\{c,d\}$, $a+b=c+d$, has $t=\kappa(r-a)(r-b)$ exactly ⇒ $D=0$; a Nelder–Mead search over $(a,b,p_a,c,p_c)$ for the
minimum sup-distance of its binomial-mixture CDFs to the pilot's empirical CDFs finds such a world inside the band in 20/20 pilots
(narrow: sup distance 0.025–0.050). So the DKW set also contains $D=0$ worlds; the DKW certificate cannot fire either. (Finding a
world is a proof for that pilot; the count 20/20 is a simulation.)

(iii) **Matrix Bernstein** for $\bar A-Q$ (Tropp): $P(\|\bar A-Q\|\ge s)\le4\exp(-n\,\tfrac{s^2/2}{\sigma_1^2+Rs/3})$ with
$\sigma_1^2=\|\mathbb E(\hat M-Q)^2\|$ and $R=\max_K\|\hat M-Q\|$ computed exactly from the Beta-binomial count law. PD of $\bar A$ needs
$s<\lambda_{\min}(Q)$; the $n$ required for a 2% guarantee is $\approx1.1\times10^{11}$ (narrow, $\lambda_{\min}(Q)=8.2\cdot10^{-6}$),
and $\approx1.2$–$1.4\times10^{5}$ for the whitened version $Q^{-1/2}(\hat M-Q)Q^{-1/2}$ (where $R\approx3.5\cdot10^4$). Versus $n=200$.
Wide-world numbers in `a3_rigorous_constants.json`.

Consequence: the certificate of §2 can only be built on asymptotic (delta-method / bootstrap) confidence sets; a finite-sample theorem
with explicit constants for size or non-PD at $n=200$ is out of reach by these tools. This does not exclude other exact constructions.

## 4. Results (filled after the runs) — see `a2_summary.json`, `a2_summarize.out`, and the StructuredOutput claims.
