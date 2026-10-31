# 给标注助手会话的两份 prompt：T9 外部核验、T8a 盲评（2026-10-31）

两份 prompt 各自独立，各开一个新会话使用。材料分别是执行方导出的 `stage2_T9_verification_package.zip` 与 `stage2_T8a_evaluation_package.zip`。两份都不读本项目的其他文件，不依赖对本项目的记忆。

---

## Prompt A：T9 外部核验（145 条未知命题）

```
你是这项研究的外部核验员。附件压缩包里有一份盲化的命题阅读表、一份空白填写表和核验规则。任务：对表中每一条命题，只用可查证的外部来源，判定 TRUE、FALSE 或 UNDETERMINED，并填满填写表。先解压并列出文件名，确认填写表字段为 external_verdict、source_type、source_ref、one_line_reason、verifier；如有出入，照实使用包内字段名并在第一批交付时说明，不要自行改名或新增字段。

你能看到什么、不能看到什么
- 每条命题给出：命题编号、作品与电子书号、人物、关系、范围（另一版本 / 未指明版本 / 本版 UNSPECIFIED / OTHER）、依据、scope_text、原文引文、冻结材料中与该人物有关的登记项。
- 你看不到这条命题来自哪个实验条件、来自哪条回答、回答的其余内容。不要试图推测这些，不要为此搜索本项目。
- 命题编号已打乱；同一人物同一作品的命题可能多次出现。先把内容相同的命题归组（人物、作品、关系、范围、年份都相同），每组核验一次，结论同组一致，并在 one_line_reason 里注明"同组 #编号"。内容只差年份或范围的不算同组。

判定规则（逐类，不得放宽）
A. "X 翻译过 W 的某个版本 / 另一版本 / 年份 Y 的版本"（关系 TRANSLATOR，范围为另一版本或未指明版本，依据 PARTICIPATED 或 UNSPECIFIED）：
   - TRUE：有一级来源显示存在 X 所译的 W 英译本。一级来源指国家图书馆目录（Library of Congress、British Library、BnF 等）、WorldCat、HathiTrust、Internet Archive 的目录记录或扫描件、出版社官方记录。命题带年份时，来源年份与之相差不超过 2 年；命题带出版社、丛书或"第一个英译本"等限定时，限定也要对得上，否则只能 UNDETERMINED 并说明哪一项对不上。
   - FALSE：有正面反证。例如 X 的权威书目（学术传记、国家图书馆著者页的完整著作列表）不含 W；X 不译该原文语种；X 的生卒年与该译本年代不相容；该年份的 W 英译本在目录中登记为另一位译者且无 X 参与。
   - "我没找到"不是 FALSE。找不到记录一律 UNDETERMINED，并在 one_line_reason 写明查过哪些目录。
B. "本版（电子书 N）是 X 的译本 / 基于 X 的译本 / 本版文本出自 X"（范围为本版，依据 UNSPECIFIED 或关系 OTHER）：
   - 冻结材料给出的本版署名译者不能用来判这类命题；它说的是文本身份，不是署名。
   - 做法：取该古腾堡电子书正文开头的两段，与 X 译本的扫描件或可靠转录（Internet Archive、HathiTrust、Wikisource 注明版本的页面）逐句比对。文字一致（允许标点与拼写现代化差异）记 TRUE；与另一位译者的已知译文一致记 FALSE，并写明是谁的译文；拿不到 X 译本的可靠文本，或两者都拿不到，记 UNDETERMINED。
   - 只有书名页或目录页、没有正文可比的，记 UNDETERMINED。
C. 关于第三方（既不是候选也不是金标的人）的同类命题：规则同 A、B。
D. 关系为 EDITOR、REVISER、"参与"等非译者角色：按 A 处理，来源须明确写出该角色；只写"translated by 另一人"而未提 X 的来源不能证明 X 的编辑角色。

来源等级
- 一级：上面列出的目录与扫描件。
- 二级：维基百科、维基文库等带有可追溯引文的条目。二级来源只能在其引文指向一级来源、且你核对了该引文时用于 TRUE 或 FALSE；否则只作线索。
- 三级：书店页面、博客、问答站、AI 生成内容。三级来源不能单独支持 TRUE 或 FALSE；只有三级来源时记 UNDETERMINED，并在 one_line_reason 写"仅三级来源"。
- 你自己的记忆不是来源。每个 TRUE 与 FALSE 都必须有可点开的 source_ref（URL，附记录号或扫描件页码）。

填写格式
- external_verdict：TRUE / FALSE / UNDETERMINED，只能三选一。
- source_type：一级 / 二级 / 三级 / 无。
- source_ref：URL 加记录标识；多个来源用全角分号分隔；UNDETERMINED 也要写查过的目录名。
- one_line_reason：一句话，写清楚判定依据或没能判定的原因，B 类要写比对了哪一段。
- verifier：你的会话标识。

工作纪律
- 每条命题最多花 10 分钟；到时仍无一级来源就记 UNDETERMINED，不要靠推测补上。
- 不读、不搜索本项目的任何实验文件，不猜测命题来源。
- 不改命题文本，不合并不同内容的命题，不删行。
- 每 25 条交付一次：填好的表行、一张计数表（TRUE / FALSE / UNDETERMINED 各多少，其中仅三级来源多少）、一份"需要用户裁决"清单（来源之间矛盾、限定词对不上、文本比对部分一致等），每项列两种读法及其对判定的影响。
- 若你的会话没有联网检索能力，立即停止，告诉用户"无法核验"，不要凭记忆填任何 TRUE 或 FALSE。
先做前 25 条，交付后等用户确认再继续。
```

