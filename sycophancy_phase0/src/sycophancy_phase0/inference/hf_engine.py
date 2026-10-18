"""HF-side primitives (plan §4.4–4.7, §8.3).

Rules enforced here:
  * ``generate`` uses LEFT padding (generate then assigns position ids 0..prompt_len-1 to each row's real tokens, so
    the hook's position-id rule ``pid >= prompt_len - 1`` is exact for every row);
  * every non-``generate`` forward uses RIGHT padding and an explicit ``position_ids`` — a direct ``model(...)``
    call does not derive positions from ``attention_mask`` (it uses ``cache_position``). RoPE is exactly invariant
    to a uniform shift in fp32, but bf16 leaks ~1e-2 logit differences at large pad counts (measured in
    tests/test_hf_semantics.py), which matters for the G0.5 argmax-consistency gate;
  * ``hidden_states[L + 1]`` is the output of ``model.model.layers[L]``; the last entry is post-norm and unused;
  * fp32 ``log_softmax`` of ``logits / T`` (T = the frozen generation temperature, constants.TEMPERATURE = 0.7) for every
    log-prob / KL / gradient: the distribution the model SAMPLED from is P_T, and T = 1 is a different distribution (round 9,
    first GPU contact review: the reference implementation normalised raw logits before 2026-10-18); integer
    ``logits_to_keep`` is never used (it slices the padded tensor from the end and breaks for shorter rows).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F

from ..constants import ENDOFTEXT, IM_END, PAD_ID, TEMPERATURE


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
              user_spans: Sequence[Tuple[int, int]], prev_assistant_spans: Optional[Sequence[Optional[Tuple[int, int]]]] = None,
              steer=None) -> Dict[str, Dict[int, torch.Tensor]]:
    """z_t (plan §4.5) from a clean forward: R1 last prompt token, R2 mean over user_span, R3 mean over y_{t-1}.

    Spans are validated against each row's length (no pad leakage); an EMPTY previous-assistant span (y_{t-1} had no
    content, e.g. an unclosed think block, plan §4.1) makes R3 *missing* for that row: a NaN row plus ``valid["R3"][b] =
    False`` — never a mean over an empty slice, never a zero vector, and the trajectory is kept (plan §4.5, round 7).
    ``steer`` (if given) must be off, because the recorder is pre-hook only at the hooked layer — layers above it would
    be steered.  Returned rows are fp32 on CPU; the store decides the dtype (fp16 unless a value overflows, plan §4.5).
    """
    if steer is not None and (steer.alpha is not None or steer.delta is not None):
        raise RuntimeError("extract_z requires the Steer hook to be off (plan §4.2 clean-read)")
    out, att = clean_forward(model, seqs, output_hidden_states=True)
    lens = att.sum(-1).tolist()
    for b, (s, e) in enumerate(user_spans):
        if not (0 <= s < e <= lens[b]):
            raise ValueError(f"user_span {(s, e)} outside row {b} (len {lens[b]})")
    r3_valid = None
    if prev_assistant_spans is not None:
        r3_valid = torch.zeros(len(seqs), dtype=torch.bool)
        for b, sp in enumerate(prev_assistant_spans):
            if sp is None or sp[0] == sp[1]:
                continue                                   # no previous content: R3 missing for this row
            if not (0 <= sp[0] < sp[1] <= lens[b]):
                raise ValueError(f"prev_assistant_span {sp} outside row {b} (len {lens[b]})")
            r3_valid[b] = True
    res: Dict[str, Dict[int, torch.Tensor]] = {"R1": {}, "R2": {}, "R3": {}}
    if r3_valid is not None:
        res["valid"] = {"R3": r3_valid}
    for L in layers:
        h = layer_output(out.hidden_states, L).float()
        B = h.shape[0]
        r1 = torch.stack([h[b, lens[b] - 1] for b in range(B)])
        r2 = torch.stack([h[b, s:e].mean(0) for b, (s, e) in enumerate(user_spans)])
        res["R1"][L] = r1.cpu()
        res["R2"][L] = r2.cpu()
        if prev_assistant_spans is not None:
            rows = []
            for b, sp in enumerate(prev_assistant_spans):
                rows.append(h[b, sp[0]:sp[1]].mean(0) if bool(r3_valid[b]) else torch.full((h.shape[-1],), float("nan"), device=h.device))
            res["R3"][L] = torch.stack(rows).cpu()
        for pos in ("R1", "R2", "R3"):
            if L in res[pos]:
                chk = res[pos][L] if (pos != "R3" or r3_valid is None) else res[pos][L][r3_valid]
                if not torch.isfinite(chk).all():
                    raise ValueError(f"non-finite z at layer {L} ({pos})")
    return res


def extract_z_think(model, seqs_with_think: Sequence[Sequence[int]], layers: Sequence[int], steer=None
                    ) -> Dict[int, torch.Tensor]:
    """Thinking arm (plan §4.5, §7.5): hidden state of the last token *before* ``</think>`` from a clean forward on
    ``prompt_ids + think_ids`` (think_ids ends with 151668).  Position = len(seq) - 2."""
    if steer is not None and (steer.alpha is not None or steer.delta is not None):
        raise RuntimeError("extract_z_think requires the Steer hook to be off")
    out, att = clean_forward(model, seqs_with_think, output_hidden_states=True)
    lens = att.sum(-1).tolist()
    res: Dict[int, torch.Tensor] = {}
    for L in layers:
        h = layer_output(out.hidden_states, L).float()
        res[L] = torch.stack([h[b, lens[b] - 2] for b in range(h.shape[0])]).cpu()
    return res


# ---------------------------------------------------------------------- teacher forcing
def response_logprobs(model, ids: Sequence[int], prompt_len: int, *, steer=None, alpha: float = 0.0,
                      scope: str = "S_gen", grad_delta: Optional[torch.Tensor] = None,
                      pos_mask: Optional[torch.Tensor] = None, temperature: float = TEMPERATURE) -> torch.Tensor:
    """Per-token log P_T(y_k | y_<k, h) for the response ids[prompt_len:], B=1, fp32 log_softmax of logits / T
    (T = the generation temperature; plan §4.3/§8.3: "温度 0.7 的条件分布").

    With ``steer`` the hook is applied at positions >= prompt_len - 1 (S_gen) or on ``pos_mask`` (S_read).
    The hook state the caller had set is restored afterwards.
    """
    ids_t = torch.as_tensor(list(ids), dtype=torch.long, device=model.device)[None]
    att = torch.ones_like(ids_t)
    saved = steer.state() if steer is not None else None
    if steer is not None:
        steer.set([alpha], scope, gen_start=torch.tensor([prompt_len - 1]), pos_mask=pos_mask, delta=grad_delta)
    try:
        ctx = torch.enable_grad() if grad_delta is not None else torch.no_grad()
        with ctx:
            out = model(input_ids=ids_t, attention_mask=att, position_ids=position_ids_from_mask(att),
                        use_cache=False, return_dict=True)
            logits = out.logits[0, prompt_len - 1: ids_t.shape[1] - 1].float()   # predicts ids[prompt_len:]
            targets = ids_t[0, prompt_len:]
            lp = F.log_softmax(logits / float(temperature), dim=-1).gather(-1, targets[:, None])[:, 0]
    finally:
        if steer is not None:
            steer.restore(saved)
    return lp


@torch.no_grad()
def next_token_kl(model, ids: Sequence[int], prompt_len: int, steer, alpha: float, scope: str = "S_gen",
                  pos_mask: Optional[torch.Tensor] = None, direction: str = "zero_to_alpha",
                  temperature: float = TEMPERATURE) -> torch.Tensor:
    """Per-position KL over response positions between the T-tempered distributions (fp32); caller takes the mean (plan
    §4.7 step 1: KL(P^0 || P^alpha), ``direction="zero_to_alpha"``) or the sum (kappa_1, §4.7 step 4: KL(P^alpha || P^0),
    ``"alpha_to_zero"``)."""
    ids_t = torch.as_tensor(list(ids), dtype=torch.long, device=model.device)[None]
    att = torch.ones_like(ids_t)
    pos = position_ids_from_mask(att)
    sl = slice(prompt_len - 1, ids_t.shape[1] - 1)
    saved = steer.state()
    steer.off()
    try:
        T = float(temperature)
        lp0 = F.log_softmax(model(input_ids=ids_t, attention_mask=att, position_ids=pos, use_cache=False).logits[0, sl].float() / T, -1)
        steer.set([alpha], scope, gen_start=torch.tensor([prompt_len - 1]), pos_mask=pos_mask)
        lpa = F.log_softmax(model(input_ids=ids_t, attention_mask=att, position_ids=pos, use_cache=False).logits[0, sl].float() / T, -1)
    finally:
        steer.restore(saved)
    if direction == "zero_to_alpha":
        return (lp0.exp() * (lp0 - lpa)).sum(-1)                 # [n_response_positions]
    if direction == "alpha_to_zero":
        return (lpa.exp() * (lpa - lp0)).sum(-1)
    raise ValueError(direction)


@torch.no_grad()
def router_topk_sets(model, ids: Sequence[int], prompt_len: int, steer, alpha: float, top_k: int = 8, scope: str = "S_gen",
                     pos_mask: Optional[torch.Tensor] = None) -> Dict[int, "np.ndarray"]:
    """Top-k expert ids per response position for every MoE layer (output_router_logits), under ``alpha``.
    Returns {layer: int array [n_response_positions, top_k]} with positions prompt_len-1 .. len-2 (the positions that
    predict the response tokens)."""
    import numpy as np
    ids_t = torch.as_tensor(list(ids), dtype=torch.long, device=model.device)[None]
    att = torch.ones_like(ids_t)
    pos = position_ids_from_mask(att)
    saved = steer.state()
    steer.set([alpha], scope, gen_start=torch.tensor([prompt_len - 1]), pos_mask=pos_mask)
    try:
        out = model(input_ids=ids_t, attention_mask=att, position_ids=pos, use_cache=False, output_router_logits=True)
    finally:
        steer.restore(saved)
    S = ids_t.shape[1]
    sl = slice(prompt_len - 1, S - 1)
    sets = {}
    for ell, rl in enumerate(out.router_logits):
        if rl is None:
            continue
        E = rl.shape[-1]
        r = rl.float().view(1, S, E)[0, sl]
        sets[ell] = torch.topk(r, top_k, dim=-1).indices.cpu().numpy()
    return sets


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
                     scope: str = "S_gen", pad_id: Optional[int] = None, pos_mask: Optional[torch.Tensor] = None,
                     eos_ids: Sequence[int] = (IM_END, ENDOFTEXT)):
    """Left-padded generate with per-row alpha; returns (gen_ids, finish_reasons): ids cut after the first EOS
    (trailing pads removed), finish_reason "length" iff no EOS within max_new_tokens.

    ``pos_mask`` (S_read) is indexed by position id = index in the unpadded prompt; it is shifted here for left
    padding automatically because generate assigns position ids 0..prompt_len-1 to the real tokens.
    """
    if gen_kwargs.get("return_dict_in_generate"):
        raise ValueError("generate_steered expects plain tensor output")
    ids, att = left_pad(seqs, pad_id=_pad_id(model, pad_id), device=model.device)
    steer.set(list(alphas), scope, gen_start=att.sum(-1) - 1, pos_mask=pos_mask)
    try:
        out = model.generate(input_ids=ids, attention_mask=att, **gen_kwargs)
    finally:
        steer.off()
    L = ids.shape[1]
    mnt = int(gen_kwargs.get("max_new_tokens", 0))
    gens, reasons = [], []
    for b in range(out.shape[0]):
        g = out[b, L:].tolist()
        cut = next((k for k, t in enumerate(g) if t in eos_ids), None)
        if cut is not None:
            g = g[: cut + 1]
            reasons.append("stop")
        else:
            reasons.append("length" if (mnt and len(g) >= mnt) else "stop")
        gens.append(g)
    return gens, reasons


@torch.no_grad()
def confidence_features(model, seqs: Sequence[Sequence[int]], suffix_ids: Sequence[Sequence[Sequence[int]]], top_k: int = 50,
                        pad_id: Optional[int] = None, temperature: float = TEMPERATURE) -> Dict[str, object]:
    """plan §4.5 baseline features for each prompt: top-k RAW logits (sorted) and ids at the last prompt token, and the
    summed T-tempered log-prob of each forced suffix (``suffix_ids[b]`` = list of suffix id lists, e.g. encode("最终答案：" + d_i)
    and ... g_i), scored only over the suffix tokens.  Right padding + explicit positions."""
    out, att = clean_forward(model, seqs, pad_id=pad_id)
    lens = att.sum(-1).tolist()
    last = torch.stack([out.logits[b, lens[b] - 1].float() for b in range(len(seqs))])
    top = torch.topk(last, top_k, dim=-1)
    res = dict(top_logits=top.values.cpu().numpy(), top_ids=top.indices.cpu().numpy(), suffix_logp=[])
    for b, seq in enumerate(seqs):
        lps = []
        for suf in suffix_ids[b]:
            lp = response_logprobs(model, list(seq) + list(suf), len(seq), temperature=temperature)
            lps.append(float(lp.sum()))
        res["suffix_logp"].append(lps)
    res["suffix_logp"] = np.asarray(res["suffix_logp"]) if res["suffix_logp"] else np.zeros((len(seqs), 0))
    return res
