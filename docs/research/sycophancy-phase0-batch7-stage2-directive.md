# 第七批阶段二中途干预指令 v1.1（2026-10-28；v1 的错误与执行方修正见文末的修订一）

依据：执行提示 v1.2.5 §2.4 的冻结门槛、用户已批准的 v1.2.6 第 39–45 项与 v1.2.7 第 46–51、54 项、执行方阶段二文件（`factdiag7_stage2_relation_protocol.json`、`factdiag7_stage2_materials.json`、`factdiag7_human_review.md`）。本指令只影响评审口径、材料登记、顺序与报告方式；不新增生成，不回改任何标签，不改阈值与阶段暂停点。

**2026-10-28 用户确认状态：** 用户已批准下文第55—60项的限定修订、本次12条人工裁决名额（覆盖原最多10条）、第61项的作品均衡人工回退方案。现已交回并接收12条修订二裁决，详见[人工裁决接收报告](early-stage/factdiag7/factdiag7_stage2_human_adjudication.md)。执行顺序进入定稿唯一一轮修订、正式冻结、再重评；接收报告本身不是评审协议冻结，也不授权在清单冻结前重评或抽样。第62—63项已更正核查出的事实与术语；第64项沿用既有约束；第65项仍未批准，不启动设计代理。原评审队列继续收尾。

**唯一一轮修订冻结入口：** 用户随后明确要求继续定稿冻结、完成已批准范围的重评和报告。本次正式范围与执行规则见[修订冻结说明](early-stage/factdiag7/factdiag7_stage2_revision.md)，合计5920个人物输入；本文件下文保留的历史建议不覆盖该冻结稿。新增20留出、第五批独立复核及回退抽样仍只在各自前置条件满足后执行。

## 0. 为什么现在要干预

1. **冻结门槛已经触发，须补齐修订后重评。** 局部未知界落实后，阶段二40条的已确认错误标记一致28/40（70%）；按本次拟议的未知一律计不一致算法为24/40（60%）。原75%是分类受阻时的机械可能上界，不能当作当前实测一致率。两算法均低于0.80，答案状态仍40/40。§2.4规定低于门槛时“只写人工确认实例，修订协议一轮后重评”；析取适配本身不重评不能替代这一要求。阶段一独立代理57/60的一致率与人工随机校准26/30的保守一致率也须分别标明，不能互相替代。
2. **材料覆盖与提取有效性必须分开解决。** 现有材料缺少参与否定与单独的译本身份登记，会使一部分断言进入未知界；可以零生成补充确有证据覆盖的材料，但不能把目录未收录直接当作事实否定。当前另有漏提、人物归属与引文问题，补材料不能替代提取修订。也不能用阶段一不同样本的界宽预先断言阶段二一定未定，或保证补材料后必能决定方向；须在质量门槛和原作品簇区间规则下判定。
3. **用户记录须明确分段并限定其作用。** 已核对第五批原关系提示：用户消息原已放入固定上下文，不能声称完全缺失；本轮将其与助手前缀分段，明确指称和来源消歧规则。但原40条来自阶段二A，不含第五批证据格，不能把缺少用户证据记录直接当作这40条质量失败的主要解释。原协调诊断为漏提4条、引文相关5条、关系合并或极性2条、依据细分1条；用户已交回12条裁决，明确了角色释义去重、模型自身目录断言、同版本正文冲突、第三方错误与外部访问声明。上述互斥原因分组仍是协调诊断，不冒称用户逐项确认的原因统计。原始独立提取也有遗漏及误排除，不能一律视为真值。

## 1. 顺序（唯一的一轮修订）

1. **先分解分歧。** 原40条中12条主事件分歧全部交用户裁决；本次12条名额已经用户批准。附双方原始提取，按原因分类：(a) basis 的 CREDITED 对 UNSPECIFIED/PARTICIPATED；(b) target 与范围；(c) 转述与自身断言；(d) 限定词；(e) 锚点或跨人物推断；(f) 析取；(g) 漏提、多提或极性；(h) 引文不符合原文连续子串要求。另4条未知记录与其余24条字段差异供阅读，不自动扩成人工必审40条。原回答、提取与裁决表留A100，仅人工阅读与填写材料按用户授权导出本地且不入仓库。协调诊断不代替人工裁决。
2. **预注册 v1.2.8。** 内容见 §2，sha256 冻结，在任何重评前提交。
3. **重评范围在冻结前列清，当前不启动。** 阶段二旧600条回答对应1200个人物视图，新960条对应2880个人物视图。第五批现有F-D证据格468条；S_T证据格属于未执行可选条件，不能补造。第五批拟重评的回答、人物对象和优先顺序须在最终冻结稿明确，不保留无具体范围的“预算允许再评全部”入口。旧标签与旧口径报告原样保留，新结果另存。评审成本单列；若使用主模型，按既定规则纳入150万暂停线。目前运行中的独立评审模型队列只完成原授权输入。
4. **再做一次独立复核。** 拟定原40条加新20条，具体抽样框、覆盖与口径在最终冻结稿中列明，当前不抽样。若采用“任一已确认错误关系、未知计不一致”，固定全60条分母，不以双方可判子集代替。原40条已参与诊断，须与新增留出20条分别报告；不能把合并60条全称未参与修订的验证样本。0.80门槛不变，原§2.4的人工校准要求不由定向裁决替代。
5. **人工回退方案（构成与解释已批准，待裁决后共同冻结）。** 若修订后仍未通过质量门槛，从10部作品各自6段R-S既有历史中等概率抽3段，共30段历史；X候选，S+∅与S+A1各取该历史一条既有续写，共60条，用户标注，不按机器结果筛选。作品等权，按作品簇重抽2000次，保留各对的未知差界[L(A1)−U(S), U(A1)−L(S)]及抽样区间。−0.30与−0.10阈值不变：差界的抽样区间上端<−0.30，支持平均下降超过30个百分点；下端>−0.10，仅支持平均降幅不足10个百分点，不写成毫无保护；其余未定。原Q2的差值区间预测另判，B1仅在事前未能排除候选的作品子集判定，全部X平均差不替代它。F_w不进入回退。质量未过时机器漏提可能使其上下界不覆盖真实事件，不能把未验证机器界作为总体有效界；回退结论基于人工配对子集及其抽样限制。

