import json
import os

from fake_tok import encode
from sycophancy_phase0.constants import IM_END
from sycophancy_phase0.run import DEFAULT_CONFIG, Context, _dump_yaml, init_run, load_config_sha, record_deviation, sha256_text, stage_data, write_summary
from sycophancy_phase0.gates.g0 import GateResult, write_gates_md


def test_init_run_and_yaml(tmp_path):
    d = init_run(str(tmp_path), "R1", DEFAULT_CONFIG)
    for name in ("config.yaml", "config.sha256", "env.txt", "git_commit.txt", "GATES.md", "DEVIATIONS.md"):
        assert os.path.exists(os.path.join(d, name))
    for sub in ("trajectories", "z", "tables", "figures", "configs", "data"):
        assert os.path.isdir(os.path.join(d, sub))
    text = open(os.path.join(d, "config.yaml"), encoding="utf-8").read()
    assert load_config_sha(d) == sha256_text(text) and "transformers_version: \"4.57.1\"" in text and "lambda_dose_primary: 0.05" in text
    assert "M_main: \"Qwen/Qwen3-30B-A3B-Instruct-2507\"" in text and "- -1.0" in text
    assert _dump_yaml(dict(a=None, b=True, c=[1, 2], d={})) == "a: null\nb: true\nc:\n  - 1\n  - 2\nd: {}\n"
    record_deviation(d, "max_new_tokens 512->768", "截断率 6%", "G1")
    assert "偏离：max_new_tokens 512->768" in open(os.path.join(d, "DEVIATIONS.md"), encoding="utf-8").read()
    p = write_summary(d, "G1", dict(decision="GO", x=1.5))
    assert json.load(open(p))["decision"] == "GO"
    write_gates_md([GateResult("G1.a", True, dict(v=1.0), criteria="c")], os.path.join(d, "GATES.md"), "R1", gate="G1", title="校准 pilot", decision="GO")
    assert "## G1 — 校准 pilot   run_id=R1" in open(os.path.join(d, "GATES.md"), encoding="utf-8").read()


def test_fake_context_and_data_stage(tmp_path):
    ctx = Context.fake(str(tmp_path), "R2", lambda ids, seed, alpha, mnt: encode("最终答案：40") + [IM_END])
    assert ctx.run_path.endswith(os.path.join("runs", "R2")) and ctx.router is not None and ctx.builder.mode == "instruct"
    ids = ctx.first_turn_ids("题")
    assert ids[0] == encode("<|im_start|>")[0] and ctx.decode(encode("abc")) == "abc"
    out = stage_data(ctx)
    assert out["F2"] == 120 and out["F3"] == 120 and os.path.exists(os.path.join(ctx.run_path, "data", "F3.jsonl"))
    gsm = [dict(question=f"Q{i} has {i} apples.", answer=f"x\n#### {i}") for i in range(1319)]
    out2 = stage_data(ctx, gsm_rows=gsm, zh_rows=None)
    assert out2["F1"] == 150 and out2["F1_needs_translation"] == 150
