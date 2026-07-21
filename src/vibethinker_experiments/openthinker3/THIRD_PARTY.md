# Skywork verifier integration

The local source tree used for this migration did not contain a license file
covering the complete Skywork/LiveCodeBench verifier dependency closure.
Although selected files carry Apache-2.0 headers, that is not enough to
establish redistribution terms for every imported file. No verifier
implementation, benchmark prompt, test payload, or sample has therefore been
copied into this repository.

Install a license-reviewed verifier separately and expose its callable through:

```text
VT_SKYWORK_VERIFIER=package.module:compute_score
```

The callable must accept `(solution, ground_truth, task=..., timeout=...,
is_binary_reward=True)` and return `(score, metadata)`. The metadata mapping
should set `verifier_ok=false` and `verifier_error` when infrastructure fails.

Before deployment, record outside this repository:

1. the exact verifier source revision and archive hash;
2. all licenses and notices for its transitive source closure;
3. the environment or image digest used to install it;
4. sandbox controls appropriate for executing untrusted generated code.

The adapter is fail-closed when `VT_SKYWORK_VERIFIER` is absent or malformed.
