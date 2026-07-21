# Qwen2.5 30K 数据占位

私有运行需要提供：

- `sft.jsonl`：原生教师 math、code、general 各 10,000 条；
- `math500.jsonl`：与 15K 分支共享的 500 条数学 prompt；
- 对应数据 manifest：行数、SHA-256、域分布、verifier、token 和去重审计。

现有证据不足以证明最终 30K 全量使用同一版 benchmark deny 完成审计，因此正式复跑
必须重新执行全量去污染。本目录不包含真实样本。
