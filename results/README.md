# 结果占位目录

仓库不提交原始生成、逐题判分、训练日志或内部报告。私有结果建议按主线分目录保存：

```text
results/
  qwen25-15k/
  qwen25-30k/
  qwen35-30k/
  openthinker3-skywork/
```

评测运行应分别保存 generation、judgment 和 scored artifacts，并使用
`vibethinker_experiments.evaluation` 的 `GENERATED` / `FINALIZED` 状态合同封存。
需要发布摘要时，只导出不含 prompt、模型输出、内部资源标识和凭据的聚合指标。

除本说明外，`results/` 下所有内容均被 Git 忽略。
