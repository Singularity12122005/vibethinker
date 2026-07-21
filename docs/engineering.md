# Shared engineering modules

这些模块提取的是旧实验脚本中可复用的工程合同，不是旧运行环境的镜像。所有
服务地址、凭证、组织信息、模型和数据标识都由调用方配置；仓库不提供任何
厂商默认值。

## 教师蒸馏

`distillation` 将教师定义为 `TeacherClient` protocol。HTTP、SDK 或本地推理
实现位于应用层；共享层只处理：

- 可注入退避与抖动的有限重试，且区分临时错误和不可重试错误；
- 有界线程池并发、每条样本完成后原子替换的恢复账本；
- 原生 reasoning/answer 通道组装、候选 validator；
- 至少两个教师的候选验证和按分数择优，平分时按配置顺序稳定选择。

该设计来自 `distill_sft_v3_qwen_flash.py` 的重试、恢复、验证和多候选经验。
没有迁移该脚本中的厂商 payload、端点、密钥环境变量、模型名称、tokenizer
路径和领域私有 judge prompt。复杂数学等价和业务 judge 通过 verifier 注入。

## Verification

`verification` 为 math、code 和输出协议提供统一的 `VerificationRequest` /
`VerificationResult` / `Verifier` 合同。math 默认实现仅做保守数值或规范化文本
比较，正式实验应注入经过审计的数学 verifier。协议验证只接受一个非空
`<think>...</think>` 块及其后的非空可见答案。

代码执行借鉴 `code_sft_verifiers.py` 的 runner 边界，但没有把进程资源限制包装
成安全承诺。`python -I`、超时和子进程隔离都不是 hardened sandbox。
`IsolatedPythonSubprocessRunner` 必须由调用方显式声明外部隔离环境；生产使用应
放在权限受限的容器或虚拟机中，网络、文件系统和系统调用策略由该环境负责。
测试只使用 fake runner，不执行不受信任代码。

## Checkpoints

`checkpoints` 合并了 `checkpoint_guardian.py`、现有 checkpoint schedule 和
训练状态提交标记中的通用部分：

- 最终步、临近回收、固定周期和 epoch 边界返回纯 `SaveDecision`；
- checkpoint 文件先校验并写原子 manifest，最后写 `COMMITTED` marker；
- guardian 只在主进程、达到间隔、目录存在且已提交时发布；
- 训练框架保存和外部发布分别通过 `CheckpointStoreAdapter` 与
  `CheckpointPublisher` 注入。

没有迁移 CLI 自下载、固定二进制路径、平台命令、认证变量、后台上传线程或
平台数据集创建逻辑。共享 guardian 是同步决策边界；调用方如果需要后台执行，
必须管理线程生命周期、失败可见性和进程退出前的 drain。

## Persistence

`persistence` 从 `result_persist.py` 中保留“结果必须显式发布，而不能假定作业
结束即持久化”的修复。artifact manifest 包含稳定排序的相对路径、字节数和
SHA-256，并使用现有 `common.io` 原子写和 `common.hashing` 文件摘要。发布流程
先冻结 manifest，再调用 `PublishAdapter`，复核文件和 manifest 未变化，最后
原子写 `PUBLISHED.json` receipt。

没有迁移任何平台 CLI、上传参数、组织解析、自动建数据集或凭证处理。上传
失败不会生成成功 receipt；错误是否重试由 adapter 或上层作业策略决定。

## Runtime

`runtime` 从 `package_frozen_panel_runtime.py` 仅提取确定性文件清单和 bundle
身份哈希。它不会复制文件、打 tar 包、下载模型或 vendoring 依赖。manifest
输入必须是根目录内的相对文件路径，文件按路径排序并逐个记录 SHA-256。

长提示构造、needle 位置记录、结果匹配和 context override 判断被保留为纯逻辑。
共享模块不导入推理引擎、模型框架或
GPU 库，也不修改进程环境。引擎启动、采样、adapter 装载和显存配置留给平台
集成层，CPU 测试使用 tokenizer contract。

## 未直接迁移的旧代码

- 旧 RL 候选整理脚本的 denylist、稳定 hash 和 JSONL 能力已经由
  `data.decontamination`、`data.rl`、`common.hashing`、`common.jsonl` 覆盖；
  特定质量等级、来源配额和固定样本规模属于数据版本策略，不进入共享层。
- 厂商 HTTP schema、专有 finish reason 和 token usage 字段不属于
  `TeacherClient` 的稳定合同，由 client adapter 解释。
- 第三方 verifier 实现、模型/runtime 文件、归档产物、vendored dependency、
  平台上传命令和训练框架 callback 均未迁移。

旧脚本不能直接复制，因为它们同时混合实验策略、平台认证、机器路径、网络
端点、模型/数据身份和执行逻辑；复制会泄露环境假设、扩大安全边界，并产生与
现有 `common`、`data`、`evaluation`、`qwen35` 和 `openthinker3` 模块重复且
逐渐分叉的实现。
