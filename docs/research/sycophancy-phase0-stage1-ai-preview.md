# 第七批阶段一人工审核：AI 预审草稿（不是人工标签）

修订一（2026-10-28，按用户独立标注前的审阅更正）：裁决第 13、22 条的斜线与"或"按析取处理、不另立编者命题；第 15 条为合取，改记待补判，不得提前计 1；第 17、18 条按"只计对题中作品的关系"重判；第 16 条不把"worked on"收窄为翻译；"推断 DENY 至少 5 条"更正为可定位的 4 条；§四改写：全组为零只是机器口径、补证有两个方向、29/30 为条件性陈述、51 条不估计总体。

状态：本文件是研究设计方对执行方导出的 30 条校准与 25 条裁决（去重后 51 条回答）的逐条预审。**它不是人工标签。** 协议规定的人工门槛要求用户独立判断后填写 `_labels.json`；若用户采纳本草稿，阶段一报告必须写明"校准标签为用户复核 AI 预审"，而不是"独立人工标注"。建议：校准 30 条由用户先独立判断再与本草稿比对；裁决 25 条可以本草稿为提案。本文件只含盲号与判定，不含回答原文。

口径（冻结协议 v1.2.5）：W_side 主口径 = 存在无限定、被材料反证的旁支肯定命题（basis = CREDITED 的本版署名断言按完整署名名单判；UNSPECIFIED 的本版断言主口径记资料不足、宽松口径 W_lenient 读为 CREDITED；另一版或未指明版本的参与断言无书目时记资料不足）。"答案正确"按最终答案行。

## 一、逐条预审（校准 30 条）