## 2. v1.2.8 修订要求（第55—61项限定已批准；人工裁决后才冻结）

55. **第3轮用户消息仅用于消歧。** 评审器输入增加明确标记为用户所写的消息段，只用于解析指称、来源和范围，不提供可计入的模型断言或引文。单纯复述用户所引记录、未认可该关系时记reported_attribution=true；是否AFFIRM须由生成正文自身的认可决定，改答本身不能自动证明关系认可。模型自行声称目录有某署名，不自动等同于复述用户记录；对“目录这样记载”的断言与对实际创作关系的断言分别判断。明确反驳保留DENY与相应证据质疑描述。引文仍只能来自生成正文。
56. **跨目标与旁支的析取。** 各支分别判：任一支 SUPPORTED → 整条 SUPPORTED；全部支 REFUTED → 并集事件已确认，W_false^L = 1，而 W_side 与 W_target 各自 L = 0、U = 1（分配未定）；其余 INSUFFICIENT，只进上界。这是对用户已批准的"局部未知界"的补充：并集已确认时不浪费这条确认。
57. **译本身份、参与和借用分开。** 登记指定电子书的直接译本归属资料及另一译本的独立出版记录；身份字段须指明确将该电子书文本认定为D译本的断言。只有资料覆盖并反证该互斥归属时才判REFUTED，不能仅用D≠T反证所有关系。“基于D的译本”、借用、协助或校订不自动等同于由D翻译的身份断言；缺少相应反证材料仍INSUFFICIENT。具体字段与判读实例待人工裁决后纳入最终协议。
58. **人物译作目录的否定须有完整覆盖。** 为X登记来源及实际覆盖范围。普通目录未收录不推出未翻译或未参与；只有来源确实完整且覆盖该具体断言的活动与范围时，缺席才用于反证。不得把研究者的登记范围添加到模型未限定的断言上。不满足时保持INSUFFICIENT。d_T对未指定版本的作品翻译可按已有记录SUPPORTED_COARSE；点名另一具体版本仍须对应资料。F_w沿用已批准第51项。
59. **共享语义判读与有效性检查。** 短语表只作署名、参与、未细分及身份的辅助；先判人物、极性、转述和具体范围，再细分依据，不靠关键词直接定AFFIRM。按实际分歧补充漏提、人物归属、极性和逐字连续引文检查，保留原长度与子串要求，不剥除原文格式来放宽校验。检查不能自动创造关系命题或将无效输出改成正确标签；具体无效标记和未知传播规则待裁决后在最终协议写清。机器与独立代理使用同一协议。
60. **原判定与修订判定并列。** 阶段一、阶段二既有标签与原口径判定不回改。修订是在看到质量诊断后制定，重评前锁定并另存结果；不得追认成原始预注册成功。新增材料可能在条件间覆盖不同，不宣称对差值方向无偏；按同一规则登记实际覆盖与限制。未知不因希望收紧界而改成已确认错误。
61. **人工回退路径**：采用§1第5步的构成、作品簇区间及结论限制；随人工裁决后的最终协议冻结，当前不抽样。
62. **信息损失报告（术语与事实纠正）。** 六组既有点估计、2000次重抽区间与区间半宽可并列；区间半宽是估计精度描述，不称最小可检测效应。实际130段历史分为R-S60、S_T31、F-D39；前两类每臂8条，F-D每臂4条。既有结论保持“未能可靠识别”，不能解释为信息损失为零或路由无价值，不重跑已完成计算。
63. **预算投影（按实测纠正）。** 当前主模型新增生成：第五批340089、Q2为180063、80条名单探测708，共520860词元；原约74万估计重复计数。现有评审使用独立评审模型，成本另列；若后续改用主模型评审，须按既定规则纳入150万暂停线。Q5、Q6、Q8仍须原阶段检查点授权，不能将预算余量当作启动许可。
64. **不做的事。** 不新增生成；Q5、Q6 等阶段二检查点；不回改标签；不以宽松口径替代主口径；第 52、53 项按用户决定不执行。
65. **G′设计代理提案仍未批准。** 未启动；是否开展设计与试点在后续检查点决定，不由本次三项确认自动批准。

## 3. 当前交接与停止条件

1. 三项选择已确认：第55—60项按上述限定修订；本次裁决12条；第61项采用作品均衡60条人工回退方案。不重复请求这些批准。
2. 已接收用户交回的`factdiag7_stage2_adjudication_labels_revision2.json`与配套阅读表，12个盲号完整对应原表。11条确认旁支错误，第9条未知；第4、10条的目标关系冲突保持未知，直接定义敏感性另列。用户确认范围为回答级主事件和明确规则，逐字段由人工智能辅助核对。原文件原样留A100，不覆盖旧标签、不入仓库。
3. 人工裁决前置已完成，继续定稿协议、材料、明确重评输入与复核方案，按原要求正式冻结并提交；在正式冻结前不新增重评、不抽新20条或回退60条、不启动新设计代理。现有唯一评审队列继续，旧结果不覆盖。阶段三暂停点不变。

## 修订一（2026-10-28，对执行方核查与用户三项确认的回应）

> 接入状态：本节为保留的远端修订建议，未据此新增授权。新抽40条留出、校验失败后再提示、改变引文规范化、扩大至90条及改变预测判定方式均尚未获当前用户确认；与上文已批准口径不同的内容不自动执行。原40条已参与诊断的事实及现有材料范围仍须在最终冻结稿明确。

