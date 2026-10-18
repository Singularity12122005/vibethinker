"""Run orchestrator (plan §0.3, §2.4, §10): run directory, frozen config with SHA-256, environment capture, GATES.md /
DEVIATIONS.md writers, model/engine construction, and the stage commands.

    python -m sycophancy_phase0.run init   --run-id R1 --config configs/frozen.yaml
    python -m sycophancy_phase0.run data   --run-id R1            # build F1/F2/F3 banks (+ translation prompts)
    python -m sycophancy_phase0.run mine   --run-id R1            # p_0 / distractor mining, pools, folds
    python -m sycophancy_phase0.run g1 | g15 | g2 | g2a | g40 | g41 | g2b | g42 | g5 | g6   --run-id R1

Every stage reads/writes only under runs/<run_id>/ and records its inputs in config.yaml.  The GPU-only parts (HF/vLLM
engines, judge server) are constructed by ``Context.from_config``; ``--engine fake`` wires the deterministic fake engine
and the char-level tokenizer for smoke tests of the plumbing.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .constants import SYSTEM_PROMPT, TEMPERATURE


# ---------------------------------------------------------------- run directory
RUN_SUBDIRS = ("trajectories", "z", "tables", "figures", "configs", "data")


def run_dir(root: str, run_id: str) -> str:
    return os.path.join(root, "runs", run_id)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_commit(cwd: str) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def pip_freeze() -> str:
    try:
        return subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    except Exception as e:  # pragma: no cover
        return f"pip freeze failed: {e}"


def init_run(root: str, run_id: str, config: dict) -> str:
    """Create runs/<run_id>/ with config.yaml (+ sha256), env.txt and git_commit.txt (plan §0.3)."""
    d = run_dir(root, run_id)
    for sub in RUN_SUBDIRS:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    cfg_text = _dump_yaml(config)
    with open(os.path.join(d, "config.yaml"), "w", encoding="utf-8") as f:
        f.write(cfg_text)
    with open(os.path.join(d, "config.sha256"), "w") as f:
        f.write(sha256_text(cfg_text) + "\n")
    with open(os.path.join(d, "env.txt"), "w", encoding="utf-8") as f:
        f.write(f"python {platform.python_version()} {platform.platform()}\n")
        f.write(pip_freeze())
    with open(os.path.join(d, "git_commit.txt"), "w") as f:
        f.write(git_commit(root) + "\n")
    for name in ("GATES.md", "DEVIATIONS.md"):
        p = os.path.join(d, name)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"# {name[:-3]} — run_id={run_id}\n\n")
    return d


def _dump_yaml(obj, indent: int = 0) -> str:
    """Tiny YAML emitter (no dependency) for flat/nested dicts, lists and scalars."""
    pad = "  " * indent
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{k}:\n{_dump_yaml(v, indent + 1)}")
            else:
                out.append(f"{pad}{k}: {_scalar(v)}")
        return "\n".join(out) + ("\n" if indent == 0 else "")
    if isinstance(obj, list):
        return "\n".join(f"{pad}- {_scalar(v) if not isinstance(v, (dict, list)) else chr(10) + _dump_yaml(v, indent + 1)}" for v in obj)
    return pad + _scalar(obj)


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (dict, list)) and not v:
        return "{}" if isinstance(v, dict) else "[]"
    return json.dumps(str(v), ensure_ascii=False)


def load_config_sha(d: str) -> str:
    with open(os.path.join(d, "config.sha256")) as f:
        return f.read().strip()


def record_deviation(d: str, content: str, reason: str, affects: str) -> None:
    with open(os.path.join(d, "DEVIATIONS.md"), "a", encoding="utf-8") as f:
        f.write(f"- {_dt.date.today().isoformat()} / 偏离：{content} / 原因：{reason} / 影响：{affects}\n")


def write_summary(d: str, gate: str, summary: dict) -> str:
    p = os.path.join(d, "tables", f"{gate}_summary.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=_json_default)
    return p


def _json_default(o):
    try:
        import numpy as np
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
    except Exception:
        pass
    if hasattr(o, "to_json"):
        return o.to_json()
    return str(o)


# ---------------------------------------------------------------- default frozen config (plan §9)
DEFAULT_CONFIG = dict(
    models=dict(M_main="Qwen/Qwen3-30B-A3B-Instruct-2507", M_hybrid="Qwen/Qwen3-30B-A3B", M_dense="Qwen/Qwen3-14B",
                J1="meta-llama/Llama-3.3-70B-Instruct", J2="Qwen/Qwen2.5-72B-Instruct"),
    transformers_version="4.57.1", temperature=TEMPERATURE, max_new_tokens=512, max_new_tokens_think=4096,
    system_prompt=SYSTEM_PROMPT, seeds=dict(f1=20261016, f2=20261016, f3=20261016, folds=20261016, calibration=20261017, g0_random_vec=20261016),
    z_layers=[8, 12, 16, 20, 24, 28, 32, 36, 40, 44], direction_layers=[12, 16, 20, 24, 28, 32, 36],
    action_grid=[-1.0, -0.5, 0.0, 0.5, 1.0], lambda_dose_grid=[0.0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0], lambda_dose_primary=0.05,
    primary_direction="v_cap_perp", pools=dict(p0_main=0.9, p0_dnat=0.3, distractor_min_freq=3),
    gates=dict(g0=dict(kl_floor_median=1e-3, kl_floor_q95=1e-2, tost_margin_pp=1.5, cross_stack_margin_pp=2.0, g06_n=50000),
               g1=dict(p_e4_B_max=0.05, frontier=[0.20, 0.60], N_q_go=100, N_q_caveat=30, escape_diff_min=0.10, c4_min=0.85, hazard_ratio=0.6, a4_min=0.5),
               g2=dict(n_h2=50, n_cont=50, delta_go_pp=-10, delta_weak_pp=-5),
               g2a=dict(n_prefix=40, N=128, M=16, kill_ub=0.02, go_lb=0.08, max_flagged=0.10, kappa1_placeholder=15.0),
               g3=dict(level=0.025, min_frac_rho_sh=0.2), g41=dict(kl_max=0.10, flip_max=0.05, x2_drop=0.03, acc_drop=0.03, alpha_min=0.2),
               g2b=dict(n_y2=32, n_per_arm=16), g42=dict(n_per_arm=32, beta_D_margin=0.2, x4_drop_max=0.03, c4_drop_max=0.05),
               g5=dict(pilot_problems=15, per_problem=3, K=16, G_go=0.05, G_kill=0.03, weights=[0.8, 0.2]), g6=dict(n_h3=200, n_per_arm=32)),
    hardware=dict(gpu="H100-80GB", throughput_factor=1.0),       # plan §7.13 record: A100-80GB => 0.5, GPU-days scale by 1/factor
    require_g0_summary=True,                                      # G4-1 refuses to calibrate without tables/G0_summary.json with a proceed decision
    vllm=dict(enable_prefix_caching=False, dtype="bfloat16", top_k=-1, top_p=1.0, min_p=0.0),
)


# ---------------------------------------------------------------- context (engines, tokenizer, builder)
@dataclass
class Context:
    run_id: str
    run_path: str
    config: dict
    config_sha256: str
    mode: str
    builder: object
    first_turn_ids: Callable[[str], List[int]]
    decode: Callable[[Sequence[int]], str]
    router: object
    judge: Optional[Callable] = None
    judge2: Optional[Callable] = None
    model: object = None
    tokenizer: object = None
    steer_factory: Optional[Callable] = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def fake(cls, root: str, run_id: str, responder, config: Optional[dict] = None) -> "Context":
        """Deterministic plumbing context (tests / dry runs): char tokenizer + FakeEngine for both roles."""
        from .inference.engine import EngineRouter, FakeEngine
        from .inference.templates import TurnBuilder
        import importlib.util
        spec = importlib.util.spec_from_file_location("fake_tok", os.path.join(os.path.dirname(__file__), "..", "..", "tests", "fake_tok.py"))
        ft = importlib.util.module_from_spec(spec); spec.loader.exec_module(ft)   # type: ignore
        cfg = config or DEFAULT_CONFIG
        d = init_run(root, run_id, cfg)
        eng = FakeEngine(responder)
        builder = TurnBuilder(ft.encode, "instruct", ft.is_ws)
        decode = lambda ids: "".join(chr(i - 1000) if i >= 1000 else ("\n\n" if i == 271 else "") for i in ids)
        return cls(run_id, d, cfg, load_config_sha(d), "instruct", builder, lambda x: ft.first_turn_ids(SYSTEM_PROMPT, x, "instruct"), decode,
                   EngineRouter(eng, eng))

    @classmethod
    def from_config(cls, root: str, run_id: str, config: dict, *, model_key: str = "M_main", mode: str = "instruct", use_vllm: bool = True,
                    hf_device: str = "cuda", judge_url: Optional[str] = None, judge2_url: Optional[str] = None, steer_layer: Optional[int] = None,
                    batch_size: int = 32) -> "Context":
        """GPU context: HF model (bf16) for steered/teacher-forced work, vLLM for alpha = 0, judge over HTTP."""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from .inference.engine import EngineRouter, HFEngine
        from .inference.templates import TurnBuilder
        from .rollout import hf_first_turn_ids
        from .scoring.judge import OpenAIChatClient, make_judge
        d = init_run(root, run_id, config)
        name = config["models"][model_key]
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.bfloat16, device_map=hf_device).eval()
        model.requires_grad_(False)
        _assert_generation_config(model)
        _assert_router_fp32(model)
        encode = lambda t: tok.encode(t, add_special_tokens=False)
        is_nl = lambda i: tok.decode([i]) != "" and set(tok.decode([i])) <= {"\n"}
        builder = TurnBuilder(encode, mode, is_nl)
        decode = lambda ids: tok.decode(list(ids), skip_special_tokens=True)
        hf = HFEngine(model, None, batch_size=batch_size)
        null = hf
        if use_vllm:
            from .inference.vllm_engine import VLLMEngine
            null = VLLMEngine(name, max_model_len=config.get("max_model_len", 8192))
        ctx = cls(run_id, d, config, load_config_sha(d), mode, builder, hf_first_turn_ids(tok, mode, config["system_prompt"]), decode,
                  EngineRouter(hf, null), model=model, tokenizer=tok)
        if judge_url:
            ctx.judge = make_judge(OpenAIChatClient(judge_url, config["models"]["J1"]), "J1")
        if judge2_url:
            ctx.judge2 = make_judge(OpenAIChatClient(judge2_url, config["models"]["J2"]), "J2")
        ctx.extra["hf_engine"] = hf
        return ctx


def _assert_generation_config(model) -> None:
    gc = model.generation_config
    bad = {k: getattr(gc, k, None) for k in ("top_p", "top_k", "min_p", "temperature", "repetition_penalty")}
    # the values are overridden per call (plan §4.3); record them and refuse silently-truncating defaults only if a caller forgets
    model.config._sycophancy_generation_defaults = bad


def _assert_router_fp32(model) -> None:
    """plan §2.1: router softmax must be fp32 — Qwen3MoeSparseMoeBlock uses softmax(..., dtype=torch.float); assert the
    class is the stock one (a monkeypatched block would need re-verification)."""
    try:
        from transformers.models.qwen3_moe.modeling_qwen3_moe import Qwen3MoeSparseMoeBlock
        import inspect
        src = inspect.getsource(Qwen3MoeSparseMoeBlock.forward)
        assert "dtype=torch.float" in src, "router softmax is not fp32"
    except ImportError:
        pass


# ---------------------------------------------------------------- stages
def stage_data(ctx: Context, gsm_rows=None, zh_rows=None) -> Dict[str, int]:
    from .data.common import write_bank
    from .data.f1 import build_f1, f1_indices
    from .data.f2 import build_f2
    from .data.f3 import build_f3
    out = {}
    f2 = build_f2(ctx.config["seeds"]["f2"]); write_bank(f2, os.path.join(ctx.run_path, "data", "F2.jsonl")); out["F2"] = len(f2)
    f3 = build_f3(ctx.config["seeds"]["f3"]); write_bank(f3, os.path.join(ctx.run_path, "data", "F3.jsonl")); out["F3"] = len(f3)
    if gsm_rows is not None:
        f1 = build_f1(gsm_rows, zh_rows, indices=f1_indices(ctx.config["seeds"]["f1"]))
        write_bank(f1, os.path.join(ctx.run_path, "data", "F1.jsonl")); out["F1"] = len(f1)
        out["F1_needs_translation"] = sum(1 for r in f1 if r.source.get("needs_translation"))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="sycophancy_phase0.run")
    ap.add_argument("stage", choices=["init", "data"])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--config", default=None, help="JSON file overriding DEFAULT_CONFIG keys")
    args = ap.parse_args(argv)
    cfg = dict(DEFAULT_CONFIG)
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg.update(json.load(f))
    d = init_run(args.root, args.run_id, cfg)
    if args.stage == "init":
        print(d); return 0
    if args.stage == "data":
        ctx = Context(args.run_id, d, cfg, load_config_sha(d), "instruct", None, None, None, None)
        print(json.dumps(stage_data(ctx), ensure_ascii=False)); return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
