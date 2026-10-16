"""Per-row seeded Gumbel-max sampling (plan §4.3).

transformers 4.57.1 merges user ``logits_processor`` entries *before* appending the temperature warper,
so the sampler applies the temperature itself and ``generate`` must be called with ``temperature=1.0``.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, List, Optional

import torch

try:  # transformers is optional at import time (analysis-only installs)
    from transformers import LogitsProcessor, LogitsProcessorList
except Exception:  # pragma: no cover
    LogitsProcessor = object      # type: ignore
    LogitsProcessorList = list    # type: ignore


def derive_seed(run_id: str, problem_id: str, prefix_id: str, arm_id: str, trajectory_idx: int, turn: int) -> int:
    key = "|".join([run_id, problem_id, prefix_id, arm_id, str(trajectory_idx), str(turn)])
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "little") & (2**63 - 1)


class SeededGumbelSampler(LogitsProcessor):
    """Argmax of (logits/T + Gumbel noise) per row with a private generator == temperature sampling."""

    def __init__(self, seeds: Iterable[int], temperature: float, device: Optional[str] = None):
        self.T = float(temperature)
        self.seeds: List[int] = [int(s) for s in seeds]
        self._device = device
        self.gens: Optional[List[torch.Generator]] = None

    def _ensure(self, device):
        if self.gens is None:
            dev = torch.device(self._device) if self._device is not None else device
            self.gens = [torch.Generator(device=dev).manual_seed(s) for s in self.seeds]

    def __call__(self, input_ids, scores):
        if scores.shape[0] != len(self.seeds):
            raise ValueError(f"{scores.shape[0]} rows but {len(self.seeds)} seeds")
        self._ensure(scores.device)
        s = scores.float() / self.T
        out = torch.full_like(scores, float("-inf"))
        V = s.shape[-1]
        for b, g in enumerate(self.gens):
            u = torch.rand(V, generator=g, device=g.device, dtype=torch.float32).to(s.device)
            tok = torch.argmax(s[b] - torch.log(-torch.log(u.clamp_(1e-20, 1.0))))
            out[b, tok] = 0.0
        return out


def generate_kwargs(seeds: Iterable[int], temperature: float = 0.7, max_new_tokens: int = 512,
                    pad_token_id: int = 151643, eos_token_id=(151645, 151643), device: Optional[str] = None) -> dict:
    """Frozen decoding configuration (plan §4.3): no truncation, temperature inside the sampler."""
    return dict(
        do_sample=True, temperature=1.0, top_k=0, top_p=1.0, min_p=None, repetition_penalty=1.0,
        max_new_tokens=max_new_tokens, pad_token_id=pad_token_id, eos_token_id=list(eos_token_id),
        logits_processor=LogitsProcessorList([SeededGumbelSampler(seeds, temperature, device)]),
    )


def has_temperature_warper(processors) -> bool:
    return any(type(p).__name__ == "TemperatureLogitsWarper" for p in processors)