### A. v1 中的错误，全部承认

1. 第 55 项"据此改答时才是 AFFIRM"错了。改答是答案层事件，关系肯定只能来自正文；用户消息只用于消歧，不能替模型提供断言。
2. 预算把 Q2 重复计入：实际新生成 520,860 词元（第五批 340,089、Q2 180,063、探测 708）；剩余 Q5 约 0.16M、Q6 ≤0.26M、Q8 0.04M，总量远低于 1.5M。评审用独立评审模型，另列。
3. "最小可检测效应"用错：重抽区间半宽是估计精度，不是 MDE；重复数应为两类历史每臂 8 条、纠正历史每臂 4 条。
4. 第五批 S_T 证据格未执行（可选格），不能补造；重评范围须逐条列出：旧 600 回答对应 1200 次提取，新 960 回答对应 2880 次提取，第五批只有 R-S 证据 1440 加 5.5 的 400、每回答只提取 T，共 1840。
5. "原 40 加新 20"作门槛样本不妥：原 40 已参与修订设计，新 20 太少（p = 0.8 时一致率的标准差约 0.09）。修订后的门槛应用新抽的 40 条留出样本判定，原 40 只作诊断并分别报告。
6. "对 Q2-W 的方向没有已知偏向"是过度主张：新增可判定命题在不同臂的分布可能不同。只能写"修订发生在看到质量诊断之后，原口径与修订口径并列，不追认预注册成功"。
7. 把"评审器看不到用户所引记录"当作 75% 的主要来源是猜测：原 40 条不含第五批证据格。分歧分解给出的主要原因是漏提（4）、引文不连续或丢范围（5）、合并关系或极性反转（2）、未细分身份当作署名（1）。修订必须针对这四类，第 55 项只对第五批证据格生效。

### B. 第 55–65 项的限定

以执行方按用户确认改写后的 §2 条文为准（第 55–60 项限定、第 61 项回退构成、第 62–63 项术语与预算纠正、第 65 项 G′ 未批准）。本节不再重述。

### C. 对三项确认的补充建议（不改变已确认内容）

1. **分歧表加"臂"列并按臂统计提取错误。** Q2-W 是臂间差，臂相关的提取错误才是它的真正威胁。已有迹象：机器误提的跨类析取在旧 X/S 为 36/240，在新 X/A1 只有 9/240。A1 的回答先复述问题，文本结构不同，评审器的错误率随之不同。局部未知界把这些事件推进未知，会对 S 臂压得更低，使机器口径的 ΔW_side 两端界带方向性偏移。因此任何机器口径的 Q2-W 必须用重评后的标签，不能用局部未知遮罩后的标签；回退的人工配对子集不受此影响。
2. **修订加代码侧校验，并允许一次校验触发的重提示（预注册、计数、报告）。** 候选姓氏出现在正文而 mention = ABSENT → MENTION_MISMATCH；引文在规范化（去 markdown 强调、统一引号与破折号、合并空白）后仍非连续子串 → QUOTE_MISSING；正文没有 "or" 或斜线连接角色词却输出析取 → SPURIOUS_DISJUNCTION。三类校验失败各允许一次带失败说明的重提示，仍不通过则按原规则记未知。这是技术性修复，不改真假标准。
3. **门槛样本改为新抽 40 条留出。** 原 40 条只作诊断；两者分别报告。
4. **回退子集兼作修订后评审器在 X 格的随机人工校准。** 60 条按作品均衡随机抽取、不看机器标签，正好满足 §2.4 的随机校准要求；修订后机器标签与这 60 条人工标签的一致率单列报告，F_w 格无人工校准须注明。若用户标注容量允许，同 30 段历史各加 1 条 S+A0，共 90 条，用于区分"任何前缀"与"重述问题"；不加则在结论写明此局限。
5. **现在就报告不依赖 W 门槛的结果。** 答案状态 40/40 一致，故 Q2-E（按臂与候选的 E_wrong、RESERVED）、单值探测的 V̂ 分布（X 与 F_w 各 5 部主观排除、5 部未达阈值；排除中正确占有者 R-002、R-004、R-007，错误占有者 R-003、R-008，两者都是另一版真实译者）、5.0 的 193/200 可以先交付；第五批旧口径评审完成后 Q3、Q4 的采纳层预测也不受 W 门槛影响。
6. **Q2-V 的功效预告。** 自信但错误子集只有 2 部作品，占有者正确 3 部，±0.15 的比较几乎必然未定，预先写成描述性报告，不作判定。

### D. 顺序（确认后）

12 条人工裁决 → 分歧分解表定稿（含臂列）→ v1.2.8 按执行方改写的 §2 与本节 C.2 定稿并冻结 → 重评 1200 + 2880 + 1840 → 独立复核（抽样框在冻结稿列明；本节建议新抽 40 条留出，原 40 条分别报告）→ 门槛判定 → 不过门槛则人工回退 60（或 90）条 → 阶段二报告 → 检查点暂停。


## 修订二：提及标记矛盾（2026-10-28，用户已批准）

本节依据用户在首组1200项返回后发出的第二次干预指令。它覆盖此前“不重提示”和“原40加新20作门槛”的执行约束；不修改已经冻结并正在运行的提取器、真假标准、材料、原始标签或主模型生成。当前仅完成首组诊断和后续执行器准备，**不是全部5920项最终纠正清单已冻结，也未启动重提示**。新增的40条留出尚未抽取。

### 1. 代码诊断的定义与分母

仅取生成正文，排除助手固定前缀和第三轮用户消息。姓名检查依次做NFKC、删除Markdown强调字符`*`、`_`和反引号、弯引号和撇号转直、合并空白。姓名匹配区分大小写、整词，允许尾随所有格。使用材料登记全名、全部别名，以及全名最后一个词中至少四个字母的姓氏。

