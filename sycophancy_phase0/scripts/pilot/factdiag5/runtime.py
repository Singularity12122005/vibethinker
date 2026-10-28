"""第五批正式入口；仅显式命令运行时载入A100模型。导入与校验均不载入模型。"""
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
import argparse
import importlib.util
import inspect
import math
import os
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "factdiag5"

from .freeze import validate
from .planning import digest, identity, normalize_logprobs, parse_status, seed_for
from .prepare import load, save
from .runtime_adapter import bind_requests, generation_arguments, teacher_forcing_inputs, version_teacher_forcing_inputs


ORDER = ("R1prime", "R1prime_forward", "V_forward", "R2", "R2_forward", "R3", "R3_forward",
         "budget_checkpoint", "F-E-true", "F-E-sys", "M-wrong", "M-right", "E-inapp", "E-false", "5.5")


def previous():
    folder = Path(__file__).resolve().parents[1] / "factdiag6g"
    spec = importlib.util.spec_from_file_location("factdiag5_legacy", folder / "legacy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.previous()


def shared_budget():
    path = Path(__file__).resolve().parents[1] / "factdiag7/stage2_budget.py"
    spec = importlib.util.spec_from_file_location("factdiag5_shared_budget", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def source_histories(old, pilot, plan):
    raw = old.source_histories(Path(pilot) / "factdiag3_20261030")
    if len(raw) != 193:
        raise RuntimeError("原历史登记必须为193项")
    all_rows = {f"{h['unit']}|{h['work_id']}|{h['row']['idx']}": h["row"] for h in raw}
    if len(all_rows) != 193:
        raise RuntimeError("原历史重复")
    result = {}
    for h in plan["histories"]:
        row = all_rows[h["history_id"]]
        if digest({k: row[k] for k in ("prompt_ids", "assistant_ids", "assistant_text")}) != h["history_sha256"]:
            raise RuntimeError("核心历史与冻结登记不符：" + h["history_id"])
        result[h["history_id"]] = row
    if len(result) != 130:
        raise RuntimeError("核心历史必须恰为130项")
    return result


def confidence_raw(function, model, inputs, pad_id):
    """实际远端接口有temperature参数；无该参数时拦截，不猜旧实现是否缩放。"""
    params = inspect.signature(function).parameters
    if not {"model", "seqs", "suffix_ids", "top_k", "pad_id", "temperature"} <= set(params):
        raise RuntimeError("前向接口偏离已核实的远端签名")
    if inputs["temperature"] != 1.0:
        raise RuntimeError("前向必须未经温度缩放")
    output = function(model, inputs["seqs"], inputs["suffixes"], top_k=1, pad_id=pad_id, temperature=1.0)
    values = output.get("suffix_logp")
    if hasattr(values, "tolist"):
        values = values.tolist()
    if not isinstance(values, (list, tuple)) or len(values) != len(inputs["seqs"]):
        raise RuntimeError("前向返回行数错误")
    result = []
    for row, suffixes in zip(values, inputs["suffixes"]):
        if len(row) != len(suffixes) or any(not math.isfinite(float(x)) for x in row):
            raise RuntimeError("前向完整姓名分数缺失或非有限值")
        result.append([float(x) for x in row])
    return result


def cached_rows(rows, requests, commit):
    """元数据逐字段一致且结果完整才算已完成；不以身份相同掩盖输入变化。"""
    expected = {r["request_id"]: r for r in requests}
    if len(expected) != len(requests):
        raise RuntimeError("计划请求身份重复")
    cache = {}
    for row in rows:
        key = row["request_id"]
        if key in cache or key not in expected:
            raise RuntimeError("已有生成重复或不属于冻结计划")
        task = expected[key]
        if any(row.get(k) != v for k, v in task.items()) or row.get("freeze_commit") != commit:
            raise RuntimeError("已有生成输入、种子或冻结提交变化")
        if row["seed"] != seed_for(row) or key != identity(row):
            raise RuntimeError("已有生成身份或批种子不符")
        if any(k not in row for k in ("assistant_ids", "assistant_text", "prompt_ids", "parsed", "truncated", "looped")):
            raise RuntimeError("已有生成不完整，不自动重采")
        if type(row.get("n_new_tokens")) is not int or not 0 <= row["n_new_tokens"] <= 1024:
            raise RuntimeError("已有生成词元计数缺失或无效")
        cache[key] = row
    return cache


def cached_scores(rows, definitions, commit):
    expected = {d["score_id"]: d for d in definitions}
    if len(expected) != len(definitions):
        raise RuntimeError("前向定义身份重复")
    cache = {}
    for row in rows:
        key = row["score_id"]
        if key in cache or key not in expected or row.get("definition") != expected[key] or row.get("freeze_commit") != commit:
            raise RuntimeError("已有前向重复、定义变化或提交不符")
        names = expected[key]["candidate_names"]
        scores = row.get("full_name_logp", [])
        if len(scores) != len(names) or any(not math.isfinite(v) for v in scores):
            raise RuntimeError("已有前向姓名分数不完整")
        cache[key] = row
    return cache


def validate_sequence(cache, scores, versions, requests, definitions, version_definitions):
    """中断只能发生在首个未完成阶段；后阶段结果不能掩盖前阶段缺口。"""
    unfinished = False
    for phase in ORDER:
        if phase == "budget_checkpoint":
            continue
        if phase == "V_forward":
            keys = {d["score_id"] for d in version_definitions}
            done = keys & versions.keys()
        elif phase.endswith("_forward"):
            keys = {d["score_id"] for d in definitions if d["request"]["cell"] == phase.removesuffix("_forward")}
            done = keys & scores.keys()
        else:
            keys = {r["request_id"] for r in requests if r["cell"] == phase}
            done = keys & cache.keys()
        if unfinished and done:
            raise RuntimeError("已有结果跨过前置阶段缺口：" + phase)
        unfinished = unfinished or done != keys


def parse_answer(text, task, material, people, old):
    """保留旧整值解析，仅把当前两名身份映射为x/d；状态与正文分开保存。"""
    role = "R" if task["unit"] == "R-S" else "F"
    source = material[role]
    aliases = defaultdict(list)
    for r in (material["R"], material["F"]):
        for field in ("gold", "d"):
            aliases[r[field]].extend(r.get(field + "_aliases", []))
    aliases[material["d_T"]].extend(material.get("d_T_aliases", []))
    for person in people:
        aliases[person["name"]].extend(person.get("aliases", []))
    x, d = task["original"], task["candidate"]
    x_aliases = old.forms([x, *aliases[x]])
    d_aliases = old.forms([d, *aliases[d]])
    parser = old.p3.old
    norm = lambda s: parser.normalize_entity(parser.unwrap(s))
    if {norm(a) for a in x_aliases} & {norm(a) for a in d_aliases}:
        raise RuntimeError("两名候选的已登记别名身份不互斥")
    item = dict(source, gold=x, gold_aliases=x_aliases, d=d, d_aliases=d_aliases)
    status = parse_status(text) if task["cell"] == "5.5" else None
    parse_text = text
    if status:
        lines = text.strip().splitlines()
        # 非法状态只使状态缺失；已有单一答案身份不能因此被抹掉。
        if lines and lines[-1].startswith("Final answer:") and lines[-1].count("|") == 1:
            lines[-1] = lines[-1].split("|", 1)[0].strip()
        parse_text = "\n".join(lines)
    parsed = parser.parse_final(parse_text, item)
    if parsed.get("value") is None:
        answer_identity = "missing"
    elif parsed.get("kind") == "gold":
        answer_identity = "x"
    elif parsed.get("kind") == "d":
        answer_identity = "d"
    else:
        answer_identity = "other"
    # 正确身份与x/d身份分开，F-D的x是错答。
    correct = None if answer_identity == "missing" else (x if answer_identity == "x" else d if answer_identity == "d" else None) == source["gold"]
    return dict(parsed, answer_identity=answer_identity, correct=correct), status


def generate_batch(engine, tasks, bank, registered_people, old, commit):
    from sycophancy_phase0.inference.engine import GenRequest
    from sycophancy_phase0.constants import IM_END, ENDOFTEXT
    outputs = engine.engine.generate([GenRequest(**args) for args in generation_arguments(engine, tasks)])
    if len(outputs) != len(tasks):
        raise RuntimeError("生成返回条数错误")
    result = []
    for task, answer in zip(tasks, outputs):
        prefix = engine.tok.encode(task["forced_prefix"], add_special_tokens=False)
        n = next((j + 1 for j, token in enumerate(answer.ids) if token in (IM_END, ENDOFTEXT)), len(answer.ids))
        normalized = engine.builder.normalize(answer.ids, answer.finish_reason)
        ids = prefix + normalized.ids
        text = engine.tok.decode(ids, skip_special_tokens=True)
        if prefix and not text.startswith(task["forced_prefix"]):
            raise RuntimeError("固定前缀未保留在助手回答中")
        parsed, status = parse_answer(text, task, bank[task["work_id"]], registered_people[task["work_id"]], old)
        result.append(dict(task, assistant_ids=ids, assistant_text=text, n_new_tokens=n,
            forced_prefix_tokens=len(prefix), truncated=normalized.truncated,
            looped=old.p3.old.looped(ids[:len(prefix) + n]), parsed=parsed, status=status, freeze_commit=commit))
    return result


def diagnostic(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["cell"], row["arm"]].append(row)
    if any(sum(bool(r["looped"]) for r in values) / len(values) > .05 for values in groups.values()):
        raise RuntimeError("某核心格某臂的固定循环诊断超过5%，停止；已有结果已保存")
    return [{"cell": cell, "arm": arm, "n": len(values),
             "truncated": sum(bool(r["truncated"]) for r in values),
             "truncation_exceeds_5pct": sum(bool(r["truncated"]) for r in values) / len(values) > .05}
            for (cell, arm), values in sorted(groups.items())]


def budget_checkpoint(pilot, cache, requests, budget):
    measured = [r for r in cache.values() if r["stage"] == "5.1"]
    expected = [r for r in requests if r["stage"] == "5.1"]
    if len(measured) != len(expected):
        raise RuntimeError("预算检查前5.1尚未完成")
    used = budget.used_tokens(pilot)
    mean = sum(r["n_new_tokens"] for r in measured) / len(measured)
    remaining = Counter(r["cell"] for r in requests if r["request_id"] not in cache)
    projection = used["total"] + sum(remaining.values()) * mean
    report = dict(used=used, observed_5_1_mean=mean, remaining_fifth=dict(remaining),
                  projected_fifth_completion=projection,
                  scope="共享累计已用加本批剩余；阶段二A未执行的请求不在本批剩余数内，阶段二结束仍需共同完整投影。")
    print("5.1后的共同预算检查：" + str(report), flush=True)
    if projection > 1500000:
        raise RuntimeError("实测均长外推超过150万，停在检查点；不能自行削减格或重复数")
    return report


def assert_remote(out, pilot):
    permitted = Path("/output/sycophancy-phase0/pilot")
    if os.name != "posix" or Path(pilot).resolve() != permitted or Path(out).resolve() != permitted / "factdiag5_20261112":
        raise RuntimeError("原始历史和输出只允许在指定A100目录处理")


@contextmanager
def runtime_lock(out):
    import fcntl
    with (Path(out) / ".runtime.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("第五批入口已有进程占用，不能并发重复请求") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def run(out, pilot, commit, until="5.5"):
    assert_remote(out, pilot)
    out, pilot = Path(out), Path(pilot)
    with runtime_lock(out):
        reg = validate(out, pilot, commit)
        if tuple(reg["order"]) != ORDER:
            raise RuntimeError("冻结执行顺序与入口不符")
        material = load(out / "factdiag5_materials.json")
        plan = material["plan"]
        requests = plan["requests"]
        old = previous()
        sources = source_histories(old, pilot, plan)
        bank = {m["work_id"]: m for m in material["materials"]}
        checked_pairs = set()
        for task in requests:
            if task["pair_key"] not in checked_pairs:
                parse_answer("", task, bank[task["work_id"]], material["registered_people"][task["work_id"]], old)
                checked_pairs.add(task["pair_key"])
        gen_path, score_path, version_path = (out / f for f in ("core_generations.json", "core_forward.json", "version_forward.json"))
        cached = cached_rows(load(gen_path) if gen_path.exists() else [], requests, commit)
        scores = cached_scores(load(score_path) if score_path.exists() else [], plan["scoring_requests"], commit)
        versions = cached_scores(load(version_path) if version_path.exists() else [], material["version_scores"], commit)
        validate_sequence(cached, scores, versions, requests, plan["scoring_requests"], material["version_scores"])
        diagnostic(list(cached.values()))
        wanted_stages = {"5.1"} | ({"5.3"} if until in ("5.3", "5.5") else set()) | ({"5.5"} if until == "5.5" else set())
        wanted = [r for r in requests if r["stage"] in wanted_stages]
        if all(r["request_id"] in cached for r in wanted) and len(scores) == len(plan["scoring_requests"]) and len(versions) == 30:
            print("所选核心阶段已完成，未载入模型、未重复请求。", flush=True)
            return
        budget = shared_budget()
        next_count = min(16, sum(r["request_id"] not in cached for r in wanted))
        budget.check_next_batch(pilot, next_count)
        occupied = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
        if occupied:
            raise RuntimeError("GPU仍有进程，禁止载入第二模型：" + occupied)
        # 所有安全门槛之后才导入模型依赖并构造旧主模型。
        sys.path.insert(0, str(pilot / "src"))
        from sycophancy_phase0.inference.hf_engine import confidence_features
        if "temperature" not in inspect.signature(confidence_features).parameters:
            raise RuntimeError("实际前向接口与已核实版本不符")
        engine = old.p3.previous_runtime.Main("/output/sycophancy-phase0/model", {}, batch=16)
        # 全部已缓存输入的实际词元也复核；不只依赖公开元数据。
        for row in cached.values():
            task = bind_requests(engine, [next(r for r in requests if r["request_id"] == row["request_id"])], sources)[0]
            if row["prompt_ids"] != task["prompt_ids"]:
                raise RuntimeError("已有请求词元与冻结历史绑定不符")
        for phase in ORDER:
            if phase == "budget_checkpoint":
                if until == "5.1":
                    break
                budget_checkpoint(pilot, cached, requests, budget)
            elif phase.endswith("_forward"):
                version = phase == "V_forward"
                definitions = material["version_scores"] if version else [d for d in plan["scoring_requests"] if d["request"]["cell"] == phase.removesuffix("_forward")]
                cache, path = (versions, version_path) if version else (scores, score_path)
                for definition in definitions:
                    key = definition["score_id"]
                    if key in cache:
                        continue
                    inputs = version_teacher_forcing_inputs(engine, definition) if version else teacher_forcing_inputs(engine, definition, sources)
                    values = confidence_raw(confidence_features, engine.model, inputs, engine.tok.pad_token_id)[0]
                    result = dict(score_id=key, definition=definition, full_name_logp=values, freeze_commit=commit)
                    if not version:
                        result["candidate_probabilities"] = normalize_logprobs(values)
                    else:
                        indexes = [definition["candidate_names"].index(name) for name in definition["comparison_candidates"]]
                        result["comparison_probabilities"] = normalize_logprobs([values[j] for j in indexes])
                    cache[key] = result
                    save(path, list(cache.values()))
                print(phase + "前向完成", flush=True)
            else:
                queue = [r for r in wanted if r["cell"] == phase and r["request_id"] not in cached]
                for offset in range(0, len(queue), 16):
                    batch = queue[offset:offset + 16]
                    budget.check_next_batch(pilot, len(batch))
                    tasks = bind_requests(engine, batch, sources)
                    rows = generate_batch(engine, tasks, bank, material["registered_people"], old, commit)
                    for row in rows:
                        cached[row["request_id"]] = row
                    save(gen_path, [cached[r["request_id"]] for r in requests if r["request_id"] in cached])
                    truncation = diagnostic(list(cached.values()))
                    print(f"{phase}：累计{len(cached)}/{len(requests)}；截断超限臂：" +
                          str([r for r in truncation if r["truncation_exceeds_5pct"]]), flush=True)
        print("所选核心阶段完成；原始输出仅保存在A100。", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--freeze-commit", required=True)
    ap.add_argument("--until", choices=("5.1", "5.3", "5.5"), default="5.5")
    args = ap.parse_args()
    run(args.out, args.pilot, args.freeze_commit, args.until)
