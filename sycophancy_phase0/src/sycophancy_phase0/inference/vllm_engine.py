"""vLLM engine for all alpha = 0 rollouts (plan §4.9).  Not exercised on CPU; G0.8 is its acceptance test.

Rules enforced here: ``enable_prefix_caching=False``, bf16, per-request ``seed``, pure temperature sampling
(``top_k=-1, top_p=1.0, min_p=0.0``), explicit stop ids {151645, 151643}; the model's ``generation_config.json``
defaults (top_k=20 / top_p=0.8) are overridden on every request and asserted at start-up.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from ..constants import ENDOFTEXT, IM_END, TEMPERATURE
from .engine import GenRequest, GenResult


class VLLMEngine:
    name = "vllm"
    supports_steering = False

    def __init__(self, model: str, *, tensor_parallel_size: int = 1, gpu_memory_utilization: float = 0.90,
                 max_model_len: int = 8192, temperature: float = TEMPERATURE, llm=None, seed: int = 0,
                 **llm_kwargs):
        if llm is None:
            from vllm import LLM
            llm = LLM(model=model, dtype="bfloat16", enable_prefix_caching=False, seed=seed,
                      tensor_parallel_size=tensor_parallel_size, gpu_memory_utilization=gpu_memory_utilization,
                      max_model_len=max_model_len, **llm_kwargs)
        self.llm = llm
        self.T = float(temperature)
        self.eos_ids = [IM_END, ENDOFTEXT]
        self.n_generated_tokens = 0
        self.n_prompt_tokens = 0
        self.assert_defaults_overridden()

    def assert_defaults_overridden(self) -> None:
        """vLLM reads top_k=20/top_p=0.8 from generation_config.json as *defaults*; we pass explicit params per
        request, but record the defaults and refuse to run if explicit params are not honoured."""
        get = getattr(self.llm, "get_default_sampling_params", None)
        self.default_sampling_params = repr(get()) if callable(get) else None
        sp = self._params(GenRequest(ids=[0], seed=1))
        assert sp.top_k == -1 and abs(sp.top_p - 1.0) < 1e-12 and sp.min_p == 0.0, sp

    def _params(self, r: GenRequest):
        from vllm import SamplingParams
        T = 0.0 if r.greedy else (self.T if r.temperature is None else float(r.temperature))
        return SamplingParams(temperature=T, top_k=-1, top_p=1.0, min_p=0.0,
                              repetition_penalty=1.0, presence_penalty=0.0, frequency_penalty=0.0,
                              max_tokens=int(r.max_new_tokens), seed=int(r.seed),
                              stop_token_ids=self.eos_ids, skip_special_tokens=False, n=1, logprobs=None)

    def generate(self, reqs: Sequence[GenRequest]) -> List[GenResult]:
        if any(r.alpha != 0.0 for r in reqs):
            raise RuntimeError("VLLMEngine only serves alpha = 0 requests (plan §4.9)")
        try:
            from vllm.inputs import TokensPrompt
            prompts = [TokensPrompt(prompt_token_ids=list(r.ids)) for r in reqs]
        except Exception:  # older vLLM
            prompts = [{"prompt_token_ids": list(r.ids)} for r in reqs]
        params = [self._params(r) for r in reqs]
        outs = self.llm.generate(prompts, params, use_tqdm=False)
        res: List[GenResult] = []
        for r, o in zip(reqs, outs):
            c = o.outputs[0]
            ids = list(c.token_ids)
            fr = "length" if c.finish_reason == "length" else "stop"
            res.append(GenResult(ids, fr, self.name))
            self.n_generated_tokens += len(ids); self.n_prompt_tokens += len(r.ids)
        return res
