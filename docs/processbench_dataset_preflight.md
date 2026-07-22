# ProcessBench Dataset Preflight

This document describes the dataset layer for a future process-observation pilot.
It is deliberately limited to source inventory, deterministic sampling, and
manifest sealing. It does not implement a model transport, load a checkpoint,
generate target-native traces, construct ARU interventions, or claim that ARUs
exist.

## Dataset Roles

Every dataset-facing record is typed by `dataset_role`:

- `contract_toy`: synthetic rows used only for software contract tests.
- `transport_qualification_micro`: handcrafted private rows for future runtime
  qualification.
- `processbench_external_trace`: ProcessBench solution traces used as external
  macro-region sources.
- `target_native_trace`: target-checkpoint rollouts that are not materialized by
  this layer.
- `checkpoint_alignment_confirmation`: later alignment-confirmation sources such
  as MATH-500 or the Health Panel.

Trace provenance is separate from dataset role. A ProcessBench trace is
`external_benchmark_trace`; it must never be represented as a natural rollout
from the target checkpoint.

## ProcessBench Source Contract

The official source identity is `Qwen/ProcessBench`, with the supported splits
`gsm8k`, `math`, `olympiadbench`, and `omnimath`. Imported records preserve the
official fields `id`, `generator`, `problem`, `steps`, `final_answer_correct`,
and `label`.

Official label semantics are recorded separately from the dataset snapshot
revision. The implementation records the evaluation-code revision and hashes for
the official evaluation/template/documentation receipts used to interpret labels.
The importer treats labels fail-closed:

- `label == -1` is the all-correct sentinel.
- `label >= 0` is a zero-based step index.
- missing labels, non-integer labels, empty `steps`, empty step strings, duplicate
  source IDs, and out-of-range labels are rejected before inventory or selection.
- `final_answer_correct` is preserved as a separate field and is never silently
  equated with earliest-error presence.

## Inventory Before Selection

Selection is gated on a complete aggregate inventory. The inventory records row
counts, label/final-answer cross-tabs, generator distributions, step-count
statistics, earliest-error positions, normalized error positions, conservative
duplicates, aggressive duplicate-review clusters, malformed-field counts, source
file hashes, and semantics-source receipts.

The aggregate inventory must not contain full problem text or full solution-step
text.

Synthetic tests are necessary but insufficient. They prove fail-closed schema
contracts, deterministic sampling behavior, and privacy guards, but they cannot
prove that the code is compatible with the real official repository layout,
official field types, row counts, or converted storage files. Real-source
compatibility begins only after a pinned official snapshot is materialized and
validated.

## Two-Stage Source Resolution

Official ProcessBench source handling is split into reviewable stages:

1. Metadata-only resolution queries the official `Qwen/ProcessBench` dataset
   repository and records the exact immutable dataset Git SHA, repository file
   inventory, source license, client versions, metadata response digest, and the
   already pinned QwenLM/ProcessBench label-semantics receipts. It downloads no
   dataset rows.
2. A human reviews the resolution receipt and commits a formal
   `ProcessBenchSourceLock` in a separate source-lock commit.
3. Pinned inventory later reads only that committed source lock, materializes only
   the locked revision, validates real rows without logging text, and emits safe
   aggregate inventory.
4. Pilot selection happens in a later task after inventory review.

The exact dataset commit is reviewed and committed separately so that inventory
cannot silently follow `main`, `latest`, a tag, or `refs/convert/parquet`.
Converted Parquet storage may be how Hugging Face serves files, but it is not the
canonical source identity. The canonical source revision is the immutable dataset
repository commit SHA.

Source lock, inventory lock, and selection lock are distinct:

- source lock freezes the official dataset revision and semantics-source receipts;
- inventory lock freezes aggregate facts observed from that revision;
- selection lock freezes a reviewed deterministic subset and split assignment.

Raw ProcessBench rows are not uploaded as CI artifacts because they contain full
problem text and solution traces. CI uploads only resolution receipts, aggregate
inventory, schema validation reports, logs, and SHA-256 manifests after a safety
scan.

## Sampling Controls

The deterministic 32-record pilot target is eight records per split: four
error-labelled traces and four all-correct traces. Error/correct relationships
are `sampling_pair` / `position_matched_control`, not causal pairs, because the
two arms contain different problems.

Within a split, the selector prefers:

1. error examples covering early, middle, and late normalized error positions;
2. generator diversity among error examples;
3. all-correct controls with the same generator;
4. close normalized macro-step position;
5. similar number of steps;
6. deterministic seeded tie breaks.

Conservative normalized problem hashes are hard leakage guards. Aggressive
duplicate-review hashes are advisory only; they flag possible duplicates for
human review and do not automatically merge or drop records.

## Discovery And Confirmation

Discovery and confirmation manifests are written separately. Confirmation rows are
sealed with an explicit confirmation gate and must not be loaded by discovery
analysis without an explicit unseal flag.

Before confirmation use, the selection policy, rendering policy, ARU segmentation
policy, intervention policy, and decision thresholds must be frozen. This layer
only prepares the split; it does not open the confirmation set.

## Trace Rendering

`TraceRenderingPolicy` defines a canonical text rendering for external ProcessBench
steps before tokenizer materialization. It records the policy ID, step prefix,
delimiter, LF newline convention, reasoning-channel wrapper, `<think>` tag policy,
final-answer inclusion policy, text normalization rules, Unicode normalization,
tokenization status, and tokenizer receipt requirement.

Before a tokenizer is supplied, rendering may produce only canonical text and
character spans. After tokenizer materialization, formal traces must record prompt
token IDs, per-step token spans, assistant reasoning boundary, rendering hash,
tokenizer hash, and chat-template hash. Materialized formal traces must not be
silently retokenized.

## ARU Boundary

Every ProcessBench step is represented only as an `external_macro_region`.
ProcessBench labels identify source benchmark macro-regions, not ARUs. Converting
a macro-region into an ARU candidate requires later semantic segmentation,
premise/state-update annotation, and counterfactual validation. A causally
validated ARU requires still more evidence.

## Storage And Privacy

Raw ProcessBench rows and materialized benchmark traces stay outside the public
repository, for example under `private_runs/datasets/processbench/<revision>/`.
The repository may track loader code, schemas, source IDs, hashes, manifests
without raw benchmark text, documentation, and synthetic tests. It must not track
full ProcessBench problems, full ProcessBench traces, target-model rollouts,
checkpoint paths, cache paths, endpoint URLs, or credentials.
