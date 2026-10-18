# 研究目标档案（/goal）——动态控制多轮迎合：向最强可证主张推进

版本 r1，2026-10-18（对应主线第十二轮）。本档案是 `/goal` 的落地形式：一个**跨轮累积的研究档案**，不是计划书。每一轮只在用户触发（"继续做下去"或新的审查/诊断输入）时推进；**不设自动调度**，不在无人触发时自行运行任何东西。

## 0. 用法与规则

- **成功判据**：给出有意义的 idea formulation——一个把本项目的主张推到最强、可证伪、可预报的表述，并指明它依赖的命题哪些已证明、哪些是候选、哪些被淘汰。
- **诚实规则**：未完成的必须写"尚未解决"；不得为满足目标而编造证明、重述旧结果、换名字、或悄悄弱化主张。每条结论标注状态：`已证明`（有推导且有自动化检验）/ `自检`（本人推导与模拟一致）/ `独立复核`（另一独立上下文的审查通过）/ `候选` / `已淘汰`。
- **每轮流程**（用户模板）：① 核验问题与文献 → ② ≤5 条独立路线（工具、核心命题、如何蕴含主张、失败点、最便宜的可行性检查；不得全部依赖同一个未证引理）→ ③ 实际推导 → ④ 核查/淘汰/切换 → ⑤ 对抗式审查。
- **跨轮规则**：用户只输入"继续做下去"时，选当前最关键的未解决障碍，做新的推导或尝试；不重复已失败的路线；若连续两轮无实质进展，回到问题本身重新审视；只在需要时做定向文献核查；每轮给出真实的阶段结论并更新 §7。
- **每轮输出格式**：A 原始目标；B 本轮核心障碍；C 本轮实际推导；D 严格核查；E 路线决策；F 更新研究档案（§7）。
- **自动化**：§8 的证据阶梯。任何"已证明"条目必须对应一个 `pytest` 用例（CPU 模拟或精确算术）或一个已跑通的 GPU 诊断；用例失败即该条目降级。

## 1. 原始目标与最强主张阶梯

**原始目标**：在冻结的 Qwen3-30B-A3B-Instruct-2507 上，建立"多轮迎合是一个可读、可控、且值得**动态**（逐轮、依状态）控制的状态变量"这一主张，并用 Phase-0 的门控实验（G0→G7，`sycophancy-phase0-execution-plan.md` v1.4）给出可证伪的证据。

**主张阶梯**（每级含量词；只有上一级成立下一级才有意义）：

| 级 | 主张 | 对应 Gate | 状态 |
| --- | --- | --- | --- |
| C0 | 推理栈忠实：对所有 regime，cache/重算、batch 组成、跨栈差异在预注册容差内 | G0 | 未测（两次 GPU 诊断给出风险点，见 §7） |
| C1 | 现象可测：存在题目与施压脚本族使 $P(e_4)$ 在 $[0.15,0.85]$ 且前缀间风险 $r(h)$ 有非零方差 | G1、G1.5 | 未测 |
| C2 | 状态可读：$\exists L,\phi$ 使 $\rho^2(\phi(z_t),r_t)>0$ 且超过置信度/轮次/文本基线 | G3 | 未测 |
| C3 | 状态可控：$\exists \hat v$ 使剂量–响应单调、存在线性区、$\alpha_{\max}\ge0.2$ | G4-1、G4-2 | 未测（随机方向预览：阈值越过点在 (0.25, 0.5)） |
| C4 | 前瞻价值：第 2 轮干预在第 3 轮最优干预之上有边际价值 $G>0$ | G2′、G5 | 未测 |
| C5 | 闭环优势：读内部状态的控制器在误差–剂量前沿上优于一切开环时间表 | G7 | 未测 |
| C6 | 风险之外的信息：匹配真实风险后，类型/状态仍携带控制相关信息（命题二） | G6 | 未测；**识别问题本轮解决（P1–P3）** |

**C★（本轮给出的最强表述，候选）——闭环优势的可预报性**：
令 $r_t(h)$ 为前缀 $h$ 在第 $t$ 轮的真实条件风险，$\hat z_t=\phi(z_t)$ 为控制器读出，$\rho_t^2:=\rho^2(\hat z_t,r_t)$（去衰减后的平方相关）。在剂量–响应的线性–二次区内：

