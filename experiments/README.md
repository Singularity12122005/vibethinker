# 实验主线

本目录只保留四条教授版主线，不使用按时间递增的流水编号。

| 主线 | SFT 起点 | RL | 当前可引用边界 |
|---|---|---|---|
| `qwen25-15k` | 三域 15K SFT epoch 1 | 64K Math500 | RL epoch 1 checkpoint 与双 Panel |
| `qwen25-30k` | 三域 30K SFT epoch 5 | 64K Math500 | RL epoch 1 checkpoint 与双 Panel |
| `qwen35-30k` | 三域 30K SFT epoch 9 | 128K Math500 / Mix1K | 两变体 RL epoch 1 与双 Panel |
| `openthinker3-skywork` | OpenThinker3-1.5B | 32K Skywork math/code | preflight 完成，训练健康性未验证 |

每个子目录只描述研究问题、数据、训练配方、实际完成边界和限制。数据清洗、蒸馏、
verifier、评测、checkpoint 与平台修复属于共享代码，不单独包装成训练实验。
