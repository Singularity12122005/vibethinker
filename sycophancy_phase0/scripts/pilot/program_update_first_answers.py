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


def questions():
    prompts = {}
    for index, family in enumerate(FAMILIES):
        assert tuple(family.outcome(v) for v in (0, 1)) == family.expected
        for variant in (0, 1):
            turns, _, _ = material(family, variant)
            assert [role for role, _ in turns] == ["user", "assistant", "user", "assistant", "user"]
            assert turns[3][1].startswith(OLD_OPENING)
            prompts[f"f{index + 1}-v{variant}"] = [
                {"role": role, "content": content} for role, content in turns
            ]
    assert len(prompts) == 8
    return prompts


def collect(directory, prompts):
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
                    assert row["prompt_ids"] == ids and 0 < len(row["raw_ids"]) <= 1024
                    assert row["raw_ids"][-1] in stops or len(row["raw_ids"]) == 1024
            if all(f"{item}-{i}" in rows for i in range(8)):
                continue
            if engine is None:
                engine = Engine()
            initial = engine.call(ids, None, "program_first_prefill")
            for i in range(8):
                key = f"{item}-{i}"
                if key in rows:
                    continue
                seed = legacy.derive_seed(STAGE, item, "first", "native", i, 1)
                sampler = legacy.SeededGumbelSampler([seed], temperature=.7, device="cuda")
                seq = torch.tensor([ids], device="cuda")
                cache = copy.deepcopy(initial.past_key_values)
                scores = initial.logits[0, -1].float()
                raw = []
                for _ in range(1024):
                    token = sampler(seq, scores[None, :]).argmax(-1).item()
                    raw.append(token)
                    if token in stops or len(raw) == 1024:
                        break
                    seq = torch.cat((seq, seq.new_tensor([[token]])), dim=1)
                    step = engine.call([token], cache, "program_first_token")
                    scores, cache = step.logits[0, -1].float(), step.past_key_values
                rows[key] = {"prompt_ids": ids, "raw_ids": raw,
                             "text": tokenizer.decode(raw, skip_special_tokens=True),
                             "truncated": raw[-1] not in stops}
                tmp = result_file.with_suffix(".part")
                tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf8")
                tmp.replace(result_file)
    assert set(rows) == keys
    print("已生成或接续至 64 条；等待逐条首答判分。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("materials", "configuration", "sample"))
    action = parser.parse_args().action
    if action == "configuration":
        verify_configuration()
        return
    prompts = questions()
    if action == "materials":
        print(f"已核对 {len(prompts)} 道题；首答输入不含后续施压消息和评估标签。")
        return
    import fcntl
    import os

    directory = RUNS / STAGE
    directory.mkdir(exist_ok=True)
    fd = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        collect(directory, prompts)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