1. 任何以 $\hat z_t$ 为输入的**线性**闭环控制器，相对最优开环时间表所能实现的 oracle 增益比例恰为 $\rho_t^2$ 上界，并由 $d=a+b\,\mathbb E^*[r_t\mid\hat z_t]$ 达到（P4，已证明）；一般控制器的上界是相关比 $\eta_t^2$。
2. 因此 G7 的 headline（前沿优势）的**量级**可在 G7 之前由三件已有数据预报：G3 的 $\hat\rho_t^2$（P5，零额外生成）、G4-2 的剂量–响应斜率与曲率、G1.5 的 $\mathrm{Var}(r_t)$。
3. 若 G7 的实测优势与预报一致 ⇒ "内部状态读出通过其可靠性 $\rho^2$ **定量**决定闭环控制的价值"；若显著**超过** $\hat\rho_t^2\times$oracle 增益 ⇒ 读出携带 $r_t$ 之外的控制相关信息，即命题二的强形式——这正是 G6 校正后的 $b_{\text{type}}\neq0$（P1–P2）在检验的东西；若显著**低于** ⇒ 控制器实现损失（plug-in 危险，P4 推论）或线性–二次近似失效。

这比"闭环优于开环"强：它给出一个在实验前就能写下的数字，并把 G3、G4-2、G6、G7 绑到同一个量 $\rho^2$ 上。它的最便宜可行性检查（"G7 预检"）：$\hat\rho_t^2\times$oracle 增益若小于 G5 量级的检测限（SE≈1.8pp），G7 不可能显示优势，应在 G7 之前改读出或改前缀分布，而不是跑 G7。

## 2. 第一步：问题核验与文献定位

