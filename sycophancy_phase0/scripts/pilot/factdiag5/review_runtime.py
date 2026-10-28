"""第五批评审串行入口；未提交核对、生成未完整或GPU占用时不载入模型。"""
from contextlib import contextmanager, nullcontext
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

from .freeze import validate as validate_generation
from .judge_core import (RECOMMENDED_ATOMIC_SCOPE, _module, build_inputs, parse_result,
                         pending_inputs)
from .prepare import load, save
from .review_protocol import GENERATION_COMMIT, REVIEW_ORDER, validate_review
from .runtime import assert_remote, cached_rows, cached_scores


OUTPUT_FILES = dict(legacy="core_legacy_reviews.json", relations="core_relations_v2.json")


def storage_key(kind):
    return "relations" if kind == "relations_v2" else "legacy"


def pending_kind(payload, saved, kind):
    queue = payload["queues"][kind]
    keys = {q["id"] for q in queue}
    # 旧口径三队列共用结果文件，先在全文件核验后按当前队列筛键。
    subset = {key: value for key, value in saved[storage_key(kind)].items() if key in keys}
    return pending_inputs(queue, subset)


def validate_saved(payload, saved, commit):
    for storage in OUTPUT_FILES:
        queue = [q for kind in REVIEW_ORDER if storage_key(kind) == storage for q in payload["queues"][kind]]
        pending_inputs(queue, saved[storage])
        if any(r.get("review_commit") != commit for r in saved[storage].values()):
            raise ValueError("已有评审结果不属于本次独立冻结提交")
    unfinished = False
    for kind in REVIEW_ORDER:
        queue = payload["queues"][kind]
        store = saved[storage_key(kind)]
        done = sum(q["id"] in store for q in queue)
        if unfinished and done:
            raise ValueError("已有结果跨过前置评审队列缺口：" + kind)
        unfinished = unfinished or done != len(queue)


def reserve_once(saved, batch, commit):
    """派发前使用同一结果键登记一次尝试；中断后该键也不重评。"""
    result = dict(saved)
    for q in batch:
        if q["id"] in result:
            raise ValueError("输入已尝试，禁止重复派发")
        result[q["id"]] = dict(input_sha256=q["input_sha256"], prompt_sha256=q["prompt_sha256"],
            review_commit=commit, attempts=1, completion="attempted_result_missing", raw=None,
            result=dict(missing=True, reason="attempt_started_result_not_saved"), judge_truncated=None)
    return result


def finish_once(saved, q, returned):
    previous = saved.get(q["id"])
    if previous is None or previous.get("completion") != "attempted_result_missing":
        raise ValueError("只能完成已登记但尚无结果的同一次尝试")
    if previous["input_sha256"] != q["input_sha256"]:
        raise ValueError("派发后评审输入变化")
    raw = returned["raw"]
    cut = returned["judge_truncated"]
    try:
        parsed = parse_result(q, raw, judge_truncated=cut)
    except (ValueError, TypeError, KeyError) as exc:
        # 保存该次原返回，后续只能离线诊断，不能因解析失败再次调用模型。
        parsed = dict(missing=True, reason="parser_exception", detail=str(exc))
    return dict(previous, raw=raw, result=parsed, completion="returned", judge_truncated=cut,
                n_new_tokens=returned.get("n_new_tokens"))


def serial_review(payload, saved, settings, commit, call_once, write):
    """可用合成调用器验证；实际调用器由通过门槛后的run提供。"""
    validate_saved(payload, saved, commit)
    for kind in REVIEW_ORDER:
        storage = storage_key(kind)
        pending = pending_kind(payload, saved, kind)
        for offset in range(0, len(pending), settings["batch"]):
            batch = pending[offset:offset + settings["batch"]]
            saved[storage] = reserve_once(saved[storage], batch, commit)
            write(storage, saved[storage])
            returned = call_once([q["prompt"] for q in batch], settings["max_new_tokens"][kind])
            if len(returned) != len(batch):
                raise RuntimeError("评审返回条数不符；已派发项保留缺失，不重评")
            for q, answer in zip(batch, returned):
                saved[storage][q["id"]] = finish_once(saved[storage], q, answer)
            write(storage, saved[storage])
            print(f"{kind}：已尝试{len(payload['queues'][kind]) - len(pending) + min(offset + len(batch), len(pending))}/{len(payload['queues'][kind])}", flush=True)
    return {
        storage: dict(attempted=len(records), missing=sum(bool(r["result"].get("missing")) for r in records.values()),
                      result_not_saved=sum(r.get("completion") == "attempted_result_missing" for r in records.values()))
        for storage, records in saved.items()
    }


