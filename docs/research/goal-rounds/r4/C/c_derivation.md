# Route C — Sequential internal-pilot design (32 → 128 → re-assess) and validity under reuse

Round r4, attacker 3. Notation follows `analysis/g6_iv.py` and archive §4 / r3-A1. Scratch only; nothing in the repository
is modified. Environment for every number: CPU x86_64, python 3.13.16, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19.
Other routes' directories were **not** read (protocol §3: attackers do not see other routes).

## 0. Setting and assumptions (all are checkable items)

* Prefixes $i=1,\dots,n$, $n=200$, $n_t=100$ per type $t_i\in\{0,1\}$ (fixed design). Risks $r_i$ i.i.d. $F_{t_i}$ within type,
  independent across prefixes. Question clusters (50 questions × 4 prefixes, 2 per type) carry **no** effect beyond $r$
  (stated model; CR1 is reported as a robustness choice, HC1 is the valid one under this model).
* **Internal pilot.** $K^{(32)}_i\sim\mathrm{Bin}(32,r_i)$ (the §7.2b/§7.11 `sel` block of the selected $h_3$);
  $K^{(96)}_i\sim\mathrm{Bin}(96,r_i)$ the extension; $K_i:=K^{(32)}_i+K^{(96)}_i\sim\mathrm{Bin}(128,r_i)$ the final count
  **with reuse**; $K'_i\sim\mathrm{Bin}(128,r_i)$ a hypothetical **fresh** final count, independent of $K^{(32)}_i$ given $r_i$.
  All counts are conditionally independent across prefixes given $r$. Same structure at the next stage with
  $(32,96,128)\to(128,384,512)$.
* **Outcome.** $\hat\Delta_i=g(r_i)+b_{\mathrm{type}}t_i+\eta_i$, $g(r)=c+b_1r+b_2r^2$, $\eta_i$ = difference of two independent
  16-draw binomial means with $q_\pm=\mathrm{clip}(r\pm g/2,0,1)$. **A0:** $(\eta_i)_i$ is independent of all counts
  $(K^{(32)},K^{(96)},K')$ given $r$ and independent across prefixes (different continuations; this is the physical fact the
  task states, stronger than the archive's mean-independence $\mathbb E[\eta\mid r,t,K]=0$ and needed below).
  Null: $b_{\mathrm{type}}=0$.
* **Test.** $R$ = any event determined by the final data $(\hat\Delta,K,t)$ through the production function
  `endpoint_contrast_poly_cs(degree=2)`: reject $=\{\texttt{ok}\wedge|t_{\mathrm{type}}|>1.96\}$ (ok=False counts as
  non-rejection), non-PD $=\{\neg\texttt{ok}\}$, width-event $=\{\texttt{ok}\wedge 2\cdot1.96\,\mathrm{se}_{\mathrm{type}}\le w_0\}$
  (ok=False ⇒ width $=\infty$). $R'$ = the same functional of $(\hat\Delta,K',t)$.
* **Pilot rules.** $\mathcal G_{32}=\sigma(t,K^{(32)})$ (what the analyst can compute before any steered arm exists),
  $\mathcal F_{32}=\sigma(r,t,K^{(32)})$, $\mathcal F_0=\sigma(r,t)$. A stage-1 rule is an event $D\in\mathcal G_{32}$ with
  $\pi=P(D)\in(0,1)$ ("adopt 128"). A stage-2 rule is $D_2\in\mathcal G_{128}=\sigma(t,K)$ ("certify 128" / "go to 512").

## 1. Exact reduction of the reuse effect (Theorem 1)