- **问题**：G6 预注册主判据"控制 $\mathrm{logit}\,\hat r^{\text{sel}}$ 后类型×剂量交互显著"是否识别"类型携带真实风险之外的信息"。第七轮已指出存在反例（§7.11 示例：真实风险完全决定最优动作，但 $\hat r$ 噪声使交互显著）。本轮把反例变成定量理论并给出识别方法。
- **已知结果**（本轮做了定向在线核查，2026-10-18；标注"已核"的有公开来源，其余仍是训练记忆）：
  - 已核：Spearman（1904）的去衰减相关——观测相关除以两可靠性乘积的平方根；已知局限：可能超过 1、假设误差方差齐性（[Wikipedia 镜像](https://static.hlt.bme.hu/semantics/external/pages/pszichometriai_g-faktor/en.wikipedia.org/wiki/Correction_for_attenuation.html)、[SAGE 条目](https://methods.sagepub.com/ency/edvol/embed/encyclopedia-of-measurement-and-statistics/chpt/attenuation-correction)）。P5 是它的单侧版本（只有 $r$ 一侧有重复测量），故不受"超过 1"的问题影响方向，但同样可因抽样波动超出 $[0,1]$。
  - 已核：以第二个独立测量作工具变量校正测量误差（Ashenfelter–Krueger 1994 双生子数据：两测量误差不相关则其一可作另一的工具，[Princeton IRS](https://irs.princeton.edu/bibcite/contributor/54)）。注意 Angrist–Krueger 的 "split-sample IV"（[IRS 工作论文](https://irs.princeton.edu/publications/working-papers/split-sample-instrumental-variables)）是**另一回事**（按样本分半解决弱工具偏差），本档案的"分半"指每个前缀的续写分两半——命名上须避免混淆，正文改称"两半工具变量（repeated-measurement IV）"。
  - 已核：LQ 控制的确定性等价（Simon 1956、Theil 1957；[QuantEcon](https://python.quantecon.org/theil_1.html)；LQG 下最优控制对信息只通过状态的条件期望起作用，[Springer 章节](https://link.springer.com/chapter/10.1007/978-3-030-49995-2_14)）。P4 的"最优控制器用 $\mathbb E[r\mid\hat z]$"是它在静态单步情形的直接实例。
  - 已核（仅书目）：Fuller 1987《Measurement Error Models》（Wiley）；Feucht 1989 报告 Fuller 型校正估计在小样本中只有适度改进且有风险（[IDEAS](https://ideas.repec.org/a/sae/somere/v17y1989i3p257-282.html)）——与本轮 P3 的弱识别失败模式一致。校正得分（corrected score）的已知方差设定来自 Stefanski 的工作（搜索结果提及，未读原文）。
  - 未核：Oldham 1962（变化分数对基线回归的向均值回归伪相关）；本轮设计里 $\hat\Delta_i$ 用不同续写，不触发该问题，但若有人用 $\hat r$ 本身的臂作端点，会触发。
  **本轮的贡献不在这些定理，而在于把它们映射到本项目的量**（$\hat r^{\text{sel}}$ 的二项误差方差已知、两半独立、$\hat\Delta_i$ 用不同续写、LOQO 探针预测）并得到零额外生成成本的可估计量与设计规则。

## 3. 第二步：独立路线（≤5）

| 路线 | 工具 | 核心命题 | 如何蕴含主张 | 失败点 | 最便宜的可行性检查 |
| --- | --- | --- | --- | --- | --- |
| R1 两半工具变量（repeated-measurement IV） | 2SLS；`subsplit` 两半 | 两半误差独立 ⇒ $\hat r_b$ 是 $\hat r_a$ 的有效工具 ⇒ $b_{\text{type}}$ 一致 | C6 的识别 | 弱工具（$F<10$）斜率变号 | 用前缀库算组内半可靠性 $\lambda_h$，代入 $F\approx n\lambda_h^2/(1-\lambda_h^2)$ |
| R2 已知方差校正得分 | 矩修正（Fuller 型）；全部 32 条 | $E[\hat r(1-\hat r)/(m-1)]=r(1-r)/m$ ⇒ 修正矩阵一致 | C6 的识别，功效高于 R1 | 修正矩阵非正定（同一弱识别） | 同上；非正定时估计量拒绝输出 |
| R3 可靠性上限 | LQ 分解；DP 数值 | 最优线性闭环实现比例 $=\lambda$；plug-in 比例 $=1-\sigma_e^2/\mathrm{Var}(r)$ | C★ 的量化；G7 预检 | 离散动作 + $\vert d\vert$ 代价偏离 LQ | 三个先验下的 5 动作 DP 模拟（本轮已做） |
| R4 一般 Bayes 风险界 | $\mathbb E[J(d(\hat z),r)]\ge\mathbb E[\min_d\mathbb E[J(d,r)\mid\hat z]]$ | 不依赖 LQ；上界用 $\eta^2$ | C★ 的非参数版本 | 只给界，不给等式；$\eta^2$ 估计需非参数回归 | 尚未做 |
| R5 设计路线 | 增大组内风险方差或续写数 | $F\ge10\iff\lambda_h^2\ge10/(n+10)$ | 使 R1/R2 可用 | 前缀选择若按 $\hat r^{\text{sel}}$ 分层，会破坏两半独立性 | 预算算术（本轮给出公式） |

R1–R3 不依赖同一个未证引理：R1/R2 依赖"两半误差独立 + 线性"，R3 依赖"LQ 近似"，R4 只依赖 Jensen。

## 4. 第三步：本轮实际推导

**记号**：前缀 $i=1..n$，真实风险 $r_i$，类型 $t_i\in\{0,1\}$，$\mu_k=\mathbb E[r\mid t=k]$，$\Delta\mu=\mu_1-\mu_0$，组内方差 $V=\mathbb E[\mathrm{Var}(r\mid t)]$。$m$ 条独立续写给 $\hat r_i=r_i+e_i$，$\mathbb E[e_i\mid r_i,t_i]=0$，$\mathrm{Var}(e_i\mid r_i)=r_i(1-r_i)/m$，$s:=\mathbb E[r(1-r)]/m$，组内可靠性 $\lambda_w:=V/(V+s)$。端点对比 $\Delta_i=c+b_r r_i+b_t t_i$，观测 $\hat\Delta_i=\Delta_i+\eta_i$，$\eta\perp(e,r,t)$（两臂用各自的续写）。

**P1（朴素检验的偏差，已证明）**。总体 OLS $\hat\Delta\sim(1,\hat r,t)$ 的类型系数为
$$\gamma=b_t+b_r(1-\lambda_w)\Delta\mu .$$
*证明*：FWL——把 $\hat r$ 与 $\hat\Delta$ 分别对 $(1,t)$ 投影，残差为 $(r_i-\mu_{t_i})+e_i$ 与 $b_r(r_i-\mu_{t_i})+\eta_i$；斜率 $\beta=\mathrm{Cov}/\mathrm{Var}=b_rV/(V+s)=b_r\lambda_w$（$\mathrm{Cov}(e,r-\mu_t)=0$ 因 $\mathbb E[e\mid r,t]=0$，异方差无妨）。拟合的类型均值差必须等于实际均值差：$b_r\Delta\mu+b_t=\beta\Delta\mu+\gamma$。∎ 
*数值*（$n=200$，$m=32$，每臂 16 条，模拟 2000 次）：Beta(3,5)/Beta(5,3) 两类，$\lambda_w=0.80$，预测偏差 $-0.0252$，模拟 $-0.0251$，名义 0.05 的检验实际拒绝率 **0.163**；§7.11 示例型（$r\approx0.20/0.25$，$b_r=-0.8$），$\lambda_w=0.24$，预测 $-0.0304$ = 模拟 $-0.0304$，拒绝率 **0.281**，$n=1000$ 时 **0.878**（偏差不随 $n$ 消失，是一致性问题）。

**P2（两种一致估计，已证明 + 自检）**。(a) 分半 2SLS：$X=(1,\hat r_a,t)$，$Z=(1,\hat r_b,t)$。矩条件 $\mathbb E[Z(y-X\beta)]=0$ 成立：$\mathbb E[\hat r_b\eta]=0$；$\mathbb E[\hat r_be_a]=\mathbb E[\hat r_b\,\mathbb E(e_a\mid r,t,\hat r_b)]=0$（两半给定 $r$ 独立）；相关性 $\mathrm{Cov}(\hat r_b,\hat r_a\mid t)=V>0$。(b) 校正得分：$v_i=\hat r_i(1-\hat r_i)/(m-1)$ 满足 $\mathbb E[v_i\mid r_i]=r_i(1-r_i)/m$（因 $\mathbb E[\hat r(1-\hat r)]=r(1-r)(1-1/m)$），故 $(X^\top X-\sum_i\Sigma_i)/n\to\mathbb E[x^*x^{*\top}]$，$\Sigma_i=\mathrm{diag}(0,v_i,0)$，$x^*=(1,r,t)$；$\hat\beta=(X^\top X-\sum\Sigma_i)^{-1}X^\top y$ 一致，SE 用 M-估计三明治（得分 $\psi_i=x_i(y_i-x_i^\top\beta)+\Sigma_i\beta$）。
*数值*：强识别情形下 null 拒绝率 2SLS 0.066、校正得分 0.056、oracle 0.063；$b_t=0.05$ 时功效 0.317/0.338/0.413，$b_t=0.10$ 时 0.835/0.865/0.921；斜率 $-0.482/-0.483$（真值 $-0.5$，朴素 $-0.384$）。

**P3（识别强度，已证明——标准 $F$–$R^2$ 恒等式的设计化）**。$\mathrm{Corr}(\hat r_a,\hat r_b\mid t)=\lambda_h=V/(V+s_h)$，$s_h=\mathbb E[r(1-r)]/m_h$，故单工具的第一阶段
$$F\approx n\frac{\lambda_h^2}{1-\lambda_h^2}=n\frac{V^2}{s_h(2V+s_h)},\qquad F\ge10\iff\lambda_h^2\ge\frac{10}{n+10}.$$
*数值*：预测 158.5 对模拟 161.9；示例型预测 3.8 对模拟中位数 3.9（弱）；$n=1000$ 预测 19.4 对 20.4。弱识别时：2SLS 斜率在备择下均值 $+0.95$（真值 $-0.8$，变号），校正矩阵在部分重复中非正定——两种估计量都不可用，**不是**换估计量能修的；示例型需 $n\approx520$ 或每半 $m_h\gtrsim26$。

**P4（读出可靠性上限，LQ 理想化下已证明）**。设 $J(d;r)=J^*(r)+\tfrac{\kappa}{2}(d-a-br)^2$，读出 $\hat z$。对任意 $d(\hat z)$：
$$\mathbb E[(d(\hat z)-a-br)^2]=\mathbb E[(d(\hat z)-a-b\,\mathbb E[r\mid\hat z])^2]+b^2\,\mathbb E[\mathrm{Var}(r\mid\hat z)]\ \ge\ b^2\,\mathbb E[\mathrm{Var}(r\mid\hat z)] .$$
开环（常数 $d$）的 regret 为 $\tfrac\kappa2b^2\mathrm{Var}(r)$；最优控制器 regret $\tfrac\kappa2b^2\mathbb E[\mathrm{Var}(r\mid\hat z)]=\tfrac\kappa2b^2\mathrm{Var}(r)(1-\eta^2)$；线性类中最优者 $d=a+b\,\mathbb E^*[r\mid\hat z]$ 得 $(1-\rho^2)$。故**实现的 oracle 增益比例**：一般 $\le\eta^2$，线性 $=\rho^2$。当 $\hat z=\hat r$（$m$ 条二项抽样）时 $\rho^2=\lambda=\mathrm{Var}(r)/(\mathrm{Var}(r)+\mathbb E[r(1-r)]/m)$。**推论（plug-in 危险）**：$d=a+b\hat r$ 的 regret 为 $\tfrac\kappa2b^2\sigma_e^2$，当 $\lambda<1/2$ 时**差于开环**。
*数值*（LQ，$N=4\times10^5$）：$m=4/16/32/128$ 时线性最优比例 $0.336/0.668/0.800/0.941$ 对 $\lambda=0.334/0.667/0.800/0.941$；$m=4$ 的 plug-in 比例 $-0.994$。
*离散动作检查（候选，非定理）*：用 §7.11 的翻转模型 $q(r,d)=r+(0.9-4r)d$、5 动作、代价 $0.05\vert d\vert$、三个先验（Beta(5,15)/(10,30)/(2,6)），Bayes 最优策略实现比例对 $\lambda$：$0.191/0.311/0.454/0.604/0.733/0.836/0.950$ 对 $\lambda=0.167/0.286/0.445/0.616/0.762/0.865/0.962$（Beta(5,15)）；另两先验偏差 $\le0.06$。plug-in 一律更低（Beta(10,30)、$m=16$：0.079 对 0.341）。规律"比例 $\approx\lambda$"在离散集上只是经验观察。

**P5（任意读出的去衰减 $\rho^2$，已证明）**。若 $\hat z$ 由不含该前缀续写的计算得到（LOQO/交叉拟合预测、logit 特征等），两半误差独立，则
$$\rho^2(\hat z,r)=\frac{\mathrm{Cov}(\hat z,\hat r_a)\,\mathrm{Cov}(\hat z,\hat r_b)}{\mathrm{Var}(\hat z)\,\mathrm{Cov}(\hat r_a,\hat r_b)} ,$$
因 $\mathrm{Cov}(\hat z,\hat r_a)=\mathrm{Cov}(\hat z,r)$、$\mathrm{Cov}(\hat r_a,\hat r_b)=\mathrm{Var}(r)$。需 $\mathrm{Cov}(\hat r_a,\hat r_b)>0$。*数值*：$n=200$ 时无偏、SD 0.059；$n=1000$ 时 SD 0.019–0.028；朴素 $\mathrm{Corr}(\hat z,\bar{\hat r})^2$ 低估 0.07–0.17。**零额外生成**：前缀库已有 `sel`/`est` 奇偶两半，G3 探针预测是 LOQO 的。

## 5. 第四步：核查、淘汰与切换

- **淘汰**：把"控制 $\hat r$ 后的交互"当作 C6 的识别性检验（P1：偏差不随 $n$ 消失）。预注册主判据保留，但其结论范围按第七轮限定，识别性结论只来自 P2 的两种估计（$F\ge10$ 时）。
- **淘汰**：单独依赖 2SLS 而不报 $F$（弱识别下变号）。
- **淘汰（无信息而非反例）**：P4′ 第一次参数化（$p=\sigma(\mathrm{logit}r+d)$、Beta(2,5)）——最优动作几乎不随 $r$ 变，oracle 增益 0.0016，比例噪声淹没；改用翻转模型后才有信息。
- **切换**：G7 的"myopic $\pi(z_t)$"若以 plug-in 方式使用噪声读出，可能差于开环（P4 推论）；控制器规格须用后验均值/收缩（§7.11 的 EB 收缩正是这个方向），并在 G7 规格中写明。
- **未解决**：离散动作 + $\vert d\vert$ 代价下"比例 $\approx\lambda$"没有证明或界；G6 regret 估计量比较的是**两个带噪策略**（每前缀 fit 半 argmin 与 $\hat r$ 分位箱策略），其期望值与 $\lambda$ 的关系尚未推导；R4 未做。

## 6. 第五步：对抗式审查状态

- P1–P5 的推导与 `scratchpad/round12_math.py`、`round12_p4b.py` 的模拟一致（**自检**）。
- 自动化检验：`tests/test_analysis.py` 的 `test_g6_split_half_iv_removes_the_measurement_error_bias`、`test_g6_naive_bias_formula_and_corrected_score_estimator`、`test_g6_identification_strength_formula_and_weak_regime`、`test_readout_reliability_ceiling_and_disattenuation`（全部通过，95 passed）。
- 独立复核：见 §9 本轮记录（独立上下文的代理审查结果，含被驳回/修正的条目）。代理审查不等于人类同行审查。

## 7. 研究档案

**已证明（有推导 + 自动化检验）**
1. P1 朴素类型系数偏差 $b_r(1-\lambda_w)\Delta\mu$。
2. P2 分半 2SLS 与已知方差校正得分一致；三明治 SE。
3. P3 $F\approx n\lambda_h^2/(1-\lambda_h^2)$ 与 $F\ge10$ 的设计条件。
4. P4 LQ 理想化下线性闭环的实现比例 $=\rho^2$、一般 $\le\eta^2$、plug-in 在 $\lambda<1/2$ 时差于开环。
5. P5 去衰减 $\rho^2$ 恒等式。
6. （主线早期轮次）$\hat J_{\mathrm U}$ 对截断目标无偏；regime 标记非保证；G5 联合功效 0.50/6.5pp；hook 位置规则；`real_mask` 增长序列规则。

**候选**
- C★（闭环优势的可预报性）；离散动作下"实现比例 $\approx\lambda$"；G6 regret 的 $(1-\lambda)$ 解释；"结构化方向的 $\alpha_{\max}$ 更小"。

**反例与错误（已修正或撤回）**
- 执行方反例：`use_cache=False` 增长序列跳过 `real_mask`（已修，测试覆盖）。
- "重建误差固有、与后端无关"、"半剂量仅为底噪 3–9 倍"（撤回：不同序列；rms 不能换算 KL）。
- 第九/十轮：hook 自检比较最终 logits、T=1 口径、`output_scores`、G0.3 inf/负值通过、10× 规则空洞。
- P4′ 首次参数化无信息。

**已淘汰路线**
- 朴素调整交互作为识别；无 $F$ 报告的 2SLS；plug-in 噪声读出控制器作为 G7 的默认 reactive 控制器。

**最近的关键缺口**
- (i) 离散动作/绝对值代价下的实现比例的界；(ii) G6 regret 估计量在两个带噪策略下的期望与 $\lambda$ 的关系；(iii) 三项 GPU 测量未做（时序拆分、固定序列带符号误差、batch 两指标）；(iv) 吞吐路线 1 的小规模比较未做。

**下一轮攻击**
- 推导 (ii)：$\mathbb E[\widehat{\mathrm{Regret}}_a]$ 在 null（真实风险控制充分）下关于 $\lambda_{\text{fit}}$、$\lambda_{\text{sel}}$ 的表达式，给出 G6 的"测量误差 regret 预测值"作为对照；尝试 (i) 的 Jensen 型界。

## 8. 自动化证据阶梯

| 级 | 内容 | 触发 | 当前 |
| --- | --- | --- | --- |
| L0 | `pytest`（CPU 假模型 + 统计模拟）：每条"已证明"命题一个用例 | 每轮、每次提交 | 95 passed |
| L1 | GPU 诊断（RUNBOOK §6.2 三项 + §6 五项） | 执行方在 A100 上运行并贴回 | 五项已做；三项待做 |
| L2 | 门控 G0–G7（`GATES.md` + `tables/*_summary.json`） | 路线 1 吞吐决定后 | 未开始 |

## 9. 轮次记录

### r1（2026-10-18，主线第十二轮）
- A 原始目标：§1。
- B 核心障碍：C6 的识别（§7.11 反例的定量化）与 C5 的可预报量。
- C 推导：P1–P5（§4）。
- D 核查：§5；模拟数值与公式一致到第三位小数；弱识别失败模式记录在案。
- E 路线决策：R1+R2 同报（$F$ 为门槛）；R3 作为 C★ 的量化工具；R4 下一轮；R5 作为 G6 前缀数/续写数的预算规则。
- F 档案：§7 已更新。
- 独立复核：见本节末尾（审查后补）。
