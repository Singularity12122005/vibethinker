"""统一、可注入的候选验证接口。

代码验证只负责编排一个外部 ``CodeRunner``。即使使用本模块提供的子进程
runner，也必须由调用方保证它运行在容器、虚拟机等隔离环境中；资源限制和
``python -I`` 不是 hardened sandbox。
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, Union

THINK_PROTOCOL = re.compile(
    r"^\s*<think>\s*(?P<reasoning>[\s\S]+?)\s*</think>\s*(?P<answer>[\s\S]+?)\s*$",
    re.IGNORECASE,
)
ANY_PROTOCOL_TAG = re.compile(r"</?(?:think|answer)>", re.IGNORECASE)
CODE_FENCE = re.compile(r"```(?:python)?\s*(?P<code>[\s\S]*?)```", re.IGNORECASE)


@dataclass(frozen=True)
class VerificationRequest:
    domain: str
    candidate: str
    reference: object | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    verifier: str
    reason: str = ""
    score: float = 0.0
    details: Mapping[str, Any] = field(default_factory=dict)


class Verifier(Protocol):
    def verify(self, request: VerificationRequest) -> VerificationResult: ...


def parse_think_protocol(text: str) -> tuple[str, str] | None:
    """解析一个且仅一个 think 块，返回 reasoning 与可见答案。"""
    match = THINK_PROTOCOL.fullmatch(text)
    if match is None:
        return None
    reasoning = match.group("reasoning").strip()
    answer = match.group("answer").strip()
    if (
        not reasoning
        or not answer
        or ANY_PROTOCOL_TAG.search(reasoning)
        or ANY_PROTOCOL_TAG.search(answer)
    ):
        return None
    return reasoning, answer


class ProtocolVerifier:
    def verify(self, request: VerificationRequest) -> VerificationResult:
        parsed = parse_think_protocol(request.candidate)
        return VerificationResult(
            passed=parsed is not None,
            verifier="think_protocol",
            reason="" if parsed is not None else "invalid_think_protocol",
            score=1.0 if parsed is not None else 0.0,
            details={} if parsed is None else {"answer": parsed[1]},
        )


MathComparator = Callable[[str, object], Union[bool, float]]  # noqa: UP007


def _default_math_comparator(candidate: str, reference: object) -> bool:
    """保守的数值/规范化文本比较；复杂数学等价性应注入专用 comparator。"""
    left, right = candidate.strip(), str(reference).strip()
    try:
        left_number, right_number = Decimal(left), Decimal(right)
    except InvalidOperation:
        return " ".join(left.split()).casefold() == " ".join(right.split()).casefold()
    return math.isclose(float(left_number), float(right_number), rel_tol=1e-12, abs_tol=1e-12)


class MathVerifier:
    def __init__(self, comparator: MathComparator = _default_math_comparator):
        self._comparator = comparator

    def verify(self, request: VerificationRequest) -> VerificationResult:
        candidate = parse_think_protocol(request.candidate)
        answer = candidate[1] if candidate is not None else request.candidate
        try:
            compared = self._comparator(answer, request.reference)
            score = float(compared)
        except Exception as exc:  # verifier plugins are an explicit failure boundary
            return VerificationResult(
                False,
                "math",
                "comparator_error",
                details={"error_type": type(exc).__name__},
            )
        passed = score >= 1.0
        return VerificationResult(passed, "math", "" if passed else "not_equivalent", score)


@dataclass(frozen=True)
class ExecutionResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class CodeRunner(Protocol):
    """在调用方提供的隔离边界内执行代码的 adapter。"""

    def run(self, code: str, stdin: str, timeout_s: float) -> ExecutionResult: ...


class IsolatedPythonSubprocessRunner:
    """轻量执行器，不是 sandbox；仅允许在外部隔离环境中显式启用。"""

    def __init__(self, *, isolated_environment: bool):
        if not isolated_environment:
            raise ValueError(
                "candidate code execution requires an externally isolated environment; "
                "this runner is not a hardened sandbox"
            )

    def run(self, code: str, stdin: str, timeout_s: float) -> ExecutionResult:
        try:
            process = subprocess.run(
                [sys.executable, "-I", "-c", code],
                input=stdin,
                text=True,
                capture_output=True,
                timeout=timeout_s,
                env={"PATH": os.environ.get("PATH", "")},
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                -1,
                str(exc.stdout or ""),
                str(exc.stderr or ""),
                timed_out=True,
            )
        return ExecutionResult(process.returncode, process.stdout, process.stderr)


def extract_python_code(candidate: str) -> str:
    parsed = parse_think_protocol(candidate)
    visible = parsed[1] if parsed is not None else candidate
    match = CODE_FENCE.search(visible)
    return (match.group("code") if match else visible).strip()


class CodeVerifier:
    def __init__(self, runner: CodeRunner, *, timeout_s: float = 8.0):
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._runner = runner
        self._timeout_s = timeout_s

    def verify(self, request: VerificationRequest) -> VerificationResult:
        code = extract_python_code(request.candidate)
        inputs = request.metadata.get("inputs")
        outputs = request.metadata.get("outputs")
        if (
            not code
            or not isinstance(inputs, Sequence)
            or isinstance(inputs, (str, bytes))
            or not isinstance(outputs, Sequence)
            or isinstance(outputs, (str, bytes))
            or not inputs
            or len(inputs) != len(outputs)
        ):
            return VerificationResult(False, "code", "invalid_code_test_contract")
        for index, (stdin, expected) in enumerate(zip(inputs, outputs)):  # noqa: B905
            result = self._runner.run(str(code), str(stdin), self._timeout_s)
            if result.timed_out:
                return VerificationResult(False, "code", "timeout", details={"case": index})
            if result.returncode != 0 or result.stdout.strip() != str(expected).strip():
                return VerificationResult(
                    False,
                    "code",
                    "case_failed",
                    details={"case": index, "returncode": result.returncode},
                )
        return VerificationResult(
            True,
            "code",
            score=1.0,
            details={"passed_cases": len(inputs)},
        )


class DomainVerifier:
    """按 domain 路由，并可先统一检查输出协议。"""

    def __init__(
        self,
        verifiers: Mapping[str, Verifier],
        *,
        require_protocol: bool = True,
    ):
        self._verifiers = dict(verifiers)
        self._require_protocol = require_protocol
        self._protocol = ProtocolVerifier()

    def verify(self, request: VerificationRequest) -> VerificationResult:
        if self._require_protocol:
            protocol = self._protocol.verify(request)
            if not protocol.passed:
                return protocol
        verifier = self._verifiers.get(request.domain)
        if verifier is None:
            return VerificationResult(False, "domain_router", "unsupported_domain")
        return verifier.verify(request)
