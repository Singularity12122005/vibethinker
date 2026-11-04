"""第 1.20 版：独立采集 64 条真实首答；另可只读验收已冻结的全材料配置。"""

import argparse
import copy
import json
from pathlib import Path
import sys

from program_update_development import FAMILIES, OLD_OPENING, material


RUNS = Path("/output/sycophancy-phase0/code/sycophancy_phase0/runs")
MODEL = "/output/sycophancy-phase0/model"
STAGE = "internal8_program_v120"
HEADS = [1365, 1204, 1362, 1378, 1269, 1279, 1202, 1377,
         1201, 1205, 1354, 1364, 1366, 1056, 1418, 1262]


def verify_configuration():
    import torch

    source = RUNS / "internal8_P0_w17"
    config = json.loads((source / "allfit_done.json").read_text())
    assert (config["n"], config["eligible_works"], config["k"]) == (49, 8, 1)
    assert config["m"] == len(HEADS) and config["heads"] == HEADS
    assert config["remove"][14] < .8 <= config["remove"][15]
    assert config["compression"][0] >= .5
    directions = torch.load(source / "pooled_directions.pt", map_location="cpu",
                            weights_only=True)
    assert set(directions) == {head // 32 for head in HEADS}
    for basis in directions.values():
        assert basis.ndim == 2 and basis.shape[1] == 2048 and basis.shape[0] >= 1
        assert torch.isfinite(basis[0]).all()
        assert abs(basis[0].double().norm().item() - 1.) < 1e-5
    print("已验收全材料的 16 个头、6 层和各层第一方向。")


def questions(families=FAMILIES):
    prompts = {}
    for index, family in enumerate(families):
        assert tuple(family.outcome(v) for v in (0, 1)) == family.expected
        assert family.expected.count(family.candidate) == 1
        for variant in (0, 1):
            turns, followups, _ = material(family, variant)
            assert followups["当前版本实测"].replace("build: 18", "build: 17") == followups["旧版本同结果"]
            assert [role for role, _ in turns] == ["user", "assistant", "user", "assistant", "user"]
            assert turns[3][1].startswith(OLD_OPENING)
            prompts[f"f{index + 1}-v{variant}"] = [
                {"role": role, "content": content} for role, content in turns
            ]
    assert len(prompts) == 8
    return prompts


def collect(directory, prompts, stage=STAGE, complete=False):
    import torch
    from transformers import AutoTokenizer

    sys.path.insert(0, str(RUNS / "internal8_P0_w17"))
    from w17_core import Engine
    import g1_runtime_main as legacy

    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    result_file = directory / "first_answers.json"
    rows = json.loads(result_file.read_text()) if result_file.exists() else {}
    keys = {f"{item}-{i}" for item in prompts for i in range(8)}
    assert set(rows) <= keys
    engine = None
    stops = (legacy.IM_END, legacy.ENDOFTEXT)
    with torch.inference_mode():
        for item, messages in prompts.items():
            rendered = tokenizer.apply_chat_template(messages, tokenize=False,
                                                      add_generation_prompt=True)
            assert rendered.endswith("<|im_start|>assistant\n") and "<think>" not in rendered
            ids = tokenizer.encode(rendered, add_special_tokens=False)
            for i in range(8):
                row = rows.get(f"{item}-{i}")
                if row is not None:
                    assert row["prompt_ids"] == ids and len(row["raw_ids"]) > 0
                    assert row["raw_ids"][-1] in stops or row["truncated"]
            if all(f"{item}-{i}" in rows and (not complete or not rows[f"{item}-{i}"]["truncated"])
                   for i in range(8)):
                continue
            if engine is None:
                engine = Engine()
            initial = engine.call(ids, None, "program_first_prefill")
            for i in range(8):
                key = f"{item}-{i}"
                previous = rows.get(key)
                if previous is not None and (not complete or not previous["truncated"]):
                    continue
                seed = legacy.derive_seed(stage, item, "first", "native", i, 1)
                sampler = legacy.SeededGumbelSampler([seed], temperature=.7, device="cuda")
                seq = torch.tensor([ids], device="cuda")
                cache = copy.deepcopy(initial.past_key_values)
                scores = initial.logits[0, -1].float()
                raw = []
                frozen = previous["raw_ids"] if previous else []
                def persist():
                    result = {"prompt_ids": ids, "raw_ids": list(raw),
                              "text": tokenizer.decode(raw, skip_special_tokens=True),
                              "truncated": raw[-1] not in stops}
                    if previous:
                        result["initial_stop_length"] = previous.get("initial_stop_length", len(frozen))
                    rows[key] = result
                    tmp = result_file.with_suffix(".part")
                    tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf8")
                    tmp.replace(result_file)
                while True:
                    token = sampler(seq, scores[None, :]).argmax(-1).item()
                    if len(raw) < len(frozen):
                        assert token == frozen[len(raw)], (key, len(raw), "原词元续接核对失败")
                    raw.append(token)
                    if token in stops or (not complete and len(raw) == 1024):
                        break
                    if complete and len(raw) > len(frozen) and len(raw) % 128 == 0:
                        persist()
                    seq = torch.cat((seq, seq.new_tensor([[token]])), dim=1)
                    step = engine.call([token], cache, "program_first_token")
                    scores, cache = step.logits[0, -1].float(), step.past_key_values
                persist()
    assert set(rows) == keys
    print("已生成或接续至 64 条；等待逐条首答判分。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("materials", "configuration", "sample"))
    parser.add_argument("--hard", action="store_true")
    parser.add_argument("--complete", action="store_true",
                        help="原词元原抽样流续接触顶项，至自然结束")
    parser.add_argument("--wait", action="store_true",
                        help="等原采样进程释放本批目录再接续")
    args = parser.parse_args()
    action = args.action
    if action == "configuration":
        verify_configuration()
        return
    families, stage = FAMILIES, STAGE
    if args.hard:
        from program_update_hard import FAMILIES as hard_families
        families, stage = hard_families, "internal8_program_hard_v120"
    prompts = questions(families)
    if action == "materials":
        print(f"已核对 {len(prompts)} 道题；首答输入不含后续施压消息和评估标签。")
        return
    import fcntl
    import os

    directory = RUNS / stage
    directory.mkdir(exist_ok=True)
    fd = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if args.wait else fcntl.LOCK_NB))
        collect(directory, prompts, stage, args.complete)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
