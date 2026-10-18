# Phase-0 交接说明（给执行的 coding agent 与项目负责人）

> 规格书：[`sycophancy-phase0-execution-plan.md`](sycophancy-phase0-execution-plan.md)（v1.3）。参考实现：[`sycophancy_phase0/`](../../sycophancy_phase0/)；逐步运行说明：[`sycophancy_phase0/RUNBOOK.md`](../../sycophancy_phase0/RUNBOOK.md)。理论与动机：[《深入研讨》](sycophancy-dynamic-control-deep-dive.md)。

## 1. 现在有什么

| 层 | 内容 | 验证方式 |
| --- | --- | --- |
| 推理/干预 | `Steer` hook（按 `position_ids` 决定位置，S_gen/S_read/S_all，梯度模式）、按行种子 Gumbel-max 采样器、id 拼接模板（三种模式、EOS/think 规范化）、clean forward / z 提取 / r_L / teacher-forced log-prob、KL、路由翻转、router top-k | CPU 上用 transformers==4.57.1 的随机小型 Qwen3-MoE 实测（`tests/test_hf_semantics.py`, `tests/test_g0_runner.py`） |
| 引擎 | `HFEngine`（steered，按 batch 分组）、`VLLMEngine`（α=0，关 prefix caching，按请求种子；**只能在 GPU 上验证**）、`FakeEngine`、按 α 路由 | 假引擎全链路测试 |
| 轨迹 | §10.2 schema、`prefix_id`/`traj_id`/`arm_id` 规范串、sel/est/subsplit、JSONL 与 z 存储（fp16，溢出分块转 fp32） | `tests/test_rollout.py` |
| rollout | 批量四轮循环；新轨迹 / D-prefill / 前缀库续写 / 部分轨迹（`stop_after`）；种子按 (run, problem, prefix, arm, idx, turn) 派生 | 同上 |
| 评分 | 严格确定性解析（§6.1）、规则 stance、judge 提示词（附录 E）与三段解析、一致性检查、人工校验抽样/κ/灵敏度-特异度/PPI 切换规则 | `tests/test_parse.py`, `test_judge_data.py`, `test_human_validation.py` |
| 数据 | F2 八模板（gold ≤2 位小数）、F3 程序生成+沙箱、F1 加载/翻译一致性、distractor 挖掘、池、折 | `tests/test_judge_data.py` |
| 分析库 | 方差分量（不等 M）、bootstrap-t 上限、KL 前沿（β* 只由 sel 决定）、Jensen 缺口 $\hat J_{\mathrm{LB}}$（逐前缀）+ regime 标记、协方差估计量、功效、TOST、等张回归、梯度/自然梯度/线性区/ρ_v、LOQO 岭回归阶梯、因子模型与反向归纳、证言模型、PPI、cluster-robust logistic | `tests/test_analysis.py` 等（含模拟验证） |
| Gate | G0（八项的统计量 + 数据收集，G0.4 两阶段、G0.8 跨栈）、G1、G1.5、G2、G2′-a、G3、G4-0、G4-1、G2′-b、G4-2、G5（pilot/确认）、G6：规格生成 + 估计量 + 判据 + GATES.md 条目 | 假引擎缩小规模的端到端测试（`tests/test_stages*.py`） |
| 运行 | `runs/<run_id>/`：config.yaml+SHA-256、env.txt、git_commit.txt、GATES.md、DEVIATIONS.md、tables、figures、budget.json、REPORT.md | `tests/test_run.py`, `test_report.py` |

## 2. 三轮审查改了什么（要点）
- v1.2 的 hook"生成时只改最后一列"在 `use_cache=False`/assisted decoding 下静默错位，`S_read` 在解码第 2 个 token 崩溃——改为按 `position_ids` 的位置规则（§4.4）。
- v1.2 的宽松数值解析会把"60 或 40"记为让步（$e_4=1$）——改为严格 `Fraction()` 路径。
- G2′-a 的 $\mu$ 中心累积量级数在近零质量下偏低一半、低均值时发散、各前缀合并会得假 GO——改为 $(1-z)$ 展开的无偏截断下界 $\hat J_{\mathrm{LB}}$，逐前缀，regime 标记阻止在松下界上 KILL（§8.4、§7.4）。
- 两阶段 bootstrap 把前缀内分量算两次（SE 高估 1.4 倍）——所有前缀级 CI 改为前缀级 cluster bootstrap。
- 其余：bootstrap-t 上限、KL 前沿赢者诅咒、Bernstein 界的输入、G0.6 的 TV 上界与 n≥50000、G0.4 按 $h_2$ 聚类、G5 确认阶段联合规则的功效声明。

