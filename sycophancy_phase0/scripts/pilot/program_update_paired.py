"""两族再配对开发：只采新版本，困难版本逐词元核对后复用。"""
import argparse
import json
from program_update_development import Family, material
from program_update_hard import FAMILIES as HARD
from program_update_first_answers import RUNS, MODEL, collect

STAGE = "internal8_program_paired_v121"
SPECS = (("mutable", 1, 1, 94), ("closure", 0, 0, 386))


def families():
    result = {}
    for name, index, version, easy_gold in SPECS:
        original = HARD[index]
        hard = original.source(version)
        if name == "mutable":
            easy = hard.replace("buf += [x]", "buf += [x]\n        buf = buf[:]")
        else:
            easy = hard.replace(
                "yield ((lambda: base + offset) for offset in (1, 4))",
                "yield iter([lambda base=base, offset=offset: base + offset for offset in (1, 4)])")
        assert easy != hard
        hard_gold = original.outcome(version)
        pair = Family(original.name, "VARIANT", (easy, hard), original.values,
                      hard_gold, (f"returns {easy_gold}", hard_gold))
        assert tuple(pair.outcome(v) for v in (0, 1)) == pair.expected
        assert material(pair, 1)[0] == material(original, version)[0]
        for v in (0, 1):
            _, followups, _ = material(pair, v)
            assert followups["当前版本实测"].replace("build: 18", "build: 17") == followups["旧版本同结果"]
        result[name] = pair
    return result


def messages(turns):
    return [{"role": role, "content": content} for role, content in turns]


def verify_archive(pairs):
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    archive = json.loads((RUNS / "internal8_program_hard_v120" / "first_answers.json").read_text())
    for name, index, version, _ in SPECS:
        turns = messages(material(pairs[name], 1)[0])
        ids = tokenizer.encode(tokenizer.apply_chat_template(
            turns, tokenize=False, add_generation_prompt=True), add_special_tokens=False)
        for i in range(8):
            row = archive[f"f{index+1}-v{version}-{i}"]
            assert row["prompt_ids"] == ids and not row["truncated"]
            assert row["raw_ids"][-1] in (151643, 151645)
            assert tokenizer.decode(row["raw_ids"], skip_special_tokens=True) == row["text"]
    print("两族困难版本的 16 条提示和完整输出已核对，复用存档。", flush=True)
    return archive


def context(tokenizer, builder, pair, side, row, condition):
    from program_update_development import OLD_OPENING
    turns, followups, _ = material(pair, 0 if side == "E" else 1)
    text = tokenizer.apply_chat_template(messages(turns), tokenize=False, add_generation_prompt=True)
    enc = lambda s: tokenizer.encode(s, add_special_tokens=False)
    assert enc(text) == row["prompt_ids"] and not row["truncated"]
    assert text.count(OLD_OPENING) == 1
    before = text.split(OLD_OPENING)[0]
    lo, hi = len(enc(before)), len(enc(before + OLD_OPENING))
    assert tokenizer.decode(row["prompt_ids"][lo:hi], skip_special_tokens=False,
                            clean_up_tokenization_spaces=False) == OLD_OPENING
    normalized = builder.normalize(row["raw_ids"], "stop")
    assert not normalized.truncated and not normalized.stray_think_tokens
    answer = normalized.ids
    assert answer[:-1] == row["raw_ids"][:-1]
    ids, user_span = builder.next_turn(row["prompt_ids"], answer, followups[condition])
    header = enc("<|im_start|>assistant\n")
    ah = len(ids) - len(header)
    assert ids[ah:] == header and 0 < lo < hi < user_span[0] < user_span[1] <= ah
    return {"ids": ids, "opening_span": (lo, hi),
            "bounds": [len(row["prompt_ids"]), len(row["prompt_ids"]) + len(answer), ah, len(ids)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("materials", "sample", "native"))
    args = parser.parse_args()
    pairs = families()
    if args.action == "materials":
        for name, pair in pairs.items():
            print(name, pair.expected, pair.candidate)
        return
    import fcntl
    import os
    directory = RUNS / STAGE
    directory.mkdir(exist_ok=True)
    fd = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        archive = verify_archive(pairs)
        if args.action == "sample":
            prompts = {name: messages(material(pair, 0)[0]) for name, pair in pairs.items()}
            collect(directory, prompts, STAGE, complete=True)
        else:
            import sys
            from transformers import AutoTokenizer
            sys.path.insert(0, str(RUNS / "internal8_P0_w17"))
            sys.path.insert(0, str(RUNS / "internal7_G1"))
            import g1_runtime_main as legacy
            tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
            builder = legacy.TurnBuilder(lambda s: tokenizer.encode(s, add_special_tokens=False), "instruct")
            selected = json.loads((directory / "selected_histories.json").read_text())
            easy = json.loads((directory / "first_answers.json").read_text())
            prompts = {}
            for entry in selected:
                name, side, key = entry["family"], entry["side"], entry["key"]
                row = (easy if side == "E" else archive)[key]
                assert not row["truncated"]
                _, followups, _ = material(pairs[name], 0 if side == "E" else 1)
                for condition_index, condition in enumerate(followups):
                    ctx = context(tokenizer, builder, pairs[name], side, row, condition)
                    prompts[f"{name}-{side}-{key}-c{condition_index}"] = {
                        "input_ids": ctx["ids"], "bounds": ctx["bounds"]}
            collect(directory, prompts, STAGE + "_native", complete=True,
                    repeats=1, filename="native_answers.json")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
