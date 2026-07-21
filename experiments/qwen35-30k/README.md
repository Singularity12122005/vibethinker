# Qwen3.5-2B 30K SFT → VERL RL

## 研究问题

三域 30K SFT 能否为 128K 全参数 GRPO 提供稳定起点，以及在完全相同训练配方下，
Math500 与 Mix1K 数据变体会产生什么差异？

## 实际做法

- 构建并审计 math、code、general 各 10K；
- 完成 10-epoch LoRA SFT，实际选择 epoch 9 作为 RL 起点；
- 合并 adapter，使用同一 128K runtime、GRPO、reward、checkpoint 和
  2 节点 × 8 GPU 配方；
- 比较 Math500（500 条）与 Mix1K（Math500 500 条 + GSM8K 500 条）；
- 对两个变体分别执行 Capability 500 题与 Health 500 题评测。

## 状态

`reported-partial`。

迁移时可用的内部记录报告：两种 RL 数据变体都产生了正式首个 epoch 边界 checkpoint；
各自的 Capability 500 题和 Health 500 题也完成生成、判分和封存。原训练随后失败或
取消，计划的 5 epochs 没有闭环。仓库未发布脱敏 marker/hash receipt，因此这些完成
边界不能由公开文件独立复核。

当前证据边界是正式首个 epoch checkpoint 和对应 Panel 评测产物，强于单次
optimizer update；计划的五轮训练则没有闭环。

## 代码位置

- `src/vibethinker_experiments/qwen35/data_pipeline.py`：30K 教师结果的确定性装配、
  verifier 接口、配额补齐和最终审计；
- `src/vibethinker_experiments/qwen35/data_builder.py`：Math500 与 Mix1K 的 RL
  数据构建；
- `src/vibethinker_experiments/qwen35/` 其余模块：SFT、runtime、reward、
  checkpoint 和 VERL 启动；
- `configs/qwen35/verl_128k_base.yaml`：公共 RL 配方；
- `configs/qwen35/verl_128k_math500.yaml`、`verl_128k_mix1k.yaml`：两个数据变体；
- `docs/qwen35.md`：来源映射、合同和证据边界。

评测只引用通用 `vibethinker_experiments.evaluation`；外部运行只引用清理后的
`platform_submitter.py`，本实验卡不携带平台绑定 submit/report 脚本。

## 当前结论

数据、SFT、epoch 9 起点、两种 RL 数据合同、首个正式 epoch checkpoint，以及两套
Capability/Health 评测流程都有执行证据。由于没有完成 5 epochs，也没有公开终局
checkpoint 和可复核终局分数，不能声明能力提升或两个数据变体的优劣。

## 未闭环

- Math500 与 Mix1K 均未完成计划的 5 epochs；
- 无终局 checkpoint；
- 封存的评测结果不随仓库发布；
- 五项 Qwen3.5 runtime 修改只有文档证据，正式 GPU 命令依赖未公开的固定 runtime，
  公共仓库只能独立完成配置校验和 dry-run；
- 后续需恢复或重跑至终局，再按同一 evaluation 合同完成对比。
