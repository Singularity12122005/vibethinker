# Qwen3.5-2B：30K SFT → 128K VERL RL

这是一条连续主线：先在三域 30K 数据上完成 LoRA SFT，再合并选定的 SFT
checkpoint，以同一套 128K、16-GPU、GRPO 配方比较 Math500 与 Mix1K 两个 RL
数据变体。唯一公开实验卡是 `experiments/qwen35-30k/README.md`。

仓库只保存可复用代码、配置和状态边界，不包含数据行、生成结果、模型权重、
checkpoint、私有资源标识、凭据或提交记录。

## 已有证据与状态边界

以下状态来自迁移时可用的内部记录，公共仓库不含脱敏 marker/hash receipt，因此标为
`reported`，不等同于第三方可独立复核：

- 数据构建已完成：math、code、general 各 10,000 条，合计 30,000 条；
- SFT 已完成 10 epochs；进入 RL 的实际起点是 SFT epoch 9，而不是最终 epoch 10；
- Math500 和 Mix1K 都已生成正式首个 epoch 边界 checkpoint；
- 两个变体都已分别完成 Capability 500 题与 Health 500 题的生成、判分和封存；
- 原 RL 训练随后失败或取消，计划的 5 epochs 均未闭环，因此两者状态都是
  `partial`。

已有证据边界是正式首个 epoch checkpoint，而非单次 optimizer update；同时也不能
外推到计划的五轮训练已经闭环。封存的 Panel 产物证明评测流程已经执行，不在本仓库
中公开其题目、回答、分数或私有产物位置，也不据此声明能力提升。

## 来源映射

- `data_pipeline.py` 保存 prompt pool、教师结果连接、三域配额和最终审计合同；
- `data_builder.py` 保存 Math500 选择、Mix1K 合并和 VERL 数据转换；
- `train_sft_qwen35.py` 保存 Qwen3.5 LoRA SFT 的 template、collator、目标模块和
  训练入口；
- `math_protocol.py`、`math_grading.py`、`verl_reward.py`、
  `reward_manager_math.py` 保存最终答案判分、协议与 VERL reward ABI；
- `runtime_model.py` 保存 adapter 合并、128K runtime view 和 metadata 校验；
- `checkpoint_schedule.py` 保存 checkpoint 提交标记合同；
- `verl_launcher.py` 与 `configs/qwen35/verl_128k_*.yaml` 保存共享 VERL 配方和两个
  数据变体；
- `platform_submitter.py` 只提供已清理的通用提交边界。Capability/Health 评测复用
  `vibethinker_experiments.evaluation`，不在实验目录复制平台绑定的 submit 或
  report 脚本。

## 30K 数据装配合同

`data_pipeline.py` 补齐此前缺失的确定性纯逻辑：

1. 校验 prompt pool 的单 user 消息、domain、规范化 hash 和唯一性，同时保留
   primary/reserve 的冻结顺序；
2. 按 prompt hash 连接异步教师生成结果；同一 prompt 的多次结果按 attempt 和内容
   hash 稳定排序，因此不受并发完成顺序影响；
3. 从教师原生 reasoning/content 通道装配
   `<think>reasoning</think>visible_answer`，拒绝非 `stop`、空通道、嵌套协议标签和
   缺失 token 计数；
4. 调用 verifier：math 使用包内等价性判分，code/general 由调用方注入已经审计的
   verifier；API 并发、重试和 general judge transport 不在该模块重复实现；
5. 按冻结的 prompt-pool 顺序选择 verifier pass，失败时自然使用 reserve 补足每域
   10,000 条；
6. 最终审计三域配额、跨域去重、协议、verifier 类型、code 全测试通过、教师
   finish reason，以及 think/visible/chat 的 15K/15K/30K token 墙，再用固定 seed
   合并洗牌。

教师结果必须携带 prompt hash、reasoning、content、finish reason 以及 think、
visible、完整 chat token 计数。code 的测试载荷、general 的参考答案和 math gold
只参与验证，不进入最终训练行。

