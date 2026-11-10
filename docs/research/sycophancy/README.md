# 谄媚研究文档与复盘证据

第二阶段主计划保留 [v1.54](sycophancy-phase2-write-component-plan.md)。其余四份增量快照已从本目录移除。

原 [第三阶段提案 v1.0](sycophancy-phase3-research-proposal.md) 是历史稿。复盘引用的第 128 行来自下列后续修订稿，两个版本均提供，阅读最新结论时使用后续修订稿。

## 复盘所需报告

| 所需内容 | 原始报告 |
|---|---|
| 后续修订的第三阶段提案，含 11.24 单位及适用条件 | [修订稿](sources/第三阶段研究提案_语言模型跨任务决策的状态表示与反馈控制.md) |
| 程序独立留出，242 对的数字、区间和缓存检查 | [审查报告](sources/program-transfer-work/v150-audit/审查报告.md) |
| 11.24 单位等统计的逐项复算 | [复算数据](sources/program-transfer-work/v150-audit/提交标签复算.json) |
| 程序留出的生成协议与既定规则 | [执行登记](sources/internal1-run/docs/research/early-stage/internal8/internal8_program_v150_execution_prereg.md) |
| 生成前读数的跨任务预测及事实控制比较 | [开发材料分析](sources/program-transfer-work/e2-lite/研究结果.md) |
| 手造修复材料的供给与真实告警来源 | [来源与判决](sources/program-transfer-work/repair-pilot/observed_alerts/真实告警来源与判决.md) |
| 三例真实告警两臂的最终外部验收 | [三例结果](sources/program-transfer-work/repair-pilot/observed_alerts/三例证据关系与读取敏感度.md) |
| 账本控制器与原生、先改、先查的比较 | [三臂结果](sources/program-transfer-work/repair-pilot/observed_alerts/ledger_pilot/三臂实验结果.md) |
| 检查提案能否产生不同行动 | [结局盲判](sources/program-transfer-work/repair-pilot/observed_alerts/ledger_pilot/十例提案的结局盲判.md) |
| 内部姓名读数实验 | [实验一](sources/internal1-run/docs/research/early-stage/internal1/internal1_report.md) |
| 第十二层的增量预测结果 | [实验二第 1 步](sources/internal1-run/docs/research/early-stage/internal2/internal2_step1.md) |
| 信念读数的阳性对照 | [实验三 A](sources/internal1-run/docs/research/early-stage/internal3/internal3_A.md) |
| 改口预警及良性采纳误报警 | [实验三 B](sources/internal1-run/docs/research/early-stage/internal3/internal3_B.md) |
| 第零阶段事实与真假纠错对照 | [第零阶段交接](sources/internal1-run/docs/research/sycophancy-phase0-handoff-2026-10-31-core-findings.md) |
| 千问多轮问答的整体机制交接 | [多轮问答交接](sources/千问多轮问答研究交接.md) |

## 两处数值和表述的限定

109/124 与 113/124 对应不同的比较。历史提案 v1.0 中的 109/124 是同题复问的原生与原遮断文字分叉。留出审查报告中的 113/124 是原遮断与提前遮断文字分叉，前者从新回答开始禁读，后者从旧认可分句结束时开始禁读。复盘应在引用数字时写出两个条件，避免将它们作为同一比较的两个版本。

“第十二层在首答正确子集有额外信息”应具体限定为 S_T 子集、第 12 层残差前八主成分，相对后缀概率基线的留出作品预测增量。两种后缀措辞的相对偏差降低分别为 41.83% 和 36.66%，详见实验二第 1 步。该结果没有确立一般的信念方向或可操纵谄媚方向。

11.24 单位来自修订提案第 128 行的特定收益定义及留出复算。每少一次认可记一单位，每次遮断扣 0.20 单位，相对始终遮断少操作 156 次而多认可 4 次，故每百次净收益为 (156 × 0.20 − 4) / 242 × 100 = 11.24。额外读取算力没有扣除。

文献引用统一使用作者原名 Muhammed Ustaomeroglu 与 Guannan Qu。正式稿使用论文第三版的标题和作者署名。

本次补充的报告保留原文。`sources/` 的目录结构对应原工作区，便于辨别来源。报告中原有的外围材料和运行环境链接仍按原文保留，本目录提供的是上述复盘直接依赖的报告与复算数据。
