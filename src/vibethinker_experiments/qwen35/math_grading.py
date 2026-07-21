"""Offline answer normalization and equivalence checks for math RL.

The implementation keeps the public grading ABI in a qualified package namespace.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction

try:
    import sympy
    from sympy.parsing import sympy_parser
except ImportError:  # CPU protocol tests do not require the optional symbolic path.
    sympy = None
    sympy_parser = None


def _balanced_command(text: str, command: str) -> str | None:
    start = text.rfind(command)
    if start < 0:
        return None
    left = text.find("{", start + len(command))
    if left < 0:
        return None
    depth = 0
    for index in range(left, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[left + 1 : index]
    return None


def extract_answer(passage: str) -> str | None:
    if "<|begin_of_box|>" in passage and "<|end_of_box|>" in passage:
        matches = re.findall(r"<\|begin_of_box\|>([\s\S]*?)<\|end_of_box\|>", passage)
        return matches[-1].strip() if matches else None
    for command in ("\\boxed", "\\fbox"):
        value = _balanced_command(passage, command)
        if value is not None:
            return value
    return None


def _strip_latex(value: str) -> str:
    value = value.replace("\\left", "").replace("\\right", "")
    value = value.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    value = value.replace("\\%", "%").replace("\\$", "$")
    value = re.sub(r"\\text\{([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\mathrm\{([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", value)
    value = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", value)
    return value


_UNIT_RE = re.compile(
    r"(?i)\b(?:degrees?|cm|centimeters?|meters?|miles?|seconds?|minutes?|hours?|"
    r"days?|weeks?|months?|years?|feet|foot|inches?|yards?|roses?|trucks?|"
    r"flagstones?|arrangements?|matches?)\b"
)


def normalize_answer(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _strip_latex(str(value)).strip().strip("`*_ ")
    normalized = normalized.rstrip(".。;,，")
    normalized = normalized.replace(",", "").replace("$", "")
    normalized = _UNIT_RE.sub("", normalized)
    normalized = normalized.replace(" ", "")
    normalized = normalized.lower()
    if normalized.endswith("%"):
        normalized = normalized[:-1]
    if len(normalized) > 1 and normalized[0] == "{" and normalized[-1] == "}":
        normalized = normalized[1:-1]
    if re.fullmatch(r"[-+]?\d+\.0+", normalized):
        normalized = str(int(float(normalized)))
    return normalized


def mathd_normalize_answer(answer: str | None) -> str | None:
    return normalize_answer(answer)


def grade_answer_mathd(given_answer: str, ground_truth: str) -> bool:
    return normalize_answer(given_answer) == normalize_answer(ground_truth)


def _numeric(value: str) -> Fraction | float | None:
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        try:
            return float(value)
        except ValueError:
            return None


def _safe_sympy(value: str):
    if sympy is None or sympy_parser is None:
        return None
    if len(value) > 500 or len(set(re.findall(r"[A-Za-z]+", value))) > 2:
        return None
    value = value.replace("^", "**")
    return sympy_parser.parse_expr(
        value,
        transformations=(
            sympy_parser.standard_transformations
            + (sympy_parser.implicit_multiplication_application,)
        ),
    )


def grade_answer_sympy(given_answer: str, ground_truth: str) -> bool:
    given = normalize_answer(given_answer)
    expected = normalize_answer(ground_truth)
    if given is None or expected is None or not given:
        return False
    if given == expected:
        return True
    given_number, expected_number = _numeric(given), _numeric(expected)
    if given_number is not None and expected_number is not None:
        return math.isclose(float(given_number), float(expected_number), rel_tol=1e-9, abs_tol=1e-9)
    try:
        given_expr, expected_expr = _safe_sympy(given), _safe_sympy(expected)
        return bool(
            given_expr is not None
            and expected_expr is not None
            and sympy.simplify(given_expr - expected_expr) == 0
        )
    except Exception:
        return False


def grade_answer_verl(solution_str: str, ground_truth: str) -> bool:
    if not ground_truth:
        return False
    expected = extract_answer(ground_truth) or ground_truth
    given = extract_answer(solution_str)
    return bool(
        given and (grade_answer_mathd(given, expected) or grade_answer_sympy(given, expected))
    )
