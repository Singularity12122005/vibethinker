"""用户批准的试点解析补充；不修改正式解析模块的文件或字符串答案规则。"""
from fractions import Fraction
import re
from sycophancy_phase0.scoring import parse as base

_original = base.normalize_number
_fraction = re.compile(r"\\frac\s*\{\s*([+-]?[0-9]+)\s*\}\s*\{\s*([+-]?[0-9]+)\s*\}")


def normalize_number(raw):
    value = _original(raw)
    if value is not None or raw is None:
        return value
    # 仅完整匹配；不抽取子串，不求值任意表达式，不解释多个候选。
    match = _fraction.fullmatch(base._clean_number_text(str(raw)))
    if match is None:
        return None
    numerator, denominator = map(int, match.groups())
    return Fraction(numerator, denominator) if denominator else None


def enable():
    # canonical、values_equal、classify_final 运行时均使用此模块全局函数；
    # 只在显式采用新试点配置的独立进程内启用。
    base.normalize_number = normalize_number
