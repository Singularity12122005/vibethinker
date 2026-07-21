"""平台无关的教师蒸馏编排、重试与可恢复进度。"""

from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..common.io import write_json
from ..verification import VerificationRequest, Verifier, parse_think_protocol


@dataclass(frozen=True)
class TeacherRequest:
    request_id: str
    prompt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TeacherResponse:
    reasoning: str
    answer: str
    finish_reason: str = "stop"
    usage: Mapping[str, Any] = field(default_factory=dict)
    teacher: str = ""

    @property
    def training_target(self) -> str:
        return f"<think>\n{self.reasoning.strip()}\n</think>\n{self.answer.strip()}"


class TeacherClient(Protocol):
    """厂商 SDK、HTTP 或本地服务均通过该接口注入。"""

    def complete(self, request: TeacherRequest) -> TeacherResponse: ...


class RetryableTeacherError(RuntimeError):
    """表示限流、超时或临时服务失败。"""


class FatalTeacherError(RuntimeError):
    """表示认证、配置或请求合同错误，不应重试。"""


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 4
    initial_delay_s: float = 0.5
    maximum_delay_s: float = 8.0
    multiplier: float = 2.0
    jitter_s: float = 0.25

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be positive")
        if min(self.initial_delay_s, self.maximum_delay_s, self.jitter_s) < 0:
            raise ValueError("retry delays cannot be negative")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least one")


class RetryingTeacherClient:
    def __init__(
        self,
        client: TeacherClient,
        policy: RetryPolicy | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ):
        self._client = client
        self._policy = policy or RetryPolicy()
        self._sleep = sleep
        self._jitter = jitter

    def complete(self, request: TeacherRequest) -> TeacherResponse:
        delay = self._policy.initial_delay_s
        for attempt in range(1, self._policy.attempts + 1):
            try:
                return self._client.complete(request)
            except FatalTeacherError:
                raise
            except RetryableTeacherError:
                if attempt == self._policy.attempts:
                    raise
                self._sleep(delay + self._jitter(0.0, self._policy.jitter_s))
                delay = min(self._policy.maximum_delay_s, delay * self._policy.multiplier)
        raise AssertionError("unreachable retry state")


@dataclass(frozen=True)
class CandidateVerdict:
    accepted: bool
    score: float = 0.0
    reason: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)


class CandidateValidator(Protocol):
    def validate(self, request: TeacherRequest, response: TeacherResponse) -> CandidateVerdict: ...


class VerifierCandidateValidator:
    """把共享 verifier 适配为蒸馏候选 validator。"""

    def __init__(
        self,
        verifier: Verifier,
        *,
        domain: str,
        reference_key: str = "reference",
    ):
        self._verifier = verifier
        self._domain = domain
        self._reference_key = reference_key

    def validate(self, request: TeacherRequest, response: TeacherResponse) -> CandidateVerdict:
        if response.finish_reason != "stop":
            return CandidateVerdict(False, reason=f"finish_{response.finish_reason or 'missing'}")
        if parse_think_protocol(response.training_target) is None:
            return CandidateVerdict(False, reason="invalid_native_channels")
        result = self._verifier.verify(
            VerificationRequest(
                domain=self._domain,
                candidate=response.training_target,
                reference=request.metadata.get(self._reference_key),
                metadata=request.metadata,
            )
        )
        return CandidateVerdict(
            result.passed,
            result.score,
            result.reason,
            {"verifier": result.verifier, **result.details},
        )


@dataclass(frozen=True)
class DistillationConfig:
    max_workers: int = 8
    candidate_rounds: int = 2

    def __post_init__(self) -> None:
        if self.max_workers < 1 or self.candidate_rounds < 1:
            raise ValueError("max_workers and candidate_rounds must be positive")


class JsonProgressStore:
    """单文件原子进度账本；完成一条即替换，不依赖追加写修复。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("version") != 1 or not isinstance(value.get("results"), dict):
            raise ValueError(f"unsupported progress format: {self.path}")
        return dict(value["results"])

    def save_result(
        self,
        results: dict[str, dict[str, Any]],
        request_id: str,
        result: dict[str, Any],
    ) -> None:
        with self._lock:
            results[request_id] = result
            write_json(self.path, {"version": 1, "results": results})


class DistillationRunner:
    """并发处理样本，并在两个或更多教师候选间确定性择优。"""

    def __init__(
        self,
        teachers: Iterable[TeacherClient],
        validator: CandidateValidator,
        progress: JsonProgressStore,
        config: DistillationConfig | None = None,
    ):
        self._teachers = tuple(teachers)
        if len(self._teachers) < 2:
            raise ValueError("at least two teachers are required for candidate selection")
        self._validator = validator
        self._progress = progress
        self._config = config or DistillationConfig()

    def _process(self, request: TeacherRequest) -> dict[str, Any]:
        failures: list[str] = []
        for round_number in range(1, self._config.candidate_rounds + 1):
            accepted: list[tuple[float, int, TeacherResponse, CandidateVerdict]] = []
            for teacher_index, teacher in enumerate(self._teachers):
                try:
                    response = teacher.complete(request)
                    verdict = self._validator.validate(request, response)
                except FatalTeacherError:
                    raise
                except Exception as exc:
                    failures.append(f"teacher_{teacher_index}:{type(exc).__name__}")
                    continue
                if verdict.accepted:
                    accepted.append((verdict.score, -teacher_index, response, verdict))
                else:
                    failures.append(verdict.reason or f"teacher_{teacher_index}:rejected")
            if accepted:
                _, _, response, verdict = max(accepted, key=lambda item: (item[0], item[1]))
                return {
                    "status": "accepted",
                    "request_id": request.request_id,
                    "prompt": request.prompt,
                    "target": response.training_target,
                    "teacher": response.teacher,
                    "finish_reason": response.finish_reason,
                    "usage": dict(response.usage),
                    "verification": {
                        "score": verdict.score,
                        "reason": verdict.reason,
                        "details": dict(verdict.details),
                    },
                    "round": round_number,
                }
        return {
            "status": "rejected",
            "request_id": request.request_id,
            "reasons": failures,
            "rounds": self._config.candidate_rounds,
        }

    def run(self, requests: Iterable[TeacherRequest]) -> dict[str, dict[str, Any]]:
        materialized = list(requests)
        identifiers = [request.request_id for request in materialized]
        if any(not identity for identity in identifiers) or len(set(identifiers)) != len(
            identifiers
        ):
            raise ValueError("request_id values must be non-empty and unique")
        results = self._progress.load()
        pending = [request for request in materialized if request.request_id not in results]
        with ThreadPoolExecutor(max_workers=self._config.max_workers) as pool:
            futures = {pool.submit(self._process, request): request for request in pending}
            for future in as_completed(futures):
                request = futures[future]
                try:
                    result = future.result()
                except FatalTeacherError:
                    raise
                except Exception as exc:
                    result = {
                        "status": "rejected",
                        "request_id": request.request_id,
                        "reasons": [f"worker:{type(exc).__name__}"],
                    }
                self._progress.save_result(results, request.request_id, result)
        return results


def progress_as_rows(results: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """按 request_id 稳定导出已接受结果，供 JSONL 写出层使用。"""
    return [
        dict(results[request_id])
        for request_id in sorted(results)
        if results[request_id].get("status") == "accepted"
    ]
