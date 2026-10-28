"""等第五批生成与前向完整退出，再串行执行独立冻结的评审。"""
from pathlib import Path
import argparse
import fcntl
import json
import os
import subprocess
import time

from .review_protocol import validate_review


OUTPUTS = {"core_generations.json": 3364, "core_forward.json": 496, "version_forward.json": 30}


def generation_complete(out):
    complete = True
    for name, expected in OUTPUTS.items():
        path = out / name
        if not path.exists():
            complete = False
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or len(rows) > expected:
            raise RuntimeError("第五批输出结构或计数偏离冻结：" + name)
        complete = complete and len(rows) == expected
    return complete


def generation_processes(out):
    result = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            args = [word.decode(errors="replace") for word in (path / "cmdline").read_bytes().split(b"\0") if word]
        except OSError:
            continue
        if str(out) in args and any(word in ("scripts.pilot.factdiag5.runtime", "scripts.pilot.factdiag5.continue_core") for word in args):
            result.append(int(path.name))
    return result


def run(out, pilot, commit):
    if os.name != "posix" or pilot.resolve() != Path("/output/sycophancy-phase0/pilot") or out.resolve() != pilot.resolve() / "factdiag5_20261112":
        raise RuntimeError("评审接续只能在指定A100目录执行")
    validate_review(out, pilot, commit)
    with (out / ".continue_reviews.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("等待第五批核心生成、前向及其进程退出；不占用显卡。", flush=True)
        while True:
            complete = generation_complete(out)
            active = generation_processes(out)
            if complete and not active:
                break
            if not complete and not active:
                raise RuntimeError("第五批生成或前向未完整且没有执行进程，停止评审接续并等待协调诊断")
            time.sleep(30)
        env = dict(os.environ, PYTHONPATH="/output/sycophancy-phase0/code/src",
                   OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        command = ["/output/sycophancy-phase0/venv-experts/bin/python", "-u", "-m",
                   "scripts.pilot.factdiag5.review_runtime", "--out", str(out), "--pilot", str(pilot),
                   "--review-commit", commit]
        print("第五批生成与前向已完整退出，开始独立冻结的机器评审。", flush=True)
        result = subprocess.run(command, cwd=pilot, env=env)
        if result.returncode:
            raise RuntimeError("第五批机器评审异常停止，退出码=" + str(result.returncode))
        print("第五批机器评审完成，等待独立复核、规定分析及阶段二报告；不启动阶段三。", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--review-commit", required=True)
    args = ap.parse_args()
    run(args.out, args.pilot, args.review_commit)
