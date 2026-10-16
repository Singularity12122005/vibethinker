# sycophancy_phase0

Harness for the Phase-0 study specified in `docs/research/sycophancy-phase0-execution-plan.md` (v1.2).
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
| `analysis/desirability.py` | §8.4 Jensen gap $\hat J$ with EB shrinkage + jackknife, $A(\lambda)$ |
| `analysis/covvar.py` | §7.8 covariance estimator of the 4-sample policy-value heterogeneity |
| `analysis/power.py` | §8.6 paired-design variance components, $F_{80}$, $n^*$ |
| `analysis/tost.py`, `gates/g0.py` | §7.1 paired cluster-bootstrap TOST, TV/χ² checks and the G0 decision logic (data collection left to the runner) |
