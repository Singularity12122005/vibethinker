# Qwen2.5-Coder-3B：15K 三域 SFT → 64K Math RL

## 数据与 SFT

- SFT 共 15,000 条：math、code、general 各 5,000 条。
- math 采用难题优先、规则可判分、无截断的清洗选择；code 保留可执行测试验证通过的解答并转换为 visible-after-think；general 从干净 prompt-only 池生成同一教师调用的 reasoning 与 visible answer。
- 每条训练样本均为单轮 user/assistant，assistant 目标是
  `<think>reasoning</think>visible answer`；prompt 不附加协议指令。
- 完整 chat 上限实测约 29,967 tokens。SFT 使用 32,768 上限、无 packing、超长即报错、assistant-only loss。
- LoRA r16/alpha32/all-linear，global batch 128，学习率 5e-5，训练 10 epoch、共 1,180 optimizer steps；每个 epoch 118 steps。

## 检查点选择与 RL

- 正式 RL 起点取 SFT epoch 1（step 118），不是最后一个 SFT epoch。
- 两条主线共用同一批 500 个已审计 Math prompts 和同一 64K VERL recipe。
- RL 使用 16×A100-80GB（2 节点）、VERL v0.8.0、FSDP2、vLLM async，
  prompt 768 + completion 64,768。
- 在合并后的 SFT policy 上新建 LoRA r16/alpha32；G=8、global prompt batch=16、
  actor LR=1e-6、KL loss coefficient=0.01。
- 计划 5 epoch，每 epoch 31 steps；正式 epoch 边界为 31/62/93/124/155。

## 代码与配置

- `src/vibethinker_experiments/qwen25/`：数据组装、SFT、Math500、reward、runtime 与启动；
- `configs/qwen25/sft_15k.yaml`：15K SFT；
- `configs/qwen25/verl_math500_64k.yaml`：两条 Qwen2.5 主线共享的 RL recipe；
- `docs/qwen25.md`：命令、来源映射和复现限制。

## 已完成边界与限制

- 迁移时可用的内部记录报告 15K 数据组装、审计和 10-epoch SFT 已完成。
- 同一记录只报告正式第 1 epoch checkpoint（step 31）及 capability/health 双面板完成。
- 仓库未发布脱敏运行 receipt 或结果 hash，因此这些属于 `reported` 边界，不能由公开
  文件独立复核。
- 不得据此声称 5 个 RL epoch 全部完成。
- 后期 benchmark deny 审计发现 4 条高置信近重复，仍需重新裁决；本分支不能声称零污染。
- SFT 数据本身不提供 32K 以上位置训练信号；64K runtime view 属于未缩放 RoPE
  元数据扩展，不等价于证明原始基座具备原生 64K 质量。