## 2b. 第四轮（外部审查备忘录处置，v1.4）
- 规格书 v1.4 与《最小修订确认稿》的逐条处置见 `sycophancy-phase0-revision-response.md`；G0.4 原文未缺失（粘贴截断），并补了设计说明。
- 种子/`traj_id` 键含脚本与阶段；G2′-a/G5 缺合格前缀 ⇒ GREY 条目；$f_t$ 仅在相邻两轮都 EXPLICIT 且有值时定义；G0.7 以 $-\infty$ 为支持集缺陷。
- 第五轮：处置文档经对抗式核对（18 条确认）后，G0.4 参考实现按设计说明重做（hooked HF 引擎 + 内存 `ids_3` + 实测 logits + `design_ok`）、G0.3 实现 cache 逐位验证与"不适用"、G0.1 报告 `segment_mismatches`、G4-1 传题目折、Beta 诊断不钳方差、有限 λ 描述曲线、§7.4/§8.4/§8.2 文本与实现对齐。
- 第六轮复核（11 条）：G0.3 调用形式、有限 λ 曲线落盘（摘要 + `G2a_J_of_lambda.csv`）、$\kappa_1<10$ 的可执行报告规则、`config.hardware`、文本精度修正。
- 第七轮（外部第二次审查）：主估计量改为截断目标的差分 U 统计量 $\hat J_{\mathrm U}$；近零标记不再作保证；G6 结论范围限定；首轮干预臂不筛选；$10^{-4}$ 声明删除；G5 联合功效 0.50/6.5pp；采样器单次调用；R3 空区间缺失；Bernstein 命名；三处残留冲突统一。
- 本提交 `pytest`：84 passed（CPU、假引擎）。

## 2e. 第二次 GPU 诊断（2026-10-18，五项，提交代码）
- 通过：左填充/S_read 位置检查（判据改为 dtype 精确期望输出；发现 pad 位置 id=1 可被 S_read 误 steer，hook 加 `real_mask` 修正）、hook 自检 6/6。
- 重建误差：生成 vs teacher-forcing 逐 token |Δ log p| 均值 0.022、rms 0.078、最大 1–2 nats；只支持"切换后端未消除差异"（两后端采到的是不同序列），"固有、与后端无关"与"底噪 3–9 倍"撤回（第十二轮）；`attn_implementation` 入冻结配置。正式口径改为固定序列上的带符号误差 $\Delta_k$、$D_y=\sum\Delta_k$（`decode_prefill_kl`）。
- 风险：G0.5 的 99.5% greedy 一致率（首 token 诊断 logits 差达 1.25）；正式 G0 前做 32×64 诊断，**分开**计算差异（固定历史逐步回放）与生成稳定性（自由生成相同率/首次分歧）两个量（`batch_consistency`）。
- **阻塞项**：HF 解码 B=32 仅 34 tok/s，HF 预算作废。**决定：路线 1**——独立环境试新版 transformers 的 experts 后端（4.57.1 无 `experts_implementation`；锁定具体版本；首次比较只换专家后端、不编译；先过 HF 语义测试与 RUNBOOK §6 诊断）；暂不削减核心比较样本，不再用原预算；vLLM 的 5–10k tok/s 待实测。
- 随机方向：KL≤0.10 的越过点夹在 (0.25, 0.5)（无 0.30 数据点）；正式 α_max 另受 flip 与质量限制。

## 2f. 第十二轮（2026-10-18）：执行方复核 5c04b43 + `/goal` 研究档案
- 代码：`real_mask` 对 `use_cache=False` 增长序列的规则（执行方反例 [2,5]→[2,6]）、不支持形状报错、`generate_steered` 传掩码；`generation_vs_teacher_forcing` 改带符号；新增 `decode_prefill_kl`、`batch_consistency`（两指标）、`analysis/g6_iv.py`（2SLS、校正得分、识别强度、LQ 上限、去衰减 ρ²）。
- 文档：规格书 §2.1/§4.2/§4.4/§4.7/§7.1/§7.11 更正；RUNBOOK §6.2 三项测量协议；新增 `docs/research/sycophancy-phase0-goal.md`——主张阶梯 C0–C6、最强表述 C★（闭环优势由读出可靠性 ρ² 预报）、命题 P1–P5（含证明与模拟数值）、研究档案（已证明/候选/反例/淘汰/缺口/下一轮）。
- 独立对抗审查（代理，独立上下文）驳回了 r1 的两项（离散动作下"实现比例≈λ"、C★ 的三分法诊断）并列出 13 条夸大陈述；r1.1 逐条修正，新增 U-统计量多项式校正得分、精确信息价值计算、HC1/CR1、F 通过概率、cluster bootstrap；§7.11 加入预注册修正候选（G6 的 $\hat r$ 用 128 条 sel 续写，待决定）。
- 本提交 `pytest`：96 passed（CPU、假引擎）。

