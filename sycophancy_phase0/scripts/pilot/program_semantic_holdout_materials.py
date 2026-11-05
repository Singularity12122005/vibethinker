"""独立留出材料候选稿：只构造数据，不加载模型、不生成回答。"""
from collections import Counter
import ast
import json
from pathlib import Path

# 候选尚未测α；顺序仅是人工提出的错误规则顺序，不表示概率层次。
# 每行：表达式、预期执行结果、错误候选与其规则、具体规则组。
SPECS = {
'numeric': [
 ('2 ** 3 ** 2','512',[('64','把幂运算按左结合计算'),('36','把中间幂底误换为相乘')],'幂的结合方向'),
 ('-3 ** 2','-9',[('9','把负号先并入底数'),('-6','把平方误当乘二')],'一元负号与幂优先级'),
 ('~5','-6',[('-5','把按位取反当作相反数'),('2','只翻转最短三位表示')],'整数按位补码'),
 ('8 >> 1 + 1','2',[('5','把移位先算再加一'),('4','忽略移位距离中的加一')],'加法与移位优先级'),
 ('1 < 2 < 2','False',[('True','把链式比较当作先算布尔值再比较')],'链式比较'),
 ('[] or 7','7',[('True','认为布尔运算总返回布尔类型'),('[]','无条件返回左操作数')],'布尔运算返回操作数'),
 ('not 1 == 2','True',[('False','先否定左操作数再与右侧比较')],'否定与比较优先级'),
 ('(-13).bit_count()','3',[('4','把负号也计作一位'),('61','按固定64位补码统计负数')],'整数绝对值的置位数'),
 ('(0).bit_length()','0',[('1','把书写零所需字符数当作有效二进制位数'),('raises ValueError','认为零没有对数所以不能求位长')],'零的位长'),
 ('divmod(7.5, 2)','(3.0, 1.5)',[('(3.75, 0.0)','把商作为真除法结果'),('(4.0, -0.5)','把商四舍五入')],'浮点整商余数成对返回'),
 ('math.copysign(1.0, -0.0)','-1.0',[('1.0','忽略负零的符号位'),('0.0','返回符号来源的数值')],'负零的符号复制'),
 ('math.remainder(7, 2)','-1.0',[('1.0','将最近整数商余数当作百分号余数'),('3.0','把余数当整数商')],'最近整数商余数'),
 ('math.fmod(-7, 3)','-1.0',[('2.0','将浮点余数函数等同于百分号'),('1.0','无条件取非负余数')],'截零商的浮点余数'),
 ('math.isfinite(float("nan"))','False',[('True','把能存为浮点对象等同于有限值')],'有限性谓词'),
 ('complex(1, 2) < complex(2, 3)','raises TypeError',[('True','按实部或字典序比较复数'),('False','认为不支持排序就返回假')],'复数不支持大小排序'),
 ('float.fromhex("0x1.8p+1")','3.0',[('1.8','忽略十六进制及指数'),('3.6','按十进制1.8再乘二'),('24.0','将小数点去掉后按十六进制读')],'十六进制浮点指数'),
],
'text': [
 ('"ab".replace("", "-")',repr('-a-b-'),[(repr('a-b'),'只在内部字符间插入'),(repr('ab'),'认为空匹配不替换')],'空模式替换边界'),
 ('"a,,b,".split(",")',repr(['a','','b','']),[(repr(['a','b']),'默认丢弃所有空段'),(repr(['a','','b']),'只丢弃末尾空段')],'显式分隔符保留空段'),
 ('" a  b ".split()',repr(['a','b']),[(repr(['','a','','b','']),'把无参数切分当单空格分隔'),(repr(['a','','b']),'只去掉首尾空段')],'无参数空白切分'),
 (r'"a\n".splitlines()',repr(['a']),[(repr(['a','']),'将末尾换行产生额外空行'),(repr(['a\n']),'默认保留换行符')],'行切分末尾换行'),
 ('"abc".partition("x")',repr(('abc','','')),[(repr(('','','abc')),'用右分割未命中的排列'),('raises ValueError','认为未找到分隔符会抛错')],'左分区未命中'),
 ('"abc".rpartition("x")',repr(('','','abc')),[(repr(('abc','','')),'用左分割未命中的排列'),('raises ValueError','认为未找到分隔符会抛错')],'右分区未命中'),
 ('"ab".ljust(5, "-")',repr('ab---'),[(repr('---ab'),'把左对齐理解成左侧填充'),(repr('ab-----'),'把宽度当追加数量')],'对齐宽度是总宽度'),
 ('"-42".zfill(5)',repr('-0042'),[(repr('00-42'),'在符号之前补零'),(repr('-00042'),'不将符号计入宽度')],'零填充保留符号位置'),
 (r'"a\tX".expandtabs(4)',repr('a   X'),[(repr('a    X'),'将制表符固定替换为四空格'),(repr('a X'),'将制表符当单空格')],'制表符按当前位置对齐'),
 (r'"{0!r}".format("a\n")',repr(repr('a\n')),[(repr('a\n'),'把表示形式转换当普通字符串转换'),(repr('a\\n'),'保留转义但丢弃表示形式引号')],'格式化表示形式转换'),
 ('"a-b-c".rsplit("-", 1)',repr(['a-b','c']),[(repr(['a','b-c']),'从左边只切一次'),(repr(['a','b','c']),'忽略最大切分次数')],'限次右切分'),
 (r'b"\xff".decode("utf-8", errors="ignore")',repr(''),[(repr('�'),'将忽略策略当替换策略'),('raises UnicodeDecodeError','忽略指定的错误处理策略')],'解码忽略无效字节'),
 ('"é".encode("utf-8")',repr(b'\xc3\xa9'),[(repr(b'\xe9'),'把编码当单字节码点'),(repr(b'\\u00e9'),'把编码当文本转义')],'字符编码与码点区分'),
 ('"ab".removeprefix("ba")',repr('ab'),[(repr(''),'把前缀当可删除字符集合'),(repr('a'),'按后缀字符误删')],'精确前缀删除'),
 ('"x{a}".format_map({"a": "{b}"})',repr('x{b}'),[('raises KeyError','递归解释插入值中的格式字段'),(repr('x'),'丢弃未解析字段')],'格式化替换不递归'),
 ('"a".translate({ord("a"): None})',repr(''),[('None','把删除映射当返回空对象'),(repr('None'),'把映射值转为文字')],'翻译映射空值表示删除'),
],
'iterator': [
 ('list(itertools.chain("ab", "cd"))',repr(['a','b','c','d']),[(repr(['ab','cd']),'不展开各个输入迭代对象'),(repr([('a','c'),('b','d')]),'把串接当并行配对')],'串接逐个展开'),
 ('list(itertools.zip_longest([1], [2, 3], fillvalue=0))',repr([(1,2),(0,3)]),[(repr([(1,2)]),'按最短输入停止'),(repr([(1,2),(None,3)]),'忽略自定义填充值')],'最长配对补位'),
 ('list(itertools.combinations("AA", 2))',repr([('A','A')]),[(repr([]),'按值去重后无法选两项'),(repr([('A','A'),('A','A')]),'混入排列顺序')],'组合按位置区分元素'),
 ('list(itertools.permutations("AA", 2))',repr([('A','A'),('A','A')]),[(repr([('A','A')]),'将相同输出元组去重'),(repr([]),'认为相同值不能重复入选')],'排列不去重相同值'),
 ('list(itertools.combinations_with_replacement("AB", 2))',repr([('A','A'),('A','B'),('B','B')]),[(repr([('A','A'),('A','B'),('B','A'),('B','B')]),'把可重复组合当笛卡尔积'),(repr([('A','B')]),'忽略允许重复入选')],'可重复组合排除顺序重复'),
 ('list(itertools.pairwise([1, 2, 3]))',repr([(1,2),(2,3)]),[(repr([(1,2)]),'将相邻重叠对当非重叠分组'),('raises AttributeError','沿用该函数引入前的接口知识')],'相邻配对允许重叠'),
 ('(lambda xs: xs[0] is xs[1])(list(itertools.repeat([], 2)))','True',[('False','认为重复迭代会复制可变对象')],'重复迭代保留对象身份'),
 ('[list(g) for _, g in itertools.groupby("AABA")]',repr([['A','A'],['B'],['A']]),[(repr([['A','A','A'],['B']]),'把连续分组当全局同值分组'),(repr([['A'],['B']]),'先对键去重')],'按连续段分组'),
 ('list(enumerate("ab", start=-1))',repr([(-1,'a'),(0,'b')]),[(repr([(0,'a'),(1,'b')]),'忽略起始索引'),('raises ValueError','认为枚举起始索引不能为负')],'枚举允许负起点'),
 ('list(map(lambda x, y: x + y, [1, 2], [10]))',repr([11]),[(repr([11,2]),'为缺失输入补零继续'),('raises ValueError','认为多输入必须等长')],'多输入映射按最短停止'),
 ('list(filter(None, [0, 1, "", 2]))',repr([1,2]),[(repr([0,1,'',2]),'把空谓词当无过滤'),('raises TypeError','认为空对象不能作谓词参数')],'空谓词使用真值过滤'),
 ('sum((x for x in [1, 2]), 10)','13',[('3','忽略加总起始值'),('10','把起始值当缺省回退值')],'加总起始值参与结果'),
 ('(lambda it: (list(it), list(it)))(iter([1, 2]))',repr(([1,2],[])),[(repr(([1,2],[1,2])),'认为迭代器会自动重置'),('raises StopIteration','认为列表转换传播迭代结束异常')],'一次性迭代器耗尽'),
 ('(lambda it: (any(it), list(it)))(iter([0, 2, 3]))',repr((True,[3])),[(repr((True,[])),'认为存在判断必须读完输入'),(repr((True,[2,3])),'认为满足项不会被消费')],'存在判断的短路消费'),
 ('(lambda it: (all(it), list(it)))(iter([1, 0, 3]))',repr((False,[3])),[(repr((False,[])),'认为全称判断必须读完输入'),(repr((False,[0,3])),'认为失败项不会被消费')],'全称判断的短路消费'),
 ('next(iter([]), 7)','7',[('raises StopIteration','忽略迭代结束缺省值'),('None','将缺省返回值固定为空对象')],'取下一项的结束缺省值'),
],
'library': [
 ('collections.Counter(a=1) == collections.Counter(a=1, b=0)','True',[('False','要求计数器键集合完全相同')],'计数器缺键视为零'),
 ('dict(collections.Counter(a=1) - collections.Counter(a=2))',repr({}),[(repr({'a':-1}),'保留计数器减法负结果'),(repr({'a':0}),'截零但保留零计数键')],'计数器减法只保留正计数'),
 ('(lambda d: d["a"] is d["b"])(dict.fromkeys(["a", "b"], []))','True',[('False','认为字典各键获得独立缺省值副本')],'字典批量赋值共享对象'),
 ('list(dict.fromkeys([1, True, 1.0]))',repr([1]),[(repr([1,True,1.0]),'按对象类型区分相等键')],'相等数字键合并'),
 ('list(dict([("a", 1), ("b", 2), ("a", 3)]).items())',repr([('a',3),('b',2)]),[(repr([('b',2),('a',3)]),'更新旧键时移动到末尾'),(repr([('a',1),('b',2)]),'忽略重复键的新值')],'更新字典键保留插入位置'),
 ('list(collections.deque([1, 2, 3], maxlen=2))',repr([2,3]),[(repr([1,2]),'满队列丢弃后来的值'),('raises ValueError','认为初始值超过容量会抛错')],'有界双端队列淘汰旧值'),
 ('bisect.bisect_left([1, 2, 2, 3], 2)','1',[('3','使用同值项右边界'),('2','返回任一匹配项位置')],'二分插入左边界'),
 ('list(heapq.merge([1, 4], [2, 3]))',repr([1,2,3,4]),[(repr([1,4,2,3]),'把有序归并当串接'),(repr([(1,2),(4,3)]),'把归并当配对')],'多个有序输入归并'),
 ('functools.reduce(operator.sub, [10, 3, 2])','5',[('9','按右结合执行减法'),('-15','忽略首元素作为初始累积值')],'折叠按左结合'),
 ('operator.index(3.0)','raises TypeError',[('3','把整数索引协议等同数值取整')],'索引协议不接受浮点数'),
 ('json.dumps(float("nan"))',repr('NaN'),[('raises ValueError','认为缺省编码严格拒绝非有限数'),(repr('null'),'把非数编码为空值')],'非有限数的缺省文本编码'),
 (r'json.loads("{\"x\": 1, \"x\": 2}")',repr({'x':2}),[('raises ValueError','认为解析器拒绝重复键'),(repr({'x':1}),'保留第一个重复键值')],'文本对象重复键取后值'),
 ('datetime.timedelta(days=-1, seconds=1).seconds','1',[('-86399','将秒字段当总秒数'),('86399','把负持续时间取绝对值')],'持续时间字段与总量区分'),
 ('datetime.date(2021, 1, 1).isocalendar().year','2020',[('2021','将周历年当公历年'),('2019','错误跨越两年')],'周历年跨公历边界'),
 ('statistics.pstdev([4])','0.0',[('raises StatisticsError','把总体标准差当样本标准差'),('4.0','把单样本标准差当原值')],'单样本总体标准差'),
 ('fractions.Fraction("1.5").denominator','2',[('10','保留未约分的十进制分母'),('5','把小数位数字当分母'),('1','把小数解析成整数')],'字符串分数约分'),
]}

