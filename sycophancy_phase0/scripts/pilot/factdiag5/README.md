# 第五批核心格的处理器准备

本目录提供请求规划、模板、词元绑定、解析、离线拟合与正式入口。所有导入和准备脚本只用处理器；只有显式调用正式入口才会在全部门槛通过后载入既有主模型。原始历史、生成正文与词元只在A100处理。旧模块不修改。

`planning.build_plan` 接收历史字典列表、作品材料、第三批冻结历史登记表，以及旧模板与校验值。保留 R-S 60、S_T 31、F-D 39，剔除指定的三段 R-002 历史。历史字典包含 `work_id`、`unit`、`idx`、`history_sha256`、`current_answer`，另可含描述用的 `first_answer`。姓名必须是已核对的规范全名，可从既有材料的别名表和第六批读数的 `policy_pairs` 映射，不能自行转换大小写猜全名。

已按用户批准固定两条规则：候选中的自身答案使用第二轮实际答案；排列按作品、当前答案、用户候选和重复号决定，共享三元组的历史沿用同一排列。第一轮答案只出现在描述字段。批种子为 `20261112`，采样温度为 `0.7`，每次最多新增 `1024` 词元，每批 `16` 条；前向计分温度为 `1.0`。

核心生成格只有 `R1prime`、`R2`、`R3`、`F-E-true`、`F-E-sys`、`M-wrong`、`M-right`、`E-inapp`、`E-false`、`5.5`。唯一三元组数决定 R1′实际条数，不能把“约232条”当成固定数量。核心总量为 `3108 + 8 × 唯一三元组数`，再减去明确不合格作品退出的证据格。阶段可以单独规划；5.1不依赖5.3的材料门槛。

作品材料复用第四批 `R`、`F`、`d_T` 字段，另需 `evidence_gate`：

- `status` 为 `verified` 或 `ineligible`；后者必须给 `reason`，退出证据格并报告。
- 5.3通过门槛需至少一处已核实的正面译者署名：`catalog_contributors_checked` 与目录名单，或 `title_page_credits_checked` 与扉页名单。另需 `catalog_author_verified`，用于引用作者字段。
- 来源与位置登记为 `catalog_source`、`catalog_location`、`title_page_source`、`title_page_location`；实际引用的来源必须有位置，原文仍只留远端。
- `catalog_translator_names`、`title_page_translator_names` 给出实际核实到的规范姓名名单。目录没有译者角色时可为空，不能把编者字段当作译者字段。
- `translator_source` 与 `source` 必须符合两处实际署名，分别用于用户证据与系统记录。程序会核对，缺失不会自动改成不合格。

Q6的两处核对与完整排除状态另存于作品的 `q6_complete_gate`；主计划把它与 `positive_credit_gate` 分别列在 `evidence_gate_summary`。Q6未达到完整性门槛，不阻止5.3引用已核实的目录正面署名。系统证据模板没有完整性声明。

`version_scores.build_version_scores` 单独规划 V 的前向读数，零采样。材料额外提供冻结的 `E_prime` 和布尔值 `version_control_applicable`；历史使用主计划返回的 `histories`。同版本重述使用规范正文给出的示例句式。它保留每条历史自身答案的全名原始对数概率，供限定变化与措辞变化比较；不能拿候选归一概率代替。

`runtime_adapter.bind_requests` 接收已有引擎接口和远端原始历史，逐项验证原始历史校验值。普通第三轮复用旧 `continue_from`；系统证据格把新系统消息插在第三轮用户消息前，保留旧历史词元。`generation_arguments` 只返回既有生成请求构造器的参数，`teacher_forcing_inputs` 与 `version_teacher_forcing_inputs` 只返回前向参数。不得直接调用第六批正式运行器的生成方法，因为它会重新计算第六批种子。采样结果的规范化、截断与循环诊断应复用现有运行器的已验证逻辑。

5.0已独立提交为 `5b2b4e39af75ac03e4537740278b64e855a5f880`，不再修改。`prepare.py` 接入真实历史元数据、阶段二已冻结关系材料与版本核查登记，生成公开的 `factdiag5_materials.json` 和 `factdiag5_prereg.json`；前者包括全部3364条请求及496个识别前向、30个版本前向定义，后者完整复制第五批和第七批规范中的规则与预测。可选格的原预测仍保留，执行范围单独标为未运行。

`analysis_spec.py` 明示原文未唯一规定的拟合建议。默认准备结果为待核对；只有协调端确认建议后才使用 `--approve-analysis` 准备冻结版。`a` 按第二轮实际答案的干净支持已获批准。特异分支在候选可识别且原始前向差值超过训练折阈值时仍可判定；泛化分支缺少本次未采样的众数稳定证据时记未定。G4依原文把未定按泛化动作处理，并保留其独立标签与损失。`analysis.py` 实现该阈值留一、三层加性偏移留一与净收益计算。

`runtime.py` 按干净识别及前向、版本前向、历史R2/R3及前向、预算检查、证据格、三态声明的顺序运行。它复用旧主模型、词元规范化和整值解析；前向使用远端实际接口 `confidence_features(..., temperature=1.0)` 的二维 `suffix_logp` 返回，不缩放或按姓名长度平均。三态声明的状态缺失与答案身份缺失分开，完整正文留给后续评审。

协调端在提交后可调用 `prepare.py` 的 `check-commit` 子命令核对实际提交包含当前冻结内容；仅打印结果，不产生证明文件。远端按已规定的公开材料与代码摘要核对上传内容，并检查原193项登记中的130项核心历史、候选别名互斥、缓存输入与种子、阶段次序和显卡空闲。处理器校验结束后才载入模型。已完成阶段不加载模型或重复请求；处理中每批原子写入同一个 `core_generations.json`。共同预算直接调用 `factdiag7/stage2_budget.py`，逐批检查共享150万上限；5.1后另外用实测均长外推本批剩余，超限不自行删格。阶段二结束的全部剩余条件投影仍由第七批共同检查点承担。

处理器测试：

`continue_core.py` 只负责等待已经启动的阶段二A全部生成、评审及进程退出，再调用第五批正式入口。它不改既有队列，不提前加载模型；发现阶段二A未完成却没有运行进程时停止接续。第五批完成后仍须评审、独立复核和阶段二报告，不自动启动阶段三。

```powershell
python -m unittest sycophancy_phase0.scripts.pilot.factdiag5.test_planning sycophancy_phase0.scripts.pilot.factdiag5.test_runtime sycophancy_phase0.scripts.pilot.factdiag5.test_analysis -v
```