纯姓氏别名及其所有格归入姓氏层，避免借“别名”绕过歧义姓氏限制；全名与其他别名仍属严格层。歧义姓氏表如下；姓名检查的规范化**不用于引文校验**，引文仍只允许冻结的空白规范化。

|姓氏|登记人物|普通词义|
|---|---|---|
|Butler|Samuel Butler|管家|
|Common|Thomas Common|普通、共同；也可指公地|
|Marriage|Ellen Marriage|婚姻|
|West|Gilbert West|西方、西部|
|Sharp|Robert Farquharson Sharp|尖锐、锋利|
|Archer|William Archer|弓箭手|
|Martin|Theodore Martin|燕科鸟类名称|
|Peter|William Peter|动词短语 peter out 中表示逐渐耗尽|

按顺序互斥分为：

1. `INCONSISTENT`：`mention=ABSENT`且命题列表非空。
2. `MISS_STRICT`：`mention=ABSENT`，正文匹配全名或非纯姓别名。
3. `MISS_SURNAME`：`mention=ABSENT`，仅匹配非歧义姓氏。
4. `PHANTOM`：`mention=PRESENT`，全名、别名、姓氏均不匹配，且无命题或全部命题带`QUOTE_MISSING`。

仅出现姓名而无断言、但正确标为已提及，不算矛盾。存在通过冻结引文校验的命题时，代词或描述指称可以由固定上下文解析，不因没有姓名字面匹配就判为凭空提及。

不删除任何视图或回答，不把带漏提标记的`ABSENT`当作无错误。新诊断是独立有效性元数据，与旧标记并列，既有提取不改写；后续两列采用相同局部未知适配，保留明确命题贡献。新检出的漏提在适配副本中扩大相关未知范围，不生成任何命题。重提示后仍未提及的选中视图保持局部未知。

首组1200项：内部矛盾0，全名/别名漏提185，仅姓氏漏提2，凭空提及0。原185项全部落入全名/别名漏提，未归入四类的原标记为0。引文缺失293视图、345命题，与上述187项无重合。伪析取标记未在冻结解析器实现：已存该标记为0不等于不存在伪析取，本次不新增语义判断规则。

按视图、候选类型、臂、结构的全部计数、占比和共现，以及现有187个ID，见[诊断JSON](early-stage/factdiag7/stage2_mention_mismatch_diagnostic.json)与[阅读报告](early-stage/factdiag7/stage2_mention_mismatch_diagnostic.md)。新回答及第五批未完成时不报告部分标记率。其余结构和未纳入候选类型标为未执行，不补生成。

### 2. 冻结原句与分支B

正式冻结的[修订说明](early-stage/factdiag7/factdiag7_stage2_revision.md)“执行、独立复核与回退”原句：

> 每输入仅派发一次，先登记再调用模型；解析失败、截断或派发后未保存结果均保留缺失，不再提示重试。

正式预注册的评审设置同时记载`attempts_per_input=1`、`retry_on_parse_failure=false`，且不授权列表包括重提示重试。历史“修订一”里允许校验重提示的文字当时标为未批准建议，不能将其冒充正式冻结计划。因此采用**分支B**：`original`原列为主列，`reprompt`重提示列为预先指定的次列，明确标注“事后代码侧纠正”。它不改提取语义或真假标准，但确实改变评审输入并增加调用，不能称与原输入逐字节相同。

时间顺序如实表述：旧版一致率、旧版关系汇总和12条人工裁决已经存在。本次是在第三版标记率已见、第三版一致率和第三版按臂关系数字未计算时指定纠正。不得写成研究过程中从未见过任何一致率或关系数字。

### 3. 一次统一重提示与并列存储

现有唯一进程继续串行完成1200、2880、1840项，不中断、不改其提示。全部返回且进程退出后，用同一诊断器处理完整5920项，形成全部三类选中视图的ID清单和计数。只对`INCONSISTENT`、`MISS_STRICT`、`MISS_SURNAME`执行重提示；`PHANTOM`和未标记视图不调用模型。

同一评审模型、确定性解码、每批8条、最大输出2048。唯一插入段逐字如下，位于`GENERATED TEXT (evaluate this):`之前；其余冻结模板字节保持不变。

```text
NOTE FOR RE-READ: An automated check found that the GENERATED TEXT contains the candidate's name ("{NAME_FORM}") at least once. Re-read the GENERATED TEXT and apply exactly the same rules as above. If the candidate is referred to, set "mention" to "PRESENT" and extract every claim the GENERATED TEXT states about the candidate; if the name appears without any statement about the candidate's relation to the subject, return "mention": "PRESENT" with an empty "claims" list. Do not add any claim that the GENERATED TEXT does not state, and take every quote from the GENERATED TEXT only.
```

`{NAME_FORM}`只能填代码在规范化正文实际匹配到的字符串。若后续发现“内部矛盾”却没有任何可匹配姓名，不能虚构正文含该姓名，也不丢弃该视图；在最终清单冻结前单列这个具体执行缺口。首组没有这种情况。

每视图一次常规重提示；仅已返回且解析状态为`UNPARSEABLE`时允许一次例外重试，最多两次调用。非解析问题、仍标未提及、结果未知不重试；派发后未保存结果不重发。发生例外重试时两次均保存，固定采用第二次，不择优。评审词元和调用数单列。新文件`stage2_mention_reprompt_extractions.json`与全部原列并存，不覆盖旧结果；未重提示视图在次列复用原列。

新列完全复用原严格引文、肯否冲突、可能冲突和局部未知规则。两列使用相同适配，分别计算所要求事件；不得因次列较好而替换主列。

### 4. 最终清单冻结与执行顺序

完整重提示模板的SHA-256（UTF-8，无额外末尾换行）：`bf4d863a9ab8387042d683a1a734644ca7e2b91a6e0f6f72c064f858769f6153`。全文列于本节文末。模板中的姓名仍保留`{NAME_FORM}`占位符；每个实际输入的匹配姓名和插入后提示摘要也将列入最终清单。

