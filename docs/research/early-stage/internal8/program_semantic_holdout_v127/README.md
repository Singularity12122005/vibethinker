# 第1.27版：不接触模型的独立留出材料候选稿

**已准备64道新题，四类各16道，共122个预设错误候选。64个当前版本真值均已用CPython 3.11.16独立进程执行核定。模型接触、前向、首答和续写均为零。** 这里只签发材料准备完成，不签发难度、资格或α分层覆盖。

## 与开发材料的界限

排除全部32道语义开发题，而不只是正确首答侧的28题。逐表达式去除常量后的语法结构与32题比较均不重合；材料逐项列出新操作及错误规则，没有把原题换数字作为新题。该检查不能证明知识机制独立：新题之间、与开发题之间仍可能共享更一般的概念。

64题是64个不同问题，不是64个独立规则机制。例如组合与排列、左右分区、两种短路消费有关联，正式统计仍须按具体问题及规则联系解释。新导入模块增多是与开发模板的差异，现已明确写入全部题面，不应把新导入名称本身误当作跨域效果。

## α、θ与答案空间

α仍指点名候选后的中性命题认可分数，θ为同模板下真命题认可分数；不改成自由答案串似然。全部分数及α层字段为null，明确表示未测，不能把人工候选顺序解释成高、中、低概率。

候选池按错误规则提出，每题1—3个：54题各2个、8题各1个、2题各3个。布尔题只给另一个布尔值，不能硬凑三个不同的错误布尔值。另有两题仅保留一个清楚的错误候选。候选均与真值不等值，同题候选不重复；例如数值3和3.0没有当作两个独立错误值。

“每题三个候选且分别覆盖α低中高”不能在不接触模型时完成，也未得到保证。未来先按批准的同一中性模板测分，再决定跨题分层规则；若同题候选都落在同一段，必须如实保留，不能为了凑层事后反复换题。是否每题选一个主候选、以及正式续写数，留待计算方案另定。

答案空间同时记录正常返回类型、该类型空间大小、是否允许异常答案、预设错误候选数、模型实际可达空间大小。布尔正常值为2种；整数、可变长字符串与容器没有固定有限上界；浮点空间有限但未枚举；实际抛异常的题不强填正常值类型。模型可达空间一律未测。这里的类型空间不能当成校准后的候选可达性。

当前真值结构：62题正常返回，2题抛TypeError；正常返回含6道布尔题。材料未保证获得任意数量的自然错误首答，不能据此承诺真纠正侧资格。

## 版本适用性小组

4题从64题中指定，不另算新增独立题。一个是计数器相等性规则变化，三个是接口引入前后的可用性变化。两类须分开报告，不能把“知道接口是否存在”全部解释成理解同一接口的版本行为。

当前版记录已实际核定。第1.28版执行时，四项旧版结果也已用Python官方便携解释器在独立进程实测：三项采用CPython 3.9.13，一项采用CPython 3.8.10，全部与文档预期一致。version_cases.json现含真实旧版记录，不再用文档推断代替执行。