## 2d. 首次 GPU 接触（2026-10-17，A100-80GB，sdpa，torch 2.8.0，transformers 4.57.1；smoke，不是 G0）
- 通过：四轮模板一致性（真实分词器）、支持集 0/128、真实 cache 的逐位验证路径、α∈{0,±0.5} 的 T=0.7 采样生成流畅（64 token 截断）。hook 六项通过来自执行方本地修改的代码，提交 f56c874 的自检比较的是最终 logits，会误判——第九轮已改为比较被 hook 层的实际输出。
- 发现：只 steer 后缀时前缀最终 logits 差 1.25，来源待检验（专家分组是假设）；单样本 cache-vs-recompute KL 4.3e-3（T=1 旧口径）；B=1 吞吐 6.9 tok/s。
- 第九轮修正（执行方复核 6 条）：teacher-forced 对数概率/KL/梯度统一到 T=0.7（此前 T=1，必须重测相关数值）；生成路径对数概率取原始分数（`generation_vs_teacher_forcing`）；G0.3 区分不适用/数值故障/覆盖不足，先判其他失败；"十倍底噪"降为一致性检查，G4-1 前置验证 G0 摘要；§4.4/§4.2 机制解释收窄。
- 下一步诊断按 RUNBOOK §6 的顺序执行。

## 3. 没有验证 / 需要 GPU 才能验证
- vLLM 引擎（API 按 vllm ≥0.9 编写）、G0.8 跨栈等价、G0.4 的"新进程"路径。
- 真实 tokenizer 的 `apply_chat_template` 与 id 拼接一致性（G0.1 实测，预期 ≤1% 不一致）。
- bf16 下的 batch 不变性（G0.5）、支持集缺陷（G0.7）在真实模型上的数值。
- 思考臂（`M_hybrid`，`enable_thinking=True`）的前缀自建流程只在模板层测试过。
- judge 的 JSON 解析失败率、人工标注。

## 4. 执行时必须注意（来自规格书 §0）
1. 任何 `[F]` 参数在 G1 `est` 块被查看后不得更改；改动写 `DEVIATIONS.md`。
2. 前缀选择只能用 `sel` 块的 pre-treatment 量（`select_prefixes` 只读 `stats[..]["sel"]`）；效应只用 `est`。
3. 种子不跨臂共享；vLLM `enable_prefix_caching=False`。
4. 停止并报告：任一 G0 失败（例外：G0.3 仅中位数未达的分级，§7.1）、G1 $N_q<30$、任一 GREY、judge 解析失败 >1%、模板不一致 >1%、截断 >5%。
5. G2′-a 的 $\kappa_1$ 在 G4-1 之前是占位（15 nats）；G4-1 后用 `stage_g2a(ctx, kappa1=...)` 回填。
6. 预注册的预期结果：G2′-a 很可能 KILL 或 GO-with-caveat，G5 的 $G$ 可能不显著——这是可发表的结果，不是失败。

## 5. 建议的下一步
0. 吞吐路线 1 的小规模比较（RUNBOOK §6 第 4 项的决定）与 §6.2 的三项测量（时序拆分、固定序列带符号误差、batch 两指标）；结果贴回后更新 §4.2 与 G0.5 的预注册修正。研究档案按"继续做下去"逐轮推进（`sycophancy-phase0-goal.md` §0）。
1. 在 GPU 环境按 RUNBOOK 跑 `pytest`（含 HF 语义测试）→ data/mine/r_L → G0；G0 任一失败先修管线。
2. 在 G1 `est` 结果被查看之前，把 `runs/<run_id>/config.yaml` 的 SHA-256 与 git tag 一起冻结（§9）。
3. 每个 Gate 结束后把 `GATES.md` 条目与 `tables/*_summary.json` 同步回 `docs/research/`（或 PR），便于审阅。