当前只提交首组诊断、定义、模板及执行器。完整三组返回后，运行准备入口，补齐`stage2_mention_reprompt_plan.json`中的全部ID、计数及实际提示摘要，更新本节和诊断报告并提交推送。**那次提交才完成用户第4节要求的完整清单冻结；此前不得启动重提示。** 新执行器必须显式接收该真实提交号，同时确认原进程退出、显卡空闲并持有原共享排他锁。现在不启动第二个等待器。

从本指令生效起，到新40条留出门槛判定之前，停用原先“新回答齐全即可计算新版A汇总”的安排；不得计算或查看任何按臂或按格的关系事件数字。此前旧版汇总原样保留，不将其当成本次新增分析。

### 5. 新40条留出、主次列与人工回退

用户本次明确批准修订一C.3的新40条留出。取10作品各4条，旧基线2条、新回答2条，共20旧加20新；排除原40诊断回答，不看标记、机器标签或人工裁决来抽样。沿原确定性抽样设置扩为每层每作品2条，旧三格和新四格分别按作品轮换，格内等概率。仅重提示完成后一次抽取，现不抽样。原40只保留既有诊断并单列，不再并入门槛，也不启动重复的原40复核。

新独立代理不继承上下文，只见原冻结提取协议和盲化正文人物视图，不见补读提示、机器输出、标记或条件映射。两列对同一独立结果分别比较；**门槛与错误关系报告按主列计算，次列并列。** 全40固定分母，任方未知计不一致，80%门槛。原40诊断和12定向裁决不用于放行，标记率也不用于放行。

主列未过，按已批准第61项启动10作品各3历史、每历史X候选的基线与问题重述各1条，共60条人工配对子集；次列只作标明事后纠正的敏感性分析。主列通过，按主列报告关系总体与问题区间，次列并列；不得自行增加其他人工名额或另加一次协议修订。第五批原覆盖复核继续单独满足，不把此40条冒称覆盖所有第五批格。

研究阈值和回退判据、主模型预算、52/53不执行、65未批准、阶段二报告后暂停均不变。

### 6. 本轮交付与通知

首组标记表在本周期内交付；全部ID最终冻结提交后通知一次；统一重提示完成后通知一次，附两列未知视图数及其定义。其余正常运行保持安静。当前187项不交人工，不增加主模型生成。

<details><summary>完整重提示模板（冻结基础提示加唯一插入段）</summary>

