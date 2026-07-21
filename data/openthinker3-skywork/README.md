# OpenThinker3 Skywork 数据占位

私有运行需要提供经独立审计的 Skywork math/code 数据及 manifest：

- 每个 epoch 调度 42,000 行；
- 30,000 个唯一数学 prompt；
- 6,000 个唯一代码 prompt，按冻结 recipe 重复调度；
- prompt token 上限、fingerprint、域分布和 verifier 路由均与
  `configs/openthinker3/data.yaml` 一致。

本目录不包含 Skywork 原始数据、benchmark 题目或 verifier 私有依赖。
