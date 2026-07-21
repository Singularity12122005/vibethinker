# Qwen2.5-Coder-3B 正式后期主线

本页描述两条由真实后期血缘重建的 SFT→64K Math RL 主线：

1. 15K 三域 SFT（math/code/general 各 5K）→ SFT epoch 1 → 共享 Math500 RL。
2. 30K 原生教师三域 SFT（各 10K）→ SFT epoch 5 → 同一 Math500 RL recipe。

## 来源映射

- `train_sft_math_code_v1.py` →
  `qwen25/sft.py`：无 packing、超长报错、assistant-only loss、LoRA all-linear。
- `common_utils.py`、`math_grading.py`、`math_rl_protocol.py` →
  复用 `common/` 和 `qwen35` 已公开的健壮 JSONL、超时判分及 final-answer
  纯逻辑；Qwen2.5 reward 封装位于 `qwen25/verl_reward.py`。
- `prepare_qwen25_64k_model_view.py`、历史 runtime/merge/validate 脚本 →
  `qwen25/runtime_model.py`。
- 历史 VERL reward、manager、checkpoint、launcher 与 tests →
  `qwen25/verl_reward.py`、`reward_manager_math.py`、
  `checkpoint_schedule.py`、`verl_launcher.py` 和 `tests/qwen25/`。
- 15K 的 math/code/general 构建、visible-after-think 转换与 RL candidate 审计脚本 →
  `qwen25/assembly.py` 的确定性组装、协议审计和可选 benchmark deny 审计。
- 30K 的 prompt pool、原生 channel 蒸馏、verified backfill、finalize 与 code
  harness 脚本 → `qwen25/assembly.py`、`code_verifier.py`；联网教师调用和
  数据源抓取不迁移。
- 历史 Math RL 数据构建合同 →
  `qwen25/math500.py`：恢复原始 gold、规则复验、exact/near deny、
  topic×difficulty quota、768-token reserve 与 VERL schema。

历史冻结 bundle/manifest 仅用于提取 VERL v0.8.0、FSDP2、vLLM async、64K
预算和 optimizer/LoRA 参数；内部路径、任务标识、数据标识、凭据和提交逻辑均未迁移。

## 共享与分支边界

- 两个 SFT YAML 分别冻结 15K 和 30K 的数据、10-epoch schedule 与所选 RL 起点。
- `verl_math500_64k.yaml` 是两条分支唯一共享的 RL recipe：500 prompts，
  16×A100-80GB/2 节点，prompt 768 + completion 64,768，fresh LoRA
  r16/alpha32，G=8，global prompt batch 16，actor LR 1e-6，KL loss 0.01。
- `patches/verl-math-rl/` 保存 epoch-boundary checkpoint、原子 `COMMITTED`
  marker 与 Qwen2.5 包导入 adaptation；它必须应用到干净 VERL v0.8.0。
- RL 计划 5×31=155 steps。当前证据只支持两条分支各自正式第 1 epoch
  checkpoint（step 31）和 capability/health 双面板完成。
- 上述完成边界来自迁移时可用的内部记录；公共仓库未发布脱敏 marker/hash receipt，
  因此应理解为 `reported`，而不是第三方可独立复核。
- 15K 后期审计有 4 条高置信 benchmark 近重复待重新裁决；30K 缺少最终全量
  benchmark deny 的充分证据。两者都不能发布“零污染”结论。

## 运行

所有路径都必须显式传入，配置不猜测挂载点：

```bash
python -m vibethinker_experiments.qwen25.sft \
  --config configs/qwen25/sft_15k.yaml \
  --model MODEL_DIR --data SFT_JSONL --output-dir SFT_OUTPUT

python -m vibethinker_experiments.qwen25.math500 build \
  --sft NATIVE_SFT_JSONL --prompt-pool MATH_PROMPT_POOL_JSONL \
  --deny-index BENCHMARK_INDEX_DIR --output MATH500_JSONL

python -m vibethinker_experiments.qwen25.runtime_model \
  --base-model MERGED_SFT_MODEL --output RUNTIME_MODEL

python -m vibethinker_experiments.qwen25.math500 prepare-verl \
  --input MATH500_JSONL --model RUNTIME_MODEL --output-dir VERL_DATA

python -m vibethinker_experiments.qwen25.verl_launcher \
  --config configs/qwen25/verl_math500_64k.yaml \
  --model-path RUNTIME_MODEL --train-file VERL_DATA/train.parquet \
  --output-dir RL_OUTPUT --lineage qwen25-15k \
  --model-receipt MODEL_RECEIPT.json \
  --data-receipt DATA_RECEIPT.json \
  --runtime-receipt RUNTIME_RECEIPT.json
```

30K SFT 把第一条命令的配置替换为 `sft_30k_native.yaml`。运行 RL 前应先用
`runtime_model.merge_sft_adapter` 合并所选 SFT adapter，再创建 64K runtime
view；这样 adapter-disabled reference 才是所选 SFT policy，而不是原始 base。30K
RL 同时把 `--lineage` 改为 `qwen25-30k`。三个 receipt 分别绑定所选 SFT epoch 与
adapter SHA、Math500 parquet SHA/行数，以及已 apply-check 且验证 COMMITTED 的
VERL runtime；只有 `--dry-run` 可不提供。

## 安全与不可还原边界

- `code_verifier.py` 只有隔离 Python、wall timeout 和 rlimit，不是 hardened
  sandbox；不可信代码必须在禁网、最小权限的外部容器或 VM 中执行。
- 未迁移真实数据、teacher 输出、checkpoint、训练结果、凭据或集群调度。
- 未公开的教师服务行为、运行时镜像、完整 optimizer/RNG state 和最终 30K 全量
  benchmark deny 证据无法从现有公开安全材料中完整还原。
