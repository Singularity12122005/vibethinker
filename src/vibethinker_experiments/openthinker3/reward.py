"""VERL reward ABI around a separately installed Skywork verifier."""

from __future__ import annotations

import json
import os
import signal
import threading
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from multiprocessing import get_context

from .verifier import SkyworkVerifier, load_verifier

_executor: ProcessPoolExecutor | None = None
_executor_lock = threading.Lock()

FORMAL_RUNTIME_ENV = {
    "VT_FORMAL_RUNTIME": "1",
    "VT_REWARD_WORKERS": "16",
    "VT_VERIFIER_TIMEOUT_SECONDS": "330",
    "VT_CODE_CASE_TIMEOUT_SECONDS": "6",
}


def validate_formal_runtime(environment: dict[str, str] | None = None) -> None:
    values = os.environ if environment is None else environment
    mismatches = {
        key: {"expected": expected, "actual": values.get(key)}
        for key, expected in FORMAL_RUNTIME_ENV.items()
        if values.get(key) != expected
    }
    if mismatches:
        raise RuntimeError(f"formal reward runtime environment mismatch: {mismatches}")


class _VerifierTimeout(Exception):
    pass


def score_one(
    solution: str,
    ground_truth: object,
    data_source: str,
    *,
    verifier: SkyworkVerifier | None = None,
) -> dict[str, object]:
    """Score one completion and separate wrong answers from verifier failures."""

    def timeout_handler(_signum, _frame):
        raise _VerifierTimeout("verifier timeout")

    previous = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(int(os.environ.get("VT_VERIFIER_TIMEOUT_SECONDS", "30")))
    try:
        if isinstance(ground_truth, str):
            ground_truth = json.loads(ground_truth)
        scorer = verifier or load_verifier()
        score, metadata = scorer(
            solution,
            ground_truth,
            task=data_source,
            timeout=int(os.environ.get("VT_CODE_CASE_TIMEOUT_SECONDS", "6")),
            is_binary_reward=True,
        )
        details = metadata if isinstance(metadata, dict) else {}
        return {
            "score": float(bool(score)),
            "acc": float(bool(score)),
            "verifier_ok": bool(details.get("verifier_ok", True)),
            "verifier_error": str(details.get("verifier_error", ""))[:2000],
        }
    except _VerifierTimeout as exc:
        return {
            "score": 0.0,
            "acc": 0.0,
            "verifier_ok": False,
            "verifier_error": f"timeout: {exc}",
        }
    except BaseException as exc:
        return {
            "score": 0.0,
            "acc": 0.0,
            "verifier_ok": False,
            "verifier_error": f"{type(exc).__name__}: {exc}"[:2000],
        }
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _get_executor() -> ProcessPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ProcessPoolExecutor(
                max_workers=int(os.environ.get("VT_REWARD_WORKERS", "16")),
                mp_context=get_context("spawn"),
            )
    return _executor


def compute_score(data_source, solution_str, ground_truth, extra_info=None, **_kwargs):
    """VERL's single-sample reward ABI backed by a persistent process pool."""

    del extra_info
    validate_formal_runtime()
    timeout = int(os.environ["VT_VERIFIER_TIMEOUT_SECONDS"]) + 5
    future = _get_executor().submit(score_one, solution_str, ground_truth, str(data_source))
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        return {
            "score": 0.0,
            "acc": 0.0,
            "verifier_ok": False,
            "verifier_error": f"verifier process timeout after {timeout}s",
        }
    except BaseException as exc:
        return {
            "score": 0.0,
            "acc": 0.0,
            "verifier_ok": False,
            "verifier_error": f"worker {type(exc).__name__}: {exc}"[:2000],
        }
