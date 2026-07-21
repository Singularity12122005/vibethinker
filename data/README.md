# 数据契约

仓库不提交训练集、benchmark 题目、模型输出或结果。`schemas/` 只定义记录
结构，`examples/` 是最小合成样例，不代表真实训练数据。

四条主线的数据占位和已知审计边界分别位于：

- `qwen25-15k/`
- `qwen25-30k/`
- `qwen35-30k/`
- `openthinker3-skywork/`

真实文件应放在 Git 忽略的私有挂载中，并由配置显式传入；代码不会猜测本机路径。

## SFT

`sft_v1.json` 要求 `messages` 至少包含 user 与 assistant。assistant 必须是
唯一一层 `<think>...</think>` 后跟可见答案；user prompt 不得包含协议标签。
`vibethinker_experiments.data.sft` 提供协议校验、prompt 去重和 Stage-2
长思维估算筛选。字符/token 比只可用于粗筛，不能代替真实 tokenizer 截断检查。

## RL

`rl_v1.json` 统一 math、code、stem 的 `problem`、`answer` 和来源字段。
code 的 `answer` 是 `{"inputs": [...], "outputs": [...]}` JSON 字符串，
并应同时保留结构化 `tests`。测试必须等长、去除冲突输入并限制 payload。

代码执行 verifier **不是 hardened sandbox**。数据中的 verifier 名称明确写为
`python_stdin_stdout_not_hardened_sandbox`；对不可信代码必须使用独立强化沙箱。

## benchmark 去污染

调用 `data.decontamination build` 从显式提供的 benchmark JSONL 构建索引；
每行应含 `label`（或 `id`）及可提取的 prompt。匹配包括：

- NFKC/casefold/词元化后的整题 hash；
- 规范化 10-gram 的分级 containment 阈值。

索引本身包含 benchmark 派生 hash，是否可发布取决于原 benchmark 许可。

## 来源

当前实现从私有原型中提取纯数据合同后重新组织，不保留无法公开解析的本机路径或旧
脚本入口。下载、私有缓存扫描和平台 orchestration 均未迁移；公开实现以
`vibethinker_experiments.data` 及各模型主线的数据模块为准。
