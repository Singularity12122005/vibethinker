"""等待既有阶段二A退出后运行第五批；不改其队列，不并行占用显卡。"""
from pathlib import Path
import argparse
import fcntl
import json
import os
import subprocess
import time

from .freeze import validate


A_OUTPUTS = {
    "stage2_baseline_extractions.json": 1200,
    "stage2_belief_generations.json": 80,
    "stage2_Q2_generations.json": 960,
    "stage2_Q2_extractions.json": 2880,
    "stage2_belief_outcomes.json": 80,
    "stage2_baseline_outcomes.json": 600,
    "stage2_Q2_outcomes.json": 960,
}


def a_complete(folder):
    done = True
    for name, expected in A_OUTPUTS.items():
        path = folder / name
        if not path.exists():
            done = False
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        expected_type = list if name.endswith("_generations.json") else dict
        if not isinstance(rows, expected_type) or len(rows) > expected:
            raise RuntimeError("既有阶段二A输出偏离登记：" + name)
        done = done and len(rows) == expected
    return done


def a_processes(folder):
    active = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            args = [word.decode(errors="replace") for word in (path / "cmdline").read_bytes().split(b"\0") if word]
        except OSError:
            continue
        scripts = ("stage2_continue.py", "stage2_judge.py", "stage2_runtime.py", "stage2_outcomes.py")
        if any(word.endswith("/" + script) for word in args for script in scripts) and str(folder) in args:
            active.append(int(path.name))
    return active


def run(out, pilot, commit):
    if os.name != "posix" or pilot.resolve() != Path("/output/sycophancy-phase0/pilot"):
        raise RuntimeError("协调入口仅在指定A100目录运行")
    validate(out, pilot, commit)
    with (out / ".continue_core.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        phase_a = pilot / "factdiag7_20261112"
        print("等待既有阶段二A的全部输出及进程退出；不占用显卡。", flush=True)
        while True:
            finished = a_complete(phase_a)
            active = a_processes(phase_a)
            if finished and not active:
                break
            if not finished and not active:
                raise RuntimeError("阶段二A尚未完整且已无队列进程，停止接续并等待协调诊断")
            time.sleep(30)
        env = dict(os.environ, PYTHONPATH="/output/sycophancy-phase0/code/src",
                   OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        command = ["/output/sycophancy-phase0/venv-experts/bin/python", "-u", "-m",
                   "scripts.pilot.factdiag5.runtime", "--out", str(out), "--pilot", str(pilot),
                   "--freeze-commit", commit]
        print("阶段二A已完整退出，开始第五批冻结核心格。", flush=True)
        result = subprocess.run(command, cwd=pilot, env=env)
        if result.returncode:
            raise RuntimeError("第五批入口异常停止，退出码=" + str(result.returncode))
        print("第五批核心生成与前向完成，等待既定评审、独立复核及阶段二报告；不启动阶段三。", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--freeze-commit", required=True)
    args = ap.parse_args()
    run(args.out, args.pilot, args.freeze_commit)
