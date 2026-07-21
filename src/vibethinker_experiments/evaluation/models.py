"""Typed configuration loaded from explicit profile and panel manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

Mode = Literal["toy", "formal"]
DOMAINS = ("math", "code", "stem", "ifc", "knowledge")


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class EvaluationProfile:
    """Frozen generation/scoring settings; context is intentionally required."""

    profile_id: str
    mode: Mode
    context_tokens: int
    generation_cap_tokens: int
    temperature: float
    top_p: float
    seed: int
    require_judgments: bool

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> EvaluationProfile:
        required = {
            "profile_id",
            "mode",
            "context_tokens",
            "generation_cap_tokens",
            "temperature",
            "top_p",
            "seed",
            "require_judgments",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise ValueError(f"profile missing required fields: {missing}")
        mode = str(value["mode"])
        if mode not in {"toy", "formal"}:
            raise ValueError("profile mode must be toy or formal")
        context = _positive_int(value["context_tokens"], "context_tokens")
        generation_cap = _positive_int(value["generation_cap_tokens"], "generation_cap_tokens")
        if generation_cap > context:
            raise ValueError("generation_cap_tokens cannot exceed context_tokens")
        temperature = float(value["temperature"])
        top_p = float(value["top_p"])
        if temperature < 0 or not 0 < top_p <= 1:
            raise ValueError("temperature must be non-negative and top_p must be in (0, 1]")
        if not isinstance(value["require_judgments"], bool):
            raise ValueError("require_judgments must be boolean")
        return cls(
            profile_id=str(value["profile_id"]),
            mode=mode,  # type: ignore[arg-type]
            context_tokens=context,
            generation_cap_tokens=generation_cap,
            temperature=temperature,
            top_p=top_p,
            seed=int(value["seed"]),
            require_judgments=value["require_judgments"],
        )

    @classmethod
    def load(cls, path: str | Path) -> EvaluationProfile:
        value = yaml.safe_load(Path(path).read_text())
        if not isinstance(value, dict):
            raise ValueError("profile must be a YAML object")
        return cls.from_mapping(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "mode": self.mode,
            "context_tokens": self.context_tokens,
            "generation_cap_tokens": self.generation_cap_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "require_judgments": self.require_judgments,
        }


@dataclass(frozen=True)
class PanelManifest:
    """Identity and isolation boundary for a panel dataset."""

    panel_name: str
    panel_version: str
    mode: Mode
    panel_sha256: str
    row_count: int
    domains: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> PanelManifest:
        mode = str(value.get("mode", ""))
        if mode not in {"toy", "formal"}:
            raise ValueError("panel mode must be toy or formal")
        digest = str(value.get("panel_sha256", ""))
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("panel_sha256 must be a lowercase SHA-256 digest")
        domains = tuple(str(item) for item in value.get("domains", ()))
        if not domains or any(domain not in DOMAINS for domain in domains):
            raise ValueError("panel domains must be a non-empty subset of supported domains")
        return cls(
            panel_name=str(value["panel_name"]),
            panel_version=str(value["panel_version"]),
            mode=mode,  # type: ignore[arg-type]
            panel_sha256=digest,
            row_count=_positive_int(value["row_count"], "row_count"),
            domains=domains,
        )

    @classmethod
    def load(cls, path: str | Path) -> PanelManifest:
        value = yaml.safe_load(Path(path).read_text())
        if not isinstance(value, dict):
            raise ValueError("panel manifest must be an object")
        return cls.from_mapping(value)

    def assert_compatible(self, profile: EvaluationProfile) -> None:
        if self.mode != profile.mode:
            raise ValueError(
                f"formal/toy isolation violation: panel={self.mode}, profile={profile.mode}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "panel_name": self.panel_name,
            "panel_version": self.panel_version,
            "mode": self.mode,
            "panel_sha256": self.panel_sha256,
            "row_count": self.row_count,
            "domains": list(self.domains),
        }
