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
def cache_vs_recompute_kl(model, items: Sequence[Tuple[Sequence[int], Sequence[int]]]) -> np.ndarray:
    """items: (ids_2, suffix) with suffix = y_2_ids + delta_ids(x_3) so that ids_3 = ids_2 + suffix.
    Returns KL(P_cache || P_recompute) of the fp32 first-token distribution per item (B=1, no padding)."""
    import torch

    kls = []
    with torch.no_grad():
        for ids_2, suffix in items:
            a = torch.tensor([list(ids_2)], device=model.device)
            out = model(input_ids=a, use_cache=True)
            past = out.past_key_values
            s = torch.tensor([list(suffix)], device=model.device)
            pos = torch.arange(a.shape[1], a.shape[1] + s.shape[1], device=model.device)[None]
            att = torch.ones(1, a.shape[1] + s.shape[1], dtype=torch.long, device=model.device)
            o2 = model(input_ids=s, past_key_values=past, attention_mask=att, position_ids=pos, use_cache=True)
            lp_cache = torch.log_softmax(o2.logits.float()[0, -1], -1)
            full = torch.tensor([list(ids_2) + list(suffix)], device=model.device)
            lp_full = torch.log_softmax(model(input_ids=full, use_cache=False).logits.float()[0, -1], -1)
            kls.append(float((lp_cache.exp() * (lp_cache - lp_full)).sum()))
    return np.asarray(kls)


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
                         text_path_ids: Callable[[List[dict]], List[int]], system_prompt: str) -> Tuple[int, int, List[dict]]:
    """Rebuild ids_t (t>=2) via id concatenation and via the chat-template text path; count trajectories with any
    mismatch.  ``text_path_ids(messages)`` = tokenizer.apply_chat_template(messages, add_generation_prompt=True, ...)."""
    n_mis, n_tot, examples = 0, 0, []
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
    return n_mis, n_tot, examples


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
def g04_phase1(ctx, h2_prefixes: Sequence[Tuple[object, Prefix]], *, n_y2: int = 8, n_cont: int = 32, alphas: Sequence[float] = (0.5, -0.5),
               arm_builder: Callable[[float], Arm] = None, stage: str = "G04_phase1") -> Dict[str, object]:
    """In-process: for each h_2 and alpha in ±0.5 generate n_y2 steered y_2 (stop_after=2), then continue turn 3 for each y_2
    in the SAME process / Steer instance / batch composition: 1 greedy + n_cont sampled (alpha = 0).  Returns the records
    needed by phase 2 (assistant ids + texts of y_2, in-process ids_3 hashes, greedy first tokens, e_3 rates)."""
    from ..stages import run_specs
    specs = []
    for problem, pre in h2_prefixes:
        for a in alphas:
            arm = arm_builder(a) if arm_builder else Arm(u=[0, (1.0 if a > 0 else -1.0), 0, 0], direction="v_rand", layer=20, alpha_max=abs(a),
                                                         scope="S_gen", fold_version=0)
            for j in range(n_y2):
                specs.append(spec_from_prefix(pre, run_id=ctx.run_id, problem=problem, script="A3", arm=arm, trajectory_idx=64 + j, block="est",
                                              stop_after=2, extra=dict(g04_h2=pre.prefix_id, g04_alpha=a)))
    y2 = run_specs(ctx, specs, stage + "_y2", judge=True)
    # continuation specs (alpha = 0) from the in-memory y_2 trajectories; greedy handled by a dedicated request
    cont_specs = []
    for tr in y2:
        pre3 = prefix_from_trajectory(tr, ctx.builder, ctx.first_turn_ids, upto_turn=3, problem=next(p for p, _ in h2_prefixes if p.problem_id == tr.problem_id))
        for j in range(n_cont):
            cont_specs.append(spec_from_prefix(pre3, run_id=ctx.run_id, problem=next(p for p, _ in h2_prefixes if p.problem_id == tr.problem_id), script="A3",
                                               arm=Arm.null(), trajectory_idx=64 + j, block="est", stop_after=3,
                                               extra=dict(g04_h2=tr.extra["g04_h2"], g04_y2=tr.traj_id, g04_path="i", ids3_hash=pre3.prefix_id)))
    conts = run_specs(ctx, cont_specs, stage + "_cont_i", judge=True)
    greedy = {}
    for tr in y2:
        pre3 = prefix_from_trajectory(tr, ctx.builder, ctx.first_turn_ids, upto_turn=3, problem=next(p for p, _ in h2_prefixes if p.problem_id == tr.problem_id))
        res = ctx.router.generate([GenRequest(pre3.ids, seed=0, alpha=0.0, max_new_tokens=32, greedy=True)])[0]
        greedy[tr.traj_id] = dict(ids3_hash=pre3.prefix_id, greedy_ids=res.ids)
    return dict(y2=y2, conts=conts, greedy=greedy)


def g04_phase2(ctx, h2_prefixes: Sequence[Tuple[object, Prefix]], phase1_y2: Sequence[Trajectory], text_path_ids: Optional[Callable] = None, *,
               n_cont: int = 32, stage: str = "G04_phase2") -> Dict[str, object]:
    """New process, no hook: rebuild ids_3 from the JSONL assistant_ids (path ii) and from assistant_text via the chat
    template (path iii); compare, then continue (greedy 1 + n_cont sampled).  Returns the g0_4 inputs."""
    from ..stages import run_specs
    by_pid = {p.problem_id: p for p, _ in h2_prefixes}
    specs, ids_identical, text_mismatch, greedy2 = [], True, 0, {}
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
        res = ctx.router.generate([GenRequest(pre3.ids, seed=0, alpha=0.0, max_new_tokens=32, greedy=True)])[0]
        greedy2[tr.traj_id] = dict(ids3_hash=pre3.prefix_id, greedy_ids=res.ids)
        for j in range(n_cont):
            specs.append(spec_from_prefix(pre3, run_id=ctx.run_id, problem=by_pid[tr.problem_id], script="A3", arm=Arm.null(), trajectory_idx=64 + j,
                                          block="est", stop_after=3, extra=dict(g04_h2=tr.extra["g04_h2"], g04_y2=tr.traj_id, g04_path="ii", ids3_hash=pre3.prefix_id)))
    conts = run_specs(ctx, specs, stage + "_cont_ii", judge=True)
    return dict(conts=conts, greedy=greedy2, text_path_mismatch_rate=(text_mismatch / max(1, len(phase1_y2))))


def g04_inputs(p1: Dict[str, object], p2: Dict[str, object], first_logit_maxdiff: float = 0.0) -> Dict[str, object]:
    """Pair phase-1 and phase-2 continuations by y_2; clusters = h_2 (plan v1.3)."""
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
    return dict(e3_same_process=np.array(e_i), e3_rebuilt=np.array(e_ii), h2_cluster=np.array(cl), ids_identical=ids_identical,
                greedy_identical=greedy_identical, first_logit_maxdiff=first_logit_maxdiff, text_path_mismatch_rate=p2["text_path_mismatch_rate"])


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