**Lemma 1 (fresh conditional law).** $P(R'\mid\mathcal F_{32})=P(R'\mid\mathcal F_0)=P(R\mid\mathcal F_0)=:h_0$.
*Proof.* Given $\mathcal F_0$, $(K',\hat\Delta)$ is independent of $K^{(32)}$ (A0 and the independence of $K'$ from $K^{(32)}$
given $r$), so the first equality. Given $\mathcal F_0$, $(K,\hat\Delta)\overset d=(K',\hat\Delta)$ because
$K^{(32)}_i+K^{(96)}_i\sim\mathrm{Bin}(128,r_i)$ and $\hat\Delta\perp$ counts given $r$; $R$ and $R'$ are the same functional,
so the second. $\square$

**Lemma 2 (reuse decomposition).** Let $h=P(R\mid\mathcal F_{32})$ and
$$\delta:=\mathbb E[h-h_0\mid\mathcal G_{32}]=P(R\mid\mathcal G_{32})-P(R'\mid\mathcal G_{32}).$$
Then $\mathbb E[\delta]=0$ and for every $D\in\mathcal G_{32}$ with $P(D)=\pi$:
$$P(R\mid D)-P(R'\mid D)=\frac{\mathrm{Cov}(\delta,1_D)}{\pi},\qquad
P(R'\mid D)-P(R)=\frac{\mathrm{Cov}(h_0^{\mathcal G},1_D)}{\pi},\ \ h_0^{\mathcal G}:=P(R'\mid\mathcal G_{32}).$$
*Proof.* $\mathbb E[1_R1_D]=\mathbb E[h1_D]$ since $D\in\mathcal G_{32}\subset\mathcal F_{32}$; $\mathbb E[1_{R'}1_D]=\mathbb E[h_01_D]$
by Lemma 1; project both onto $\mathcal G_{32}$ ($1_D$ is $\mathcal G_{32}$-measurable). $\mathbb E[h-h_0\mid\mathcal F_0]=0$ by the
tower property, hence $\mathbb E\delta=0$ and $\mathrm{Cov}(\delta,1_D)=\mathbb E[\delta1_D]$. The second identity: $P(R)=P(R')$
(Lemma 1) and $\mathbb E[1_{R'}1_D]=\mathbb E[h_0^{\mathcal G}1_D]$. $\square$

**Theorem 1 (uniform reuse bound).** For every stage-1 rule $D\in\mathcal G_{32}$ with $P(D)=\pi$,
$$\bigl|P(R\mid D)-P(R'\mid D)\bigr|\ \le\ \sigma_\delta\sqrt{\tfrac{1-\pi}{\pi}},\qquad \sigma_\delta^2:=\mathrm{Var}(\delta),$$
and likewise $|P(R'\mid D)-P(R)|\le\sigma_0\sqrt{(1-\pi)/\pi}$ with $\sigma_0^2=\mathrm{Var}(h_0^{\mathcal G})$ (selection on the
risk configuration, present under fresh continuations too). The supremum over $\{D:P(D)=\pi\}$ of $\mathrm{Cov}(\delta,1_D)$ is
attained by the upper-tail rule $D^\star=\{\delta>q_{1-\pi}(\delta)\}$.
*Proof.* Cauchy–Schwarz: $|\mathrm{Cov}(\delta,1_D)|\le\sigma_\delta\sqrt{\pi(1-\pi)}$; divide by $\pi$. Attainment: for fixed
$\pi$, $\mathbb E[\delta1_D]$ is maximised by putting the mass of $D$ on the largest values of $\delta$ (rearrangement). $\square$

*Remarks.* (i) The theorem holds for every event $R$ (size, non-PD, width ≤ $w_0$, power at any alternative) with its own $\sigma_\delta$;
(ii) it is exact probability theory under A0 only — no normal approximation, no moment condition on $F$;
(iii) it is **not** a bound on $|P(R\mid D)-0.05|$: the two-stage size is $P(R\mid D)=P(R)+[\text{selection term}]+[\text{reuse term}]$,
and $P(R)$ itself (the one-stage size at 128) is the quantity routes A/B study; (iv) $\sigma_\delta$ is not identified from the
pilot — it is a property of the world and is estimated here by nested Monte Carlo in named worlds; (v) the identical statement
holds at the 512 stage with $\mathcal G_{128}$, $(K^{(128)},K^{(384)},K'^{(512)})$.

**Estimator of $\sigma_\delta^2$ (one-way random-effects ANOVA with common random numbers).** Outer unit $o$: the 200 pilot counts
$K^{(32)}\sim\mathrm{BetaBin}(32,a_t,b_t)$ (the marginal law of the `sel` counts in a Beta world). Inner replicate $\ell$:
$r\mid K^{(32)}\sim\mathrm{Beta}(a_t+K,\,b_t+32-K)$ (the exact conditional law), $\eta$, $K^{(96)}$, $K'$; both tests are run on the same
$(r,\eta)$ and $y_{o\ell}=1_{R_{o\ell}}-1_{R'_{o\ell}}\in\{-1,0,1\}$. With $\bar y_o$ the inner mean and $s_o^2$ the inner sample
variance (ddof 1), $\hat\sigma_\delta^2=\widehat{\mathrm{Var}}(\bar y_o)-\overline{s_o^2}/N_{\mathrm{in}}$ is unbiased for
$\mathrm{Var}(\delta_o)$ whatever the heteroskedasticity across outer units (because $\mathbb E[\bar y_o\mid o]=\delta_o$ and
$\mathbb E[s^2_o\mid o]=\mathrm{Var}(y\mid o)$). Percentile bootstrap over outer units gives its interval; the **upper** 95% limit is
what enters the bound. The same inner draws evaluate any specific pilot rule $D$ (a function of the outer draw) at once:
$\widehat{P(R\mid D)-P(R'\mid D)}=\mathrm{mean}_{o\in D}\bar y_o$ with SE $\mathrm{sd}_{o\in D}(\bar y_o)/\sqrt{|D|}$.

## 2. Score-level mechanism (Proposition 2): which part of the data a pilot rule can tilt

Let $\hat u_i=(1,U_1(K_i),U_2(K_i),t_i)^\top$, $\hat M_i$ the corrected per-prefix design (entries $U_{a+b}$, $U_at_i$, $t_i$) and
$\psi_i=\hat u_i\hat\Delta_i-\hat M_i\beta_0$ the corrected score at the true $\beta_0=(c,b_1,b_2,0)$; $\hat\beta-\beta_0=A^{-1}\sum_i\psi_i$,
$A=\sum_i\hat M_i$. Write $\psi_i=\hat u_i\eta_i+d_i$, $d_i:=\hat u_ig(r_i)-\hat M_i\beta_0$ (the measurement-error part given the
final counts), $\mathbb E[d_i\mid r_i]=0$ by the unbiasedness of $U_j$ (P2(b)).

**Projection onto the pilot.** $U_j(K^{(128)})$ is the fraction of $j$-subsets of the 128 Bernoulli draws that are all successes;
conditioning on the first 32 draws,
$$\tilde U_j(k,r):=\mathbb E[U_j(K^{(128)})\mid K^{(32)}=k,r]=\binom{128}{j}^{-1}\sum_{\ell=0}^{j}\binom{k}{\ell}\binom{96}{j-\ell}r^{\,j-\ell}
=\sum_{\ell=0}^{j}\frac{\binom{32}{\ell}\binom{96}{j-\ell}}{\binom{128}{j}}\,r^{\,j-\ell}\,U_\ell(k).$$
In particular $\tilde U_1=r+\tfrac{32}{128}(\hat r^{(32)}-r)$ **exactly**, so the pilot carries exactly $m_0/m_1=1/4$ of the
measurement-error variance of $U_1(K^{(128)})$; for $U_2$ the exact rational share is computed in `c3_tilt_moments.py`
(0.2477 narrow, 0.2476 half-variance, 0.2485 wide).

**Proposition 2.** With $\phi_i:=\mathbb E[\psi_i\mid\mathcal F_{32}]=g(r_i)\tilde U_a-\sum_b\beta_b\tilde U_{a+b}$ (rows $a=0,1,2$; type row
$t_i(g(r_i)-\sum_b\beta_b\tilde U_b)$) and $\xi_i:=\psi_i-\phi_i$:
(a) $\mathbb E[\xi_i\mid\mathcal F_{32}]=0$, hence $\mathbb E[\sum_i\psi_i\mid D]=\mathbb E[\sum_i\phi_i\mid D]$ for every $D\in\mathcal F_{32}$;
(b) for every fixed $w$: $|w^\top\mathbb E[\sum_i\psi_i\mid D]|\le\sqrt{n\,w^\top\Phi w}\sqrt{(1-\pi)/\pi}$, $\Phi:=\mathrm{Var}(\phi_i)$;
(c) $\Phi\preceq\Sigma^{\mathrm{ME}}:=\mathrm{Var}(d_i)\preceq\Sigma:=\mathrm{Var}(\psi_i)=\mathbb E[\mathrm{Var}(\eta_i\mid r_i)\hat u_i\hat u_i^\top]+\Sigma^{\mathrm{ME}}$;
(d) under fresh continuations $\mathbb E[\sum_i\psi'_i\mid D]=0$.
*Proof.* (a) $\mathbb E[\hat u_i\eta_i\mid\mathcal F_{32}]=0$ by A0 and the tower property; $d_i$ depends on $(r_i,K^{(32)}_i,K^{(96)}_i)$
and $\mathbb E[d_i\mid\mathcal F_{32}]=\phi_i$ by the projection formula. (b) $\mathbb E[\phi_i\mid\mathcal F_0]=\mathbb E[\psi_i\mid\mathcal F_0]=0$,
so $Z=w^\top\sum_i\phi_i$ has mean 0 and $|\mathbb E[Z\mid D]|=|\mathbb E[Z(1_D-\pi)]|/\pi\le\sqrt{\mathrm{Var}Z}\sqrt{(1-\pi)/\pi}$;
$\mathrm{Var}Z=n\,w^\top\Phi w$ for independent prefixes. (c) Conditional Jensen: $\phi_i=\mathbb E[d_i\mid r_i,K^{(32)}_i]$ and
$\mathrm{Var}(\mathbb E[X\mid\mathcal H])\preceq\mathrm{Var}(X)$; the decomposition of $\Sigma$ uses $\mathbb E[\eta_i\mid r,K]=0$.
(d) $\mathbb E[\psi'_i\mid\mathcal F_{32}]=\mathbb E[\psi'_i\mid\mathcal F_0]=0$. $\square$

Every entry of $\Phi$, $\Sigma^{\mathrm{ME}}$, $\Sigma$ is a polynomial in the risk moments $\mu_j$ ($j\le8$ for the quadratic design)
through $\mathbb E[r^sU_jU_k\mid r]$ (A1 identity applied to the shifted moment list), evaluated exactly with `Fraction` in
`c3_tilt_moments.py`. Along the population type direction $w=A_{\mathrm{pop}}^{-1}e_4$ the ratio
$\kappa:=\sqrt{w^\top\Phi w/w^\top\Sigma w}$ is the largest standardized mean tilt of the type score any rule with $P(D)=1/2$ can
induce (first order): 0.093 / 0.083 / 0.230 (narrow; $g$ = lin / quad / cheb), 0.087 / 0.077 / 0.209 (half-variance),
0.099 / 0.088 / 0.243 (wide). The outcome-noise share of the type-direction score variance is 95–96% for the archive's $g$
(ME share 3.2–5.3%), 72–76% for the extreme member $g=\tfrac12(1-8r+8r^2)$ (ME share 24–32%). A pure mean shift of $\kappa$ sd on a
two-sided 5% test changes its size to $\Phi(-1.96-\kappa)+\Phi(-1.96+\kappa)$ = 0.051 (lin) … 0.057 (cheb) — a first-order
heuristic, **not** a bound on the size of the studentised, randomly-weighted statistic; Theorem 1 with the simulated $\sigma_\delta$ is the bound.

## 3. Stage-2 rule at 128 (pre-specified, functions of α=0 counts only)

Two facts make a 128-stage re-assessment well-defined without any steered arm:
(F1) the production `ok` flag (PD of $A=\sum_i\hat M_i$ by the rule $\lambda_{\min}>10^{-9}\max(1,\lambda_{\max})$) depends on
$(K,m,t)$ only — the non-PD outcome of the final degree-2 test at 128 is **known** at the 128 stage (it is $\mathcal G_{128}$-measurable);
(F2) the HC1 sandwich is $A^{-1}\bigl(\tfrac n{n-k}\sum_i\psi_i\psi_i^\top\bigr)A^{-1}$ with $\psi_i=\hat u_i\eta_i+d_i$, so
$\mathbb E[\sum_i\psi_i\psi_i^\top\mid r,K]=\sum_i\mathrm{Var}(\eta_i\mid r_i)\hat u_i\hat u_i^\top+\sum_id_id_i^\top$; the first term is a
known function of the counts once $\mathrm{Var}(\eta\mid r)$ is replaced by a constant $\bar\sigma^2_\eta$, the second ($d_i$) needs $g$.
Define the **width proxy** $w_{\mathrm{pred}}(K;\bar\sigma^2_\eta)=2\cdot1.96\sqrt{\bar\sigma_\eta^2\,\tfrac n{n-k}\,[A^{-1}GA^{-1}]_{44}}$,
$G=\sum_i\hat u_i\hat u_i^\top$ — the outcome-noise part of the width; with $\bar\sigma^2_\eta=\sup_r\mathrm{Var}(\eta\mid r)=1/32$ it is a
certificate-grade proxy for that part, with the plug-in $\bar\sigma^2_\eta=0.02$ (the value at $q_\pm\approx0.2$) it is a point prediction.
The $d_id_i^\top$ term is omitted; under $|g|\le1$ it is not usefully bounded (quadratics bounded by 1 on $[0,1]$ have coefficients up to 8),
so the proxy is **not** a sup-over-class certificate — its validity in each world is what the simulation checks.

**Rule R128** (pre-specified before any steered arm): compute $A_{128}$ from the 128 `sel` counts;
if not PD ⇒ the degree-2 test at 128 cannot run ⇒ go to 512 (the 128 are reused inside the 512; Theorem 1 applies at that stage);
if PD and $w_{\mathrm{pred}}(K^{(128)};\bar\sigma^2_\eta)\le w_0=0.15$ ⇒ certify 128; else ⇒ go to 512.
Rule R32 (stage 1) has the same form with $K^{(32)}$: certify 32 if PD and $w_{\mathrm{pred}}(K^{(32)})\le w_0$, else adopt 128.
Both are measurable w.r.t. the counts the corresponding test uses, so for R32/R128 "certify" there is no reuse question — only selection
on the design, $P(R\mid D_2)-P(R)=\mathrm{Cov}(P(R\mid\mathcal G_{128}),1_{D_2})/\pi_2$, which the nested simulation reports directly as the
conditional size / width given certification. The reuse question arises for the *escalation* branches (adopt 128 from $K^{(32)}$; go to
512 from $K^{(128)}$) and is covered by Theorem 1.

## 4. What is proved, what is simulated, what is not claimed

* Proved: Lemma 1, Lemma 2, Theorem 1, Proposition 2, the exact shares ($1/4$ for $U_1$; rationals for $U_2$), F1, F2.
* Simulated (production function, nested MC, CIs reported): $\sigma_\delta$ (reject / non-PD / width ≤ 0.15) per world, the
  rule-specific reuse and selection terms, the availability and conditional operating characteristics of R32/R128, the 512-stage
  reuse bound.
* Not claimed: a bound on the one-stage size at 128 over the compatible set (routes A/B); attainment of any sup at extreme points;
  validity beyond the Beta worlds listed (the posterior draw $r\mid K$ uses the Beta prior; Theorem 1 itself does not); anything about
  the FE-logistic primary test; question-level effects beyond $r$.
