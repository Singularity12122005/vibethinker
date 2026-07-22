# VibeThinker Experiments

一个面向小参数推理模型后训练的可审计研究代码仓库。公开入口只保留四条真实主线，
数据处理、蒸馏、训练、评测和工程修复作为共享实现集中维护。

## 四条主线

1. [Qwen2.5-Coder-3B：15K SFT → 64K Math RL](experiments/qwen25-15k/README.md)
2. [Qwen2.5-Coder-3B：30K SFT → 64K Math RL](experiments/qwen25-30k/README.md)
3. [Qwen3.5-2B：30K SFT → 128K VERL RL](experiments/qwen35-30k/README.md)
4. [OpenThinker3-1.5B：当前 Skywork math/code RL](experiments/openthinker3-skywork/README.md)

Qwen3.5 的 Math500 与 Mix1K 是同一 RL 主线的两个数据配置，不拆成独立实验。
运行时修复、失败重试、checkpoint 保存和 Panel 评测也不额外制造实验编号。

## 代码结构

```text
configs/       四条主线的冻结 recipe 与脱敏平台模板
data/          schema、合成样例和真实数据放置说明
experiments/   四条主线各自的一页实验卡
checkpoints/   checkpoint 放置和恢复合同说明
results/       评测与训练摘要的放置说明
docs/          训练细节、评测协议、工程边界与可复现性
patches/       对 VERL、vLLM 的可审查上游修改
src/           数据、蒸馏、训练、验证、评测和工程实现
tests/         CPU 单元测试、合同测试及显式跳过的 GPU 测试
```

`src/vibethinker_experiments/` 按职责分层：

- `qwen25/`、`qwen35/`、`openthinker3/`：模型和主线特定逻辑；
- `common/`、`data/`：原子 IO、JSONL、哈希、清洗、去重和去污染；
- `distillation/`、`verification/`：教师生成编排与数学/代码验证合同；
- `checkpoints/`、`persistence/`、`runtime/`：保存、发布、manifest 和长上下文探针；
- `evaluation/`：Capability/Health Panel 的生成、判分、封存与幂等状态机。

## 文档导航

- [`docs/qwen25.md`](docs/qwen25.md)、[`docs/qwen35.md`](docs/qwen35.md)、
  [`docs/openthinker3.md`](docs/openthinker3.md)：三类模型的完整运行合同；
- [`docs/methodology.md`](docs/methodology.md)：实验边界与结论强度；
- [`docs/engineering.md`](docs/engineering.md)：蒸馏、验证、checkpoint、持久化与 runtime；
- [`docs/evaluation.md`](docs/evaluation.md)：Panel 评测和产物状态机；
- [`docs/process_observation.md`](docs/process_observation.md)：ARU 过程观测合同与 toy CPU pipeline；
- [`docs/reproducibility.md`](docs/reproducibility.md)：复现记录与发布安全要求；
- [`docs/research/recipe-evidence-summary.md`](docs/research/recipe-evidence-summary.md)：
  公开 recipe 证据摘要。

## 资产边界

仓库不提交：

- 真实训练数据、正式 benchmark 题目或模型逐题输出；
- 模型、LoRA adapter、checkpoint、optimizer 或 RNG state；
- runtime 压缩包、wheelhouse 或完整 vendored VERL；
- GPU/Ray/Pod 日志、内部资源标识、服务地址或凭据。

对应目录保留 README、schema 和合成示例，说明私有资产应放在哪里、需要满足什么
hash/manifest 合同。配置中的路径和平台资源均为空值或占位符。

## 快速检查

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

普通 CPU 环境只验证纯逻辑和合同；真实 SFT、GPU rollout 与多节点 VERL 测试均有
明确标记，不会在本地检查中伪装执行。更多说明见
[`docs/reproducibility.md`](docs/reproducibility.md)。
