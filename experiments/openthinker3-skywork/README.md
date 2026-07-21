# OpenThinker3-1.5B Skywork RL

## 研究问题
强 SFT-only 起点能否通过相对难度过滤、math/code verifier 和 DAPO 风格训练继续提升？

## 实际做法
冻结 Skywork math/code 数据合同，删除全零/全一组，采用标准组优势、非对称裁剪、
双裁剪、自适应熵和可恢复 checkpoint 合同。

## 状态
数据构建与审计、算法、reward、checkpoint、32-GPU 配方和 preflight 已完成并多次
运行。最后一次平台观测（2026-07-22）只看到调度层 `running`，没有 trainer start、
rollout 或有效 step 证据。调度状态会过期，因此公开静态状态记为：
**preflight 完成，训练健康性未验证**。

当前没有终局 checkpoint，也没有能力评测。该历史观测不能证明训练已经启动推进。

## 代码位置
- `src/vibethinker_experiments/openthinker3/`：算法、reward、数据审计与 checkpoint 合同；
- `configs/openthinker3/`：冻结训练、数据和多节点启动配置；
- `patches/verl-openthinker3/`、`patches/vllm-openthinker3/`：上游修改；
- `docs/openthinker3.md`：正式 recipe、来源映射和运行限制。

## 结论
当前只确认方案具备可执行、可审计和可恢复的运行合同；不能据此确认训练健康，更不能
宣称能力增益。

## 限制
训练尚未形成结果闭环，代码 verifier 仍需持续审计，32-GPU 系统成本较高。VERL
patch 已通过 apply-check；vLLM patch 仅完成 parse-check，尚未对干净 v0.19.0
checkout 执行 apply-check。