`data_builder.py` 是后续 RL 数据入口。`select-math500` 强制接收 benchmark/panel
deny index 及冻结三份索引文件 hash 的 receipt，任一 exact/near 命中即失败，并把
receipt SHA-256 写入每条入选记录；本仓库不含正式 deny index。`combine` 将已审计
Math500 与 GSM8K 500 条精确合并、跨组件去重并固定洗牌，公开名称统一为 Mix1K。

## SFT 合同

- 三域各 10K，10 epochs，最大序列长度 32K；
- assistant-only loss：user prompt 和 padding 都是 `-100`；
- generation prompt 停在裸 assistant header，不预填 `<think>`；
- 超长样本失败，不静默截断；
- LoRA 只进入 language model 的 Qwen3.5 线性层，拒绝视觉模块；
- 保存每个 epoch 的 checkpoint；RL 明确从 epoch 9 合并出的 runtime 启动。

配置位于 `configs/qwen35/sft_30k_lora.yaml`。配置中的 10 epochs 是已完成的 SFT
事实，不应与 RL 配置中的计划 5 epochs 混淆。

## 共享 VERL 配方与数据变体

`configs/qwen35/verl_128k_base.yaml` 是真实公共 base，`verl_launcher.load_config`
执行纯 Python 深合并；不是依赖 YAML 自身不存在的继承语义。

- `verl_128k_math500.yaml`：Math500，500 条；
- `verl_128k_mix1k.yaml`：Mix1K，即 Math500 500 条 + GSM8K 500 条。

两个子配置只覆盖数据身份和实验名，其余共享：

- SFT epoch 9 合并模型作为 actor/ref 起点；
- 1024 prompt + 130048 response = 131072 context；
- full-parameter FSDP2、2 节点 × 8 GPU、Ulysses SP=8；
- rollout `n=8`，GRPO，token-mean loss，KL loss `0.01`；
- exact completion length/truncation reward、相同 checkpoint 策略；
- `total_epochs: 5` 表示计划上限，不表示已完成。

下面的命令用于配置校验与命令构建。它只有在另行提供已固定的 Qwen3.5 私有 runtime
后才能执行正式 GPU 训练：现有公共补丁只覆盖 checkpoint 调度与包导入，manifest 中
五项 Qwen3.5 runtime 行为仅有文档证据。仓库因此不声称可由公开依赖独立复现正式运行。

```bash
python -m vibethinker_experiments.qwen35.verl_launcher \
  --config configs/qwen35/verl_128k_math500.yaml \
  --model-path /path/to/runtime \
  --train-file /path/to/train.parquet \
  --output-dir /path/to/output \
  --model-receipt /path/to/model-receipt.json \
  --data-receipt /path/to/data-receipt.json \
  --runtime-receipt /path/to/private-runtime-receipt.json
```

Mix1K 只需替换为 `verl_128k_mix1k.yaml` 和对应数据文件。共享 checkpoint 补丁及
Qwen3.5 adaptation 记录在 `patches/verl-math-rl/`；本页不声称能逐字节复原未封存的
私有 runtime。
三个 receipt 必须分别证明 SFT epoch 9/adapter SHA、数据变体/行数/parquet SHA，
以及五项私有 runtime 行为和完整 apply-check；只有 `--dry-run` 可省略 receipt。

## 未闭环部分

- Math500 和 Mix1K 的 5-epoch 训练均未完成；
- 没有终局 checkpoint；
- 已完成的两个 500 题 Panel 评测没有在公共仓库发布结果，因此不能给出可复核的
  能力增益结论；
- 需要从已提交的 epoch 边界 checkpoint 继续或重跑，并以同一通用 evaluation
  合同完成终局 Capability/Health 对比。

## CPU 验证

```bash
pytest tests/qwen35
ruff check src/vibethinker_experiments/qwen35 \
  configs/qwen35 experiments/qwen35-30k \
  experiments/openthinker3-skywork/README.md \
  docs/qwen35.md docs/openthinker3.md tests/qwen35
```

CPU tests 覆盖数据装配、配额补齐、最终审计、SFT template/collator、自然答案判分、
reward、runtime、checkpoint、配置继承和平台模板清理。GPU 与多节点测试默认跳过。