IMPORTS='import itertools, statistics, fractions, decimal, datetime, re, math, collections, bisect, heapq, functools, operator, json'

def materials():
 rows=[]
 for family,specs in SPECS.items():
  assert len(specs)==16
  for i,(expression,gold,candidates,rule) in enumerate(specs,1):
   rows.append({'id':f'holdout-{family}-{i:02d}','family':family,'rule':rule,
    'expression':expression,'imports':IMPORTS,'target_interpreter':'CPython 3.11.16',
    'question':'The interpreter is CPython 3.11.16. These modules have been imported:\n'+IMPORTS+'\n\nEvaluate this expression in a fresh process:\n\n'+expression+'\n\nWhat is its value, or which exception does evaluation raise? Explain briefly. On the final line give the value or the exception type.',
    'gold':gold,'gold_status':'待目标解释器执行核定','theta':None,
    'candidates':[{'answer':a,'misconception':m,'alpha':None,'alpha_stratum':None} for a,m in candidates],
    'answer_space':{'definition':'正常返回值的类型空间；不等于模型实际可达答案集合，也不把每道确定题的真值数1当答案空间大小。','normal_domain':'布尔' if gold in ['True','False'] else '待执行结果类型','normal_domain_size':2 if gold in ['True','False'] else None,'exception_answers_allowed':True,'proposed_wrong_candidates':len(candidates)},
    'model_contact':False})
 assert len(rows)==64 and len({r['expression'] for r in rows})==64
 return rows

def syntax_shape(expression):
 tree=ast.parse(expression,mode='eval')
 for node in ast.walk(tree):
  if isinstance(node,ast.Constant):node.value='<constant>'
 return ast.dump(tree,include_attributes=False)

def main():
 root=Path(__file__).resolve().parents[3]
 report=root/'docs/research/early-stage/internal8'
 old=json.loads((report/'program_semantic_v124/materials.json').read_text(encoding='utf-8'))
 rows=materials(); shapes={syntax_shape(r['expression']) for r in old}
 assert all(syntax_shape(r['expression']) not in shapes for r in rows), '不得复用开发题的常量替换变体'
 out=report/'program_semantic_holdout_v127'
 out.mkdir(exist_ok=True)
 target=out/'materials.json'
 if target.exists():
  raise RuntimeError('材料已存在；禁止重建覆盖已核定真值或后续标注。')
 target.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'items':len(rows),'families':dict(Counter(r['family'] for r in rows)),'candidates':sum(len(r['candidates']) for r in rows),'excluded_development_items':len(old),'model_contact':False},ensure_ascii=False))

if __name__=='__main__':main()
