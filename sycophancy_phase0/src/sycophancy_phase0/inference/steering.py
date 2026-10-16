"""Additive residual-stream steering hook (plan §4.4).

Layer convention (plan §3): ``layer`` indexes ``model.model.layers[layer]`` (0-based); its output is
``hidden_states[layer + 1]`` in ``output_hidden_states`` indexing.
"""
from __future__ import annotations

from typing import Optional

import torch


class Steer:
    """Additive steering on the residual-stream OUTPUT of ``model.model.layers[layer]``.

    scope:
      ``"S_gen"``  -> positions >= gen_start[b] (last prompt token + every generated position)
      ``"S_read"`` -> positions where ``pos_mask[b, s]`` is True (current-turn user tokens)
      ``"S_all"``  -> every non-pad position
    alpha: per-row tensor [B] in units of ``r_L`` (0 => row untouched). ``None`` => hook is a no-op and
    the module output is returned *unchanged* (bitwise identical to "no hook", plan G0.2).
    """

    def __init__(self, model, layer: int, v_unit: torch.Tensor, r_L: float):
        self.model = model
        self.layer = layer
        v = v_unit.detach().float()
        v = v / v.norm()
        self.v_unit = v
        self.r_L = float(r_L)
        self.v = (v * self.r_L).to(device=model.device, dtype=model.dtype)  # [D]
        self.alpha: Optional[torch.Tensor] = None
        self.scope = "S_gen"
        self.gen_start: Optional[torch.Tensor] = None   # LongTensor [B]; teacher-forcing S_gen
        self.generating = False                          # inside generate(): prefill => last pos; decode => new pos
        self.pos_mask: Optional[torch.Tensor] = None     # BoolTensor [B, S] for S_read / S_all
        self.delta: Optional[torch.Tensor] = None        # fp32 leaf [B, S, D] (requires_grad) for scores.py
        self.calls = 0
        self.handle = model.model.layers[layer].register_forward_hook(self._hook, with_kwargs=True)

    # ------------------------------------------------------------------ control
    def set(self, alpha, scope: str = "S_gen", *, generating: bool = False, gen_start=None,
            pos_mask=None, delta=None):
        if alpha is None:
            self.alpha = None
        else:
            self.alpha = torch.as_tensor(alpha, dtype=torch.float32, device=self.model.device).reshape(-1)
        self.scope, self.generating = scope, generating
        self.gen_start, self.pos_mask, self.delta = gen_start, pos_mask, delta

    def off(self):
        self.set(None)

    def remove(self):
        self.handle.remove()

    # ------------------------------------------------------------------ hook
    def _mask(self, B: int, S: int, device) -> torch.Tensor:
        if self.scope == "S_gen":
            if self.generating:
                mask = torch.zeros(B, S, dtype=torch.bool, device=device)
                mask[:, -1] = True
            else:
                if self.gen_start is None or self.gen_start.numel() != B:
                    raise ValueError("teacher-forcing S_gen needs gen_start[B]")
                ar = torch.arange(S, device=device)[None, :]
                mask = ar >= self.gen_start.to(device)[:, None]
        elif self.scope == "S_read":
            if self.pos_mask is None:
                raise ValueError("S_read needs pos_mask")
            mask = self.pos_mask.to(device)
        elif self.scope == "S_all":
            mask = (self.pos_mask.to(device) if self.pos_mask is not None
                    else torch.ones(B, S, dtype=torch.bool, device=device))
        else:
            raise ValueError(self.scope)
        return mask

    def _hook(self, module, args, kwargs, output):
        self.calls += 1
        if self.alpha is None and self.delta is None:
            return output
        is_tuple = isinstance(output, tuple)
        hs = output[0] if is_tuple else output            # [B, S, D]
        B, S, D = hs.shape
        mask = self._mask(B, S, hs.device)
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
    """Teacher-forcing: the first steered position is the last prompt token (plan §4.4)."""
    pl = torch.as_tensor(list(prompt_lens), dtype=torch.long, device=device)
    return pl - 1
