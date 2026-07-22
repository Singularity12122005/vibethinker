# Process Observation and ARU Pilot

This module implements the minimum auditable infrastructure for a causal Atomic
Reasoning Unit (ARU) pilot on the `qwen25-15k` lineage. It does not run a real
model, retrain VERL, publish private checkpoints, or claim a real Base/SFT/RL
causal result.

## Scientific Boundary

An ARU is treated only as a candidate hypothesis:

```text
a minimal proposition-level state update with identifiable premises and
measurable downstream causal effects
```

It is not assumed to be a sentence, paragraph, fixed token window, ProcessBench
step, probe label, or hidden-state module. The implemented evidence hierarchy is:

1. ARU intervention alone shows local causal sensitivity.
2. Controlled localization, exact shared-prefix design, paraphrase variants,
   negative controls, and independent confirmation can support a stable
   functional process-unit claim.
3. Base/SFT/RL comparison plus optimization-signal audit can support claims about
   capability formation.
4. Hidden-state intervention is required for internal implementation claims.

This public implementation covers only layers 1-3 as contracts and toy CPU
fixtures. It does not implement probes, activation patching, neuron search,
attention-head analysis, process reward, or a learned meta-action classifier.

## Exact Model Input

`InterventionSpec` records:

- the exact `prompt_token_ids`;
- the exact `completion_prefix_token_ids`;
- the original candidate-unit token IDs;
- the replacement token IDs;
- the intervention kind and semantic claim provenance.

Every variant for one ARU must share the exact same prefix ending immediately
before the candidate unit. Branch input is:

```text
prompt_token_ids + completion_prefix_token_ids + replacement_unit_token_ids
```

`prompt_token_ids` is the already-tokenized model prompt. For chat models it is
where chat-template tokens, system/user boundary tokens, and the assistant-start
boundary are represented. `completion_prefix_token_ids` contains only prior
assistant completion tokens after that boundary. The transport must consume these
verified IDs directly and must not re-render a chat template.

Deletion is represented by an explicitly present empty replacement tuple. It is
not treated as missing data. Paraphrase, repair, corrupt, delete, no-op, and
unrelated-unit controls are annotation claims unless a verifier or human review
receipt validates them.

Cache reuse is an optimization only. The semantic contract is exact token replay.

## Identity and Transport

`PrefixBranchRequest.request_sha256` identifies stable scientific inputs:
checkpoint identity, prompt tokens, completion-prefix tokens, intervention
tokens, sampling parameters, seed, continuation mode, profile, transport config
ID, and non-private metadata. Request construction requires the context budget to
cover prompt tokens, completion-prefix tokens, intervention tokens, and
`max_new_tokens`.

`PrefixBranchResponse.response_sha256` records what actually happened. Stochastic
formal transports are not assumed byte-deterministic across hardware or runtime
versions. The deterministic toy transport is deterministic by construction.

Stable public identities exclude credentials, endpoint URLs, local cache
locations, and absolute runtime paths. `CheckpointReference.runtime_locator` is
runtime-only and excluded from request identity. When a committed checkpoint
directory is available, `checkpoint_manifest_hash_if_committed` validates the
existing `metadata/COMMITTED` contract. When evidence is absent, checkpoint status
remains `unverified`; no manifest hash or receipt is manufactured.

The default branch transport is network-disabled. Private model or vLLM adapters
must implement the `PrefixBranchTransport` protocol outside this public module.

## Outcomes

`ProcessOutcome` uses explicit tri-state values for semantic fields:

```text
true | false | unknown
```

Unknown semantic status is never silently coerced to false. A self-repair claim
requires an explicit evaluator rule and provenance. The toy evaluator is
synthetic and deterministic; it does not claim model reasoning.

## Artifact State Machine

`finalize_process_run` writes immutable, hash-addressed artifacts:

- `run_manifest.json`
- `natural_rollouts.jsonl`
- `candidate_regions.jsonl`
- `aru_candidates.jsonl`
- `interventions.jsonl`
- `branch_requests.jsonl`
- `branch_results.jsonl`
- `process_outcomes.jsonl`
- optional `gradient_provenance.jsonl`
- `report.json`
- `FINALIZED.json`

All process artifacts use canonical UTF-8 bytes, no BOM, LF line endings, sorted
JSON object keys, compact separators, and a final LF. Finalization checks duplicate
IDs, parent-child references, exact branch coverage, matching request/response
hashes, matching response/outcome hashes, toy/formal isolation, and upstream
tampering. Re-running finalization verifies the existing marker instead of
rewriting sealed files.

## Optimization-Signal Audit

