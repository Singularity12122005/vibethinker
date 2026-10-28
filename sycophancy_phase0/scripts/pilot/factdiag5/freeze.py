"""第五批冻结检查：协调端核对真实提交，运行端核对已规定的文件摘要。"""
from pathlib import Path
import hashlib
import json
import re
import subprocess


CODE_PREFIX = "sycophancy_phase0/scripts/pilot/"
PUBLIC_PREFIX = "docs/research/early-stage/factdiag5/"


def canonical_bytes(path):
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def sha256(path):
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def check_committed(repo, out, freeze_commit):
    """提交后在协调端检查；只返回结果，不导出证明、收据或目录树。"""
    if not re.fullmatch(r"[0-9a-f]{40}", freeze_commit):
        raise ValueError("必须提供完整真实提交号")
    reg = json.loads((Path(out) / "factdiag5_prereg.json").read_text(encoding="utf-8"))
    if reg["step0_commit"] == freeze_commit:
        raise ValueError("5.0 必须独立先提交")
    git(repo, "merge-base", "--is-ancestor", reg["step0_commit"], freeze_commit)
    names = list(reg["code_sha256"]) + [PUBLIC_PREFIX + name for name in reg["frozen_files"]]
    names.append(PUBLIC_PREFIX + "factdiag5_prereg.json")
    for name in names:
        if git(repo, "show", freeze_commit + ":" + name) != canonical_bytes(Path(repo) / name):
            raise ValueError("指定提交未包含当前冻结内容：" + name)
    for ext in ("md", "json"):
        name = PUBLIC_PREFIX + "factdiag5_step0." + ext
        if git(repo, "show", reg["step0_commit"] + ":" + name) != canonical_bytes(Path(repo) / name):
            raise ValueError("5.0 已提交产物发生变化")
    return dict(freeze_commit=freeze_commit, step0_commit=reg["step0_commit"], checked_files=len(names))


def validate(out, pilot, commit):
    """协调端先核对实际提交；远端无Git，不伪称在远端验证提交对象。"""
    out, pilot = Path(out), Path(pilot)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("缺少协调端已核对的冻结提交")
    reg = json.loads((out / "factdiag5_prereg.json").read_text(encoding="utf-8"))
    if reg["analysis_freeze"]["status"] != "frozen":
        raise ValueError("拟合细节与缺测处置仍待生成前核对冻结")
    if not reg.get("stage1_confirmed") or not reg.get("step0_complete") or reg["step0_commit"] == commit:
        raise ValueError("阶段一确认或5.0独立提交门槛未满足")
    for name, expected in reg["frozen_files"].items():
        if sha256(out / name) != expected:
            raise ValueError("公开冻结文件变化：" + name)
    for name, expected in reg["code_sha256"].items():
        if not name.startswith(CODE_PREFIX) or ".." in Path(name).parts:
            raise ValueError("代码冻结路径越界")
        path = pilot / "scripts/pilot" / name.removeprefix(CODE_PREFIX)
        if sha256(path) != expected:
            raise ValueError("运行代码偏离冻结：" + name)
    return reg
