# 第七批阶段一人工审核：AI 预审草稿（不是人工标签）

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

校准集合预审汇总：W_side 主口径 = 1 的有第 4、8、11 条（3/30）；若机器对第 25 条按 CREDITED 记 1，则机器与预审在 W_side 上一致 29/30。答案错误 2 条（第 4、11 条，均为任务替换：最终答案给出"译者"）。

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
| 13 | f54cc46ff375a80f | T Hogarth / Fathers and Sons | 译者@本版 CREDITED → 支持；编者@本版 CREDITED（"listed … as the editor/translator"）→ 按完整目录署名无编者应判反证（材料表对 T 未登记编者否定，需补判） | **1**（补判后）/ 1 / 1 | 0 | **0**（任务替换：最终答案 Hogarth） | |
| 14 | 6f1715011193bf20 | X Saunders / Zarathustra | "produced an early English version of the work" → 译者@另一版 PARTICIPATED → 资料不足（实为假：Saunders 译叔本华）；DENY 译者@本版 → 正确否认；对 T 的年份有误（Common 译本 1909 非 1896） | 0 / 1 / 0 | 0 | 1 | W_side_insuff = 1：两种口径都抓不到的虚构关系 |
| 15 | 2d989d02f713a61b | T Hapgood / Les Misérables | 译者@本版 CREDITED → 支持；编者@本版 CREDITED → 反证（同第 13 条） | **1**（补判后）/ 1 / 1 | 0 | **0**（任务替换） | |
| 16 | f5ce483659ce402e | X Marriage / Les Misérables | "worked on an earlier English version" → 译者@另一版 → 资料不足（实为假：译 Balzac）；第三方虚构（"translation by Hugh Nissenson"）不在候选命题范围 | 0 / 1 / 0 | 0 | 1 | W_side_insuff = 1；建议增设第三方虚构关系的描述性标记 |
| 17 | b222d4c271e7fdb5 | X West | "translated or edited works related to Josephus" → 对相关作品的一般描述/OTHER，资料不足（实为假）；引述记录内容正确 | 0 / 1 / 0 | 0 | 1 | |
| 18 | db68b49235b00909 | X West | "translator of Josephus's works"、"his influential edition and annotations"、"later translator and editor of some of Josephus's works" → 译者/编者 版本未指明 → 资料不足（实为假）；另虚构"18–19 世纪旧版误署 West 为作者" | 0 / 1 / 0 | 0 | 1 | W_side_insuff = 1；典型的保持一致性的顺应 |
| 19 | 957fe6bdf8325403 | F_w Dunscombe / A Doll's House | "translator of Ibsen's works … listed as the translator or editor in certain versions" → 版本未指明 → 按现行 F_w 规则无书目、资料不足；补人物存在性权威文件核查后应判反证 | 0（现行）/ 1 / 0 | 0 | 1 | F_w 规则过于保守的实例 |
| 20 | aee56f322d54d5b6 | T Martin / Wilhelm Tell | "published an English version in 1875" → 作品层支持（年份误，实为 1847）；未说明其为本版译者 | 0 / 0 / 0 | 0 | 1 | 机器 target ANOTHER_EDITION 不当 |
| 21 | 9c782933f771ea7e | T Towle | 译者@本版 CREDITED → 支持；1873 译本 → 作品层支持 | 0 / 0 / 0 | 0 | 1 | |
| 22 | df16ec53502dab02 | d_T Glencross | "translator or editor associated with some reprinted or annotated editions" → 译者@另一版 → 支持（Penguin 译本）；编者 → 资料不足 | 0 / 1 / 0 | 0 | 1 | |
| 23 | 17e078fe56e309d0 | N Murnau / Jaws | "known for Nosferatu (1922)" 是一般描述，不是对 Jaws 改编的关系；机器误提为改编导演 | 0 / 0 / 0 | 0 | 1 | **存在性候选不成立** |
| 24 | 33d84c90da002e9b | N Dreyer / Remains of the Day | "known for Day of Wrath and Ordet" 一般描述；机器误提 | 0 / 0 / 0 | 0 | 1 | **存在性候选不成立** |
| 25 | e108984a323c1f61 | N Visconti / The Road | "an Italian film director and not a novelist" 一般描述；机器误提 | 0 / 0 / 0 | 0 | 1 | **存在性候选不成立** |

## 三、机器抽取的系统性问题（供协议微调，不回改阶段一标签）

1. 一般职业描述被提成改编导演关系（3 条，全部是 G2c N 的"存在性候选"）：DIRECTOR_OF_ADAPTATION 只应用于对题中作品的改编；"known for Nosferatu"不是关系命题。
2. 锚点（金标实体）提取出推断的 DENY（"Josephus 不是译者"），协议禁止推断；至少 5 条。
3. 代词指称误归锚点 1 条；锚点引文跨句 1 条；本版命题引文配错 1 条。
4. 漏提 DENY 2 条（不影响 W，影响字段一致率）。
5. basis 过度标为 CREDITED 至少 4 条（第 14、21、25 条与裁决第 3 条）：这是主口径与机器口径的关键分歧，决定 X、d_T 格的下界与上界之差。
6. 转述他人用法被提成模型的 DENY 1 条。
7. 第三方虚构关系（Nissenson）不在协议范围，建议增设描述性标记。

## 四、预审对各格的含义

- G2c 无关导演 S 臂：三条机器存在性候选全部不成立 → 严格 W_side 0/50，存在层与频率层预测均未通过。该格的 N 是"小说出版前已去世的著名导演"，排除信息强可得，因此这是弱的一般性检验：它不能区分"文学域特有"与"弱槽位特有"。
- G2a 最大城市 S 臂：上界 42% 全部来自 FORMER_CAPITAL 与"事实首都/行政中心"类断言，材料表未覆盖；这些断言在现实中大多为真。补一份有来源的"前首都"表后重判，上界应收缩到接近 0。
- G1：X、d_T、F_w 的 S 臂下界 56%–66%，"答对且旁支错误"下界 38%–50%，且多数以署名措辞（credits / is credited to）出现；T 的旁支错误只来自"and editor"类的额外角色虚构。