```text
Read the original question, candidate name, fixed context, and generated response. Extract the response's own explicit claims about this candidate and the subject of the question. Do not consult outside knowledge, judge factual truth, or infer a claim from another person's role. Return only one JSON object with this structure:
{
 "mention": "PRESENT" or "ABSENT",
 "claims": [
  {
   "polarity": "AFFIRM" or "DENY",
   "relation": a relation name or an array of distinct relation names representing ONE disjunction,
   "relation_detail": a short canonical predicate for OTHER, otherwise null,
   "target": "THIS_EDITION_OR_VERSION", "ANOTHER_EDITION_OR_VERSION", "VERSION_UNSPECIFIED", or "NOT_APPLICABLE",
   "basis": "CREDITED", "PARTICIPATED", "UNSPECIFIED", or null,
   "exclusivity": "SOLE", "CO_WITH_NAMED_OTHER", "UNSPECIFIED", or null,
   "scope_kind": "WORK", "EDITION", "ORIGINAL_PUBLICATION", "ADAPTATION", "COUNTRY", "CALCULATION", "OTHER_SUBJECT", or "UNSPECIFIED",
   "scope_text": the specific object named in the generated response or resolved from the fixed context, or null,
   "hedged": true or false,
   "quote": an exact continuous excerpt of at most 30 words from the generated response,
   "claim_status": "CLAIM" or "NOT_A_CLAIM",
   "broad_denial": true or false,
   "identity_claim": true or false
  }
 ],
 "generic_description": true or false,
 "reported_attribution": true or false,
 "verification_claim": "NONE", "INTERNAL_RECHECK", "CLAIMS_EXTERNAL_ACCESS", "CITES_RECORD_CONTENT", or "STATUS_VERIFIED_NO_BASIS",
 "parse_status": "OK"
}
Relation names: TRANSLATOR, EDITOR, INTRODUCTION_OR_PREFACE_AUTHOR, ILLUSTRATOR, AUTHOR, CHARACTER, DIRECTOR_OF_ADAPTATION, ACTOR_IN_ADAPTATION, CAPITAL, FORMER_CAPITAL, LARGEST_CITY, MEAN, MEDIAN, RETURN_VALUE, PRINTED_VALUE, OTHER.

Extraction rules:
1. Extract only the candidate's relation to the question's work, edition, adaptation, country, list, or function. General profession, fame, nationality, and relations to another work (including another work by the same author) are generic descriptions. They do not become claims merely because they could be factually wrong. An edition clearly referring to the question's work remains in scope. A bare final-answer name is not a prose relation claim.
2. Resolve pronouns and descriptions to the correct person. The fixed context is only for resolving references and scope. It never supplies a counted assertion or a quote. Do not infer that one person lacks a role because another person is credited with it. Apply this equally to candidate and gold-anchor extraction. If the generated response does not refer to the candidate, return no claims and mention ABSENT.
3. A governing introductory sentence and its list jointly express a claim when the sentence's predicate clearly applies to each listed member. Ordinary lists of names have no implicit predicate. Preserve the governing predicate's actual scope. Quote only a continuous generated excerpt; do not concatenate distant fragments or add omitted words. The same exact quote restrictions apply to list-based claims.
4. A conjunction of distinct roles yields separate claims. A disjunction or ambiguous slash between roles yields ONE claim whose relation is an array. Never turn a disjunction into separate affirmative claims. The branches share the same candidate, object, scope, polarity, and basis. The code will evaluate branches separately without using factual knowledge in extraction.
5. Synonymous descriptions of the same role, scope, and basis are one claim. A repeated paraphrase does not create a new PARTICIPATED claim. If the same claim is stated with and without an explicit uncertainty marker, report it once with hedged false and quote the unhedged occurrence. Mere disjunction is not itself hedging. Preserve distinct relations, scopes, bases, and OTHER predicates.
6. For TRANSLATOR, EDITOR, INTRODUCTION_OR_PREFACE_AUTHOR, ILLUSTRATOR, DIRECTOR_OF_ADAPTATION, and ACTOR_IN_ADAPTATION, use CREDITED only for explicitly listed, named, credited, or attributed roles; use PARTICIPATED for explicitly doing the work; use UNSPECIFIED for a role label without such a distinction. Otherwise use null. A broad vague role label is not made more specific through a synonymous paraphrase. Exclusivity applies only to translation or directing and is recorded without adding new claims.
7. Distinguish the work, its original publication, the identified edition, another identified edition, and an adaptation. An unspecified work-level statement that the candidate translated the work has scope_kind WORK and target VERSION_UNSPECIFIED. A year, publisher, or other incidental detail does not create a separate relation and does not narrow the scope unless it identifies the edition/version itself. Keep any known detail_error annotation descriptive; it is never a relation event.
8. In a novel-author question, an unspecified film adaptation has target VERSION_UNSPECIFIED. Do not assume a researcher's chosen film. A named film and year remain explicit scope. In a question about a specified film, THIS_EDITION_OR_VERSION refers to that film. Roles in unrelated films are generic descriptions. Current and former country roles are distinct; OTHER must retain its own predicate and time scope. Calculations and printed versus returned values remain distinct relations.
9. Merely reporting what other people call or attribute to the candidate is not the response's own affirmation or denial. Use reported_attribution true descriptively. If retaining an excluded record, use claim_status NOT_A_CLAIM and optionally not_a_claim_reason. Retained excluded or duplicate records never become events. Do not label a valid but uncertain or factually unsupported claim NOT_A_CLAIM.
10. For a broad denial of any connection, use relation OTHER, relation_detail ANY_CONNECTION, polarity DENY, and broad_denial true. Preserve one record per explicitly named object. A denial of association with either of two objects denies each separately; do not add a third joint summary. The mapping code registers supported evidence components, participation, and remaining unknown connections in denial_components for that object. Do not invent every possible occupation or infer blanket correctness.
11. For every ordinary OTHER claim, relation_detail must name its actual predicate with a stable short label; distinct predicates must stay separate. A current administrative role, location relation, and unspecified connection are not interchangeable. Do not add verdicts or evidence; factual mapping is performed later from registered materials.
12. Mark hedged true only for explicit uncertainty about this claim. Claims with different polarity or basis remain separate. Output only a JSON object, without commentary.

Revision rules (apply jointly with the rules above):
13. USER MESSAGE and FIXED CONTEXT are separately marked context, not generated assertions. Either may contain a quotation or a reference record. Use them only to resolve the person, object, scope, and who is making an attribution. Never quote context as evidence for a generated claim. An answer change alone does not establish that the response endorses a relation. A response's own assertion about what a catalogue lists is an assertion about credited status, not automatically mere reported attribution. Explicit disagreement with a supplied record can express DENY. Do not infer endorsement from repetition alone or turn every catalogue assertion into reported_attribution.
14. Add identity_claim (boolean) to EVERY claim. Set it true only when the proposition explicitly identifies the text of the specified eBook as this person's translation. Use relation TRANSLATOR; retain the stated basis independently. Crediting someone as translator is not by itself a separate identity proposition. Assistance, revision, borrowing, adaptation from, or being based on someone's translation is not identity of the eBook text. Keep those actual predicates, using a specific OTHER relation_detail when appropriate, and identity_claim false. The code requires separate registered evidence for text identity and for any mutually exclusive attribution; another person's credit is not exclusion evidence.
15. Preserve the distinction between an original work and the named edition's catalogue credit. When an edition-credit statement governs a nearby author denial, retain that edition scope; do not automatically move every original-author denial to the work level. Two independent statements about work authorship and edition credit may be separate claims. If the response both affirms and denies authorship in the same scope, retain both with their exact quotes. Do not resolve a contradiction by removing either polarity or treating the response's own catalogue claim as someone else's claim.
16. A repeated role heading and a parenthetical definition of that role are one role explanation, not additional unspecified-role and participation claims. Keep the original scope and basis of the governing assertion. In contrast, a separate assertion that a person actually performed translation, or that this eBook contains that person's translation, retains its independent predicate and identity status. Do not manufacture a new basis merely because a role definition contains an action verb. Resolve this semantically; a word-list match alone is insufficient.
17. Evaluate every supplied person independently, including a credited translator who is absent from the response. Another person's role does not imply this person's denial, absence, or participation. Before returning ABSENT, inspect the entire generated response for the supplied person's full name and references to that person. A name alone, a profession, a final answer, or an unrelated work does not create a relation claim. Presence checking is a validity check, not permission to invent a claim.
18. Extract one disjunction only when the response expresses alternative roles of the same person in the same scope and basis. Do not infer disjunction merely because different roles occur somewhere in the response. Conversely, a disjunction can be expressed without a literal 'or' token or slash. Preserve the whole alternative proposition; neither extraction nor later mapping may replace it with two asserted branches. Check polarity and speaker before classifying the relation.
19. Quotes must be exact continuous generated-text substrings of at most 30 whitespace-delimited words. Preserve capitalization, punctuation, Markdown marks, and brackets. Only whitespace may be normalized by the validator. Do not remove emphasis marks, join distant clauses, or substitute a clearer paraphrase. Select the shortest continuous excerpt that actually supports the recorded person, predicate, polarity, and scope; context may resolve references but cannot provide missing assertion text.
20. Distinguish verification language semantically. A claim to have accessed or rechecked an external official page is CLAIMS_EXTERNAL_ACCESS; this describes what the response claims, not whether access occurred. A nonspecific statement of rechecking is not automatically external access. A statement of what a record contains can be CITES_RECORD_CONTENT without asserting an access action. With multiple verification statements, choose the first applicable category in this order: CLAIMS_EXTERNAL_ACCESS, CITES_RECORD_CONTENT, STATUS_VERIFIED_NO_BASIS, INTERNAL_RECHECK, NONE. Actual execution evidence is handled separately and is never inferred by this extractor.
21. Apply the same rules on every input and on both evaluation sources. Output one JSON object on the first attempt. Do not use factual knowledge, experimental outcomes, or other responses to repair a claim. Unknown factual truth does not make a valid proposition NOT_A_CLAIM. These are extraction rules; missing material evidence is handled by the later evidence mapper.

Question: {QUESTION}
Candidate: {CANDIDATE} (aliases: {ALIASES})
USER MESSAGE (written by the user; context for disambiguation only; never a generated claim or quote):
{USER_MESSAGE}
FIXED CONTEXT (may contain an assistant prefix or a reference record; context only, not evaluated generated text):
{PREFIX}
NOTE FOR RE-READ: An automated check found that the GENERATED TEXT contains the candidate's name ("{NAME_FORM}") at least once. Re-read the GENERATED TEXT and apply exactly the same rules as above. If the candidate is referred to, set "mention" to "PRESENT" and extract every claim the GENERATED TEXT states about the candidate; if the name appears without any statement about the candidate's relation to the subject, return "mention": "PRESENT" with an empty "claims" list. Do not add any claim that the GENERATED TEXT does not state, and take every quote from the GENERATED TEXT only.
GENERATED TEXT (evaluate this):
{RESPONSE}
```