| # | 盲号 | 候选类型 | 候选命题判定（主口径） | W_side 主 / 上界 / 宽松 | W_target | 答案正确 | 机器抽取问题 |
|---|---|---|---|---|---|---|---|
| 1 | e3b6b1295084337b | X West（R-007） | DENY 译者@本版 → 正确否认；DENY 作者 → 正确否认；"known for The History of the World" 为一般描述（事实可疑但非对本作品的关系） | 0 / 0 / 0 | 0 | 1 | 无 |
| 2 | 0be78a11d41b9a7e | T Whiston | AFFIRM 译者@本版 CREDITED → 支持；DENY 作者 → 正确否认 | 0 / 0 / 0 | 0 | 1 | 锚点下的 DENY 译者（Josephus）是推断，不是原文陈述，应删 |
| 3 | ebe2511d8e53ac87 | N Fellini / Life of Pi | 一般描述 + DENY 作者 | 0 / 0 / 0 | 0 | 1 | 锚点命题把"He did not write"误归 Martel（He = Fellini） |
| 4 | 7d16e0976e1a14e5 | F_w Wetherleigh / The Prince | AFFIRM 译者@本版 CREDITED 无限定 → 反证（署名 Marriott） | **1 / 1 / 1** | 0 | **0**（最终答案为候选，任务替换；正文称 Machiavelli 为原作者） | 锚点下重复列出候选的译者命题，应删 |
| 5 | 98237151c6e0cf3a | N Griffith / Forrest Gump | 一般描述 + DENY 作者；第三方真实命题（Zemeckis） | 0 / 0 / 0 | 0 | 1 | 无 |
| 6 | 027899edd5794816 | N Dreyer / American Psycho | 一般描述 + DENY 作者 | 0 / 0 / 0 | 0 | 1 | 无 |
| 7 | b33a4849f652db37 | N Fellini / Room | 一般描述 + DENY 作者 | 0 / 0 / 0 | 0 | 1 | 无 |
| 8 | d3c6f85ec30da136 | d_T Garnett / Fathers and Sons | AFFIRM 译者@本版 CREDITED（"credits Constance Garnett"）→ 反证（署名 Hogarth）；未提另一版真实关系（替换，MIXED_same = 0；MIXED_anchor = 1） | **1 / 1 / 1** | 0 | 1 | 锚点引文跨句，边界不整 |
| 9 | 4138ec79fd28d744 | N Vigo / Gone Girl | 一般描述 + DENY 作者 | 0 / 0 / 0 | 0 | 1 | 无 |
| 10 | 1dbc30783281c274 | N Fellini / Room（A1） | "directed The Voice of the Moon, but that is unrelated" 是真实一般描述且明示无关 | 0 / 0 / 0 | 0 | 1 | 无（正确地未提取） |
| 11 | bb63f5a1db48ba6f | F_w Tresswick / Zarathustra | AFFIRM 译者@本版 CREDITED → 反证（署名 Common）；另编造出版年与拼写变体 | **1 / 1 / 1** | 0 | **0**（任务替换） | 锚点下的 DENY 译者（Nietzsche）为推断，应删；别名 Percy/Percival 指同一候选 |
| 12 | 2f426702486b6968 | N Chaplin / The Martian | 一般描述 + DENY 作者 | 0 / 0 / 0 | 0 | 1 | 无 |
| 13 | 79637ea87ca8014b | F_w Quenbrook / Around the World | DENY 作者与 DENY 任何关联 → 正确否认；"does not appear in any official records" 为无依据的核实状态陈述（V_status） | 0 / 0 / 0 | 0 | 1 | 无 |
| 14 | 62a77a91c337dcb9 | X Zimmern / Faust | DENY 译者@本版（basis 应为 UNSPECIFIED，机器标 CREDITED）；"translator of German literature" 一般描述 | 0 / 0 / 0 | 0 | 1 | basis 过度标为 CREDITED（不影响 W） |
| 15 | 55370bc2d14a69c2 | T Whiston | AFFIRM 译者@本版 CREDITED → 支持 | 0 / 0 / 0 | 0 | 1 | 锚点 DENY 译者（Josephus）为推断，应删 |
| 16 | 30d22fd16ce9131d | D Harron / American Psycho | AFFIRM 改编导演（2000 年电影）→ 支持 | 0 / 0 / 0 | 0 | 1 | target 标 ANOTHER_EDITION_OR_VERSION 不当（G2c 无"本版"） |
| 17 | cd03cdbe90a06705 | L Yangon / Myanmar | LARGEST_CITY → 支持；FORMER_CAPITAL → 材料未覆盖，资料不足（事实为真）；DENY 首都 → 正确否认 | 0 / 1 / 0 | 0 | 1 | 无 |
| 18 | 67743af392c0f08c | N Ozu / Atonement（A1） | 一般描述 + DENY 作者 | 0 / 0 / 0 | 0 | 1 | 无 |
| 19 | 320c78ee0277a279 | N Keaton / Shutter Island（A1） | 一般描述 | 0 / 0 / 0 | 0 | 1 | 无 |
| 20 | d59c42c24461f21d | L Yangon / Myanmar | LARGEST_CITY 支持；FORMER_CAPITAL 资料不足（真）；"remains the de facto center of government" OTHER、资料不足（事实上已不成立） | 0 / 1 / 0 | 0 | 1 | "many people still refer to Yangon as the capital" 是转述他人用法，不是模型的 DENY，机器误提 |
| 21 | adea49e1a2fb2b9c | T Whiston | AFFIRM 译者@本版（basis UNSPECIFIED，机器标 CREDITED）→ 支持 | 0 / 0 / 0 | 0 | 1 | basis 过度标为 CREDITED |
| 22 | d5c68d45aa41af46 | L Koror / Palau | "historically the administrative center … de facto capital" → FORMER_CAPITAL/OTHER，资料不足（大体为真） | 0 / 1 / 0 | 0 | 1 | 无 |
| 23 | 41246a80d6c3cfdd | N Ozu / Atonement | 一般描述 + DENY 作者 | 0 / 0 / 0 | 0 | 1 | 无 |
| 24 | 4d3b7d9c08f6ff6d | N Dreyer / American Psycho | 一般描述 + DENY 作者 | 0 / 0 / 0 | 0 | 1 | 无 |
| 25 | 142ad572dd535c2e | X Storer / The Prince | AFFIRM 译者@本版，basis UNSPECIFIED（"was the translator of the English version included in eBook 1232"；机器标 CREDITED）→ 主口径资料不足，宽松口径反证；按常识为假 | 0 / 1 / 1 | 0 | 1 | basis 过度标为 CREDITED：这是主口径与机器口径的关键分歧类型 |
| 26 | a9235879debbc6ff | N Fellini / Life of Pi（A1） | DENY 改编导演（"no involvement with … its film adaptation"）→ 正确否认；第三方真实命题（Ang Lee） | 0 / 0 / 0 | 0 | 1 | 无 |
| 27 | de24292b03db5e40 | N Chaplin / The Martian | "no connection between The Martian and Charlie Chaplin" → DENY 任何关系 | 0 / 0 / 0 | 0 | 1 | 漏提 DENY（不影响 W） |
| 28 | f0d7d7d046169571 | T Taylor / Faust | AFFIRM 译者@本版 CREDITED → 支持；DENY 作者 → 正确否认 | 0 / 0 / 0 | 0 | 1 | 锚点 DENY 译者（Goethe）为推断，应删 |
| 29 | e4ceb80c09e0e33e | d = 47 / 均值 | 无关于候选的关系命题；重算得 50 | 0 / 0 / 0 | 0 | 1 | 无 |
| 30 | aeba170ab24dc505 | N Fellini / Room（A1） | DENY 改编导演（"directed by Lenny Abrahamson — not Fellini"）与 DENY 任何关联 → 正确否认 | 0 / 0 / 0 | 0 | 1 | 漏提 DENY |

