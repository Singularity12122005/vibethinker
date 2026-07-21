"""Credential-safe platform launch templates for Qwen3.5 experiments.

Authentication stays in the submitter process environment.  Rendered launch
scripts never contain, read, echo, or export a token.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import yaml


def load_platform_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("platform config must be a schema_version=1 mapping")
    return config


def _required(config: dict[str, Any], key: str) -> str:
    value = str(config.get(key, ""))
    if not value or value.startswith("<"):
        raise ValueError(f"replace platform placeholder {key!r}")
    return value


def render_sft_launch(config: dict[str, Any]) -> str:
    paths = config["paths"]
    command = [
        "torchrun",
        "--standalone",
        f"--nproc_per_node={config['resources']['gpus_per_node']}",
        "-m",
        "vibethinker_experiments.qwen35.train_sft_qwen35",
        "--config",
        paths["experiment_config"],
        "--model",
        paths["model"],
        "--data-dir",
        paths["data"],
        "--output-dir",
        paths["output"],
    ]
    return "#!/usr/bin/env bash\nset -euo pipefail\n" + shlex.join(command) + "\n"


def render_verl_launch(config: dict[str, Any]) -> str:
    paths, resources = config["paths"], config["resources"]
    nodes, gpus = int(resources["nodes"]), int(resources["gpus_per_node"])
    launcher = shlex.join(
        [
            "python3",
            "-m",
            "vibethinker_experiments.qwen35.verl_launcher",
            "--config",
            paths["experiment_config"],
            "--model-path",
            paths["model"],
            "--train-file",
            paths["data"],
            "--output-dir",
            paths["output"],
        ]
    )
    launcher += ' +ray_kwargs.ray_init.address="$MASTER_ADDR:$MASTER_PORT"'
    return f"""#!/usr/bin/env bash
set -euo pipefail
NODE_RANK=${{RANK:-${{NODE_RANK:-${{JOB_COMPLETION_INDEX:-}}}}}}
MASTER_ADDR=${{MASTER_ADDR:?distributed platform must set MASTER_ADDR}}
MASTER_PORT=${{MASTER_PORT:-6379}}
if [[ ! "$NODE_RANK" =~ ^[0-9]+$ ]] || (( NODE_RANK >= {nodes} )); then
  echo "invalid or missing node rank" >&2
  exit 2
fi
export RAY_ADDRESS="$MASTER_ADDR:$MASTER_PORT"
trap 'ray stop --force >/dev/null 2>&1 || true' EXIT
if (( NODE_RANK == 0 )); then
  ray start --head --node-ip-address="$MASTER_ADDR" --port="$MASTER_PORT" \
    --num-gpus={gpus} --include-dashboard=false
  for _ in $(seq 1 120); do
    GPU_TOTAL=$(ray status 2>/dev/null | awk '/GPU/ {{print $1; exit}}' || true)
    [[ "$GPU_TOTAL" == "{nodes * gpus}.0" || "$GPU_TOTAL" == "{nodes * gpus}" ]] && break
    sleep 2
  done
  {launcher}
else
  for _ in $(seq 1 120); do
    ray start --address="$MASTER_ADDR:$MASTER_PORT" --num-gpus={gpus} && break
    sleep 2
  done
  while ray status --address="$MASTER_ADDR:$MASTER_PORT" >/dev/null 2>&1; do sleep 30; done
fi
"""


def render_launch_script(config: dict[str, Any]) -> str:
    kind = config.get("kind")
    if kind == "sft":
        script = render_sft_launch(config)
    elif kind == "verl":
        script = render_verl_launch(config)
    else:
        raise ValueError("platform kind must be 'sft' or 'verl'")
    token = os.environ.get("TRISOL_TOKEN")
    if token and token in script:
        raise RuntimeError("credential leaked into launch script")
    if "TRISOL_TOKEN" in script:
        raise RuntimeError("launch script must not handle submitter credentials")
    return script


def build_submit_command(config: dict[str, Any]) -> list[str]:
    platform = config["platform"]
    resources = config["resources"]
    script = render_launch_script(config)
    encoded = base64.b64encode(script.encode()).decode()
    command = [
        platform.get("cli", "trisol"),
        "train",
        "submit",
        _required(platform, "job_name"),
        "--framework",
        "custom",
        "--mode",
        "lora" if config["kind"] == "sft" else "full",
        "--base-model",
        _required(platform, "base_model"),
        "--dataset",
        _required(platform, "dataset"),
        "--cluster",
        _required(platform, "cluster"),
        "--nodes",
        str(resources["nodes"]),
        "--gpus-per-node",
        str(resources["gpus_per_node"]),
        "--gpu-model",
        _required(resources, "gpu_model"),
        "--image-ref",
        _required(platform, "image"),
        "--command",
        "bash",
        "--args",
        f"-lc,echo {encoded} | base64 -d | bash",
    ]
    team = platform.get("team")
    if team and not str(team).startswith("<"):
        command.extend(["--team", str(team)])
    return command


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--print-launch", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_platform_config(args.config)
    if args.print_launch:
        print(render_launch_script(config))
        return
    command = build_submit_command(config)
    if args.dry_run:
        print(json.dumps(command, indent=2))
        return
    # The CLI authenticates from its inherited environment/config. No secret is
    # copied into command arguments or the remote launch script.
    subprocess.run(command, check=True, env=dict(os.environ))


if __name__ == "__main__":
    main()