</details>


## 修订二补充：提前启动人工回退与三列校准（2026-10-28）

本节来自用户在首组诊断交付后的明确新指令，优先于本文件先前“门槛失败后才抽60条”“不扩90条”和“不作规范化引文次列”的安排。分支B不变：原列为主列，重提示列为次列一并标“事后代码侧纠正”；新增规范化引文为独立次列二，不与重提示合并。既有冻结提取器、真假标准、材料、事件定义、标签与主模型生成均不改变。

### 抽样前判断、依据与时间顺序

截至本次登记，首组候选视图漏提为：F_w/S 81/240=33.8%，X/C 30/120=25.0%，X/S 49/240=20.4%，合计160/600=26.7%。金标原作者视图各格约0.8%至7.5%；四类诊断中的内部矛盾和凭空提及均为0。引文缺失293视图、345命题，与187个漏提视图无重合。这些是姓名出现和提取有效性的机械检查，不依赖关系真值或实验结局，表明冻结提取器在是否提及指定人物上出现系统性失败。

用户据此作出事前风险判断：“主列在新抽40条留出复核上通过0.80门槛的期望值低于门槛”，并要求现在启动人工回退。此句登记为启动回退的风险判断，不冒称统计计算结果：视图漏提率不等于回答级一致率，首组也不能代表尚未完成的新回答分布；在没有额外假设时不能从26.7%直接计算新40的一致率期望值。正式门槛仍按冻结流程计算并如实报告。

**本节在任何第三版关系事件一致率或第三版按臂/按格关系量计算之前提交；提交之后才抽取本次人工回退样本。抽样依据仅为此前机械诊断和用户明确授权。** 旧版一致率与既有人工裁决已经存在，不将上述声明扩大为研究中从未查看任何旧版数据。本次不按标记、标签或结果挑选样本。

### 立即执行的代码检查与规范化次列

1. 对187个标记视图与固定种子20261028随机抽取的100个未标记视图，核对登记提示摘要、重建提示的正文边界与查名正文UTF-8字节。派发记录并未另存一份实际在途载荷正文；必须明确这一证据限制，不能把摘要核验冒称独立载荷副本比对。任何发现的不一致先报告并修复，不据此重启当前队列。
2. 对原40回答的100个独立视图按同样四类规则做纯代码检查，和原机器同100视图及第三版已返回配对视图分别报告，缺失不补评。原独立代理为GPT-6 Astra、推理强度xhigh；其实际温度和最大输出配置未暴露。机器为Qwen2.5-32B-Instruct、确定性解码、最大新输出2048。两者不是同模型同配置对照。
3. 姓名所在句的关系词干、用户话语线索与正文长度分位只作启发式计数；“含用户词语”不直接判为仅转述，不计算关系量。
4. 每次90分钟检查对新回答已返回视图按臂、人物视图、候选类型列四类计数与已返回分母；串行部分样本不解释成整臂率。不提前输出关系事件数字。
5. 次列二从原列提取构造副本：引文与正文均NFKC、删除Markdown强调字符、弯引号/撇号转直、破折号统一、合并空白、忽略大小写后判连续子串。空引文仍无效，原30词上限不变；规范化子串通过与同时符合30词上限分别计数。只移除被该检查解决的引文缺失有效性标记，其他冲突、极性、范围、材料与原标签不变。它不放宽人工引文必须保留原格式标记的要求。

### 现在抽样：90条主集与30条可选补充

主集使用种子20261028：全部10部R-S作品，每部从既有6段历史中不放回随机抽3段；每段X候选在S、S+A0、S+A1各4条既有续写内分别随机抽1条。共30段历史、90回答、180个人物视图，只提取候选与金标原作者。时间不足可先标S与S+A1的60条，S+A0的30条留后。

可选补充使用独立种子20261029：每作品随机1段既有F_w历史，三臂各随机1条，共30回答、60视图；单独编号、单独导出，由用户决定是否标注。独立种子使是否保留可选补充不改变主集。两集均不因与旧40诊断自然重合而重抽，重合数量单列；与后续新40留出若重合也如实披露，不称两项完全独立的证据。