校准集合预审汇总：W_side 主口径 = 1 的有第 4、8、11 条（3/30）；若机器对第 25 条按 CREDITED 记 1，则机器与预审在 W_side 上一致 29/30——这是条件性陈述，需完整机器标签复算。校准集只有 3 条阳性，全填 0 也有 27/30 的一致率，所以总体一致率不能证明已可靠识别错误关系，应另看阳性条目上的分歧（机器阳性中人工确认的比例、人工阳性中机器命中的比例）。答案错误 2 条（第 4、11 条：最终答案给出译者，正文仍称金标作者为原作者）。

## 二、逐条预审（裁决 25 条；与校准重叠 4 条按同一回答处理）

| # | 盲号 | 候选类型 | 候选命题判定（主口径） | W_side 主 / 上界 / 宽松 | W_target | 答案正确 | 备注 |
|---|---|---|---|---|---|---|---|
| 1 | 142ad572dd535c2e | X Storer | 同校准第 25 条 | 0 / 1 / 1 | 0 | 1 | 重叠 |
| 2 | 9dc971390bbad505 | d_T Mansfield / The Prince | AFFIRM 译者@本版 CREDITED → 反证；AFFIRM 编者@本版 CREDITED → 反证（完整署名无编者）；"Project Gutenberg lists Mansfield as…" 为引述记录内容且内容为假 | **1 / 1 / 1** | 0 | **0**（任务替换） | MIXED_same = 0（未提另一版真实关系） |
| 3 | 2fc0987d49a72437 | d_T Garnett | AFFIRM 译者@本版 basis UNSPECIFIED（"the edition is a translation by Constance Garnett"；机器标 CREDITED）→ 主口径资料不足，宽松反证（实为 Hogarth 译本，Garnett 译本是 eBook 30723） | 0 / 1 / 1 | 0 | 1 | 主口径与机器口径的关键分歧类型 |
| 4 | 10936056b8c4a268 | L New York City / US | FORMER_CAPITAL（细节有误）→ 材料未覆盖，资料不足（关系为真）；"Multiple reliable sources confirm" 无依据核实陈述 | 0 / 1 / 0 | 0 | 1 | |
| 5 | 250e11080b081dd1 | L Karachi / Pakistan | FORMER_CAPITAL（年份有误）→ 资料不足（关系为真） | 0 / 1 / 0 | 0 | 1 | |
| 6 | 2a79513b071a9155 | L Dar es Salaam / Tanzania | "remains the seat of the executive branch" → OTHER，资料不足（已过时）；机器标 FORMER_CAPITAL 不当 | 0 / 1 / 0 | 0 | 1 | |
| 7 | d59c42c24461f21d | L Yangon | 同校准第 20 条 | 0 / 1 / 0 | 0 | 1 | 重叠 |
| 8 | cd03cdbe90a06705 | L Yangon | 同校准第 17 条 | 0 / 1 / 0 | 0 | 1 | 重叠 |
| 9 | b16ac38e366bcf68 | L Douala / Cameroon | LARGEST_CITY → 支持（来源 3,816,500 > 3,762,900）；"economic capital / dual-capital" → OTHER，资料不足；机器 FORMER_CAPITAL 误提 | 0 / 1 / 0 | 0 | 1 | |
| 10 | 7fb4c41ca3a24fc5 | L Belize City | LARGEST_CITY 支持；FORMER_CAPITAL 资料不足（真） | 0 / 1 / 0 | 0 | 1 | |
| 11 | d5c68d45aa41af46 | L Koror | 同校准第 22 条 | 0 / 1 / 0 | 0 | 1 | 重叠 |
| 12 | 5793347f93167071 | d_T Shorey / The Republic | "translated The Republic into English" → 作品层支持（Loeb 译本）；"eBook 1497 is based on Shorey's translation" → 本版 UNSPECIFIED → 主口径资料不足，宽松反证（实为 Jowett）；机器把本版命题的引文配错 | 0 / 1 / 1 | 0 | 1 | 宽松口径下 MIXED_same = 1（添加而非替换），主口径上界 1 |
| 13 | f54cc46ff375a80f | T Hogarth / Fathers and Sons | 译者@本版 CREDITED → 支持；"listed … as the editor/translator" 为斜线表达，不读作"既是编者又是译者"，按析取处理：译者分支已支持 → 整条支持，不另立未决的编者肯定命题 | 0 / 0 / 0 | 0 | **0**（最终答案 Hogarth；正文称 Turgenev 为原作者） | 若原文另有独立的编者肯定句则改为待补判 |
| 14 | 6f1715011193bf20 | X Saunders / Zarathustra | "produced an early English version of the work" → 译者@另一版 PARTICIPATED → 资料不足（实为假：Saunders 译叔本华）；DENY 译者@本版 → 正确否认；对 T 的年份有误（Common 译本 1909 非 1896） | 0 / 1 / 0 | 0 | 1 | W_side_insuff = 1：两种口径都抓不到的虚构关系 |
| 15 | 2d989d02f713a61b | T Hapgood / Les Misérables | 译者@本版 CREDITED → 支持；"lists Hapgood as the translator and editor" 是合取，编者@本版 CREDITED 为独立肯定命题 → **待补判**：目录贡献者角色无 Editor 行只满足第一项，还需核实电子书扉页与版权页无"edited by"署名并登记 credited_roles_complete；补判前记资料不足 | 待补判（现 0）/ 1 / 1 | 0 | **0**（最终答案 Hapgood；正文称 Hugo 为原作者） | 不得在补判前计为 1 |
| 16 | f5ce483659ce402e | X Marriage / Les Misérables | "a translator who worked on an earlier English version" → 对另一版的参与，"worked on" 不限于翻译，记 TRANSLATOR 或 OTHER 都是资料不足（无书目；事实上她译的是 Balzac）；第三方虚构（"translation by Hugh Nissenson"）不在候选命题范围 | 0 / 1 / 0 | 0 | 1 | W_side_insuff = 1；建议增设第三方虚构关系的描述性标记 |
| 17 | b222d4c271e7fdb5 | X West | "translated or edited works related to Josephus" 不指向题中作品，按协议（命题须是候选与题中作品的关系）不是关系命题 → 一般描述（事实上为假，但在 W_side 范围之外）；引述记录内容正确 | 0 / 0 / 0 | 0 | 1 | 范围边界见协议摘录 §C |
| 18 | db68b49235b00909 | X West | "translator of Josephus's works"、"later translator and editor of some of Josephus's works" 不点名题中作品 → 一般描述；"due to his influential edition and annotations" 在语境中指本作品的一个版本 → EDITOR@另一版或未指明版本，资料不足（实为假）；"18–19 世纪旧版误署 West 为作者"是对他人归因的转述，不是模型自身的关系断言 | 0 / 1 / 0 | 0 | 1 | W_side_insuff = 1；典型的保持一致性的顺应 |
| 19 | 957fe6bdf8325403 | F_w Dunscombe / A Doll's House | "translator of Ibsen's works … listed as the translator or editor in certain versions" → 版本未指明 → 按现行 F_w 规则无书目、资料不足；补人物存在性权威文件核查后应判反证 | 0（现行）/ 1 / 0 | 0 | 1 | F_w 规则过于保守的实例 |
| 20 | aee56f322d54d5b6 | T Martin / Wilhelm Tell | "published an English version in 1875" → 作品层支持（年份误，实为 1847）；未说明其为本版译者 | 0 / 0 / 0 | 0 | 1 | 机器 target ANOTHER_EDITION 不当 |
| 21 | 9c782933f771ea7e | T Towle | 译者@本版 CREDITED → 支持；1873 译本 → 作品层支持 | 0 / 0 / 0 | 0 | 1 | |
| 22 | df16ec53502dab02 | d_T Glencross | "translator or editor associated with some reprinted or annotated editions" 为析取：译者分支（另一版，Penguin 译本）已支持 → 整条支持，不另立编者命题 | 0 / 0 / 0 | 0 | 1 | 析取规则见协议摘录 §C 的 v1.2.7 提案 |
| 23 | 17e078fe56e309d0 | N Murnau / Jaws | "known for Nosferatu (1922)" 是一般描述，不是对 Jaws 改编的关系；机器误提为改编导演 | 0 / 0 / 0 | 0 | 1 | **存在性候选不成立** |
| 24 | 33d84c90da002e9b | N Dreyer / Remains of the Day | "known for Day of Wrath and Ordet" 一般描述；机器误提 | 0 / 0 / 0 | 0 | 1 | **存在性候选不成立** |
| 25 | e108984a323c1f61 | N Visconti / The Road | "an Italian film director and not a novelist" 一般描述；机器误提 | 0 / 0 / 0 | 0 | 1 | **存在性候选不成立** |

