"""Transport-injected generation worker; this module never handles API keys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .io import canonical_json, sha256_bytes
from .models import EvaluationProfile


@dataclass(frozen=True)
class GenerationRequest:
    panel_id: str
    messages: tuple[dict[str, str], ...]
    context_tokens: int
    generation_cap_tokens: int
    temperature: float
    top_p: float
    seed: int


@dataclass(frozen=True)
class GenerationResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str


class GenerationTransport(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...


class NetworkDisabledGenerationTransport:
    """Safe test/default transport that cannot perform external I/O."""

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise RuntimeError(
            "generation transport is not configured; inject a local or explicitly "
            "approved transport"
        )


def build_generation_result(
    panel_row: dict[str, Any],
    *,
    profile: EvaluationProfile,
    panel_sha256: str,
    transport: GenerationTransport,
) -> dict[str, Any]:
    messages = tuple(
        {"role": str(message["role"]), "content": str(message["content"])}
        for message in panel_row["messages"]
    )
    request = GenerationRequest(
        panel_id=str(panel_row["panel_id"]),
        messages=messages,
        context_tokens=profile.context_tokens,
        generation_cap_tokens=profile.generation_cap_tokens,
        temperature=profile.temperature,
        top_p=profile.top_p,
        seed=profile.seed,
    )
    response = transport.generate(request)
    if response.prompt_tokens < 0 or response.completion_tokens < 0:
        raise ValueError("transport returned negative token counts")
    if response.completion_tokens > profile.generation_cap_tokens:
        raise ValueError("transport response exceeds explicit generation cap")
    if response.prompt_tokens + response.completion_tokens > profile.context_tokens:
        raise ValueError("transport response exceeds explicit profile context")
    identity = {
        "panel_id": panel_row["panel_id"],
        "panel_sha256": panel_sha256,
        "raw_completion": response.text,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "finish_reason": response.finish_reason,
        "profile_id": profile.profile_id,
    }
    return {
        **identity,
        "domain": panel_row["domain"],
        "generation_sha256": sha256_bytes(canonical_json(identity).encode()),
    }
