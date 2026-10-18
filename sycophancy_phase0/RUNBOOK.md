# RUNBOOK — Phase-0 execution with `sycophancy_phase0`

The specification is `docs/research/sycophancy-phase0-execution-plan.md` (v1.4). This file maps the spec onto the code;
when they disagree, the spec wins and the disagreement is a bug to report (plan §0.4, last bullet).

## 0. Hard rules you must enforce while running (plan §0)
- Never change a `[F]` parameter after G1's `est` block has been looked at; later changes go to `runs/<run_id>/DEVIATIONS.md`
  via `run.record_deviation`.
- Selection only on `sel`-block, pre-treatment quantities (`gates.g15.select_prefixes` reads `stats[...]["sel"]`); effects only on `est`.
- Seeds are derived, never shared across arms (`inference.sampling.derive_seed`; `Arm.arm_id()`); `enable_prefix_caching=False` in vLLM.
- One `SeededGumbelSampler` per `generate` call (the engines build one per call); reusing one without `reset()` raises (plan §4.3, round 7).
- z extraction: an empty previous-assistant span (unclosed think block) yields a NaN R3 row with `valid.R3=false`; keep the trajectory, drop the row in probes (plan §4.5).
- The §7.10 u_1 inoculation arm is NOT screened on e_1 (intention-to-treat); every other analysis keeps the §3 first-turn screen.
- Stop and report (do not improvise) on: any G0 failure (except the G0.3 median-only tier, plan §7.1); G1 N_q < 30; any GREY; judge parse failure > 1%; template mismatch > 1%;
  truncation > 5% (the single allowed fix is `max_new_tokens=768`, recorded as a deviation).

## 1. Environment
```
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e "sycophancy_phase0[hf,test]"           # transformers==4.57.1 pinned
pip install vllm>=0.9 datasets pyarrow matplotlib        # vLLM for alpha=0 rollouts; datasets for GSM8K; optional plots
cd sycophancy_phase0 && pytest -q                        # must be green (CPU tiny-model + fake-engine tests)
```
Record model weight SHA-256 (`sha256sum` over the safetensors) into `runs/<run_id>/config.yaml` (`run.init_run` stores env/git).

Judge servers (separate processes/GPUs, plan §2.1):
```
vllm serve meta-llama/Llama-3.3-70B-Instruct --tensor-parallel-size 2 --dtype bfloat16 --port 8001
vllm serve Qwen/Qwen2.5-72B-Instruct       --tensor-parallel-size 2 --dtype bfloat16 --port 8002   # J2, 20% cross-check
```

## 2. Build the context
```python
from sycophancy_phase0.run import Context, DEFAULT_CONFIG
ctx = Context.from_config(root=".", run_id="R1", config=DEFAULT_CONFIG, use_vllm=True,
                          judge_url="http://localhost:8001/v1", judge2_url="http://localhost:8002/v1")
```
`Context.from_config` loads the HF model in bf16 (steered generation, teacher forcing, activations), a `VLLMEngine` for every
alpha = 0 request (`EngineRouter`), and the judge clients (`scoring.judge.make_judge`, Appendix E prompt, 3-stage parsing).

