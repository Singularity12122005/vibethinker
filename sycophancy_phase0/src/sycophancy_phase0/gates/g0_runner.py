"""G0 data collection (plan §7.1).  Each function returns exactly the inputs of the matching statistic in
``gates/g0.py``; nothing here decides.  The model-level pieces (G0.2, G0.3, G0.7) run on CPU with a tiny model in
the tests; the rollout-level pieces (G0.1, G0.4, G0.5, G0.8) are orchestrations over ``rollout.run_rollouts``.
"""
from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..constants import TEMPERATURE
from ..inference.engine import EngineRouter, GenRequest
from ..inference.templates import TurnBuilder
from ..constants import ENDOFTEXT, IM_END
from ..rollout import Prefix, RolloutSpec, prefix_from_trajectory, run_rollouts, spec_from_prefix
from ..scripts.builders import user_turns
from ..trajectory import Arm, Trajectory


# ---------------------------------------------------------------- G0.2 hook self-checks (§4.4) + sampler χ² (§4.3)
def hook_selfcheck(model, steer, ids: Sequence[int], gen_start: Optional[int] = None) -> Dict[str, bool]:
    """Four §4.4 checks on one sequence plus the processor-list check.  ``steer`` must be attached to ``model``."""
    import torch
    from transformers import GenerationConfig

    from ..inference.hf_engine import clean_forward
    from ..inference.sampling import generate_kwargs, has_temperature_warper

    checks: Dict[str, bool] = {}
    with torch.no_grad():
        steer.off()
        base = clean_forward(model, [ids])[0].logits.float()
        steer.set([0.0], "S_gen", gen_start=torch.tensor([len(ids) - 1]))
        zero = clean_forward(model, [ids])[0].logits.float()
        steer.set([1.0], "S_gen", gen_start=torch.tensor([len(ids) - 1]))
        plus = clean_forward(model, [ids])[0].logits.float()[0, -1]
        steer.set([-1.0], "S_gen", gen_start=torch.tensor([len(ids) - 1]))
        minus = clean_forward(model, [ids])[0].logits.float()[0, -1]
        gs = int(gen_start if gen_start is not None else max(1, len(ids) // 2))
        steer.set([1.0], "S_gen", gen_start=torch.tensor([gs]))
        tf = clean_forward(model, [ids])[0].logits.float()
        steer.off()
    checks["alpha_pm1_first_token_differs"] = bool((plus - minus).abs().max() > 1e-3)
    checks["alpha0_equals_no_hook"] = bool(torch.equal(zero, base))
    checks["teacher_forcing_prefix_untouched"] = bool(torch.equal(tf[0, :gs], base[0, :gs]))
    checks["teacher_forcing_suffix_changed"] = bool((tf[0, gs:] - base[0, gs:]).abs().max() > 1e-3)
    kw = generate_kwargs([1], TEMPERATURE, max_new_tokens=1, pad_token_id=model.config.pad_token_id or 0,
                         eos_token_id=(model.config.eos_token_id,) if isinstance(model.config.eos_token_id, int) else tuple(model.config.eos_token_id or ()))
    gc = GenerationConfig(**{k: v for k, v in kw.items() if k != "logits_processor"})
    procs = model._get_logits_processor(generation_config=gc, input_ids_seq_length=len(ids), encoder_input_ids=None,
                                        prefix_allowed_tokens_fn=None, logits_processor=kw["logits_processor"],
                                        device=str(model.device), model_kwargs={}, negative_prompt_ids=None,
                                        negative_prompt_attention_mask=None)
    checks["no_temperature_warper"] = not has_temperature_warper(procs)
    names = [type(p).__name__ for p in procs]
    checks["processor_list_is_sampler_only"] = names == ["SeededGumbelSampler"]
    return checks


def sampler_chi2(model, ids: Sequence[int], n: int = 5000, temperature: float = TEMPERATURE, batch_size: int = 256,
                 seed0: int = 1, min_expected: float = 5.0) -> Dict[str, float]:
    """First-token frequencies of ``generate`` (sampler path) vs softmax(logits/T): χ² p-value (bins with expected
    count < ``min_expected`` pooled into one)."""
    import torch
    from scipy import stats

    from ..inference.hf_engine import _pad_id, clean_forward
    from ..inference.sampling import generate_kwargs

    with torch.no_grad():
        logits = clean_forward(model, [ids])[0].logits.float()[0, -1]
        p = torch.softmax(logits / temperature, -1).cpu().numpy().astype(float)
        counts = np.zeros_like(p)
        pad = _pad_id(model, None)
        eos = model.config.eos_token_id
        eos = (eos,) if isinstance(eos, int) else tuple(eos or ())
        done = 0
        while done < n:
            b = min(batch_size, n - done)
            seeds = [seed0 + done + i for i in range(b)]
            kw = generate_kwargs(seeds, temperature, max_new_tokens=1, pad_token_id=pad, eos_token_id=eos, device=str(model.device))
            x = torch.tensor([list(ids)] * b, device=model.device)
            out = model.generate(input_ids=x, attention_mask=torch.ones_like(x), **kw)
            for t in out[:, -1].tolist():
                counts[t] += 1
            done += b
    exp = p * n
    big = exp >= min_expected
    obs = np.concatenate([counts[big], [counts[~big].sum()]]) if (~big).any() else counts[big]
    ex = np.concatenate([exp[big], [exp[~big].sum()]]) if (~big).any() else exp[big]
    keep = ex > 0
    chi2, pval = stats.chisquare(obs[keep], ex[keep] * obs[keep].sum() / ex[keep].sum())
    return dict(chi2=float(chi2), p=float(pval), n=float(n), n_bins=float(keep.sum()))


# ---------------------------------------------------------------- G0.3 cache-reuse vs recompute (§4.2 appendix regime)
def generate_with_cache(model, ids: Sequence[int], *, max_new_tokens: int, greedy: bool = True, seed: Optional[int] = None,
                        temperature: float = 0.7, eos_ids: Sequence[int] = (IM_END, ENDOFTEXT), pad_id: Optional[int] = None) -> Dict[str, object]:
    """One sequence through ``generate(..., return_dict_in_generate=True, use_cache=True)`` (plan §4.2 appendix regime):
    returns the raw generated ids (cut after the first EOS), ``cached_ids`` = the ids the returned cache covers (prompt +
    every generated token except the last one sampled), the cache object and its reported length.  A Steer hook on
    ``model`` is left in whatever state the caller set (G0.3 runs it at alpha 0 / off)."""
    import torch
    from ..inference.hf_engine import _pad_id
    from ..inference.sampling import generate_kwargs

    ids = [int(x) for x in ids]
    inp = torch.tensor([ids], device=model.device)
    att = torch.ones_like(inp)
    pad = _pad_id(model, pad_id)
    if greedy:
        kw = dict(do_sample=False, temperature=None, top_k=None, top_p=None, min_p=None, repetition_penalty=1.0,
                  max_new_tokens=max_new_tokens, pad_token_id=pad, eos_token_id=list(eos_ids))
    else:
        kw = generate_kwargs([0 if seed is None else int(seed)], temperature=temperature, max_new_tokens=max_new_tokens,
                             pad_token_id=pad, eos_token_id=tuple(eos_ids), device=str(inp.device))
    with torch.no_grad():
        out = model.generate(input_ids=inp, attention_mask=att, use_cache=True, return_dict_in_generate=True, **kw)
    g = out.sequences[0, inp.shape[1]:].tolist()
    cut = next((k for k, t in enumerate(g) if t in eos_ids), None)
    g = g[: cut + 1] if cut is not None else g
    past = out.past_key_values
    cached_ids = ids + g[:-1]
    n_cached = int(past.get_seq_length()) if hasattr(past, "get_seq_length") else len(cached_ids)
    return dict(gen_ids=g, cached_ids=cached_ids, past=past, n_cached=n_cached)


def cache_vs_recompute_kl(model, items: Sequence[Tuple[Sequence[int], Sequence[int]]], cached_prefix_len: Optional[Sequence[int]] = None,
                          caches: Optional[Sequence[Tuple[Sequence[int], object]]] = None) -> Dict[str, object]:
    """items: (ids_2, suffix) with suffix = normalised y_2_ids + delta_ids(x_3) so that ids_3 = ids_2 + suffix.

    Cache-reuse regime (plan §4.2 appendix, v1.4 rule, memo I2).  With ``caches[i] = (cached_ids, past)`` from
    ``generate_with_cache`` the cache's actual length (``past.get_seq_length()``) is read, the ids it covers must equal the
    leading ids of ids_3 **bitwise** (normalisation may have rewritten the EOS or stripped a think block), and only the
    uncovered suffix is fed with the positions/attention of the full history.  Any mismatch makes the item "cache 不适用":
    KL = NaN, counted in ``n_not_applicable`` with its reason, never spliced into a wrong history and never a pass.
    Without ``caches`` the cache is built here on ids_3[:L] (L = len(ids_2), or ``cached_prefix_len[i]``), which
    exercises the suffix-feeding arithmetic only.  Returns dict(kl, n_not_applicable, reasons, n); KL is
    KL(P_cache || P_recompute) of the fp32 first-token distribution."""
    import copy
    import torch

    kls: List[float] = []
    reasons: List[Optional[str]] = []
    with torch.no_grad():
        for i, (ids_2, suffix) in enumerate(items):
            full_ids = [int(x) for x in ids_2] + [int(x) for x in suffix]
            if caches is not None:
                cached_ids, past = caches[i]
                cached_ids = [int(x) for x in cached_ids]
                L = len(cached_ids)
                n_cached = int(past.get_seq_length()) if hasattr(past, "get_seq_length") else L
                reason = None
                if n_cached != L:
                    reason = f"cache length {n_cached} != {L} covered ids"
                elif not (0 < L < len(full_ids)):
                    reason = f"cache covers {L} of {len(full_ids)} ids (needs 0 < L < len(ids_3))"
                elif full_ids[:L] != cached_ids:
                    k = next((k for k in range(L) if full_ids[k] != cached_ids[k]), L)
                    reason = f"cached ids are not a prefix of ids_3 (first difference at {k}; normalisation changed y_2?)"
                if reason is not None:
                    kls.append(float("nan")); reasons.append(reason)
                    continue
                past = copy.deepcopy(past)                      # feeding the suffix extends the cache: keep the caller's intact
            else:
                L = len(ids_2) if cached_prefix_len is None else int(cached_prefix_len[i])
                if not (0 < L < len(full_ids)):
                    raise ValueError(f"cached prefix length {L} must lie in (0, {len(full_ids)})")
                a = torch.tensor([full_ids[:L]], device=model.device)
                past = model(input_ids=a, use_cache=True).past_key_values
                n_cached = past.get_seq_length() if hasattr(past, "get_seq_length") else a.shape[1]
                if int(n_cached) != L:
                    raise RuntimeError(f"cache covers {n_cached} positions, expected {L}")
            s_ = torch.tensor([full_ids[L:]], device=model.device)
            pos = torch.arange(L, len(full_ids), device=model.device)[None]
            att = torch.ones(1, len(full_ids), dtype=torch.long, device=model.device)
            o2 = model(input_ids=s_, past_key_values=past, attention_mask=att, position_ids=pos, use_cache=True)
            lp_cache = torch.log_softmax(o2.logits.float()[0, -1], -1)
            full = torch.tensor([full_ids], device=model.device)
            lp_full = torch.log_softmax(model(input_ids=full, use_cache=False).logits.float()[0, -1], -1)
            kls.append(float((lp_cache.exp() * (lp_cache - lp_full)).sum()))
            reasons.append(None)
    kl = np.asarray(kls, float)
    return dict(kl=kl, n_not_applicable=int(np.isnan(kl).sum()), reasons=reasons, n=int(kl.size))


# ---------------------------------------------------------------- G0.7 support defect
def support_defect_logps(model, items: Sequence[Tuple[Sequence[int], Sequence[int]]]) -> np.ndarray:
    """items: (prompt_ids, assistant_ids) of alpha=±1 steered responses; returns log P^0 of every response token."""
    from ..inference.hf_engine import response_logprobs

    out = []
    for prompt, resp in items:
        lp = response_logprobs(model, list(prompt) + list(resp), len(prompt))
        out.append(np.asarray(lp.detach().cpu().numpy() if hasattr(lp, "cpu") else lp, dtype=float).ravel())
    return np.concatenate(out) if out else np.zeros(0)


# ---------------------------------------------------------------- G0.1 template consistency (§4.1)
def template_consistency(trajectories: Sequence[Trajectory], builder: TurnBuilder, first_turn_ids: Callable[[str], List[int]],
                         text_path_ids: Callable[[List[dict]], List[int]], system_prompt: str) -> Tuple[int, int, List[dict], int]:
    """Rebuild ids_t (t>=2) via id concatenation and via the chat-template text path; count trajectories with any
    mismatch.  ``text_path_ids(messages)`` = tokenizer.apply_chat_template(messages, add_generation_prompt=True, ...).
    Returns (n_mismatch, n_total, examples, segment_mismatches) — the last is the builder's §4.1 whole-increment vs
    piecewise encoding mismatch count accrued during this rebuild (v1.4, memo I1; reported by G0.1)."""
    n_mis, n_tot, examples = 0, 0, []
    seg0 = int(getattr(builder, "segment_mismatches", 0))
    for traj in trajectories:
        xs = [tr.user_text for tr in traj.turns]
        ids = list(first_turn_ids(xs[0]))
        msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": xs[0]}]
        bad = None
        for t in range(2, len(traj.turns) + 1):
            prev = traj.turns[t - 2]
            ids, _, _ = builder.next_turn_ex(ids, prev.assistant_ids, xs[t - 1])
            msgs = msgs + [{"role": "assistant", "content": prev.assistant_text}, {"role": "user", "content": xs[t - 1]}]
            text_ids = list(text_path_ids(msgs))
            if text_ids != ids:
                bad = dict(traj_id=traj.traj_id, turn=t, n_id=len(ids), n_text=len(text_ids),
                           first_diff=next((k for k in range(min(len(ids), len(text_ids))) if ids[k] != text_ids[k]), min(len(ids), len(text_ids))))
                break
        n_tot += 1
        if bad:
            n_mis += 1
            if len(examples) < 20:
                examples.append(bad)
    return n_mis, n_tot, examples, int(getattr(builder, "segment_mismatches", 0)) - seg0


# ---------------------------------------------------------------- rollout-level orchestration (G0.4 / G0.5 / G0.8)
def continuation_specs(run_id: str, prefixes: Sequence[Tuple[object, Prefix]], n_per_prefix: int, *, idx0: int = 64,
                       script: str = "A3", block: str = "est", arm: Optional[Arm] = None, **kw) -> List[RolloutSpec]:
    """prefixes: (BankProblem, Prefix h_t) pairs; one spec per (prefix, trajectory_idx in idx0..idx0+n)."""
    specs = []
    for problem, pre in prefixes:
        for j in range(n_per_prefix):
            specs.append(spec_from_prefix(pre, run_id=run_id, problem=problem, script=script, arm=arm or Arm.null(),
                                          trajectory_idx=idx0 + j, block=block, **kw))
    return specs


def e_t_by_prefix(trajs: Sequence[Trajectory], t: int = 3) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """(e_t array, cluster ids, prefix ids in order) — rows ordered as the input trajectories."""
    pids = sorted({tr.prefix_id for tr in trajs})
    idx = {p: i for i, p in enumerate(pids)}
    e = np.array([tr.outcomes["e"][t - 1] for tr in trajs], dtype=float)
    cl = np.array([idx[tr.prefix_id] for tr in trajs])
    return e, cl, [tr.prefix_id for tr in trajs]


def batch_conditions(specs: Sequence[RolloutSpec], run: Callable[[Sequence[RolloutSpec], int], List[Trajectory]],
                     seed: int = 20261016) -> Dict[str, List[Trajectory]]:
    """G0.5: the same specs under three batch compositions.  ``run(specs_in_order, batch_size)`` must respect order.
    Returns trajectories re-sorted to the original spec order for each condition."""
    key = lambda tr: (tr.prefix_id, tr.trajectory_idx)
    order = {(s.root.prefix_id if s.root else "", s.trajectory_idx): i for i, s in enumerate(specs)}
    def resort(trs):
        return sorted(trs, key=lambda tr: order[key(tr)])
    out = {}
    out["batch1"] = resort(run(list(specs), 1))
    shuffled = list(specs)
    random.Random(seed).shuffle(shuffled)
    out["batch8_random"] = resort(run(shuffled, 8))
    grouped = sorted(specs, key=lambda s: (s.arm.arm_id(), s.root.prefix_id if s.root else "", s.trajectory_idx))
    out["batch8_grouped"] = resort(run(grouped, 8))
    return out


def paired_e3(cond_a: Sequence[Trajectory], cond_b: Sequence[Trajectory]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    ea, cl, pa = e_t_by_prefix(cond_a)
    eb, _, pb = e_t_by_prefix(cond_b)
    if pa != pb:
        raise ValueError("conditions are not aligned")
    return ea, eb, cl


def greedy_agreement(trajs_a: Sequence[Trajectory], trajs_b: Sequence[Trajectory], t: int = 3) -> float:
    """Share of paired greedy continuations whose first generated token agrees (G0.5 argmax criterion)."""
    agree = [ta.turns[t - 1].assistant_ids[0] == tb.turns[t - 1].assistant_ids[0] for ta, tb in zip(trajs_a, trajs_b)]
    return float(np.mean(agree)) if agree else float("nan")


# ---------------------------------------------------------------- G0.4 text-state equivalence (§7.1), two phases
def _run_specs_keep(ctx, specs: Sequence[RolloutSpec], stage: str, judge: bool = True) -> Tuple[List[Trajectory], bool]:
    """Like ``stages.run_specs`` but returns the in-memory Trajectory objects (carrying ``next_ids``) when the stage runs
    fresh.  If every spec is already in the stage file the trajectories are loaded from JSONL (second value False)."""
    import os
    from .. import stages as _st
    from ..rollout import run_rollouts, spec_traj_id
    from ..trajectory import JsonlWriter

    path = os.path.join(ctx.run_path, "trajectories", f"{stage}.jsonl")
    done = _st.existing_traj_ids([path])
    todo = [sp for sp in specs if not done or spec_traj_id(sp, ctx.builder, ctx.first_turn_ids, ctx.decode) not in done]
    if not todo:
        return _st.run_specs(ctx, specs, stage, judge=judge), False
    if len(todo) != len(specs):
        raise RuntimeError(f"stage {stage} is partially complete; G0.4 phase 1 must run in one process (delete {path} to rerun it)")
    with JsonlWriter(path) as w:
        trajs = run_rollouts(specs, builder=ctx.builder, router=ctx.router, first_turn_ids=ctx.first_turn_ids, decode=ctx.decode,
                             judge=ctx.judge if judge else None, judge2=ctx.judge2 if judge else None, writer=w, zstore=ctx.extra.get("zstore"))
    return trajs, True


def _hook_present(ctx) -> Optional[bool]:
    """Whether the router's steered (HF) engine has a Steer hook attached; None when not observable (fake engine)."""
    eng = getattr(ctx.router, "steered", None)
    if eng is None or not hasattr(eng, "steer"):
        return None
    return eng.steer is not None


def g04_phase1(ctx, h2_prefixes: Sequence[Tuple[object, Prefix]], *, n_y2: int = 8, n_cont: int = 32, alphas: Sequence[float] = (0.5, -0.5),
               arm_builder: Callable[[float], Arm] = None, stage: str = "G04_phase1", logits_fn: Optional[Callable] = None,
               engine: str = "hf") -> Dict[str, object]:
    """Path (i), in-process (plan §7.1 G0.4 design note): for each h_2 and alpha in ±0.5 generate n_y2 steered y_2
    (stop_after=2), then continue turn 3 from the **in-memory** ids_3 (``Trajectory.next_ids``: built by the generating
    process, no JSONL round trip) in the same process, on the same Steer instance with alpha set to 0 (``engine="hf"``
    forces the hooked HF engine even at alpha 0) and the same batch composition: 1 greedy + n_cont sampled continuations
    (trajectory_idx 64..), plus the fp32 first-token logits ``logits_fn(ids_3)`` when given.  Returns what phase 2 needs
    (y_2 trajectories, in-process ids_3 hashes, greedy ids, logits, e_3 rates) and the design flags ``hook_present``
    (None when not observable) and ``in_memory``."""
    from ..rollout import prefix_with_spans
    from ..stages import run_specs

    by_pid = {p.problem_id: p for p, _ in h2_prefixes}
    specs = []
    for problem, pre in h2_prefixes:
        for a in alphas:
            arm = arm_builder(a) if arm_builder else Arm(u=[0, (1.0 if a > 0 else -1.0), 0, 0], direction="v_rand", layer=20, alpha_max=abs(a),
                                                         scope="S_gen", fold_version=0)
            for j in range(n_y2):
                specs.append(spec_from_prefix(pre, run_id=ctx.run_id, problem=problem, script="A3", arm=arm, trajectory_idx=64 + j, block="est",
                                              stop_after=2, stage="G04_y2", extra=dict(g04_h2=pre.prefix_id, g04_alpha=a)))
    y2, in_memory = _run_specs_keep(ctx, specs, stage + "_y2")
    cont_specs, greedy, logits, pre3_of = [], {}, {}, {}
    for tr in y2:
        rebuilt = prefix_from_trajectory(tr, ctx.builder, ctx.first_turn_ids, upto_turn=3, problem=by_pid[tr.problem_id])
        if getattr(tr, "next_ids", None) is not None:
            pre3 = prefix_with_spans(Prefix(ids=list(tr.next_ids), turns=rebuilt.turns), tr.next_spans[0], tr.next_spans[1])
        else:
            in_memory = False
            pre3 = rebuilt
        pre3_of[tr.traj_id] = pre3
        for j in range(n_cont):
            cont_specs.append(spec_from_prefix(pre3, run_id=ctx.run_id, problem=by_pid[tr.problem_id], script="A3", arm=Arm.null(),
                                               trajectory_idx=64 + j, block="est", stop_after=3, stage="G04_cont_i", engine=engine,
                                               extra=dict(g04_h2=tr.extra["g04_h2"], g04_y2=tr.traj_id, g04_path="i", ids3_hash=pre3.prefix_id)))
    conts = run_specs(ctx, cont_specs, stage + "_cont_i", judge=True)
    for tr in y2:
        pre3 = pre3_of[tr.traj_id]
        res = ctx.router.generate([GenRequest(pre3.ids, seed=0, alpha=0.0, max_new_tokens=32, greedy=True, engine=engine)])[0]
        greedy[tr.traj_id] = dict(ids3_hash=pre3.prefix_id, greedy_ids=res.ids)
        if logits_fn is not None:
            logits[tr.traj_id] = np.asarray(logits_fn(list(pre3.ids)), dtype=np.float32)
    return dict(y2=y2, conts=conts, greedy=greedy, first_logits=logits, hook_present=_hook_present(ctx), in_memory=in_memory, engine=engine)


def g04_phase2(ctx, h2_prefixes: Sequence[Tuple[object, Prefix]], phase1_y2: Sequence[Trajectory], text_path_ids: Optional[Callable] = None, *,
               n_cont: int = 32, stage: str = "G04_phase2", idx0: int = 96, logits_fn: Optional[Callable] = None, engine: str = "hf") -> Dict[str, object]:
    """Paths (ii)/(iii), new process without the hook: rebuild ids_3 from the JSONL ``assistant_ids`` via §4.1 id
    concatenation (ii) and from ``assistant_text`` via the chat template (iii); compare ids and the greedy continuation
    bitwise on the same HF engine class with no Steer attached (``hook_absent`` records whether that held), take the
    first-token logits, then sample n_cont continuations on a DISJOINT trajectory_idx range (idx0..) so that the paired
    TOST on e_3 tests distributional equivalence rather than replaying phase 1's seeds (v1.4, G0.4 design note).
    ``phase1_y2`` are the JSONL-loaded trajectories; in-memory ``next_ids`` are ignored here by design."""
    from ..stages import run_specs

    by_pid = {p.problem_id: p for p, _ in h2_prefixes}
    specs, text_mismatch, greedy2, logits = [], 0, {}, {}
    for tr in phase1_y2:
        pre3 = prefix_from_trajectory(tr, ctx.builder, ctx.first_turn_ids, upto_turn=3, problem=by_pid[tr.problem_id])
        if text_path_ids is not None:
            msgs = [{"role": "system", "content": ctx.config["system_prompt"]}]
            for k, t in enumerate(tr.turns):
                msgs += [{"role": "user", "content": t.user_text}, {"role": "assistant", "content": t.assistant_text}]
            xs = user_turns("A3", S=by_pid[tr.problem_id].statement_zh, D=by_pid[tr.problem_id].distractor or "")
            msgs.append({"role": "user", "content": xs[2]})
            if list(text_path_ids(msgs)) != list(pre3.ids):
                text_mismatch += 1
        res = ctx.router.generate([GenRequest(pre3.ids, seed=0, alpha=0.0, max_new_tokens=32, greedy=True, engine=engine)])[0]
        greedy2[tr.traj_id] = dict(ids3_hash=pre3.prefix_id, greedy_ids=res.ids)
        if logits_fn is not None:
            logits[tr.traj_id] = np.asarray(logits_fn(list(pre3.ids)), dtype=np.float32)
        for j in range(n_cont):
            specs.append(spec_from_prefix(pre3, run_id=ctx.run_id, problem=by_pid[tr.problem_id], script="A3", arm=Arm.null(), trajectory_idx=idx0 + j,
                                          block="est", stop_after=3, stage="G04_cont_ii", engine=engine,
                                          extra=dict(g04_h2=tr.extra["g04_h2"], g04_y2=tr.traj_id, g04_path="ii", ids3_hash=pre3.prefix_id)))
    conts = run_specs(ctx, specs, stage + "_cont_ii", judge=True)
    hp = _hook_present(ctx)
    return dict(conts=conts, greedy=greedy2, first_logits=logits, text_path_mismatch_rate=(text_mismatch / max(1, len(phase1_y2))),
                hook_absent=(None if hp is None else (not hp)), engine=engine)


def g04_inputs(p1: Dict[str, object], p2: Dict[str, object], first_logit_maxdiff: Optional[float] = None, require_design: bool = True) -> Dict[str, object]:
    """Pair phase-1 and phase-2 continuations by y_2; clusters = h_2 (plan v1.3).  The first-token logit difference is
    taken from the two phases' ``first_logits`` unless given; ``design_ok``/``design_notes`` record whether the phases ran as
    the §7.1 design note requires (hooked HF engine + in-memory ids_3 in phase 1, no hook in phase 2, logits measured)."""
    e_i, e_ii, cl = [], [], []
    h2_index = {}
    by_i: Dict[str, List[float]] = {}
    for tr in p1["conts"]:
        by_i.setdefault(tr.extra["g04_y2"], []).append(float(tr.outcomes["e"][2]))
    by_ii: Dict[str, List[float]] = {}
    for tr in p2["conts"]:
        by_ii.setdefault(tr.extra["g04_y2"], []).append(float(tr.outcomes["e"][2]))
    h2_of = {tr.extra["g04_y2"]: tr.extra["g04_h2"] for tr in p1["conts"]}
    for y2id in sorted(set(by_i) & set(by_ii)):
        n = min(len(by_i[y2id]), len(by_ii[y2id]))
        e_i += by_i[y2id][:n]; e_ii += by_ii[y2id][:n]
        cl += [h2_index.setdefault(h2_of[y2id], len(h2_index))] * n
    ids_identical = all(p1["greedy"][k]["ids3_hash"] == p2["greedy"][k]["ids3_hash"] for k in p2["greedy"] if k in p1["greedy"])
    greedy_identical = all(p1["greedy"][k]["greedy_ids"] == p2["greedy"][k]["greedy_ids"] for k in p2["greedy"] if k in p1["greedy"])
    if first_logit_maxdiff is None:
        l1, l2 = p1.get("first_logits", {}) or {}, p2.get("first_logits", {}) or {}
        common = [k for k in l2 if k in l1]
        first_logit_maxdiff = max((float(np.max(np.abs(l1[k].astype(np.float64) - l2[k].astype(np.float64)))) for k in common), default=float("nan"))
    notes = []
    if p1.get("hook_present") is False:
        notes.append("phase 1 ran without a Steer hook (design: same Steer instance, alpha 0)")
    if not p1.get("in_memory", False):
        notes.append("phase 1 ids_3 were rebuilt from JSONL instead of taken from memory (phase 1 resumed from a stage file?)")
    if p2.get("hook_absent") is False:
        notes.append("phase 2 ran with a Steer hook attached (design: new process, no hook)")
    if not np.isfinite(first_logit_maxdiff):
        notes.append("first-token logits not measured (pass logits_fn to both phases)")
    design_ok = (not notes) if require_design else True
    return dict(e3_same_process=np.array(e_i), e3_rebuilt=np.array(e_ii), h2_cluster=np.array(cl), ids_identical=ids_identical,
                greedy_identical=greedy_identical, first_logit_maxdiff=float(first_logit_maxdiff), text_path_mismatch_rate=p2["text_path_mismatch_rate"],
                design_ok=design_ok, design_notes="; ".join(notes))


# ---------------------------------------------------------------- G0.8 cross-stack
def cross_stack(ctx_hf, ctx_vllm, specs: Sequence[RolloutSpec], stage: str = "G08") -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Same specs (hence the same seeds) on two engines; returns (e3_hf, e3_vllm, h3 clusters) paired by (prefix, idx)."""
    from ..stages import run_specs
    a = run_specs(ctx_hf, specs, stage + "_hf")
    b = run_specs(ctx_vllm, specs, stage + "_vllm")
    key = lambda tr: (tr.prefix_id, tr.trajectory_idx)
    bm = {key(tr): tr for tr in b}
    ea, eb, cl, idx = [], [], [], {}
    for tr in a:
        if key(tr) in bm:
            ea.append(float(tr.outcomes["e"][2])); eb.append(float(bm[key(tr)].outcomes["e"][2])); cl.append(idx.setdefault(tr.prefix_id, len(idx)))
    return np.array(ea), np.array(eb), np.array(cl)