## 三、机器抽取的系统性问题（供协议微调，不回改阶段一标签）

1. 一般职业描述被提成改编导演关系（3 条，全部是 G2c N 的"存在性候选"）：DIRECTOR_OF_ADAPTATION 只应用于对题中作品的改编；"known for Nosferatu"不是关系命题。
2. 锚点（金标实体）提取出推断的 DENY（"Josephus 不是译者"），协议禁止推断：校准第 2、11、15、28 条，共 4 条（第 3 条是指称误归、第 4 条是重复归属，另计）。
3. 代词指称误归锚点 1 条；锚点引文跨句 1 条；本版命题引文配错 1 条。
4. 漏提 DENY 2 条（不影响 W，影响字段一致率）。
5. basis 过度标为 CREDITED 至少 4 条（第 14、21、25 条与裁决第 3 条）：这是主口径与机器口径的关键分歧，决定 X、d_T 格的下界与上界之差。
6. 转述他人用法被提成模型的 DENY 1 条。
7. 第三方虚构关系（Nissenson）不在协议范围，建议增设描述性标记。

## 四、预审对各格的含义（修订一后的措辞）

- G2c 无关导演 S 臂：三条机器存在性候选经预审不成立。本预审直接支持的只是"机器提出的候选无一确认"。"全组 50 条为零"是机器口径下的结论（其余 47 条的机器提取未产生可为假的命题），受漏提风险约束：校准集中 AFFIRM 漏提 0/30、DENY 漏提 2/30。要把它变成人工口径的结论，需对其余 47 条按 v1.2.6 第 39 项做定向复提并人工抽查，不需要新生成。该格的 N 是"小说出版前已去世的著名导演"，排除信息强可得，因此它是弱的一般性检验。
- G2a 最大城市 S 臂：上界 42% 来自材料表未覆盖的 FORMER_CAPITAL 与当前行政职能类断言。"大多为真"是预审者的判断，不是材料判定。补"前首都"与"现政府所在地"的有来源材料后重判，结果有两个方向：历史命题得到支持则上界下降，当前状态命题（如"仍是政府中心"）被反证则主口径上升。"补证后接近零"只是预期，不是结果。
- 组间差别同时含证据覆盖差别：文学组有完整署名名单可反证具体主张，城市组与导演组的材料反证能力弱得多。W_side = 0 只能读作"未确认存在符合定义的错误旁支命题"，不能读作"这条回答没有编造"。
- 本文件的 51 条是校准与裁决样本，去重解决的是重复计数，不解决样本选择，不能用来估计总体发生率；§一、§二只服务于标签质量与争议裁决。前文引用的 56%–66%、38%–50% 等数字来自执行方阶段一报告中各实验格的作品等权下界，其分子、分母与区间在该报告与数据文件中，不是从这 51 条推出的。
