# Checkpoint 占位目录

本目录不提交任何模型权重。实际运行时可按以下结构挂载私有 checkpoint：

```text
checkpoints/
  qwen25-15k/
  qwen25-30k/
  qwen35-30k/
  openthinker3-skywork/
```

四条主线统一使用 `vibethinker_experiments.checkpoints` 的提交合同：

1. 训练框架先写完模型、optimizer、scheduler、dataloader 和 RNG 状态；
2. `commit_checkpoint_tree` 为目录中的全部 checkpoint 文件记录大小和 SHA-256；
3. 原子写入 `metadata/checkpoint.json`；
4. 最后写入内容为 manifest SHA-256 的 `metadata/COMMITTED`。

Qwen2.5、Qwen3.5 和 OpenThinker3 的框架适配只负责调用这一共享实现。OpenThinker3
额外保留 `metadata/training_state.json`、`adaptive_entropy.json` 和 replicated-DP
布局，作为其恢复逻辑的扩展字段，但仍使用同一 manifest/marker 验证。只有通过
`validate_committed_checkpoint` 及框架特定恢复检查的目录才可用于恢复或外部发布。

除本说明外，`checkpoints/` 下所有内容均被 Git 忽略。
