"""分时真实评审；重建标签与结局，评审输入不含剂量或阶段。"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from common import Blocked, cli, context, load, parser, require_scored, save, trajectories
from sycophancy_phase0.rollout import _score
from sycophancy_phase0.scoring.judge import make_judge
from sycophancy_phase0.stages import load_problems
from sycophancy_phase0.trajectory import JsonlWriter


class LocalJudge:
    def __init__(self, model_path, batch_size=8):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch, self.batch_size = torch, batch_size
        if not torch.cuda.is_available() or "A100" not in torch.cuda.get_device_name():
            raise Blocked("评审需要当前已授权 A100，不能用规则或假模型替代")
        self.tok = AutoTokenizer.from_pretrained(model_path, padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(model_path, dtype=torch.bfloat16,
                      device_map="cuda", attn_implementation="sdpa").eval()
        self.model.requires_grad_(False)

    def __call__(self, prompts):
        result = []
        for off in range(0, len(prompts), self.batch_size):
            rendered = [self.tok.apply_chat_template([{"role": "user", "content": p}],
                         tokenize=False, add_generation_prompt=True) for p in prompts[off:off + self.batch_size]]
            batch = self.tok(rendered, return_tensors="pt", padding=True).to(self.model.device)
            with self.torch.no_grad():
                gen = self.model.generate(**batch, do_sample=False, max_new_tokens=64,
                         pad_token_id=self.tok.pad_token_id, temperature=None, top_p=None, top_k=None)
            result.extend(self.tok.batch_decode(gen[:, batch.input_ids.shape[1]:], skip_special_tokens=True))
        return result


def rescore_batch(rows, bank, judge):
    states = []
    for tr in rows:
        # 复用测试框架的题干/比较值构造；这里从不传 arm 或 alpha 给评审。
        extra = dict(tr.extra)
        extra.pop("labels_provisional", None)
        spec = SimpleNamespace(problem=deepcopy(bank[tr.problem_id]), script=tr.script, T=4,
                               stop_after=len(tr.turns) if len(tr.turns) < 4 else None, extra=extra)
        states.append(SimpleNamespace(spec=spec, turns=tr.turns))
    _score(states, judge, None)
    for tr, st in zip(rows, states):
        tr.outcomes = st.spec.extra.pop("_outcomes")
        tr.extra = st.spec.extra
    return rows


def main():
    ap = parser(__doc__)
    ap.add_argument("stage", nargs="+", choices=("P_A1", "P_A2", "P_B2", "P_B2_double", "P_B3", "P_SMOKE", "P_pressure8", "P_pressure50",
                    "P_screen_P1", "P_screen_P2", "P_screen_P3", "P_screen_B"))
    ap.add_argument("--judge-path", required=True)
    ap.add_argument("--judge-batch", type=int, default=8)
    args = ap.parse_args()
    ctx = context(args)
    if ctx.config["judge_model"] != "Qwen/Qwen2.5-32B-Instruct":
        raise Blocked("当前入口仅支持事先选定的单卡评审")
    # 验证本地路径实际模型族与结构，避免把被控模型当作评审。
    cfgpath = Path(args.judge_path) / "config.json"
    if cfgpath.exists() and load(cfgpath).get("model_type") != "qwen2":
        raise Blocked("评审路径不是指定的 Qwen2.5 模型")
    judge = None
    for stage in args.stage:
        if stage.startswith(("P_pressure", "P_screen_")):
            from pressure_inputs import pressure_bank
            bank, _ = pressure_bank(ctx)
        else:
            bank = load_problems(ctx)
        rows = trajectories(ctx, stage)
        pending = [r for r in rows if r.extra.get("labels_provisional") or any(t.t in (2, 3) and not t.judge for t in r.turns)]
        if pending:
            if judge is None:
                judge = make_judge(LocalJudge(args.judge_path, args.judge_batch), ctx.config["judge_model"])
            path = Path(ctx.run_path) / "trajectories" / f"{stage}.jsonl"
            for off in range(0, len(pending), 64):
                rescore_batch(pending[off:off + 64], bank, judge)
                tmp = path.with_suffix(".rescore.tmp")
                with JsonlWriter(str(tmp)) as w:
                    for row in rows:
                        w.write(row)
                tmp.replace(path)
                print(f"评审 {stage}: {min(off + 64, len(pending))}/{len(pending)}", flush=True)
        require_scored(rows)
        labs = [t.judge for r in rows for t in r.turns if t.t in (2, 3)]
        save(Path(ctx.run_path) / "tables" / f"{stage}_judge.json",
             dict(model=ctx.config["judge_model"], n=len(labs), parse_errors=sum(x["parse_error"] for x in labs),
                  inconsistent=sum(x.get("consistent") is False for x in labs), human_validation="尚未完成人工抽查"))


if __name__ == "__main__":
    cli(main)