## 3. Stage order (plan §1 dependency graph) and what to check
| step | call | outputs | check before continuing |
| --- | --- | --- | --- |
| data | `run.stage_data(ctx, gsm_rows, zh_rows)` (rows from `data.f1.load_from_hub`) | `data/F1.jsonl F2.jsonl F3.jsonl` | F1 `needs_translation` rows: run `data.f1.translation_prompt` through J2 and `back_translation_prompt` through J1, then `apply_translations`; F2 instances: solve once with J2 (`data.f2.unambiguity_check_prompt`), drop mismatches and record |
| mine | `stages.stage_mine(ctx)` | `data/mining.json pools.json folds.json` | report per-family exclusion rate; main pool size |
| r_L | `gpu_glue.calibrate_r_L(ctx, 200 A3 turn-2 prompts)` | `configs/r_L.json` | plan §4.6 |
| G0 | `gates.g0_runner.*` + `gates.g0.*` (see §4 below) | `GATES.md` G0 entry | all eight pass ⇒ GO; G0.3 median-only ⇒ GO with the cache regime disabled; G0.3 fault ⇒ KILL; G0.3 coverage/q95 ⇒ GREY; any other failure ⇒ KILL (plan §7.1) |
| G1 | `stages.stage_g1(ctx)` | `trajectories/G1.jsonl`, `tables/G1_summary.json`, `data/frontier.json` | decision GO / GO-with-caveat; truncation rate |
| G1.5 | `stages.stage_g15(ctx)` | `data/prefixes/prefix_bank.jsonl`, `trajectories/G15.jsonl` | z extraction for h_2/h_3 (`inference.hf_engine.extract_z` → `trajectory.ZStore`) |
| G2 | `stages.stage_g2(ctx, prebunk_texts)` (`gates.g2.prebunk_prompt` → J1) | `tables/G2_summary.json` | record notes (weak / actuator) |
| G2′-a | `stages.stage_g2a(ctx)` | `tables/G2a_summary.json` | κ₁ is a placeholder (15 nats) until G4-1; re-run `stage_g2a(ctx, kappa1=...)` after G4-1 |
| G3 | `stages_steer.stage_g3(ctx, features=gpu_glue.g3_features_for(ctx, bank, d_i, g_i))` | `tables/G3_summary.json` | thinking arm: build M_hybrid prefixes (plan §7.5) and pass `think_result` |
| G4-0 | `stages_steer.stage_g40(ctx, acts_fn=gpu_glue.acts_fn_for(ctx))` | `configs/directions/*.npy` | min cosine between LOFO versions |
| G4-1 | `stages_steer.stage_g41(ctx, gpu_glue.fine_grid_for(...), finish=gpu_glue.finish_for(...))` | `configs/alpha_max.json` | α_max ≥ 0.2 else switch layer |
| G2′-b | `stages_steer.stage_g2b(ctx)` | `tables/G2b_summary.json` | one-sided lower bound > 0 ⇒ GO |
| G4-2 | `stages_steer.stage_g42(ctx)` (+ exploratory directions with `primary=False`) | `tables/G42_*_summary.json` | axis decision + co-primary x₄ |
| G5 | `stages_steer.stage_g5(ctx)` then `stage_g5(ctx, confirm=True, u3_star=..., F=analysis.power.F_required(...))` | `tables/G5_*_summary.json` | u₃* frozen after the pilot |
| G6 | `stages_steer.stage_g6(ctx, stages_steer.g6_items(ctx))` | `tables/G6_summary.json` | |
| human validation | `scoring.human_validation.stratified_sample` → annotate → `agreement_report` | | if `ppi_switch.use_ppi`: re-report judge outcomes with `analysis.ppi` |
| report | `report.write_report(ctx.run_path, run_id, power_table, recommendation)`; `report.figures` | `REPORT.md`, `figures/` | |

## 4. G0 (plan §7.1) with the runner pieces
- G0.1 `n_mis, n_tot, examples, seg = g0_runner.template_consistency(trajs, builder, first_turn_ids, text_path_ids, SYSTEM_PROMPT)` → `g0.g0_1(n_mis, n_tot, seg)` (`seg` = §4.1 segment_mismatches, reported)
- G0.2 `g0_runner.hook_selfcheck(model, steer, ids)` + `g0_runner.sampler_chi2(model, ids, n=5000)` → `g0.g0_2`
- G0.3 per h_3 (hook off / alpha 0): `c = g0_runner.generate_with_cache(model, ids_2, max_new_tokens=..., greedy=False, seed=...)`, normalise `c["gen_ids"]` to y_2, then `r = g0_runner.cache_vs_recompute_kl(model, [(ids_2, y2_norm + delta_ids(x_3))...], caches=[(c["cached_ids"], c["past"])...])` → `g0.g0_3(r["kl"])` (NaN entries are counted as not applicable by the gate). Items whose normalised y_2 no longer matches the generated ids are "cache 不适用" (NaN, counted, never a pass).
- G0.4 `g0_runner.g04_phase1(ctx, h2_prefixes, logits_fn=gpu_glue.first_token_logits_fn(ctx))` with the Steer attached (steered y_2 with a seeded
  random unit vector at L=20 — `torch.Generator().manual_seed(20261016)`; turn-3 continuations from the in-memory ids_3 on the hooked HF engine at
  alpha 0, `engine="hf"`), then `g0_runner.g04_phase2(ctx2, h2_prefixes, y2_from_jsonl, text_path_ids, logits_fn=gpu_glue.first_token_logits_fn(ctx2))`
  in a FRESH process whose HF engine has no Steer, and `g0_runner.g04_inputs(p1, p2)` → `g0.g0_4` (clusters = h_2; `design_ok` must hold:
  phase 1 hooked + in-memory ids, phase 2 unhooked, logits measured in both)
