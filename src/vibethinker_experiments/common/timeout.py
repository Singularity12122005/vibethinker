"""对可能挂起的纯 Python 评分函数施加硬超时。"""

from __future__ import annotations

import multiprocessing as mp
import queue
import signal
import threading
from collections.abc import Callable
from typing import Any


def _worker(result_queue: Any, fn: Callable[..., Any], args: tuple[Any, ...]) -> None:
    try:
        result_queue.put((True, fn(*args)))
    except BaseException:
        result_queue.put((False, False))


def _process_call(fn: Callable[..., Any], args: tuple[Any, ...], timeout_s: float) -> Any:
    context = mp.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_worker, args=(result_queue, fn, args), daemon=True)
    process.start()
    process.join(timeout_s)
    if process.is_alive():
        process.terminate()
        process.join(1.0)
        return False
    try:
        ok, value = result_queue.get_nowait()
    except queue.Empty:
        return False
    return value if ok else False


def call_with_timeout(
    fn: Callable[..., Any], *args: Any, timeout_s: float = 5.0, fallback: Any = False
) -> Any:
    """主线程在 POSIX 使用 SIGALRM，其余场景使用 spawn 子进程。

    超时和被调用函数异常统一返回 ``fallback``，适合 verifier 边界。
    """
    if timeout_s <= 0:
        try:
            return fn(*args)
        except Exception:
            return fallback
    if threading.current_thread() is threading.main_thread() and hasattr(signal, "SIGALRM"):
        previous = signal.getsignal(signal.SIGALRM)

        def handler(signum: int, frame: Any) -> None:  # noqa: ARG001
            raise TimeoutError("call timed out")

        try:
            signal.signal(signal.SIGALRM, handler)
            signal.setitimer(signal.ITIMER_REAL, timeout_s)
            return fn(*args)
        except Exception:
            return fallback
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    result = _process_call(fn, args, timeout_s)
    return fallback if result is False and fallback is not False else result
