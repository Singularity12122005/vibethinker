# 《第一阶段执行计划：最小修订确认稿》处置（针对 v1.2 粘贴稿的外部审查）

> 外部修订稿审查的是 v1.2 的一份粘贴文本（行号指该粘贴件）。本仓库的规格书此时已是 v1.3（三轮审查）→ 现为 v1.4。下表逐条给出处置：**已覆盖**（v1.3 已含同等或更强的规则）、**采纳**（v1.4 新增/修改）、**部分采纳**（采纳其意图但以 v1.3 的估计量替代其具体做法）、**不采纳**（给出理由）。

## 0. 结论先行
- 修订稿的全部实现勘误（I1–I4）与数据/评分补充（D1–D4）在意图上正确；其中 I1、I4、D2、D3、D4 的核心已在 v1.3 实现，I2、I3、D1 为 v1.4 采纳的新修正。
- 统计裁决 S1–S5：S1 的数学观察正确（$J$ 依赖 $\lambda$），但在预注册网格内影响 $<10^{-4}$；v1.4 把主统计量明确定义为小 $\lambda$ 极限 $J_0$ 并缩小 KILL 的结论范围，但**不**回到修订稿建议的 EB 收缩 + 删一估计量（第三轮统计审计已证明其偏低约 40%，v1.3 的 $\hat J_{\mathrm{LB}}$ 经模拟验证）。S2、S3、S5 采纳；S4 在 v1.3 下基本失效（Beta 仅作诊断），采纳其"明确返回未定义"的规则。
- **G0.4 没有缺失**：原文在 §7.1 表格 G0.4 行完整存在（逐位判据、文本路径 ≤1%、配对 TOST ±1.5pp）；修订稿看到的截断是粘贴时在单元格 `$\max` 处断行所致。v1.4 保留原判据并补充设计说明：(ii) 的采样续写使用与 (i) 不相交的 `trajectory_idx`，否则共享种子下忠实管线逐位复现、TOST 为空检验。
- 修订稿中"确认前不写代码"的流程约定是外部代理的工作约定；本仓库的参考实现已存在并通过 CPU 测试，本次处置同步修改了代码（见 §3）。

## 1. 逐条处置

