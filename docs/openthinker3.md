# OpenThinker3-1.5B Skywork math/code RL

## Scope and provenance

This migration keeps the reusable experiment logic separate from platform
bindings and upstream framework edits.

- Algorithm, reward, checkpoint, dataset construction, and audit contracts are
  maintained in `vibethinker_experiments.openthinker3`.
- The VERL patch was derived from the seven modified files in a worktree at
  commit `7aed6b230776f963fa09509c10d9c3a767d1102c`.
- The vLLM patch reconstructs the two runtime bootstrap edits against public
  vLLM `v0.19.0`.

No dataset rows, audit samples, generated answers, checkpoint state, model
weights, deployment credentials, private endpoints, or submission identifiers
are included.

## Current evidence boundary

Dataset construction and independent audit, algorithm and reward contracts,
compact checkpoint/resume logic, the 32-GPU topology, and launch preflight have
all completed and have been exercised repeatedly.

The last platform observation on 2026-07-22 showed `running`, but only at the
scheduler level. There was no trainer-start marker, rollout evidence, or valid
training-step evidence. Because scheduler state is transient, the public static
status is **preflight complete; training health unverified**. There is no final
checkpoint or capability evaluation, and this repository does not claim that
training started progressing.

## Artifact identity

Historical attempts used multiple runtime archive hashes. Local directory
names and platform catalog versions were not consistently aligned, so neither
is an artifact identity. The public repository does not select one of those
historical archives.

`configs/openthinker3/train.yaml` freezes semantic configuration and upstream
revisions, while its `formal_runtime_id` remains
`REQUIRED_FROM_RUN_MANIFEST`. Every private or external run must provide a
separate manifest:

```yaml
schema_version: 1
resolved_config: openthinker3-skywork-rl-v1
runtime_archive_sha256: <lowercase-64-hex-sha256>
```

Launch preflight requires this manifest, checks that `resolved_config` matches
the public contract, and recomputes the supplied archive hash before
extraction. The formal runtime identity exists only for that run as archive
SHA plus resolved config.

## Data contract

`configs/openthinker3/data.yaml` freezes source revisions, source shard hashes,
tokenizer revision, difficulty filter, seed, counts, and maximum prompt length.
The builder emits 30,000 unique math rows and 6,000 unique code rows; code rows
are materialized twice, giving 42,000 scheduled rows per epoch.

Only code verifier routes carrying their full test payload are accepted.
`question_id` rows are rejected because they require a separate benchmark
archive. The builder no longer writes an audit sample. The independent audit
writes aggregate counts and hashes only.

```bash
python -m vibethinker_experiments.openthinker3.data_build \
  --contract configs/openthinker3/data.yaml \
  --input-dir /path/to/pinned-source \
  --output-dir /path/to/output \
  --tokenizer-path /path/to/pinned-tokenizer

python -m vibethinker_experiments.openthinker3.data_audit \
  --contract configs/openthinker3/data.yaml \
  --data-dir /path/to/output \
  --tokenizer-path /path/to/pinned-tokenizer
```

## Training contract

The resolved configuration freezes:

- five prompt epochs, batch size 160, group size 16, and `drop_last=false`;
- 4,096 prompt plus 28,672 response tokens;
- binary rewards and complete all-zero/all-one group removal without
  replacement;
- standard GRPO normalization, DAPO token-mean loss, asymmetric clipping
  `0.2/0.28`, dual-clip `C=10`, and no KL reward or loss;
- adaptive entropy target `0.2`, range `0..0.005`, and delta `0.0001`;
- constant AdamW learning rate `1e-6`, no warmup, and weight decay `0.01`;
- four nodes, eight GPUs per node, rollout TP=1, and actor FSDP size 1;
- first-step, every-50-step, epoch-boundary, final, and expiration-aware
  checkpoint saves.

The compact checkpoint contract stores model and optimizer state on rank zero,
rank-specific RNG/extra state on every rank, adaptive entropy state, dataloader
state, `metadata/training_state.json`, and a final `metadata/COMMITTED` marker.
Resume validation rejects missing, duplicate, or mismatched state before VERL
starts.

## Reward verifier

The local verifier closure lacked a license file covering all imported source.
It was therefore not copied. `reward.py` loads a separately installed,
license-reviewed callable through:

```bash
export VT_SKYWORK_VERIFIER=package.module:compute_score
```

See `src/vibethinker_experiments/openthinker3/THIRD_PARTY.md`. Missing adapters,
timeouts, and sandbox failures are reported as `verifier_ok=false`, distinct
from an ordinary wrong answer.

## Platform adapter

`train.yaml` contains experiment semantics. `platform.example.yaml` contains
only environment-name bindings. `launch_multinode.sh` verifies artifact hashes,
GPU topology, runtime environment propagation, CPU contracts, Ray membership,
and optional resume state without embedding a provider, image, account,
endpoint, or job identifier.

Required deployment variables are:

```text
VT_RUNTIME_MANIFEST VT_RUNTIME_ARCHIVE VT_TRAIN_DATA
VT_MODEL_PATH       VT_OUTPUT_DIR      VT_SCRATCH_DIR
VT_SKYWORK_VERIFIER
```

The platform supplies node rank/count and rendezvous address through one of the
generic aliases documented in `platform.example.yaml`.

## Upstream patch status

- `patches/verl-openthinker3/` contains one patch and a manifest naming exactly
  seven changed files. It is derived from the pinned worktree diff, excluding
  the untracked verifier directory; only package import paths were adapted.
  `git apply --cached --check` passed against the pinned clean index.
- `patches/vllm-openthinker3/` contains the retry and locked-port changes. It is
  parse-checked only. It has not passed `git apply --check` against a clean
  vLLM `v0.19.0` checkout, so syntax review must not be reported as patch
  applicability.

No complete VERL or vLLM source tree is vendored.

## CPU checks

```bash
PYTHONPATH=src pytest tests/openthinker3
```

These tests cover algorithm filtering, entropy state, reward failure semantics,
checkpoint layout/resume, data route and identity contracts, rendered VERL
overrides, platform topology resolution, patch manifests, and identifier
sanitization. They do not execute generated code or require GPUs.

They also do not establish trainer startup, rollout health, a valid optimization
step, final-checkpoint completeness, or capability change for the current job.
