#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TRAINING_CONFIG=${VT_TRAINING_CONFIG:-"$REPO_ROOT/configs/openthinker3/train.yaml"}
PLATFORM_CONFIG=${VT_PLATFORM_CONFIG:-"$REPO_ROOT/configs/openthinker3/platform.example.yaml"}
RUNTIME_MANIFEST=${VT_RUNTIME_MANIFEST:?set VT_RUNTIME_MANIFEST}
RUNTIME_ARCHIVE=${VT_RUNTIME_ARCHIVE:?set VT_RUNTIME_ARCHIVE}
TRAIN_DATA=${VT_TRAIN_DATA:?set VT_TRAIN_DATA}
MODEL_PATH=${VT_MODEL_PATH:?set VT_MODEL_PATH}
OUTPUT_DIR=${VT_OUTPUT_DIR:?set VT_OUTPUT_DIR}
SCRATCH_DIR=${VT_SCRATCH_DIR:?set VT_SCRATCH_DIR}
: "${VT_SKYWORK_VERIFIER:?set VT_SKYWORK_VERIFIER}"

NODE_RANK=${NODE_RANK:-${RANK:-}}
NODE_COUNT=${NNODES:-${WORLD_NODES:-}}
HEAD_ADDRESS=${MASTER_ADDR:-${HEAD_ADDR:-}}
HEAD_PORT=${MASTER_PORT:-${HEAD_PORT:-6379}}
[[ -n "$NODE_RANK" && -n "$NODE_COUNT" && -n "$HEAD_ADDRESS" ]]

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PREFLIGHT_ARGS=(
  --training-config "$TRAINING_CONFIG"
  --platform-config "$PLATFORM_CONFIG"
  --runtime-manifest "$RUNTIME_MANIFEST"
  --runtime-archive "$RUNTIME_ARCHIVE"
  --train-data "$TRAIN_DATA"
)
if [[ -n "${VT_RESUME_CHECKPOINT:-}" ]]; then
  PREFLIGHT_ARGS+=(
    --resume-checkpoint "$VT_RESUME_CHECKPOINT"
    --scratch-dir "$SCRATCH_DIR"
  )
fi
PREFLIGHT_JSON=$(python3 -m vibethinker_experiments.openthinker3.platform_adapter \
  "${PREFLIGHT_ARGS[@]}")

EXPECTED_GPUS=8
GPU_COUNT=$(nvidia-smi --query-gpu=index --format=csv,noheader | wc -l | tr -d ' ')
[[ "$GPU_COUNT" == "$EXPECTED_GPUS" ]]
nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits |
  awk '$1 + 0 < 80000 { bad=1 } END { exit bad }'

RUNTIME_SHA=$(python3 - "$PREFLIGHT_JSON" <<'PY'
import json
import sys

print(json.loads(sys.argv[1])["runtime_identity"].split("+", 1)[0].split(":", 1)[1])
PY
)
RUNTIME_ROOT="$SCRATCH_DIR/runtime-$RUNTIME_SHA"
if [[ ! -f "$RUNTIME_ROOT/.extracted" ]]; then
  mkdir -p "$RUNTIME_ROOT"
  if [[ -n "$(ls -A "$RUNTIME_ROOT")" ]]; then
    echo "runtime extraction directory is non-empty and uncommitted: $RUNTIME_ROOT" >&2
    exit 2
  fi
  tar -xzf "$RUNTIME_ARCHIVE" -C "$RUNTIME_ROOT"
  touch "$RUNTIME_ROOT/.extracted"
fi
export PYTHONPATH="$REPO_ROOT/src:$RUNTIME_ROOT/verl"

# Ray workers inherit the raylet environment, so export the complete frozen
# reward/trainer contract on every node before starting Ray.
export VT_FORMAL_RUNTIME=1
export VT_REWARD_WORKERS=16
export VT_VERIFIER_TIMEOUT_SECONDS=330
export VT_CODE_CASE_TIMEOUT_SECONDS=6
export VT_REPLICATED_DP_CHECKPOINT=1
export VT_SAVE_FIRST_STEP_CHECKPOINT=1
export VT_ADAPTIVE_ENTROPY_ENABLED=1
export VT_ENTROPY_COEFF=0
export VT_ENTROPY_TARGET=0.2
export VT_ENTROPY_MIN_COEFF=0
export VT_ENTROPY_MAX_COEFF=0.005
export VT_ENTROPY_DELTA=0.0001

python3 -m vibethinker_experiments.openthinker3.verifier --smoke-test

if [[ "${VT_SKIP_CPU_TESTS:-0}" != 1 ]]; then
  python3 -m pytest "$REPO_ROOT/tests/openthinker3" -q
fi

RESUME_ARGS=()
if [[ -n "${VT_RESUME_CHECKPOINT:-}" ]]; then
  RESUME_PATH=$(python3 - "$PREFLIGHT_JSON" <<'PY'
import json
import sys

print(json.loads(sys.argv[1])["resume_path"])
PY
  )
  RESUME_ARGS=(--resume-path "$RESUME_PATH")
fi

trap 'ray stop --force >/dev/null 2>&1 || true' EXIT
if [[ "$NODE_RANK" == 0 ]]; then
  ray start --head --node-ip-address "$HEAD_ADDRESS" --port "$HEAD_PORT" \
    --num-gpus "$EXPECTED_GPUS" --num-cpus "$(nproc)" --include-dashboard=false
else
  for _ in $(seq 1 180); do
    ray status --address "$HEAD_ADDRESS:$HEAD_PORT" >/dev/null 2>&1 && break
    sleep 2
  done
  ray start --address "$HEAD_ADDRESS:$HEAD_PORT" \
    --num-gpus "$EXPECTED_GPUS" --num-cpus "$(nproc)"
  while ray status --address "$HEAD_ADDRESS:$HEAD_PORT" >/dev/null 2>&1; do sleep 30; done
  exit 0
fi

for _ in $(seq 1 180); do
  READY=$(python3 - "$HEAD_ADDRESS:$HEAD_PORT" <<'PY' 2>/dev/null || echo 0
import ray
import sys

ray.init(address=sys.argv[1], logging_level="ERROR")
alive = [node for node in ray.nodes() if node.get("Alive")]
print(int(len(alive) == 4 and ray.cluster_resources().get("GPU", 0) == 32))
ray.shutdown()
PY
  )
  [[ "$READY" == 1 ]] && break
  sleep 2
done
[[ "${READY:-0}" == 1 ]]

python3 -m vibethinker_experiments.openthinker3.training \
  --config "$TRAINING_CONFIG" \
  --model-path "$MODEL_PATH" \
  --train-file "$TRAIN_DATA" \
  --output-dir "$OUTPUT_DIR" \
  --ray-address "$HEAD_ADDRESS:$HEAD_PORT" \
  "${RESUME_ARGS[@]}" \
  --execute
