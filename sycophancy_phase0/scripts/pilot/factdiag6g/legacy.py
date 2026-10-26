"""只读加载前批代码，保留前批冻结文件与标签。"""
import importlib.util
from pathlib import Path
import sys

PILOT = Path(__file__).resolve().parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def previous():
    key = "factdiag6g_previous_common"
    if key not in sys.modules:
        load_file(key, PILOT / "factdiag4/common.py")
    return sys.modules[key]


def judge_dependency():
    loader = load_file("factdiag6g_previous_launch_judge", PILOT / "factdiag4/launch_judge.py")
    return loader.load_judge_dependency()
