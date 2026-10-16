"""Engine abstraction: one call = a batch of independent generation requests (plan §4.2, §4.3, §4.9).

* ``HFEngine`` — HuggingFace ``generate`` with the per-row seeded Gumbel sampler and the ``Steer`` hook
  (the only engine allowed for alpha != 0 unless vLLM steering has passed G0.8).
* ``VLLMEngine`` — in ``vllm_engine.py``; alpha = 0 only.
* ``FakeEngine`` — deterministic stand-in for CPU tests of the rollout plumbing.
* ``EngineRouter`` — picks the engine per request: alpha != 0 -> steered engine; alpha == 0 -> null engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol, Sequence

from ..constants import ENDOFTEXT, IM_END, MAX_NEW_TOKENS, TEMPERATURE


@dataclass
class GenRequest:
    ids: List[int]
    seed: int
    alpha: float = 0.0            # absolute alpha in units of r_L; 0 => no steering
    max_new_tokens: int = MAX_NEW_TOKENS
    greedy: bool = False          # only G0 token-equivalence tests and the G7 oracle
    temperature: Optional[float] = None   # override of the engine temperature (only §5.2 batch 2 at T=1.0)


@dataclass
class GenResult:
    ids: List[int]                # generated ids only (prompt stripped), raw (not normalised)
    finish_reason: str            # "stop" | "length"
    engine: str = ""


class Engine(Protocol):
    name: str
    supports_steering: bool

    def generate(self, reqs: Sequence[GenRequest]) -> List[GenResult]: ...


def finish_reason_from_ids(gen_ids: Sequence[int], max_new_tokens: int) -> str:
    """HF returns padded rows; a row stopped iff an EOS id occurs, else it ran to max_new_tokens."""
    for t in gen_ids:
        if t in (IM_END, ENDOFTEXT):
            return "stop"
    return "length" if len(gen_ids) >= max_new_tokens else "stop"


# ---------------------------------------------------------------------- HF
class HFEngine:
    name = "hf"
    supports_steering = True

    def __init__(self, model, steer=None, *, batch_size: int = 32, temperature: float = TEMPERATURE,
                 pad_id: Optional[int] = None, eos_ids: Sequence[int] = (IM_END, ENDOFTEXT), device=None):
        self.model = model
        self.steer = steer
        self.batch_size = int(batch_size)
        self.T = float(temperature)
        self.pad_id = pad_id
        self.eos_ids = tuple(int(e) for e in eos_ids)
        self.device = device
        self.n_generated_tokens = 0
        self.n_prompt_tokens = 0

    def generate(self, reqs: Sequence[GenRequest]) -> List[GenResult]:
        import torch
        from .hf_engine import _pad_id, left_pad
        from .sampling import generate_kwargs

        out: List[Optional[GenResult]] = [None] * len(reqs)
        # group by (max_new_tokens, greedy) so one generate call has a single length budget / sampler
        groups: Dict[tuple, List[int]] = {}
        for i, r in enumerate(reqs):
            groups.setdefault((r.max_new_tokens, r.greedy, r.temperature), []).append(i)
        pad = _pad_id(self.model, self.pad_id)
        for (mnt, greedy, temp), idxs in groups.items():
            for s in range(0, len(idxs), self.batch_size):
                chunk = idxs[s:s + self.batch_size]
                seqs = [reqs[i].ids for i in chunk]
                alphas = [float(reqs[i].alpha) for i in chunk]
                if any(a != 0.0 for a in alphas) and self.steer is None:
                    raise RuntimeError("steered request on an HFEngine without a Steer hook")
                ids, att = left_pad(seqs, pad_id=pad, device=self.device or self.model.device)
                if greedy:
                    kw = dict(do_sample=False, temperature=None, top_k=None, top_p=None, min_p=None,
                              repetition_penalty=1.0, max_new_tokens=mnt, pad_token_id=pad,
                              eos_token_id=list(self.eos_ids), use_cache=True)
                else:
                    kw = generate_kwargs([reqs[i].seed for i in chunk], temperature=(self.T if temp is None else float(temp)), max_new_tokens=mnt,
                                         pad_token_id=pad, eos_token_id=self.eos_ids, device=str(ids.device))
                if self.steer is not None:
                    self.steer.set(alphas, "S_gen", gen_start=att.sum(-1) - 1)
                try:
                    with torch.no_grad():
                        gen = self.model.generate(input_ids=ids, attention_mask=att, **kw)
                finally:
                    if self.steer is not None:
                        self.steer.off()
                L = ids.shape[1]
                for b, i in enumerate(chunk):
                    g = gen[b, L:].tolist()
                    # strip HF's post-EOS padding so downstream sees the raw generated ids only
                    cut = next((k for k, t in enumerate(g) if t in self.eos_ids), None)
                    g = g[: cut + 1] if cut is not None else g
                    out[i] = GenResult(g, finish_reason_from_ids(g, mnt), self.name)
                    self.n_generated_tokens += len(g)
                    self.n_prompt_tokens += len(reqs[i].ids)
        return [o for o in out]  # type: ignore


# ---------------------------------------------------------------------- fake (tests)
Responder = Callable[[List[int], int, float, int], List[int]]   # (ids, seed, alpha, max_new_tokens) -> gen ids


class FakeEngine:
    """Deterministic engine for plumbing tests: ``responder`` returns raw generated ids."""
    name = "fake"

    def __init__(self, responder: Responder, supports_steering: bool = True, name: str = "fake"):
        self.responder = responder
        self.supports_steering = supports_steering
        self.name = name
        self.calls: List[List[GenRequest]] = []
        self.n_generated_tokens = 0
        self.n_prompt_tokens = 0

    def generate(self, reqs: Sequence[GenRequest]) -> List[GenResult]:
        self.calls.append(list(reqs))
        res = []
        for r in reqs:
            if r.alpha != 0.0 and not self.supports_steering:
                raise RuntimeError("steered request on a non-steering engine")
            g = list(self.responder(list(r.ids), r.seed, r.alpha, r.max_new_tokens))
            res.append(GenResult(g, finish_reason_from_ids(g, r.max_new_tokens), self.name))
            self.n_generated_tokens += len(g); self.n_prompt_tokens += len(r.ids)
        return res


# ---------------------------------------------------------------------- router
class EngineRouter:
    """alpha != 0 -> ``steered`` engine (HF); alpha == 0 -> ``null`` engine (vLLM when available, else HF)."""

    def __init__(self, steered: Optional[Engine], null: Engine):
        if steered is not None and not steered.supports_steering:
            raise ValueError("steered engine must support steering")
        self.steered = steered
        self.null = null

    def generate(self, reqs: Sequence[GenRequest]) -> List[GenResult]:
        out: List[Optional[GenResult]] = [None] * len(reqs)
        st = [i for i, r in enumerate(reqs) if r.alpha != 0.0]
        nu = [i for i, r in enumerate(reqs) if r.alpha == 0.0]
        if st:
            if self.steered is None:
                raise RuntimeError("steered requests but no steering engine configured")
            for i, res in zip(st, self.steered.generate([reqs[i] for i in st])):
                out[i] = res
        if nu:
            for i, res in zip(nu, self.null.generate([reqs[i] for i in nu])):
                out[i] = res
        return out  # type: ignore
