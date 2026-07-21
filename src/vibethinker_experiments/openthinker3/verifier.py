"""License-safe adapter boundary for the external Skywork verifier."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from collections.abc import Callable
from typing import Any, Protocol


class SkyworkVerifier(Protocol):
    def __call__(
        self,
        solution: str,
        ground_truth: object,
        *,
        task: str,
        timeout: int,
        is_binary_reward: bool,
    ) -> tuple[object, object]: ...


def load_verifier(spec: str | None = None) -> SkyworkVerifier:
    """Load ``module:callable`` without vendoring the third-party implementation."""

    resolved = spec or os.environ.get("VT_SKYWORK_VERIFIER")
    if not resolved or ":" not in resolved:
        raise RuntimeError(
            "VT_SKYWORK_VERIFIER must name a separately installed, license-reviewed "
            "callable as 'module:callable'"
        )
    module_name, attribute = resolved.split(":", 1)
    candidate: Any = importlib.import_module(module_name)
    for component in attribute.split("."):
        candidate = getattr(candidate, component)
    if not isinstance(candidate, Callable):
        raise TypeError(f"configured verifier is not callable: {resolved}")
    return candidate


def smoke_test_verifier(spec: str | None = None) -> dict[str, str]:
    verifier = load_verifier(spec)
    result = verifier(
        "<think>synthetic ABI smoke test</think>\n0",
        "0",
        task="math",
        timeout=5,
        is_binary_reward=True,
    )
    if not isinstance(result, tuple) or len(result) != 2:
        raise TypeError("Skywork verifier must return a two-item tuple")
    return {"status": "ok", "result_type": type(result[0]).__name__}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true", required=True)
    args = parser.parse_args()
    if args.smoke_test:
        print(json.dumps(smoke_test_verifier(), sort_keys=True))


if __name__ == "__main__":
    main()