- G0.5 `g0_runner.batch_conditions(specs, run)` → `g0_runner.paired_e3` + `greedy_agreement` → `g0.g0_5`
- G0.6 `controllers.contract_check(policy, ids_3, z_3, histories, n=50000, deterministic=...)` → `g0.g0_6`
- G0.7 `g0_runner.support_defect_logps(model, steered items)` → `g0.g0_7`
- G0.8 `g0_runner.cross_stack(ctx_hf, ctx_vllm, continuation_specs(...))` (same specs ⇒ same seeds ⇒ paired) → `g0.g0_8`
Then `g0.write_gates_md(results, GATES.md, run_id)` and `g0.write_g0_summary(run_path, results)`; GO with all eight present and passing, or with G0.3 in its median-only tier (plan §7.1).

## 5. Things the code does not do for you
- Download models/datasets; launch vLLM servers; the M_hybrid thinking-arm prefixes for G3 (build with `TurnBuilder(..., "hybrid_think")`
  and `max_new_tokens=4096`); the human annotation itself; figures beyond the CSV/PNG set in `report.figures`.
- Budget: `stages.budget_snapshot` appends the engines' token counters to `tables/budget.json` at every GATES entry (plan §7.13).


## 6. First GPU contact (2026-10-17, 1× A100-SXM4-80GB, sdpa, torch 2.8.0+cu128, transformers 4.57.1) — facts and the diagnostics to run before the formal G0

Facts (smoke run, not G0; three 64-token generations were T=0.7 samples truncated at 64): model resident 56.9 GiB bf16 (≈21 GiB
headroom, which does NOT by itself guarantee B=32), load 313 s; B=1 decode 6.5–6.9 tok/s; four-turn id-concat vs chat-template identical
(segment_mismatches 0, user_span offsets match); support defect 0/128 (min finite log p −6.0, T=1 convention at the time); real generate
cache covers prompt+gen−1 and verifies bitwise; single-sample cache-vs-recompute KL 4.3e-3 nats at T=1 (old convention — keep it as such;
the code now normalises logits/T). The hook self-check 6/6 of that run came from a locally patched script: the committed check compared
final logits at prefix positions and would have failed; fixed in round 9 (hooked layer's actual output, captured as the next layer's input).
Prefix final-logit max|Δ| 1.25 under suffix steering is a numerical suffix dependence whose source is still to be localised (plan §4.4).

Run these in this order (each minutes, none formal) before mining/r_L/G0:
1. Left padding + read-side mask: `g0_runner.hook_position_check(model, steer, seqs, alphas=[...], pad_id=...)` on prompts of different
   lengths in ONE left-padded batch — it captures the hooked layer's ACTUAL output and verifies per row that pad/unsteered positions are
   bitwise unchanged and steered positions moved by exactly α·r_L·v (not a final-logit comparison); then the same with
   `scope="S_read", pos_masks=read_mask_from_spans(...)`. `hook_selfcheck` is single-sequence and does not exercise padding.
2. Generation-path vs teacher-forced log-probs: `g0_runner.generation_vs_teacher_forcing(model, ids, max_new_tokens=512, seed=...)` —
   raw scores recorded inside the sampler (NOT `output_scores`), both paths at T=0.7, only the actually generated tokens (no appended
   EOS). Report max/mean/rms |Δ log p| per response over ≥20 prompts; then repeat under `attn_implementation="eager"` to see whether the
   attention backend drives the difference. Only after this may analyses that rely on response log-probs/gradients/KL be trusted.
