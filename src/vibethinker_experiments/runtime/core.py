"""确定性 runtime manifest 和长上下文探针的纯逻辑。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from ..common.hashing import sha256_text
from ..common.io import write_json
from ..persistence import build_artifact_manifest, canonical_json


def build_bundle_manifest(
    root: str | Path,
    files: Sequence[str | Path],
    *,
    configuration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """只描述现有文件；不复制模型、不归档 runtime、不 vendoring 依赖。"""
    artifacts = build_artifact_manifest(root, files)
    identity = {
        "format_version": 1,
        "files": artifacts["files"],
        "configuration": dict(configuration or {}),
    }
    return {**identity, "bundle_sha256": sha256_text(canonical_json(identity))}


def write_bundle_manifest(
    path: str | Path,
    root: str | Path,
    files: Sequence[str | Path],
    *,
    configuration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = build_bundle_manifest(root, files, configuration=configuration)
    write_json(path, manifest)
    return manifest


class TokenizerLike(Protocol):
    def encode(self, text: str, *, add_special_tokens: bool = False) -> Sequence[int]: ...

    def apply_chat_template(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str: ...


@dataclass(frozen=True)
class ContextProbeConfig:
    max_context_tokens: int = 65_536
    target_prompt_tokens: int = 60_000
    max_output_tokens: int = 128
    needle_positions: tuple[int, ...] = (8_000, 36_000, 52_000)
    filler: str = " Archive line: routine catalog material without the requested passkey."
    instruction: str = (
        "Read the complete archive. One line contains an important passkey. "
        "At the end, return that exact passkey.\n"
    )
    question: str = "\nWhat is the important passkey? Return the exact passkey."

    def __post_init__(self) -> None:
        if self.max_context_tokens < 1 or self.target_prompt_tokens < 1:
            raise ValueError("context and prompt lengths must be positive")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        if self.target_prompt_tokens + self.max_output_tokens > self.max_context_tokens:
            raise ValueError("target prompt plus output cap exceeds context window")
        invalid_positions = (
            position < 0 or position >= self.target_prompt_tokens
            for position in self.needle_positions
        )
        if any(invalid_positions):
            raise ValueError("needle positions must fall inside the target prompt")
        if not self.filler:
            raise ValueError("filler cannot be empty")


@dataclass(frozen=True)
class ProbeCase:
    name: str
    key: str
    prompt: str
    prompt_tokens: int
    needle_token: int | None


def _render(tokenizer: TokenizerLike, text: str) -> str:
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": text}],
        tokenize=False,
        add_generation_prompt=True,
    )


def _tokens(tokenizer: TokenizerLike, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def _long_case(
    tokenizer: TokenizerLike,
    config: ContextProbeConfig,
    *,
    name: str,
    key: str,
    needle_token: int,
) -> ProbeCase:
    needle = f"\nIMPORTANT PASSKEY: {key}\n"
    filler_tokens = _tokens(tokenizer, config.filler)
    if filler_tokens < 1:
        raise ValueError("filler tokenization is empty")
    fixed = _render(tokenizer, config.instruction + needle + config.question)
    units_total = max(0, (config.target_prompt_tokens - _tokens(tokenizer, fixed)) // filler_tokens)
    units_before = min(units_total, max(0, needle_token // filler_tokens))
    user_text = (
        config.instruction
        + config.filler * units_before
        + needle
        + config.filler * (units_total - units_before)
        + config.question
    )
    prompt = _render(tokenizer, user_text)
    prompt_tokens = _tokens(tokenizer, prompt)
    if prompt_tokens > config.target_prompt_tokens:
        raise ValueError("constructed probe exceeds target prompt length")
    prefix = _render(tokenizer, config.instruction + config.filler * units_before)
    return ProbeCase(name, key, prompt, prompt_tokens, _tokens(tokenizer, prefix))


def build_context_probe_cases(
    tokenizer: TokenizerLike,
    config: ContextProbeConfig | None = None,
) -> list[ProbeCase]:
    config = config or ContextProbeConfig()
    short_key = "PROBE-SHORT-CONTROL"
    short_prompt = _render(
        tokenizer,
        f"The important passkey is {short_key}. Return the exact passkey.",
    )
    cases = [
        ProbeCase(
            "short_control",
            short_key,
            short_prompt,
            _tokens(tokenizer, short_prompt),
            None,
        )
    ]
    for index, position in enumerate(config.needle_positions):
        cases.append(
            _long_case(
                tokenizer,
                config,
                name=f"long_{position}",
                key=f"PROBE-LONG-{index}",
                needle_token=position,
            )
        )
    return cases


def evaluate_context_probe(
    cases: Sequence[ProbeCase],
    completions: Sequence[str],
) -> dict[str, Any]:
    if len(cases) != len(completions):
        raise ValueError("probe cases and completions must have equal lengths")
    results = [
        {
            "name": case.name,
            "prompt_tokens": case.prompt_tokens,
            "needle_token": case.needle_token,
            "matched": case.key in completion,
        }
        for case, completion in zip(cases, completions)  # noqa: B905
    ]
    return {"all_matched": all(item["matched"] for item in results), "results": results}


def context_override(original_max_tokens: int, requested_max_tokens: int) -> dict[str, int] | None:
    """返回引擎 adapter 可消费的覆盖建议，不启动或导入任何推理引擎。"""
    if original_max_tokens < 1 or requested_max_tokens < 1:
        raise ValueError("context lengths must be positive")
    if original_max_tokens >= requested_max_tokens:
        return None
    return {"max_position_embeddings": requested_max_tokens}


def probe_case_asdict(case: ProbeCase) -> dict[str, Any]:
    return asdict(case)
