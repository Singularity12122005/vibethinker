"""Optional graders that are intentionally outside the pure scoring core."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

UNSAFE_CODE_GRADER_WARNING = (
    "This subprocess grader is NOT a security sandbox. It must only execute trusted "
    "synthetic or internally reviewed code; do not use it for untrusted model output."
)


def _extract_python(answer: str) -> str:
    match = re.search(r"```(?:python)?\s*([\s\S]*?)```", answer, flags=re.IGNORECASE)
    return match.group(1).strip() if match else answer.strip()


def unsafe_python_assert_grader(
    answer: str, grading: dict[str, Any]
) -> tuple[float, dict[str, Any]]:
    """Run trusted Python assertions.

    SECURITY: subprocess timeouts and temporary directories are resource controls,
    not isolation. This function is deliberately opt-in and is not a safe sandbox.
    """

    tests = grading.get("tests")
    if not isinstance(tests, list) or not tests:
        return 0.0, {"reason": "bad_tests", "security_warning": UNSAFE_CODE_GRADER_WARNING}
    source = "\n".join([_extract_python(answer), *(str(test) for test in tests)])
    with tempfile.TemporaryDirectory(prefix="evaluation-code-") as directory:
        script = Path(directory) / "candidate.py"
        script.write_text(source)
        try:
            process = subprocess.run(
                [sys.executable, "-I", str(script)],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=float(grading.get("timeout_seconds", 2)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return 0.0, {
                "reason": "timeout",
                "security_warning": UNSAFE_CODE_GRADER_WARNING,
            }
    passed = process.returncode == 0
    return float(passed), {
        "reason": "ok" if passed else "failed",
        "returncode": process.returncode,
        "security_warning": UNSAFE_CODE_GRADER_WARNING,
    }
