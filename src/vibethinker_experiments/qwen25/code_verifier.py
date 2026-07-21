"""隔离环境内使用的 Python harness runner；它不是安全沙箱。"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys

CPU_SECONDS = 8
MEMORY_BYTES = 1024 * 1024 * 1024

_RUNNER = r"""import base64,json,sys
payload=json.loads(sys.stdin.read())
namespace={"__name__":"candidate"}
exec(base64.b64decode(payload["code"]).decode(),namespace)
exec(base64.b64decode(payload["harness"]).decode(),namespace)
namespace["check"](eval(payload["entry_point"],namespace))
"""


def _limit_resources() -> None:
    try:
        import resource
    except ImportError:
        return
    for kind, value in (
        (resource.RLIMIT_CPU, CPU_SECONDS),
        (getattr(resource, "RLIMIT_AS", None), MEMORY_BYTES),
    ):
        if kind is None:
            continue
        try:
            resource.setrlimit(kind, (value, value))
        except (OSError, ValueError):
            pass


def run_test_harness(
    code: str,
    harness: str,
    entry_point: str,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess[str]:
    """在 `python -I` 子进程运行；调用方仍须提供禁网/最小权限容器。"""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    payload = {
        "code": base64.b64encode(code.encode()).decode(),
        "harness": base64.b64encode(harness.encode()).decode(),
        "entry_point": entry_point,
    }
    return subprocess.run(
        [sys.executable, "-I", "-c", _RUNNER],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        preexec_fn=_limit_resources if os.name == "posix" else None,
        check=False,
    )