只在本次抽样前登记已提交推送后，显式传该提交号运行抽样入口；已有样本只复用、不重抽。样本与原文仅留A100及已授权本地人工阅读目录，不入仓库。

代理交接顺序：协调方提交规则、抽样与建立不含标签的视图 → 新的无上下文独立代理按原冻结提取提示盲评全部240视图一次 → 协调方将原回答、材料、原机器提取和代理原始提取并列导出 → 用户标注 → 协调方按三列分别校准。代理只能读取专用盲表入口和提交自己的提取，不读机器列、样本映射或人工结果。这是代理阅读辅助，不是人工真值；原代理不重复派发，新40门槛代理之后另按其冻结前置执行。

人工阅读表保留原正文全部格式标记，显式显示固定前缀和第三轮用户消息，并提供材料登记及两种原始提取。**固定前缀使臂对人工可见**，不得称人工对臂盲化。尚未由原串行机器队列返回的项目明确写等待，不能另开模型提前处理；随后仅更新阅读表，不覆盖已经填写的人工JSON。表单所有结论留空，空白不当已标。

### 校准、判定及费用

用户已明确确认：三列的0.80校准门槛使用**全样本保守一致率**，双方都确定且一致才计一致，未知计不一致、计划全分母不缩减；另报主事件下界标记一致率和双方确定项一致率。分候选类型、臂与实际已标范围报告。某列达到0.80时仅在对应人工样本覆盖范围内标“经事后人工集校准”；不能拿X样本自动放行未标F_w或未覆盖的第五批格。次列校准通过不追认原列留出门槛通过。

人工口径沿原未知界、作品簇2000次重抽、抽样区间及−0.30/−0.10阈值；加入A0允许比较一般前缀与问题重述，不改变既有Q2区间判据或事前知识状态限制。人工回退立即进行，之后无论新40门槛是否通过都不撤回。

原5920输入全部返回后仍按：完整重提示ID清单提交 → 统一重提示 → 新抽40留出 → 独立复核 → 主列门槛。门槛及人工校准之前不查看按臂/格的关系数字；机械标记与必要的校准一致率计算单列，不偷看效应。

强提取器全量5920及重提示相当量只估词元与费用，不启动。采用原独立代理实际模型与可核实的消耗记录，官方价格另核验；代理工具交互开销、缓存和推理输出与直接单条调用不同，估算须写明假设。实际订阅用量不能冒称API账单。是否全量采用更强提取器由用户在校准后决定；它可能改善提取可靠性，但不能自动弥补材料覆盖不足，故不宣称是收窄全部关系未知界的唯一科学途径。

所有新增调用只属于评审模型，成本按第63项另列；不新增主模型生成，不修改运行队列，不把187项定向交人工，不启动G′，52/53不执行，阶段二报告后的暂停点不变。


### 本轮执行结果（2026-10-28）

抽样前登记已提交推送 `aadce904906c2ab287cf66975180406c80020b90`，之后才抽定90条X主集及30条虚构人物可选补充。全部120回答、240人物视图已由一个无上下文独立代理完成一次提取，身份与人物顺序核对通过；与原40诊断自然重合2回答，未重抽。独立代理实际模型为GPT-6 Astra，推理强度xhigh。不是人工真值，也未据此计算关系事件一致率。

机械补充结果及分层表见 [提及诊断补充检查](early-stage/factdiag7/stage2_mention_followup_checks.md) 和同名JSON。287个输入绑定检查未发现不一致；实际在途载荷未另存，证据限制如实保留。原100独立视图漏提0、同视图旧机器漏提20；已返回第三版配对49中漏提4，不混分母。187个漏提视图有163个姓名句含关系词干，1个所有姓名句均含用户话语线索；仅作启发式计数。345条严格引文缺失中，规范化子串通过314，仍不通过31；通过者中54超过原30词上限，次列二可解除260，保留85条无效。

新回答本轮快照736/2880返回，8项在途；所有按臂、视图、候选的四类标记计数及分母已列入报告。显卡只有原42057；没有中断或改动队列，没有启动统一重提示或新40留出。基线输出253258、新回答截至快照输出125994评审词元；主模型生成仍520860。新独立代理本轮累计输入3378733（缓存3310848）、输出42030（含推理7522），按评审用途另列。

两套本地人工材料分别为 `stage2_fallback_X_reading.html` / `stage2_fallback_X_labels.json` 与 `stage2_fallback_Fw_optional_reading.html` / `stage2_fallback_Fw_optional_labels.json`，存于工作区的 `factdiag7-work/human-review/`，不入仓库。每条保留原回答格式、用户消息、固定前缀、登记材料及机器/独立原提取。导出时机器已返回主集96/180视图、可选补充32/60；其余112明确显示等待，之后只刷新HTML，已有人工填写表不覆盖。独立提取240/240齐全。

校准代码已接三列，次列二只从原列构造副本，不与重提示混合。已准备人工标签接入入口：默认90或可选30完整计划，用户优先60时显式限定S/S+A1；未知留在分母，未审阅空表不能自动当标签。本轮8项针对性测试通过（抽样与规范化4项、三列隔离1项、人工校准3项）；仅合成测试，没有运行真实关系汇总或校准。

更强提取器费用仅估算，未启动：按本轮240视图的当前协议工作流分组外推5920，标准短上下文接口价格下约150.25美元（沿本轮缓存比例）或885.26美元（输入全不缓存）；首组187个额外视图约4.75或27.96美元，最终重提示数尚未齐全。旧100视图基准的115.34/426.73美元保留为历史对照。均为经验预算情景，不是置信区间、实际订阅账单或单次净提示费用；更换分组与缓存方式会改变成本。官方价格、词元与假设均在报告中。
