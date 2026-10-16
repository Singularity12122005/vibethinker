# RUNBOOK — Phase-0 execution with `sycophancy_phase0`

The specification is `docs/research/sycophancy-phase0-execution-plan.md` (v1.3). This file maps the spec onto the code;
when they disagree, the spec wins and the disagreement is a bug to report (plan §0.4, last bullet).

## 0. Hard rules you must enforce while running (plan §0)
- Never change a `[F]` parameter after G1's `est` block has been looked at; later changes go to `runs/<run_id>/DEVIATIONS.md`
  via `run.record_deviation`.
- Selection only on `sel`-block, pre-treatment quantities (`gates.g15.select_prefixes` reads `stats[...]["sel"]`); effects only on `est`.
- Seeds are derived, never shared across arms (`inference.sampling.derive_seed`; `Arm.arm_id()`); `enable_prefix_caching=False` in vLLM.
- Stop and report (do not improvise) on: any G0 failure; G1 N_q < 30; any GREY; judge parse failure > 1%; template mismatch > 1%;
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
| G0 | `gates.g0_runner.*` + `gates.g0.*` (see §4 below) | `GATES.md` G0 entry | all eight pass, else KILL and fix the pipeline |
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
- G0.1 `g0_runner.template_consistency(trajs, builder, first_turn_ids, text_path_ids, SYSTEM_PROMPT)` → `g0.g0_1`
- G0.2 `g0_runner.hook_selfcheck(model, steer, ids)` + `g0_runner.sampler_chi2(model, ids, n=5000)` → `g0.g0_2`
- G0.3 `g0_runner.cache_vs_recompute_kl(model, [(ids_2, y2+delta)...])` → `g0.g0_3`
- G0.4 generate y_2 under ±0.5 with a seeded random unit vector at L=20 (`torch.Generator().manual_seed(20261016)`), continue turn 3
  in-process (same `Steer`, α=0) and from a fresh process via `rollout.prefix_from_trajectory`; `g0.g0_4` (clusters = h_2)
- G0.5 `g0_runner.batch_conditions(specs, run)` → `g0_runner.paired_e3` + `greedy_agreement` → `g0.g0_5`
- G0.6 `controllers.contract_check(policy, ids_3, z_3, histories, n=50000, deterministic=...)` → `g0.g0_6`
- G0.7 `g0_runner.support_defect_logps(model, steered items)` → `g0.g0_7`
- G0.8 same 200 h_3 × 128 on `HFEngine` and `VLLMEngine` → `g0.g0_8`
Then `g0.write_gates_md(results, GATES.md, run_id)`; GO only with all eight present and passing.

## 5. Things the code does not do for you
- Download models/datasets; launch vLLM servers; the M_hybrid thinking-arm prefixes for G3 (build with `TurnBuilder(..., "hybrid_think")`
  and `max_new_tokens=4096`); the human annotation itself; figures beyond the CSV/PNG set in `report.figures`.
- Budget tracking (plan §7.13): log token counts from the engines per stage into `tables/budget.json`.
