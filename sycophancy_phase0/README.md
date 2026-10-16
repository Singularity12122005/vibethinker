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
| `analysis/frontier.py` | §8.2 cross-fitted exponential-tilt KL frontier |
| `analysis/desirability.py` | §8.4 Jensen gap $\hat J$ via the unbiased factorial-moment cumulant series (+ Beta cross-check), $A(\lambda)$ |
| `analysis/covvar.py` | §7.8 covariance estimator of the 4-sample policy-value heterogeneity |
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