`GradientProvenanceRecord` preserves qwen25 reward-field names where possible:
`total_score`, `binary_success`, `answer_correct`, `format_ok`,
`format_progress`, `base_reward`, `overlong_multiplier`, completion length, and
truncation. Aggregation reports raw and accepted groups separately:

- all-wrong `M0`;
- mixed-correctness `Mmix`;
- all-correct `M1`;
- unknown group fraction;
- acceptance rate only when observable;
- resampling factor only when observable;
- prompt repetition and reward-component means.

Unknown correctness or update-acceptance status is not inferred from YAML,
directory names, algorithm names, or average reward.

## Toy CPU Pipeline

The toy fixture lives in:

- `configs/process_observation/toy-qwen25-15k.yaml`
- `data/process_observation/toy/`

It is unmistakably synthetic. A CPU-only pipeline can run:

```bash
python -m vibethinker_experiments.process_observation.cli localize \
  --profile configs/process_observation/toy-qwen25-15k.yaml \
  --natural-rollouts data/process_observation/toy/natural_rollouts.jsonl \
  --output /tmp/candidate_regions.jsonl \
  --selection-policy-id deterministic-sparse-token-region-v1 \
  --split discovery

python -m vibethinker_experiments.process_observation.cli prepare-interventions \
  --profile configs/process_observation/toy-qwen25-15k.yaml \
  --natural-rollouts data/process_observation/toy/natural_rollouts.jsonl \
  --candidate-regions /tmp/candidate_regions.jsonl \
  --aru-candidates data/process_observation/toy/aru_candidates.jsonl \
  --output /tmp/interventions.jsonl

python -m vibethinker_experiments.process_observation.cli branch \
  --profile configs/process_observation/toy-qwen25-15k.yaml \
  --checkpoint-reference data/process_observation/toy/checkpoint_reference.jsonl \
  --interventions /tmp/interventions.jsonl \
  --prompt-id toy-aru-addition-001 \
  --requests-output /tmp/branch_requests.jsonl \
  --output /tmp/branch_results.jsonl \
  --transport toy \
  --transport-config-id deterministic-toy-prefix-branch-v1 \
  --continuation-mode short

python -m vibethinker_experiments.process_observation.cli evaluate \
  --profile configs/process_observation/toy-qwen25-15k.yaml \
  --branch-results /tmp/branch_results.jsonl \
  --interventions /tmp/interventions.jsonl \
  --aru-candidates data/process_observation/toy/aru_candidates.jsonl \
  --prompt-id toy-aru-addition-001 \
  --output /tmp/process_outcomes.jsonl \
  --evaluator toy

python -m vibethinker_experiments.process_observation.cli finalize \
  --profile configs/process_observation/toy-qwen25-15k.yaml \
  --run-dir /tmp/process_observation_run \
  --natural-rollouts data/process_observation/toy/natural_rollouts.jsonl \
  --candidate-regions /tmp/candidate_regions.jsonl \
  --aru-candidates data/process_observation/toy/aru_candidates.jsonl \
  --interventions /tmp/interventions.jsonl \
  --branch-requests /tmp/branch_requests.jsonl \
  --branch-results /tmp/branch_results.jsonl \
  --process-outcomes /tmp/process_outcomes.jsonl \
  --expected-branch-count 6
```

The toy pipeline does not claim real checkpoint behavior, real model reasoning,
real causal effects, or formal benchmark results.

## Future Formal qwen25-15k Run

A private formal adapter should supply three checkpoint references:

- Base;
- SFT epoch 1;
- RL step 31.

It must also supply formal prompts, natural rollouts, exact prompt/completion
token IDs, tokenizer verification receipts, committed checkpoint validation
evidence, private generation transport, private outcome-evaluator provenance,
and a private reward-provenance export. Formal mode fails closed if toy data, toy
transport, missing exact token identity, unverified tokenization, or missing
provenance is supplied.

Current blockers for a real public experiment are:

- private checkpoints;
- formal prompts;
- formal natural rollouts;
- tokenizer receipts;
- private generation adapter;
- private reward provenance export;
- formal outcome evaluator or human annotation receipts.

## Granularity Comparison

`export.py` defines a common counterfactual-response row schema for:

- `token_window`;
- `sentence`;
- `macro_step`;
- `aru`.

The module only prepares leakage-checked exports. It does not train a predictor.
ARU should be supported only if it improves held-out counterfactual-response
prediction enough to justify annotation cost and representation complexity.

## Limitations

This implementation provides contracts and a synthetic instrument. It gives no
semantic-equivalence guarantee, no hidden-state analysis, no proof from one
example, and no reproduction of private VibeThinker results.
