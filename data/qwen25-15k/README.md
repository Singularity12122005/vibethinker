# Qwen2.5 15K 数据占位

私有运行需要提供：

- `sft.jsonl`：math、code、general 各 5,000 条；
- `math500.jsonl`：两条 Qwen2.5 RL 分支共享的 500 条数学 prompt；
- 对应数据 manifest：行数、SHA-256、域分布、token 审计和 benchmark deny 版本。

正式使用前必须重新裁决已知的 4 条高置信 benchmark 近重复。本目录不包含真实样本。
