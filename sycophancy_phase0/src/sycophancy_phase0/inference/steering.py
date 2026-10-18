"""Additive residual-stream steering hook (plan §4.4, v1.3 position-id formulation).

Layer convention (plan §3): ``layer`` indexes ``model.model.layers[layer]`` (0-based); its output is
``hidden_states[layer + 1]`` in ``output_hidden_states`` indexing.

The steered positions are decided from the ``position_ids`` kwarg the decoder layer receives (per-row in every
``generate`` path and in explicit-position forwards), never from the tensor shape.  This makes one rule serve
teacher forcing, KV-cache decoding, ``use_cache=False`` decoding and assisted decoding alike:

  * ``S_gen``  : position id >= gen_start[b]   (gen_start = prompt_len - 1: last prompt token + every generated token)
  * ``S_read`` : pos_mask[b, position id]       (current-turn user tokens; decode steps are beyond the mask => untouched)
  * ``S_all``  : every non-pad position (pos_mask over position ids if given, else all)

Chunked prefill (``prefill_chunk_size``) must not be combined with left padding at all (HF itself mis-positions
padded rows there); the hook raises if ``position_ids`` is missing.
"""
from __future__ import annotations

from typing import Optional

import torch

_ATTR = "_sycophancy_steer_attached"


class Steer:
    """Additive steering on the residual-stream OUTPUT of ``model.model.layers[layer]``.

    alpha: per-row tensor [B] in units of ``r_L`` (0 => row untouched). ``None`` => hook is a no-op and the module
    output is returned *unchanged* (bitwise identical to "no hook", plan G0.2).
    """

    def __init__(self, model, layer: int, v_unit: torch.Tensor, r_L: float):
        self.model = model
        self.layer = layer
        v = v_unit.detach().float()
        n = v.norm()
        if not torch.isfinite(n) or n == 0:
            raise ValueError("steering vector must be finite and non-zero")
        v = v / n
        self.v_unit = v
        self.r_L = float(r_L)
        self.v = (v * self.r_L).to(device=model.device, dtype=model.dtype)  # [D]
        self.alpha: Optional[torch.Tensor] = None
        self.scope = "S_gen"
        self.gen_start: Optional[torch.Tensor] = None   # LongTensor [B]: first steered position id (prompt_len - 1)
        self.pos_mask: Optional[torch.Tensor] = None     # BoolTensor [B, P] indexed by position id (S_read / S_all)
        self.delta: Optional[torch.Tensor] = None        # fp32 leaf [B, S, D] (requires_grad) for scores.py
        self.real_mask: Optional[torch.Tensor] = None    # BoolTensor [B, S_prefill]: pad positions are never steered (round 11)
        self.calls = 0
        mod = model.model.layers[layer]
        if getattr(mod, _ATTR, False):
            raise RuntimeError(f"layer {layer} already has a Steer hook attached; remove() it first")
        self.handle = mod.register_forward_hook(self._hook, with_kwargs=True)
        setattr(mod, _ATTR, True)
        self._removed = False

    # ------------------------------------------------------------------ control
    def set(self, alpha, scope: str = "S_gen", *, gen_start=None, pos_mask=None, delta=None, generating=None, real_mask=None):
        """``generating`` is accepted and ignored (v1.2 API); positions come from ``position_ids`` now.

        ``real_mask`` (the prompt attention mask, [B, S_prefill]) excludes pad positions from steering whenever the hooked
        tensor has that length (the prefill forward); decode steps (S = 1) are all real tokens.  Needed because ``generate``
        gives left pads position id 1, so an S_read span covering position 1 would otherwise steer the pads — harmless for
        attention (pads are masked keys) but not for a MoE, where a pad's changed routing alters the expert GEMM shapes of
        the real tokens (round 11, second GPU diagnostics)."""
        if self._removed:
            raise RuntimeError("Steer.set() after remove()")
        if alpha is None:
            self.alpha = None
        else:
            self.alpha = torch.as_tensor(alpha, dtype=torch.float32, device=self.model.device).reshape(-1)
        if scope not in ("S_gen", "S_read", "S_all"):
            raise ValueError(scope)
        self.scope = scope
        self.gen_start = None if gen_start is None else torch.as_tensor(gen_start, dtype=torch.long).reshape(-1)
        self.pos_mask = None if pos_mask is None else torch.as_tensor(pos_mask).bool()
        self.delta = delta
        self.real_mask = None if real_mask is None else torch.as_tensor(real_mask).bool()

    def off(self):
        self.set(None)

    def remove(self):
        if not self._removed:
            self.handle.remove()
            setattr(self.model.model.layers[self.layer], _ATTR, False)
            self._removed = True

    def __del__(self):
        try:
            self.remove()
        except Exception:
            pass

    def state(self) -> dict:
        return dict(alpha=self.alpha, scope=self.scope, gen_start=self.gen_start, pos_mask=self.pos_mask, delta=self.delta,
                    real_mask=self.real_mask)

    def restore(self, st: dict) -> None:
        self.alpha, self.scope, self.gen_start, self.pos_mask, self.delta = (st["alpha"], st["scope"], st["gen_start"],
                                                                             st["pos_mask"], st["delta"])
        self.real_mask = st.get("real_mask")

    # ------------------------------------------------------------------ hook
    def _mask(self, B: int, S: int, device, position_ids) -> torch.Tensor:
        if position_ids is None:
            raise ValueError("Steer needs the position_ids kwarg (generate passes it; pass it explicitly in forwards)")
        pid = position_ids.to(device)
        if pid.dim() == 1:
            pid = pid[None]
        if pid.shape[0] == 1 and B > 1:
            pid = pid.expand(B, -1)
        if pid.shape != (B, S):
            raise ValueError(f"position_ids shape {tuple(pid.shape)} vs hidden [{B}, {S}]")
        if self.scope == "S_gen":
            if self.gen_start is None or self.gen_start.numel() != B:
                raise ValueError("S_gen needs gen_start[B] = prompt_len - 1 per row")
            mask = pid >= self.gen_start.to(device)[:, None]
        elif self.scope == "S_read":
            if self.pos_mask is None or self.pos_mask.shape[0] != B:
                raise ValueError("S_read needs pos_mask[B, P] indexed by position id")
            pm = self.pos_mask.to(device)
            P = pm.shape[1]
            mask = torch.gather(pm, 1, pid.clamp(min=0, max=P - 1)) & (pid < P) & (pid >= 0)
        else:  # S_all
            if self.pos_mask is None:
                mask = torch.ones(B, S, dtype=torch.bool, device=device)
            else:
                pm = self.pos_mask.to(device)
                P = pm.shape[1]
                mask = torch.gather(pm, 1, pid.clamp(min=0, max=P - 1)) & (pid < P) & (pid >= 0)
        if self.real_mask is not None:
            rm = self.real_mask.to(device)
            B0, S0 = rm.shape
            if B0 != B:
                raise ValueError(f"real_mask batch {B0} vs hidden batch {B}")
            if S == S0:
                mask = mask & rm                              # prefill: never steer pad positions
            elif S > S0:                                      # use_cache=False decoding re-feeds the grown sequence: new positions are real
                mask = mask & torch.cat([rm, torch.ones(B, S - S0, dtype=torch.bool, device=device)], 1)
            elif S == 1:
                pass                                          # cached decode step: one real token per row
            else:
                raise ValueError(f"real_mask length {S0} vs hidden length {S}: unsupported forward shape (chunked prefill is not supported)")
        return mask

    def _hook(self, module, args, kwargs, output):
        self.calls += 1
        if self.alpha is None and self.delta is None:
            return output
        is_tuple = isinstance(output, tuple)
        hs = output[0] if is_tuple else output            # [B, S, D]
        B, S, D = hs.shape
        mask = self._mask(B, S, hs.device, kwargs.get("position_ids"))
        a = (torch.zeros(B, device=hs.device, dtype=torch.float32) if self.alpha is None else self.alpha)
        if a.numel() == 1 and B > 1:
            a = a.expand(B)
        if a.numel() != B:
            raise ValueError(f"alpha has {a.numel()} entries for batch {B}")
        add = (a[:, None] * mask.float())[:, :, None] * self.v.float()[None, None, :]  # [B, S, D] fp32
        if self.delta is not None:
            add = add + self.delta * mask[:, :, None].float()
        new_hs = hs + add.to(hs.dtype)                      # out-of-place: autograd-safe; HF recorder stays clean
        return ((new_hs,) + tuple(output[1:])) if is_tuple else new_hs


def gen_start_from_prompt_lens(prompt_lens, device=None) -> torch.Tensor:
    """The first steered position id is the last prompt token: prompt_len - 1 (plan §4.4). Holds for left padding
    too because generate() assigns position ids 0..prompt_len-1 to the real tokens of every row."""
    pl = torch.as_tensor(list(prompt_lens), dtype=torch.long, device=device)
    return pl - 1


def read_mask_from_spans(spans, prompt_lens, device=None) -> torch.Tensor:
    """pos_mask[B, max_len] with True on the current-turn user_span of each row (scope S_read)."""
    P = int(max(prompt_lens))
    m = torch.zeros(len(spans), P, dtype=torch.bool, device=device)
    for b, (s, e) in enumerate(spans):
        if not (0 <= s < e <= prompt_lens[b]):
            raise ValueError(f"span {(s, e)} outside row {b} of length {prompt_lens[b]}")
        m[b, s:e] = True
    return m
