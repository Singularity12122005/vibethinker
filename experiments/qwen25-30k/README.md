# Qwen2.5-Coder-3B：30K 原生教师 SFT → 64K Math RL

## 数据与 SFT

- SFT 共 30,000 条：math、code、general 各 10,000 条。
- 教师的原生 reasoning channel 与 visible content 在同一次调用中生成；命中任一输出
  wall、非正常结束或完整 chat 超过 30,000 tokens 的 generation 均拒绝，不做本地截断。
- math 用原始 gold 做规则复验；code 仅保留完整可执行测试通过的质量 A 样本，历史上未
  保留 tests 的 5K code prompt 不进入正式原生教师数据，而由确定性 verified backfill
  替换；general 用 reference-guided judge 校验显式约束。
- 最终数据无重复 prompt，协议为 `<think>reasoning</think>visible answer`；实测完整
  chat 最大 16,695 tokens。
- LoRA r16/alpha32/all-linear，global batch 128，学习率 5e-5，训练 10 epoch、
  共 2,350 optimizer steps；每个 epoch 235 steps。

## 检查点选择与 RL

- 正式 RL 起点取 SFT epoch 5（step 1,175）。
- 与 15K 分支共用同一批 500 个 Math prompts 和相同的 64K VERL recipe。
- RL 使用 16×A100-80GB（2 节点）、VERL v0.8.0、FSDP2、vLLM async，
  prompt 768 + completion 64,768。
- 在合并后的 SFT policy 上新建 LoRA r16/alpha32；G=8、global prompt batch=16、
  actor LR=1e-6、KL loss coefficient=0.01。
- 计划 5 epoch，每 epoch 31 steps；正式 epoch 边界为 31/62/93/124/155。

## 代码与配置

- `src/vibethinker_experiments/qwen25/`：数据组装、SFT、Math500、reward、runtime 与启动；
- `configs/qwen25/sft_30k_native.yaml`：30K 原生教师 SFT；
- `configs/qwen25/verl_math500_64k.yaml`：两条 Qwen2.5 主线共享的 RL recipe；
- `docs/qwen25.md`：命令、来源映射和复现限制。

## 已完成边界与限制

- 迁移时可用的内部记录报告 30K 原生教师数据组装和 10-epoch SFT 已完成。
- 共享 Math500 构建对入选 RL prompt 执行了 exact/near deny、gold self-grade、
  教师答案复验与 768-token prompt reserve 检查。
- 同一记录只报告正式第 1 epoch checkpoint（step 31）及 capability/health 双面板完成；
  不得声称 5 个 RL epoch 全部完成。
- 仓库未发布脱敏运行 receipt 或结果 hash，因此这些属于 `reported` 边界，不能由公开
  文件独立复核。
- 没有足够证据证明最终 30K SFT 全量完成了同一版 benchmark deny 审计，因此不能
  声称全量零污染。
- 64K runtime view 使用未缩放 RoPE 元数据扩展；它不是原生 64K 能力证明。