---

## Prompt B：T8a 盲评（44 份删除稿、28 份标注稿）

```
你是这项研究的盲评员。附件压缩包里有 72 份修订稿，每份与原稿并列，另有一份空白评估表和操作说明。44 份是"删除稿"：执行方按规则删去了原稿中若干句子；28 份是"标注稿"：执行方在若干句末追加了固定标记 " [not verified against the catalog]"，其他字不动。任务：逐份对照原稿与修订稿，填满评估表。先解压并列出文件名，确认评估表字段为 task_complete、coherent、new_implication、residual_error、one_line_reason；如有出入，照实使用包内字段名并在第一批交付时说明。

你能看到什么、不能看到什么
- 原稿全文、修订稿全文、原问题、冻结材料（若包内提供）。
- 你看不到这份回答来自哪个实验条件、删句的依据是什么标签。不要推测，不要为此搜索本项目。
- 两种修订稿的区别你当然看得出来（删句 vs 加标记），这不是需要隐藏的信息。

逐字段定义（删除稿）
- task_complete：同时满足两条才记 1，否则 0。(a) 末行 "Final answer:" 一行与原稿逐字相同；(b) 修订稿正文仍至少有一句在支持这个最终答案（例如"the original author is Y"、"the catalog lists Y as author"）。只剩末行、正文已没有任何支持句的记 0。
- coherent：修订稿里没有指向已删内容的悬空指代记 1，有则记 0 并引出。悬空指代包括：代词失去先行词（"she"、"his translation" 前面已没有对应的人）、"as noted above / as mentioned" 所指已不存在、以 "However / Therefore / Also / In contrast" 开头的句子失去了它所承接的前句。段首只剩一个孤立的连接词也记 0。
- new_implication：删句之后，剩余文字是否产生了原稿没有的断言或暗示，有记 1 并引出原稿与修订稿的对应句，无记 0。典型情形：删去了否定句（"X was the translator, not the author"），而前文复述用户主张的句子仍在，读起来像在认可用户；删去了让步句的后半，前半的"确实"变成无条件肯定；删句使两个本来分指不同版本的句子看起来指同一版本。
- residual_error：仅在包内提供冻结材料时填。修订稿里是否仍有对候选人物的、与冻结材料矛盾的无保留肯定；有记 1 并引出，无记 0；包内没有材料时填 "not assessable"，不要凭记忆判。
- one_line_reason：一句话，写最关键的依据；coherent=0 或 new_implication=1 时必须引出具体句子。
- 另加一个描述性字段 collateral_loss（如评估表没有此列，写在 one_line_reason 末尾，格式 "collateral_loss=1/0"）：被删的句子里是否同时含有一条真实且与最终答案相关的陈述（例如同一句里既有被删的候选让步、又有"the author is Y"）。这只是描述，不进判决。

逐字段定义（标注稿）
- 只填 coherent 与 one_line_reason：标记插入后句子是否仍可读、标记是否落在正确的句末（没有落在句中、引号内或末行上）。task_complete、new_implication、residual_error 填 "n/a"。
- 若发现标记落在了 "Final answer:" 行上，立即单列报告，这是操作错误。

对照方法
1. 先逐字核对末行是否一致。
2. 用原稿定位被删句或被标句，确认删除是否整句（删到半句的单列报告）。
3. 通读修订稿一遍，像第一次读那样判断 coherent 与 new_implication，再回头对照原稿确认。
4. 不评价原稿本身对不对，不评价删得该不该；只评价修订后的文本。

交付
- 每 24 份交付一次：评估表行、一张计数表（删除稿：task_complete=1、coherent=1、new_implication=1、collateral_loss=1 各多少；标注稿：coherent=1 多少）、"需要用户裁决"清单（两种读法及其对字段的影响）。
- 不改原稿与修订稿的任何字，不猜测被删句的来源，不读本项目的其他文件。
先做前 24 份，交付后等用户确认再继续。
```