3. Batch-composition preview (mini G0.5): compare FIRST-token distributions (or fix a common history and compare per position under
   teacher forcing) for B=1 vs B=8 with random peers; free continuations diverge after the first differing token, so do not compare them
   token-by-token.
4. Throughput 8 → 16 → 32: every request routed to the same engine (`GenRequest(..., engine="hf")`, so alpha=0 rows are not split off to
   the null engine), 256 new tokens, half the rows at α=0.5; report aggregate tok/s on GENERATED tokens and say whether prompt
   processing is included; record peak memory at each step and stop at the first OOM.
5. α preview at L=20 (`calibration.fine_grid_stats(model, steer, items, alphas=(0.125, 0.25, 0.5, 1, 2))`, T=0.7): the function
   evaluates BOTH signs for every |α| and reports kl_pos/kl_neg, so pass magnitudes only (negative entries would duplicate rows with
   swapped labels); α=0 is G0.2's `alpha0_equals_no_hook`. A random direction only establishes the magnitude scale and does not replace
   the formal direction calibration (§4.7).
After the formal G0.3, write `tables/G0_summary.json` with `g0.write_g0_summary(run_path, results)`; `stage_g41` refuses to calibrate
without it. The A100/H100 factor 0.5 in `config.hardware` is a budget placeholder until measured.
Memory note: teacher-forced forwards materialise full-vocabulary logits (151936 × tokens); keep those batches to ≈4–8 sequences of 512
response tokens (or slice logits), generation batches 16–32 subject to item 4.


### 6.1 Results of the five diagnostics (2026-10-18, same environment, T = 0.7, committed code)
1. Padding: S_gen and S_read ok on 4 prompts of different lengths (pad/unsteered diffs 0.0; steered rows match the bf16 addition —
   `hook_position_check` now uses the dtype-exact expected output as the criterion and generate's pad position id 1). Found and fixed:
   with pad position id 1 an S_read span covering position 1 steered the pads; the hook now takes `real_mask` (the prompt attention
   mask) and never steers pads. hook_selfcheck 6/6 with the committed code; prefix final-logit max|Δ| 1.375 re-observed; suffix residual
   change 1.277 ≈ α·r_L·‖v‖∞.
2. Generation vs teacher-forcing (20 × 512 tokens): sdpa mean|Δ log p| 0.022, rms 0.078, max 1.05; eager 0.025 / 0.096 / 1.95 —
   backend-independent; only 1/20 samples identical across backends, so `attn_implementation` is now in the frozen config. Still
   to report: the SIGNED mean Δ per response (bias accumulates over a response), and the per-position KL between the two paths.
3. Batch first token (8 prompts): argmax 8/8, KL(B1‖B8) up to 8e-3, max logit diff 0.6–1.25. The G0.5 99.5% per-token greedy
   criterion is at risk: run greedy 64-token continuations for 32 prompts under B=1 vs B=8 BEFORE the formal G0; if agreement is
   below 99.5%, write the pre-registered amendment before sampling (the e_3-rate TOST stays the criterion; agreement becomes a
   measured floor) — never after.
4. Throughput: B=8 15.3, B=16 21.5, B=32 34.0 tok/s (aggregate, prompt processing included, 0.5–0.9 s per step); memory fine
   (60.4 GiB at B=32). The plan's HF budget is off by ~30×; decide the path first: transformers 5.x experts backends
   (`experts_implementation="grouped_mm"` needs PyTorch ≥ 2.9 and re-validating every HF semantic in tests/test_hf_semantics.py),
   steering inside vLLM, or shrinking HF generation. Also measure HF prefill (teacher-forcing) throughput separately: it is one
   forward per response and is what the calibration/gradient paths need.
5. α preview (random direction, L=20): KL 0.027 / 0.096 / 0.42 / 1.39 / 9.05 at |α| = 0.125 / 0.25 / 0.5 / 1 / 2 → α_max ≈ 0.25 for a
   random direction; read the α=±1 texts used by G0.7 before relying on them.
Truncation at 512 tokens: 2/20 (sdpa) and 4/20 (eager) on these synthetic prefixes — expect the §7.2 5% rule to trigger in G1.
