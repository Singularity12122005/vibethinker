# 通用评测框架

该目录是从内部 Panel 工程经验抽取出的公开安全实现，只保留协议与合同，不包含真实
题目、冻结 hash 列表、候选 ID、模型输出、内部 endpoint 或平台凭据。

## 数据与配置

- `EvaluationProfile` 必须显式提供 `context_tokens`，没有 64K 或其他隐式默认值。
- `PanelManifest` 绑定 panel 文件 SHA-256、行数、域和 `toy`/`formal` 模式。
- `toy` profile 只能读取带 `fixture: synthetic-toy` 的 toy panel。
- `formal` profile 拒绝任何 toy fixture 标记。正式 panel 必须在仓库外单独提供。
- 示例 `configs/evaluation/toy-128k.yaml` 用于 CPU 合同测试；
  `formal.example.yaml` 只是配置模板，不代表存在公开正式数据。

JSON Schema 位于
`src/vibethinker_experiments/evaluation/schemas/`。每个域各有一条完全合成的 toy
fixture，负向 fixture 覆盖重复 ID、prompt 协议泄漏和 formal/toy 混用。

## 产物状态机

生成、判分与最终评分是三个物理分离的 JSONL：

1. `generation_results.jsonl`：只含生成输出与 token 计数。
2. `judgments.jsonl`：按 `panel_id` compact 后的一条判分记录。
3. `scored_results.jsonl`：纯评分与可选 judgment 的 join，不复制原始输出。

`mark_generated` 以 SHA-256 封存 generation 文件，然后写 `GENERATED.json`。
`GENERATED` 只表示生成完整，绝不表示判分或报告完成。

`seal_judgments` 将 append-only 重试记录按 `panel_id` 和 attempt compact，完整后一次性
封存 `judgments.jsonl`。已解析且 generation hash、judge signature 均匹配的记录不会
重试；未解析、配置变化或 generation 变化才会重试。

`finalize_run` 校验所有上游 hash 后创建 `scored_results.jsonl`、`report.json`，最后写
`FINALIZED.json`。二次运行只校验并返回已有 marker，不重写任何文件。任何封存后改动
都会导致失败。

## 生成与队列

`generation.build_generation_result` 只接收注入的 `GenerationTransport`，请求对象不含
API key、secret 或 endpoint。默认 transport 禁止网络。共享 `WorkQueue` 支持原子
claim、异常 recover 和幂等 complete；`merge_result_shards` 要求恰好覆盖 panel ID，
并按 panel 顺序合并。

模型或 vLLM 适配器应在仓库外实现 `GenerationTransport`，并从 profile 读取
`context_tokens` 和 `generation_cap_tokens`。不要把凭据传给 generation worker，
不要把 key 放入 argv、manifest 或日志。

## 外部 LLM judge

测试和本地纯评分默认使用 `NetworkDisabledTransport`，不会发出网络请求。启用外部
judge 必须同时满足：

- endpoint 是 HTTPS、443 端口且 host 在精确 allowlist 中；
- URL 不含用户名或密码；
- 操作者显式设置 `data_sending_confirmed=true`，确认 prompt、参考 grading 和模型输出
  将发送给第三方；
- key 只通过 `api_key_env` 指向的环境变量读取，不进入 argv、日志、结果或对象 repr。

`configs/evaluation/external-judge.example.yaml` 默认不确认数据发送，不能直接联网。
provider 行为通过 `JsonTransport` 注入，因此 CPU 测试全部使用 fake transport。

## Code grader 安全说明

`unsafe_python_assert_grader` **不是安全沙箱**。临时目录、`python -I` 和 timeout 只是
资源控制，不能阻止恶意系统调用。它默认不启用，只能执行可信的合成或人工审查代码。
真实不可信模型输出必须交给独立容器、VM 或专用 sandbox 服务，并以 `CodeGrader`
接口注入。

## 可选 TriSol 集成

`integrations/trisol.py` 只定义脱敏的 `ResultDownloader` 协议和 GENERATED 产物校验。
它不包含 team、内部地址、命名规则、候选 ID 或认证逻辑。平台 client 由私有部署注入；
核心评分与 finalizer 不依赖 TriSol。

## CPU 测试

```bash
PYTHONPATH=src pytest tests/evaluation
```

测试覆盖显式 128K context、纯评分、formal/toy 隔离、禁网默认值、HTTPS allowlist、
密钥边界、judge 重试与 compact、队列恢复、hash 不可变和 finalizer 二次运行。
