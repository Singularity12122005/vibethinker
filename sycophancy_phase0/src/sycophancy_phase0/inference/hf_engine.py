"""HF-side primitives (plan §4.4–4.7, §8.3).

Rules enforced here:
  * ``generate`` uses LEFT padding (the hook's prefill rule ``[:, -1]`` must hit a real token);
  * every non-``generate`` forward uses RIGHT padding and an explicit ``position_ids`` — a direct ``model(...)``
    call does not derive positions from ``attention_mask`` (it uses ``cache_position``). RoPE is exactly invariant
    to a uniform shift in fp32, but bf16 leaks ~1e-2 logit differences at large pad counts (measured in
    tests/test_hf_semantics.py), which matters for the G0.5 argmax-consistency gate;
  * ``hidden_states[L + 1]`` is the output of ``model.model.layers[L]``; the last entry is post-norm and unused;
  * fp32 ``log_softmax`` for every log-prob / KL; integer ``logits_to_keep`` is never used (it slices the padded
    tensor from the end and breaks for shorter rows).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import torch
import torch.nn.functional as F

from ..constants import PAD_ID


# ---------------------------------------------------------------------- batching
def right_pad(seqs: Sequence[Sequence[int]], pad_id: int = PAD_ID, device=None):
    L = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), L), pad_id, dtype=torch.long)
    att = torch.zeros((len(seqs), L), dtype=torch.long)
    for b, s in enumerate(seqs):
        ids[b, : len(s)] = torch.as_tensor(list(s), dtype=torch.long)
        att[b, : len(s)] = 1
    if device is not None:
        ids, att = ids.to(device), att.to(device)
    return ids, att


def left_pad(seqs: Sequence[Sequence[int]], pad_id: int = PAD_ID, device=None):
    L = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), L), pad_id, dtype=torch.long)
    att = torch.zeros((len(seqs), L), dtype=torch.long)
    for b, s in enumerate(seqs):
        ids[b, L - len(s):] = torch.as_tensor(list(s), dtype=torch.long)
        att[b, L - len(s):] = 1
    if device is not None:
        ids, att = ids.to(device), att.to(device)
    return ids, att


def position_ids_from_mask(attention_mask: torch.Tensor) -> torch.Tensor:
    return (attention_mask.long().cumsum(-1) - 1).clamp(min=0)


# ---------------------------------------------------------------------- forwards
def _pad_id(model, pad_id):
    if pad_id is not None:
        return pad_id
    cfg_pad = getattr(model.config, "pad_token_id", None)
    return cfg_pad if cfg_pad is not None else PAD_ID


@torch.no_grad()
def clean_forward(model, seqs: Sequence[Sequence[int]], *, output_hidden_states: bool = False,
                  output_router_logits: bool = False, pad_id: Optional[int] = None):
    """Right-padded forward with explicit position_ids. Returns (outputs, attention_mask)."""
    ids, att = right_pad(seqs, pad_id=_pad_id(model, pad_id), device=model.device)
    out = model(input_ids=ids, attention_mask=att, position_ids=position_ids_from_mask(att),
                use_cache=False, output_hidden_states=output_hidden_states,
                output_router_logits=output_router_logits, return_dict=True)
    return out, att


def layer_output(hidden_states: Tuple[torch.Tensor, ...], layer: int) -> torch.Tensor:
    """Residual stream after ``model.model.layers[layer]`` == ``hidden_states[layer + 1]`` (plan §3)."""
    n_layers = len(hidden_states) - 1          # hidden_states[0] = embeddings, [-1] = post-norm
    if layer < 0 or layer + 1 >= n_layers:
        raise ValueError(f"layer {layer}: hidden_states[{layer + 1}] is the post-norm output (or out of range); "
                         f"valid L in [0, {n_layers - 2}]")
    return hidden_states[layer + 1]


@torch.no_grad()
def residual_norm_median(model, seqs: Sequence[Sequence[int]], layer: int, min_pos: int = 8) -> float:
    """r_L (plan §4.6): median per-position L2 norm at positions >= min_pos over the batch."""
    out, att = clean_forward(model, seqs, output_hidden_states=True)
    h = layer_output(out.hidden_states, layer).float()           # [B, S, D]
    norms = h.norm(dim=-1)                                       # [B, S]
    keep = att.bool().clone()
    keep[:, :min_pos] = False
    vals = norms[keep]
    if vals.numel() == 0:
        raise ValueError("no positions >= min_pos")
    return float(vals.median())


@torch.no_grad()
def extract_z(model, seqs: Sequence[Sequence[int]], layers: Sequence[int],
              user_spans: Sequence[Tuple[int, int]], prev_assistant_spans: Optional[Sequence[Optional[Tuple[int, int]]]] = None
              ) -> Dict[str, Dict[int, torch.Tensor]]:
    """z_t (plan §4.5) from a clean forward: R1 last prompt token, R2 mean over user_span, R3 mean over y_{t-1}."""
    out, att = clean_forward(model, seqs, output_hidden_states=True)
    lens = att.sum(-1)
    res: Dict[str, Dict[int, torch.Tensor]] = {"R1": {}, "R2": {}, "R3": {}}
    for L in layers:
        h = layer_output(out.hidden_states, L).float()
        B = h.shape[0]
        r1 = torch.stack([h[b, lens[b] - 1] for b in range(B)])
        r2 = torch.stack([h[b, s:e].mean(0) for b, (s, e) in enumerate(user_spans)])
        res["R1"][L] = r1.half().cpu()
        res["R2"][L] = r2.half().cpu()
        if prev_assistant_spans is not None:
            rows = []
            for b, sp in enumerate(prev_assistant_spans):
                rows.append(h[b, sp[0]:sp[1]].mean(0) if sp is not None else torch.zeros(h.shape[-1], device=h.device))
            res["R3"][L] = torch.stack(rows).half().cpu()
    return res


# ---------------------------------------------------------------------- teacher forcing
def response_logprobs(model, ids: Sequence[int], prompt_len: int, *, steer=None, alpha: float = 0.0,
                      scope: str = "S_gen", grad_delta: Optional[torch.Tensor] = None) -> torch.Tensor:
    """Per-token log P(y_k | y_<k, h) for the response ids[prompt_len:], B=1, fp32 log_softmax.

    With ``steer`` the hook is applied at positions >= prompt_len - 1 (teacher-forcing semantics, plan §4.4).
    """
    ids_t = torch.as_tensor(list(ids), dtype=torch.long, device=model.device)[None]
    att = torch.ones_like(ids_t)
    if steer is not None:
        steer.set([alpha], scope, generating=False,
                  gen_start=torch.tensor([prompt_len - 1], device=model.device), delta=grad_delta)
    try:
        ctx = torch.enable_grad() if grad_delta is not None else torch.no_grad()
        with ctx:
            out = model(input_ids=ids_t, attention_mask=att, position_ids=position_ids_from_mask(att),
                        use_cache=False, return_dict=True)
            logits = out.logits[0, prompt_len - 1: ids_t.shape[1] - 1].float()   # predicts ids[prompt_len:]
            targets = ids_t[0, prompt_len:]
            lp = F.log_softmax(logits, dim=-1).gather(-1, targets[:, None])[:, 0]
    finally:
        if steer is not None:
            steer.off()
    return lp


@torch.no_grad()
def next_token_kl(model, ids: Sequence[int], prompt_len: int, steer, alpha: float, scope: str = "S_gen") -> torch.Tensor:
    """Per-position KL(P^0 || P^alpha) over response positions (plan §4.7 step 1), fp32."""
    ids_t = torch.as_tensor(list(ids), dtype=torch.long, device=model.device)[None]
    att = torch.ones_like(ids_t)
    pos = position_ids_from_mask(att)
    sl = slice(prompt_len - 1, ids_t.shape[1] - 1)
    steer.off()
    lp0 = F.log_softmax(model(input_ids=ids_t, attention_mask=att, position_ids=pos, use_cache=False).logits[0, sl].float(), -1)
    steer.set([alpha], scope, generating=False, gen_start=torch.tensor([prompt_len - 1], device=model.device))
    try:
        lpa = F.log_softmax(model(input_ids=ids_t, attention_mask=att, position_ids=pos, use_cache=False).logits[0, sl].float(), -1)
    finally:
        steer.off()
    return (lp0.exp() * (lp0 - lpa)).sum(-1)                     # [n_response_positions]


def route_flip_fraction(router_logits_0: Sequence[torch.Tensor], router_logits_a: Sequence[torch.Tensor],
                        layer: int, top_k: int, response_mask: torch.Tensor) -> float:
    """Mean over MoE layers > layer and response positions of 1 - |S0 ∩ Sα| / top_k (plan §4.7)."""
    B, S = response_mask.shape
    vals = []
    for l in range(layer + 1, len(router_logits_0)):
        r0 = router_logits_0[l].view(B, S, -1)
        ra = router_logits_a[l].view(B, S, -1)
        t0 = r0.topk(top_k, dim=-1).indices
        ta = ra.topk(top_k, dim=-1).indices
        inter = (t0[..., :, None] == ta[..., None, :]).any(-1).sum(-1).float()   # [B, S]
        flip = 1.0 - inter / top_k
        vals.append(flip[response_mask.bool()])
    return float(torch.cat(vals).mean()) if vals else 0.0


# ---------------------------------------------------------------------- generation
def generate_steered(model, seqs: Sequence[Sequence[int]], steer, alphas: Sequence[float], gen_kwargs: dict,
                     scope: str = "S_gen", pad_id: Optional[int] = None):
    """Left-padded generate with per-row alpha; returns list of generated id lists (prompt stripped)."""
    ids, att = left_pad(seqs, pad_id=_pad_id(model, pad_id), device=model.device)
    steer.set(list(alphas), scope, generating=True)
    try:
        out = model.generate(input_ids=ids, attention_mask=att, **gen_kwargs)
    finally:
        steer.off()
    L = ids.shape[1]
    return [out[b, L:].tolist() for b in range(out.shape[0])]