| 编号 | 处置 | 说明 |
| --- | --- | --- |
| G0.4 缺失 | **不成立，已补回** | 见 §2；v1.4 §7.1 新增"G0.4 设计说明"。 |
| I1 `user_span` 起点 | 已覆盖 + 采纳 | v1.3 起 `start = len(base)+len(y_{t-1})+len(pre)`；v1.4 采纳"整段增量一次编码为标准、分段不一致时按公共前后缀定位、区间断言、计数报告"（`templates.py::next_turn_ex`）。第 1 轮定位：v1.3 已改为"收尾生成提示之前的最后一次出现"，不再搜索到生成提示。 |
| I1 关联：`</think>` 后换行 | 已覆盖 | v1.3：剥离全部仅含换行的前导 token（与模板 `lstrip('\n')` 一致）。`Qwen3-14B` 的空 think 块规则：按 `mode="hybrid_nothink"` 配置即可，不绑定模型名。 |
| I1 关联：思考未闭合时的历史 | 采纳 | v1.3 已实现：无 `</think>` ⇒ 内容 ids 只剩 151645（正文为空）、`think_ids` 保存、`no_think_close=true`、stance=NONE/EVASIVE，轨迹保留。与修订稿建议一致。 |
| I2 cache 后缀 | **采纳** | §4.2：读取 cache 实际长度、验证前缀一致、只喂未覆盖后缀；不一致记"不适用"。`g0_runner.cache_vs_recompute_kl(cached_prefix_len=...)`。 |
| I3 梯度符号 | **采纳（措辞）** | 代码本来对 $+\log P$ 反向（`response_gradient`，有限差分测试通过）；规格 §4.4 文本的"loss = −log P 后直接取 grad"是符号错误，已改。 |
| I4 读取侧掩码广播 | 已覆盖 | v1.3 的位置规则（`position_ids` 索引的 `pos_mask`）使 S_read 在解码步自动不施加；CPU 测试覆盖 `generate` 下 S_read 与 teacher-forcing 一致。v1.4 另把 `S_read` 臂在生成时的实际施加接入（之前臂记录 S_read 但生成用 S_gen）。 |
| S1 $A=\lambda J(\lambda)$ | **部分采纳** | 采纳：恒等式写为 $A(\lambda)=\lambda J(\lambda)$；主统计量 = 小 $\lambda$ 极限 $J_0$；有限 $\lambda$ 曲线只作描述；"delta 项为下界"改为"二阶近似"；KILL 结论范围缩小。不采纳：改回 EB 收缩 + 删一估计（偏低约 40%，见 `tests/test_analysis.py`）；保留 v1.3 的 $\hat J_{\mathrm{LB}}$ + regime 标记。数值说明：$\lambda_{KL}=\lambda_{\text{dose}}/\kappa_1\le0.1$ 时 $e^{-1/\lambda}\le4.5\times10^{-5}<1/M$，修订稿反例取 $\lambda\in\{0.1,1\}$（KL 单位）在网格之外。 |
| S2 支持集 vs 极低概率 | **采纳** | G0.7：$-\infty$ 比例须为 0；NaN/$+\infty$ 为故障；$<-60$ 比例只报告。 |
| S3 失败优先级 | **采纳** | G0.8 失败即 KILL；co-primary（明确回答率）先于效应判据（代码中 G4-2/G5/G6 均先判 co-primary ⇒ GREY）；G5 确认阶段"无灰区"仅指质量门槛通过后的效应判定。 |
| S4 Beta 矩匹配退化 | 采纳（已基本覆盖） | v1.3 起 EB 收缩不进前沿（平衡设计下为仿射变换，前沿不变）、Beta 只作诊断；代码在 $\mu\notin(0,1)$ 或 $\mathrm{Var}\ge\mu(1-\mu)$ 或 $\mathrm{Var}\le0$ 时返回 NaN 并保留原始方差估计（含负值）。v1.4 在 `jensen_gap` 输出里标注 `J_beta` 未定义的原因。 |
| S5 CS 界与经验前沿 | **采纳** | v1.3 已明确 $\mathrm{sd}\sqrt{e^\kappa-1}$ 不是上界、Bernstein 为 KL 匹配上界；v1.4 采纳"经验控制前沿"命名与诊断措辞。 |
| D1 judge 提示词 | **采纳** | 附录 E 与 `scoring/judge.py` 改为"答案可能是数值或短字符串"，`final_number` 按 `gold_type` 分流规范化。 |
| D2 $f_t$ 定义 | **采纳** | 相邻两轮均 EXPLICIT 且可提取才定义；否则 `null`；只作描述。 |
| D3 划分 | 已覆盖 | v1.3：探针 LOQO、五折只用于方向/α_max/π_a* 的轮换；v1.4 又把 G4-1 层筛选的方向版本和 G6 的分位策略改为按题目折 LOFO。 |
| D4 $h_3$ 选择续写 | **采纳** | `trajectory_idx=0,2,…,62`、`block="sel"`、无 est 半；仅用于筛选/匹配/分层。 |
| §五 续写身份含脚本信息 | **采纳（本轮核心修正）** | 种子/`traj_id` 键加入 `script` 与 `stage`；G1.5 的 A3/C 续写、G5 pilot/确认、G4-0/G4-1 等阶段不再静默共享样本。 |
| §五 其它 | 已覆盖 | 配对统计 + 不同种子不冲突；$d^{(2)}$ 不存在 ⇒ E 不可构造；首轮排除后用实际合格数；第 4 轮主结局只用确定性解析；规则标签不替代 judge（v1.4：临时标签 ⇒ Gate GREY）；温度一致、单精度。 |
| §七 硬件/模型 | 采纳为记录项 | A100-80GB 可替代 H100（bf16 吞吐约 0.5×，§7.13 预算按此放大并记入 `config.yaml`）；主模型为 `Qwen3-30B-A3B-Instruct-2507`（非思考），混合模型只用于 G3 思考臂——与 v1.2 一致。 |