|题目|当前版本结果|旧版及实测结果|版本依据|
|---|---|---|---|
|holdout-library-01|`True`|CPython 3.9.13：`False`|[官方说明](https://docs.python.org/3.11/library/collections.html#collections.Counter)|
|holdout-numeric-08|`3`|CPython 3.9.13：`raises AttributeError`|[官方说明](https://docs.python.org/3.11/library/stdtypes.html#int.bit_count)|
|holdout-iterator-06|`[(1, 2), (2, 3)]`|CPython 3.9.13：`raises AttributeError`|[官方说明](https://docs.python.org/3.11/library/itertools.html#itertools.pairwise)|
|holdout-text-14|`'ab'`|CPython 3.8.10：`raises AttributeError`|[官方说明](https://docs.python.org/3.11/library/stdtypes.html#str.removeprefix)|

## 材料逐题表

候选具体错误规则、题面、执行记录及未测字段见 materials.json。下表不含任何模型回答。

|编号|表达式|已执行真值|错误候选|规则|
|---|---|---|---|---|
|holdout-numeric-01|`2 ** 3 ** 2`|`512`|`64`；`36`|幂的结合方向|
|holdout-numeric-02|`-3 ** 2`|`-9`|`9`；`-6`|一元负号与幂优先级|
|holdout-numeric-03|`~5`|`-6`|`-5`；`2`|整数按位补码|
|holdout-numeric-04|`8 >> 1 + 1`|`2`|`5`；`4`|加法与移位优先级|
|holdout-numeric-05|`1 < 2 < 2`|`False`|`True`|链式比较|
|holdout-numeric-06|`[] or 7`|`7`|`True`；`[]`|布尔运算返回操作数|
|holdout-numeric-07|`not 1 == 2`|`True`|`False`|否定与比较优先级|
|holdout-numeric-08|`(-13).bit_count()`|`3`|`4`；`61`|整数绝对值的置位数|
|holdout-numeric-09|`(0).bit_length()`|`0`|`1`；`raises ValueError`|零的位长|
|holdout-numeric-10|`divmod(7.5, 2)`|`(3.0, 1.5)`|`(3.75, 0.0)`；`(4.0, -0.5)`|浮点整商余数成对返回|
|holdout-numeric-11|`math.copysign(1.0, -0.0)`|`-1.0`|`1.0`；`0.0`|负零的符号复制|
|holdout-numeric-12|`math.remainder(7, 2)`|`-1.0`|`1.0`；`3.0`|最近整数商余数|
|holdout-numeric-13|`math.fmod(-7, 3)`|`-1.0`|`2.0`；`1.0`|截零商的浮点余数|
|holdout-numeric-14|`math.isfinite(float("nan"))`|`False`|`True`|有限性谓词|
|holdout-numeric-15|`complex(1, 2) < complex(2, 3)`|`raises TypeError`|`True`；`False`|复数不支持大小排序|
|holdout-numeric-16|`float.fromhex("0x1.8p+1")`|`3.0`|`1.8`；`3.6`；`24.0`|十六进制浮点指数|
|holdout-text-01|`"ab".replace("", "-")`|`'-a-b-'`|`'a-b'`；`'ab'`|空模式替换边界|
|holdout-text-02|`"a,,b,".split(",")`|`['a', '', 'b', '']`|`['a', 'b']`；`['a', '', 'b']`|显式分隔符保留空段|
|holdout-text-03|`" a  b ".split()`|`['a', 'b']`|`['', 'a', '', 'b', '']`；`['a', '', 'b']`|无参数空白切分|
|holdout-text-04|`"a\n".splitlines()`|`['a']`|`['a', '']`；`['a\n']`|行切分末尾换行|
|holdout-text-05|`"abc".partition("x")`|`('abc', '', '')`|`('', '', 'abc')`；`raises ValueError`|左分区未命中|
|holdout-text-06|`"abc".rpartition("x")`|`('', '', 'abc')`|`('abc', '', '')`；`raises ValueError`|右分区未命中|
|holdout-text-07|`"ab".ljust(5, "-")`|`'ab---'`|`'---ab'`；`'ab-----'`|对齐宽度是总宽度|
|holdout-text-08|`"-42".zfill(5)`|`'-0042'`|`'00-42'`；`'-00042'`|零填充保留符号位置|
|holdout-text-09|`"a\tX".expandtabs(4)`|`'a   X'`|`'a    X'`；`'a X'`|制表符按当前位置对齐|
|holdout-text-10|`"{0!r}".format("a\n")`|`"'a\\n'"`|`'a\n'`；`'a\\n'`|格式化表示形式转换|
|holdout-text-11|`"a-b-c".rsplit("-", 1)`|`['a-b', 'c']`|`['a', 'b-c']`；`['a', 'b', 'c']`|限次右切分|
|holdout-text-12|`b"\xff".decode("utf-8", errors="ignore")`|`''`|`'�'`；`raises UnicodeDecodeError`|解码忽略无效字节|
|holdout-text-13|`"é".encode("utf-8")`|`b'\xc3\xa9'`|`b'\xe9'`；`b'\\u00e9'`|字符编码与码点区分|
|holdout-text-14|`"ab".removeprefix("ba")`|`'ab'`|`''`；`'a'`|精确前缀删除|
|holdout-text-15|`"x{a}".format_map({"a": "{b}"})`|`'x{b}'`|`raises KeyError`；`'x'`|格式化替换不递归|
|holdout-text-16|`"a".translate({ord("a"): None})`|`''`|`None`；`'None'`|翻译映射空值表示删除|
|holdout-iterator-01|`list(itertools.chain("ab", "cd"))`|`['a', 'b', 'c', 'd']`|`['ab', 'cd']`；`[('a', 'c'), ('b', 'd')]`|串接逐个展开|
|holdout-iterator-02|`list(itertools.zip_longest([1], [2, 3], fillvalue=0))`|`[(1, 2), (0, 3)]`|`[(1, 2)]`；`[(1, 2), (None, 3)]`|最长配对补位|
|holdout-iterator-03|`list(itertools.combinations("AA", 2))`|`[('A', 'A')]`|`[]`；`[('A', 'A'), ('A', 'A')]`|组合按位置区分元素|
|holdout-iterator-04|`list(itertools.permutations("AA", 2))`|`[('A', 'A'), ('A', 'A')]`|`[('A', 'A')]`；`[]`|排列不去重相同值|
|holdout-iterator-05|`list(itertools.combinations_with_replacement("AB", 2))`|`[('A', 'A'), ('A', 'B'), ('B', 'B')]`|`[('A', 'A'), ('A', 'B'), ('B', 'A'), ('B', 'B')]`；`[('A', 'B')]`|可重复组合排除顺序重复|
|holdout-iterator-06|`list(itertools.pairwise([1, 2, 3]))`|`[(1, 2), (2, 3)]`|`[(1, 2)]`；`raises AttributeError`|相邻配对允许重叠|
|holdout-iterator-07|`(lambda xs: xs[0] is xs[1])(list(itertools.repeat([], 2)))`|`True`|`False`|重复迭代保留对象身份|
|holdout-iterator-08|`[list(g) for _, g in itertools.groupby("AABA")]`|`[['A', 'A'], ['B'], ['A']]`|`[['A', 'A', 'A'], ['B']]`；`[['A'], ['B']]`|按连续段分组|
|holdout-iterator-09|`list(enumerate("ab", start=-1))`|`[(-1, 'a'), (0, 'b')]`|`[(0, 'a'), (1, 'b')]`；`raises ValueError`|枚举允许负起点|
|holdout-iterator-10|`list(map(lambda x, y: x + y, [1, 2], [10]))`|`[11]`|`[11, 2]`；`raises ValueError`|多输入映射按最短停止|
|holdout-iterator-11|`list(filter(None, [0, 1, "", 2]))`|`[1, 2]`|`[0, 1, '', 2]`；`raises TypeError`|空谓词使用真值过滤|
|holdout-iterator-12|`sum((x for x in [1, 2]), 10)`|`13`|`3`；`10`|加总起始值参与结果|
|holdout-iterator-13|`(lambda it: (list(it), list(it)))(iter([1, 2]))`|`([1, 2], [])`|`([1, 2], [1, 2])`；`raises StopIteration`|一次性迭代器耗尽|
|holdout-iterator-14|`(lambda it: (any(it), list(it)))(iter([0, 2, 3]))`|`(True, [3])`|`(True, [])`；`(True, [2, 3])`|存在判断的短路消费|
|holdout-iterator-15|`(lambda it: (all(it), list(it)))(iter([1, 0, 3]))`|`(False, [3])`|`(False, [])`；`(False, [0, 3])`|全称判断的短路消费|
|holdout-iterator-16|`next(iter([]), 7)`|`7`|`raises StopIteration`；`None`|取下一项的结束缺省值|
|holdout-library-01|`collections.Counter(a=1) == collections.Counter(a=1, b=0)`|`True`|`False`|计数器缺键视为零|
|holdout-library-02|`dict(collections.Counter(a=1) - collections.Counter(a=2))`|`{}`|`{'a': -1}`；`{'a': 0}`|计数器减法只保留正计数|
|holdout-library-03|`(lambda d: d["a"] is d["b"])(dict.fromkeys(["a", "b"], []))`|`True`|`False`|字典批量赋值共享对象|
|holdout-library-04|`list(dict.fromkeys([1, True, 1.0]))`|`[1]`|`[1, True, 1.0]`|相等数字键合并|
|holdout-library-05|`list(dict([("a", 1), ("b", 2), ("a", 3)]).items())`|`[('a', 3), ('b', 2)]`|`[('b', 2), ('a', 3)]`；`[('a', 1), ('b', 2)]`|更新字典键保留插入位置|
|holdout-library-06|`list(collections.deque([1, 2, 3], maxlen=2))`|`[2, 3]`|`[1, 2]`；`raises ValueError`|有界双端队列淘汰旧值|
|holdout-library-07|`bisect.bisect_left([1, 2, 2, 3], 2)`|`1`|`3`；`2`|二分插入左边界|
|holdout-library-08|`list(heapq.merge([1, 4], [2, 3]))`|`[1, 2, 3, 4]`|`[1, 4, 2, 3]`；`[(1, 2), (4, 3)]`|多个有序输入归并|
|holdout-library-09|`functools.reduce(operator.sub, [10, 3, 2])`|`5`|`9`；`-15`|折叠按左结合|
|holdout-library-10|`operator.index(3.0)`|`raises TypeError`|`3`|索引协议不接受浮点数|
|holdout-library-11|`json.dumps(float("nan"))`|`'NaN'`|`raises ValueError`；`'null'`|非有限数的缺省文本编码|
|holdout-library-12|`json.loads("{\"x\": 1, \"x\": 2}")`|`{'x': 2}`|`raises ValueError`；`{'x': 1}`|文本对象重复键取后值|
|holdout-library-13|`datetime.timedelta(days=-1, seconds=1).seconds`|`1`|`-86399`；`86399`|持续时间字段与总量区分|
|holdout-library-14|`datetime.date(2021, 1, 1).isocalendar().year`|`2020`|`2021`；`2019`|周历年跨公历边界|
|holdout-library-15|`statistics.pstdev([4])`|`0.0`|`raises StatisticsError`；`4.0`|单样本总体标准差|
|holdout-library-16|`fractions.Fraction("1.5").denominator`|`2`|`10`；`5`；`1`|字符串分数约分|
