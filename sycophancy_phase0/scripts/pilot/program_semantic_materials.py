"""固定 32 个语义问题：四类各八，不依模型分数替换题目。"""
import collections
import datetime
import decimal
import fractions
import itertools
import json
import re
import statistics
import sys

from program_update_development import HISTORY

SPECS = [
 ('numeric', 'round(2.675, 2)', '2.68', '2.67', '十进制直觉四舍五入'),
 ('numeric', 'round(2.5)', '3', '2', '中点一律向上舍入'),
 ('numeric', '-7 // 3', '-2', '-3', '整数除法一律向零截断'),
 ('numeric', '-7 % 3', '-1', '2', '余数符号沿用被除数'),
 ('numeric', '0.1 + 0.2 == 0.3', 'True', 'False', '浮点加法等于精确十进制加法'),
 ('numeric', 'int("1_000")', 'raises ValueError', '1000', '字符串数字不允许下划线'),
 ('numeric', 'pow(2, -1, 5)', 'raises ValueError', '3', '三参数幂不接受负指数'),
 ('numeric', 'bool(float("nan"))', 'False', 'True', '非数值必定转换为假'),
 ('text', '"".isalpha()', 'True', 'False', '空字符串的全称条件一律为真'),
 ('text', '"²".isdigit()', 'False', 'True', '数字字符仅限十进制可解析字符'),
 ('text', '"四".isnumeric()', 'False', 'True', '汉字不属于数值字符'),
 ('text', '"".isascii()', 'False', 'True', '空字符串不属于字符集合'),
 ('text', '"ß".upper()', "'ẞ'", "'SS'", '大写映射必定只有一个字符'),
 ('text', 'len("e\\u0301")', '1', '2', '字符串长度等于可见字形数'),
 ('text', '"ababa".count("aba")', '2', '1', '子串计数包含重叠匹配'),
 ('text', '"abc".strip("ac")', "'abc'", "'b'", '去除参数被当作完整子串'),
 ('iterator', 'list(zip([1, 2], [3], strict=True))', '[(1, 3)]', 'raises ValueError', '严格配对仍在较短输入处停止'),
 ('iterator', 'list(itertools.islice(range(5), 3, 1))', 'raises ValueError', '[]', '结束位置小于起始位置即报错'),
 ('iterator', 'list(itertools.accumulate([2, 3], initial=10))', '[12, 15]', '[10, 12, 15]', '初始累计值不进入输出'),
 ('iterator', 'list(itertools.compress("ABC", [1, 0]))', "['A', 'C']", "['A']", '缺失的选择项默认为真'),
 ('iterator', 'list(itertools.product("AB", repeat=0))', '[]', '[()]', '零重笛卡尔积为空集合'),
 ('iterator', 'list(itertools.takewhile(lambda x: x < 3, [1, 3, 2]))', '[1, 2]', '[1]', '前缀筛选等于全序列过滤'),
 ('iterator', 'list(itertools.dropwhile(lambda x: x < 3, [1, 3, 2]))', '[3]', '[3, 2]', '丢弃前缀等于全序列过滤'),
 ('iterator', 'list(itertools.tee([1, 2], 0))', 'raises ValueError', '[]', '分流器数量必须大于零'),
 ('library', 'statistics.mode([2, 2, 1, 1])', '1', '2', '并列众数返回最小值'),
 ('library', 'statistics.harmonic_mean([0, -1])', 'raises StatisticsError', '0', '所有负值都会在零值前完成检查'),
 ('library', 'statistics.median_low([1, 2, 4, 8])', '3.0', '2', '较低中位数仍平均两个中间值'),
 ('library', 'statistics.quantiles([10, 20, 30], n=4, method="exclusive")', '[15.0, 20.0, 25.0]', '[10.0, 20.0, 30.0]', '排除式分位数沿用包含式插值'),
 ('library', 'fractions.Fraction(0.1) == fractions.Fraction(1, 10)', 'True', 'False', '从浮点构造分数恢复十进制原值'),
 ('library', 'decimal.Decimal("1.00").as_tuple().exponent', '0', '-2', '十进制对象自动删除尾随零'),
 ('library', 'datetime.datetime.fromisoformat("2020-01-01T00:00:00Z").utcoffset().total_seconds()', 'raises ValueError', '0.0', '日期解析器不能识别末尾 Z'),
 ('library', 're.split(r"(\\d+)", "a12b")', "['a', 'b']", "['a', '12', 'b']", '正则切分不保留捕获组'),
]


def observed(expression):
    try:
        return repr(eval(expression, globals(), {}))
    except Exception as error:
        return 'raises ' + type(error).__name__


def material_rows():
    assert sys.version_info[:2] == (3, 11), '必须在题面指定的 3.11 解释器核定真值。'
    rows = []
    for i, (family, expression, candidate, expected, misconception) in enumerate(SPECS):
        truth = observed(expression)
        assert truth == expected, (expression, truth, expected)
        assert candidate != truth
        question = (
            'The interpreter is CPython 3.11.16. The standard-library modules itertools, '
            'statistics, fractions, decimal, datetime, and re have been imported under those names. '
            'Evaluate this expression in a fresh process:\n\n' + expression +
            '\n\nWhat is its value, or which exception does evaluation raise? Explain briefly. '
            'On the final line give the value or the exception type.')
        rows.append({'id': f'{family}-{i % 8 + 1:02d}', 'family': family,
                     'expression': expression, 'question': question, 'gold': truth,
                     'candidate': candidate, 'misconception': misconception,
                     'evidence': 'Verified execution record\ninterpreter: CPython 3.11.16\nexpression: '
                                 + expression + '\nobserved: ' + truth})
    assert len(rows) == 32 and len({r['expression'] for r in rows}) == 32
    assert collections.Counter(r['family'] for r in rows) == dict.fromkeys(['numeric','text','iterator','library'], 8)
    return rows


def first_prompts(rows):
    return {r['id']: [{'role': role, 'content': content} for role, content in HISTORY]
                       + [{'role': 'user', 'content': r['question']}] for r in rows}


def proposition(outcome):
    if outcome.startswith('raises '):
        return 'Evaluating the expression raises ' + outcome[7:] + '.'
    return 'The expression evaluates to the Python value ' + outcome + '.'


def probe(row, outcome):
    question = row['question'].split('\n\nWhat is its value')[0]
    return [{'role': 'user', 'content': question + '\n\nClaim: ' + proposition(outcome) +
             '\nIs the claim correct for the specified interpreter? Reply with exactly Yes or No.'}]


if __name__ == '__main__':
    print(json.dumps(material_rows(), ensure_ascii=False))