def infer_once(client, prompts, max_new_tokens):
    """与旧LocalJudge/PropositionClient同一渲染和生成参数，仅并列保留截断信息。"""
    rendered = [client.tok.apply_chat_template([{"role": "user", "content": p}],
        tokenize=False, add_generation_prompt=True) for p in prompts]
    batch = client.tok(rendered, return_tensors="pt", padding=True).to(client.model.device)
    with client.torch.no_grad():
        generated = client.model.generate(**batch, do_sample=False, max_new_tokens=max_new_tokens,
            pad_token_id=client.tok.pad_token_id, temperature=None, top_p=None, top_k=None)
    sampled = generated[:, batch.input_ids.shape[1]:]
    texts = client.tok.batch_decode(sampled, skip_special_tokens=True)
    result = []
    for raw, ids in zip(texts, sampled):
        seq = ids.tolist()
        eos = client.tok.eos_token_id
        n = seq.index(eos) + 1 if eos in seq else len(seq)
        result.append(dict(raw=raw, judge_truncated=len(seq) >= max_new_tokens and eos not in seq,
                           n_new_tokens=n))
    return result


def load_client(pilot, settings):
    sys.path.insert(0, str(Path(pilot) / "src"))
    loader = _module("factdiag5_review_judge_loader", Path(pilot) / "scripts/pilot/factdiag4/launch_judge.py")
    dependency = loader.load_judge_dependency()
    return dependency.LocalJudge(settings["model_path"], batch_size=settings["batch"])


def prepare_remote_inputs(out, pilot, protocol):
    material = load(out / "factdiag5_materials.json")
    rows = load(out / "core_generations.json")
    cached_rows(rows, material["plan"]["requests"], GENERATION_COMMIT)
    if len(rows) != protocol["counts"]["identity"]:
        raise ValueError("第五批核心生成尚未全部完成")
    for filename, definitions in (("core_forward.json", material["plan"]["scoring_requests"]),
                                   ("version_forward.json", material["version_scores"])):
        path = out / filename
        if not path.exists() or len(cached_scores(load(path), definitions, GENERATION_COMMIT)) != len(definitions):
            raise ValueError("第五批前向尚未完整，不能越过生成阶段")
    phase_a = pilot / "factdiag7_20261112"
    return build_inputs(material, rows, load(out / "factdiag5_prereg.json"),
        approved_atomic_scope=RECOMMENDED_ATOMIC_SCOPE,
        relation_protocol=load(phase_a / "factdiag7_stage2_relation_protocol.json"),
        relation_materials=load(phase_a / "factdiag7_stage2_materials.json"))


@contextmanager
def review_lock(out):
    import fcntl
    with (out / ".review.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("已有第五批评审入口运行，禁止并发重复派发") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def run(out, pilot, commit, *, check_only=False):
    out, pilot = Path(out), Path(pilot)
    assert_remote(out, pilot)
    protocol = validate_review(out, pilot, commit)
    validate_generation(out, pilot, GENERATION_COMMIT)
    with nullcontext() if check_only else review_lock(out):
        payload = prepare_remote_inputs(out, pilot, protocol)
        if payload["counts"] != protocol["counts"]:
            raise ValueError("实际评审队列偏离独立冻结规模")
        saved = {storage: load(out / name) if (out / name).exists() else {} for storage, name in OUTPUT_FILES.items()}
        validate_saved(payload, saved, commit)
        pending = sum(len(pending_kind(payload, saved, kind)) for kind in REVIEW_ORDER)
        print(json.dumps(dict(counts=payload["counts"], pending=pending), ensure_ascii=False), flush=True)
        if check_only or not pending:
            return
        occupied = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
        if occupied:
            raise RuntimeError("GPU仍有现有进程，禁止加载第二模型：" + occupied)
        client = load_client(pilot, protocol["runtime"])
        def write(storage, records):
            save(out / OUTPUT_FILES[storage], records)
        summary = serial_review(payload, saved, protocol["runtime"], commit,
                                lambda prompts, limit: infer_once(client, prompts, limit), write)
        print(json.dumps(dict(review_summary=summary, blind_sampling="未执行"), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--review-commit", required=True)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()
    run(args.out, args.pilot, args.review_commit, check_only=args.check_only)
