# Qwen3.5 30K 数据占位

私有运行需要提供：

- `sft.jsonl`：math、code、general 各 10,000 条；
- `math500.jsonl`：500 条数学 RL 数据；
- `mix1k.jsonl`：Math500 与 GSM8K 500 条组成的数据变体；
- prompt pool、教师结果和最终数据各自的不可变 manifest。

真实数据必须通过协议、finish reason、token、verifier、域配额、重复和 benchmark
去污染审计。本目录不包含真实样本或教师输出。