## 2. G0.4 原文（v1.2 §7.1 表格行，逐字）
> | G0.4 文本态等价 | 50 个 $h_2$ × $\alpha\in\{+0.5,-0.5\}$（$\hat v_{\text{rand}}$，单位 $r_{20}$）生成 $y_2$ 各 8 条。(i) 同进程、同 `Steer` 实例（α 置 0）、同 batch 组成直接续第 3 轮（greedy 1 条 + T=0.7 32 条）；(ii) 从 JSONL `assistant_ids` 经 §4.1 id 拼接在**新进程、无 hook** 下重建 `ids_3` 续写；(iii) 从 `assistant_text` 经文本路径重建 | (i)(ii) 的 `ids_3` 逐位相同、greedy 续写逐 token 相同、首 token logits $\max|\Delta|<10^{-3}$；(ii)(iii) 不一致率 ≤1%；合并 800 条 $y_2$ 的 T=0.7 续写，$\hat\Delta=\bar e_3^{(i)}-\bar e_3^{(ii)}$ 的**配对**（同一 $y_2$ 的 (i)(ii) 一起重抽）cluster bootstrap 90% CI $\subset(-1.5,1.5)$pp |

v1.3 已把配对的聚类单位改为 $h_2$（50 簇；$y_2$ 嵌套其中）；v1.4 加入设计说明（(ii) 的 batch 组成同 (i)；采样续写用不相交 idx；bf16 下 $10^{-3}$ 容差等价于逐位相等；失败 ⇒ KILL）。

## 3. 本次同步的代码改动（`sycophancy_phase0/`）
- 键：`trajectory.traj_id_of(..., script, stage)`、`seed_arm_key`；`RolloutSpec.stage`；全部 Gate 规格生成器打上阶段标签。
- `templates.next_turn_ex`：整段增量编码为标准、`segment_mismatches` 计数。
- `g0_runner.cache_vs_recompute_kl(cached_prefix_len)`；`g0.g0_7` 新语义；`g04_phase2(idx0=96)`。
- `scoring/judge.JUDGE_PROMPT`（D1）；`scoring/labels.outcomes` 的 $f_t$（D2）。
- `g15.select_h3` 要求 ORIG；`g15.h3_sel_specs/h3_stats`（D4）。
- `g2` 次要对比 97.5%；`tost.paired_cluster_means_bootstrap`（无截断）用于 G2/G4-1/G4-2/G5。
- `g2a.pick_h3/risk_strata`、单侧 95% 分位、`jensen_gap_lb` 支持不等 $M_j$。
- `g41.layer_screen_specs(fold_of_problem)`；`g42.g42_decision`（D 缺失 ⇒ GREY；固执轴不 GO）、`combine_with_exploratory`、`stages_steer.stage_g42_all`、≤100 题每题 1 个 $h_3$。
- `g5.pick_pilot_prefixes(c_pool)`、`var_c_lrt`、`confirmation_F`；`g6.regret(fold_of_problem)`、按题目聚类、`g6_decision` 的 null 记法与 λ=0 一致性检查、`g6_items` 的类型 2 搜索与 $\hat r(h_3)$。
- `g1_criteria`：D 池缺失不阻断 GO；临时标签 ⇒ GREY；`rollout` 记 `labels_provisional`。
- 缺项即 GREY 的落地（§6.1）：`stage_g2a` 无合格 $h_2$、`stage_g5` 无合格 A3/C 共享前缀时写 GREY 条目并返回，不再抛错；`run_specs` 对空规格返回空表；G6 的 LOFO 五分位策略在某折无训练前缀时退化为 $u=0$ 并在 `regret.n_policy_fallback` 计数。前缀筛选阈值（`g2a_max_P_e2`、`g2a_q_range`、`g5_max_P_e2`）只作 smoke 配置项，默认值即计划值（0.1 / [0.15,0.85] / 0 of 32）。
- `g5.confirmation_F` 按 §8.6 调用 $F_{80}(\hat\sigma^2_{f,\mathrm{UB80}},\hat\sigma^2_p,P,n,\delta,\bar p)$（此前传参错误，测试已覆盖）；G0.4 第二阶段的采样续写用不相交的 `trajectory_idx`（96..127），测试断言 traj_id 不相交而非逐位相同。
- 测试：`pytest sycophancy_phase0/tests` 在 CPU 假引擎上 77 项全部通过（本次提交）。

## 4. 仍待外部确认的项
1. S1 的主统计量口径（小 $\lambda$ 极限 $J_0$ + $\hat J_{\mathrm{LB}}$ 估计量 + regime 标记）——与修订稿第 3 点的估计量不同，需用户确认采用 v1.3/v1.4 版本。
2. G6 的 null 记法（GATES 决策 KILL + 备注"命题二 null，不影响其他 Gate"）。
3. 硬件替换（A100）的预算放大系数记入配置而非规格。
