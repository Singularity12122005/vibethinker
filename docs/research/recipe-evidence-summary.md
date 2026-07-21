# 开放推理 Recipe 证据摘要

## 对当前实验设计最有用的结论

1. 30K SFT 是可用 pilot，不是强小模型的数据量级结论。OpenThinker3-1.5B 使用约
   75K 独立题、每题 16 条轨迹，总计约 1.2M traces；增加重复 epoch 不能替代能力覆盖。
2. SFT 负责引入模型尚未掌握的知识、协议和推理路径；RL 更适合起点模型“有时答对、
   有时答错”的 frontier prompts。全对和全错组都缺少有效组内信号。
3. 500/1000 题 RL 分支适合 verifier、分布式训练和 checkpoint 合同验收，不足以承担
   最终能力结论。
4. Capability Panel 与 Health Panel 应分工：前者衡量困难能力，后者监控退化；二者都
   必须与训练数据及正式 benchmark 去重。
5. 长上下文上限必须按模型、数据和截断率实测。最大窗口不是能力目标，错误停止条件或
   rollout 适配路径会让长输出指标整体失效。
6. Skywork-OR1 说明难度是相对当前 checkpoint 的属性；同一母池对不同模型会得到不同
   的有效训练子集。

## 一手来源

- [VibeThinker-1.5B 论文](https://arxiv.org/html/2511.06221)
- [VibeThinker-3B 论文](https://arxiv.org/html/2606.16140)
- [OpenThoughts / OpenThinker](https://github.com/open-thoughts/open-thoughts)
- [OpenThinker3-1.5B](https://huggingface.co/open-thoughts/OpenThinker3-1.5B)
- [Open-R1](https://github.com/huggingface/open-r1)
- [DeepScaleR](https://github.com/agentica-project/rllm)
- [DAPO](https://github.com/BytedTsinghua-SIA/DAPO)
- [Skywork-OR1](https://github.com/SkyworkAI/Skywork-OR1)
- [Skywork-OR1-RL-Data](https://huggingface.co/datasets/Skywork/Skywork-OR1-RL-Data)
- [OLMo / Open Instruct](https://github.com/allenai/open-instruct)

本摘要不复制原调研全文；四条主线的实际配置、完成边界和限制以各自实验卡及
`configs/` 中的冻结 recipe 为准。
