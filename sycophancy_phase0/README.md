# sycophancy_phase0

Harness for the Phase-0 study specified in `docs/research/sycophancy-phase0-execution-plan.md` (v1.3).
Each module cites the plan section it implements. Nothing here downloads a model; the HF tests build a
tiny randomly-initialised Qwen3-MoE on CPU to verify the *semantics* the plan relies on (hook positions,
padding/`position_ids`, `hidden_states` indexing, logits-processor order, teacher-forcing masks).

```
pip install -e ".[hf,test]"        # transformers is pinned to 4.57.1 on purpose (plan §2.1)
pytest -q                           # HF-semantics tests are skipped if torch/transformers are absent
```

Layout (plan §2.4):

| module | plan section |
| --- | --- |
| `inference/steering.py` | §4.4 `Steer` hook (per-row α, `S_gen`/`S_read`/`S_all`, teacher-forcing mask, gradient mode) |
| `inference/sampling.py` | §4.3 per-row seeded Gumbel-max sampler, seed derivation, generate kwargs |
| `inference/templates.py` | §4.1 id concatenation, EOS normalisation, `M_hybrid` think-block handling, `user_span` |
| `inference/hf_engine.py` | §4.5–4.7 clean forward with right padding / explicit `position_ids`, $z_t$ extraction, $r_L$, teacher-forced log-probs and next-token KL, route-flip |
| `scoring/parse.py`, `scoring/labels.py` | §6.1 deterministic parsing, hedge detection, rule stance; §3 comparison-value table and outcomes |
| `scripts/builders.py` | Appendix A script templates |
| `analysis/varcomp.py` | §8.1 U-statistic variance component, ICC |
| `analysis/frontier.py` | §8.2 cross-fitted exponential-tilt KL frontier (β* from the sel half only), dual and Bernstein bounds |
| `analysis/desirability.py` | §8.4 Jensen gap: primary $\hat J_{\mathrm{LB}}$ ((1−z)-expansion with unbiased failure falling-factorial moments, per prefix), diagnostic series/Beta, regime flags, $A(\lambda)$, G2′-a rule |
| `analysis/covvar.py` | §7.8 covariance estimator of the 4-sample policy-value heterogeneity, prefix-level bootstrap |
| `analysis/power.py` | §8.6 paired-design variance components, $F_{80}$, $n^*$ |
| `analysis/tost.py`, `gates/g0.py` | §7.1 paired cluster-bootstrap TOST, TV/χ² checks, G0.1–G0.8 decision functions, §7.0 GATES.md writer |
| `gates/g0_runner.py` | §7.1 data collection: hook self-checks + sampler χ² (G0.2), cache-vs-recompute KL (G0.3), support defect (G0.7), template consistency (G0.1), batch-condition and continuation orchestration (G0.4/G0.5/G0.8) |
| `trajectory.py` | §10.2 trajectory/turn/arm records, `prefix_id`/`traj_id` hashing, blocks/subsplits, JSONL writer, z store |
| `inference/engine.py`, `inference/vllm_engine.py` | §4.2/§4.3/§4.9 engine protocol: `HFEngine` (steered, seeded), `VLLMEngine` (α=0 only, prefix caching off), `FakeEngine`, alpha router |
| `rollout.py` | §4.1–4.3, §5.5 batched four-turn rollouts (fresh / D-prefill / continuation of a bank prefix), seeds per (run, problem, prefix, arm, idx, turn), scoring + judge + z hooks |
| `scoring/judge.py` | §6.2 / Appendix E judge prompt, 3-stage JSON parsing, label normalisation, consistency check, OpenAI-compatible client |
| `data/f1.py`, `data/f2.py`, `data/f3.py` | §2.3 / Appendices B–C: GSM8K-zh loader with numeric-multiset check, 8 parametrised templates × 15 (seed 20261016, exact ≤2-decimal golds), sandboxed program generator with script-C modifications |
| `data/pools.py` | §5.2–§5.6 p₀/distractor mining, pools (main / D / D-nat / C), 5 folds, sel/est blocks |
| `controllers.py` | §0.2 rule 7 controller contract `policy(ids_t, z_t, t, rng)`, placeholders, G0.6 history-replay check |
| `gates/g1.py`, `gates/g15.py` | §7.2 G1 specs, pre-treatment filter, per-turn tables, criteria G1.a–f, frontier/shrinkage; §7.2b prefix bank (h₂/h₃ construction, continuations, sel/est prefix-level quantities, selection) |
| `inference/calibration.py`, `analysis/isotonic.py` | §4.7 fine-grid KL/route-flip, coarse-grid isotonic lower bounds, α_max rule, κ₁ |
| `inference/directions.py` | §4.8 first-16-token activations, `v_cap`/`v_press`/`v_warrant`/`d_agree`/`v_cap⊥`, LOFO versions, persistence |
| `analysis/scores.py`, `analysis/glm.py` | §8.3 response gradients (Steer gradient mode), S_v, natural gradient + out-of-fold R²_steer, linear region, disattenuated ρ_v; logistic regression with cluster-robust SE |
| `analysis/probes.py` | §8.5 LOQO ridge ladder (dual form), ΔR² question-bootstrap CI, LRT approximation, shuffled-label null, AUROC, Spearman–Brown, G3 rule |
| `analysis/factorial.py` | §8.8 empirical-logit WLS per prefix, DerSimonian–Laird pooling, cluster-robust SE, LRT for Var(c_i), EB shrinkage, backward induction MPC vs myopic, G5 statistic |
| `gates/g2.py`, `gates/g2a.py` | §7.3 single-shot text channel (sources a/b/c, paired contrasts, decision); §7.4 G2′-a prefix selection, y₂ sampling + continuations, variance components, frontier, Ĵ_LB with prefix bootstrap, A(λ), testimony specs |
| `gates/g40.py`, `gates/g41.py` | §7.6 direction data + LOFO direction estimation/persistence; §7.7 provisional α_max, layer screen, L* selection |
| `gates/g2b.py`, `gates/g42.py` | §7.8 steering-class Var(V₃) (quarters, Cov of half-estimates, prefix bootstrap); §7.9 dose–response β_S endpoints, co-primary x₄ drop, C update drop, decision |
| `gates/g5.py`, `gates/g6.py` | §7.10 split-plot factorial (y₂ reuse across u₃ and scripts), u₃* freeze, G with problem bootstrap, co-primary; §7.11 matched-risk FE logit interaction, per-prefix curves, EB-shrunk argmin, quintile policy, regret |
| `run.py` | §0.3 / §2.4 run directory, frozen config + SHA-256, env/git capture, GATES/DEVIATIONS writers, GPU/fake contexts, data stage |
| `analysis/testimony.py`, `analysis/ppi.py` | §8.9 PPV/NPV-corrected LOR and λ_m/τ with joint bootstrap, FE logit by risk stratum, same-stance ICC + permutation; §8.7 PPI difference estimator, sensitivity/specificity with Wilson CIs |
