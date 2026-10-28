"""阶段二40条独立复核：作品均衡抽取，不按机器标签挑选。"""
from pathlib import Path
import argparse
import hashlib
import json
import random

from stage2_plan import load, save, identity, baseline_records
from stage2_judge import inputs as relation_inputs
from stage2_outcomes import inputs as answer_inputs


SEED = 20261112
RULE = {
    "n": 40, "works": 10, "per_work": 4,
    "old_per_work": 2, "new_per_work": 2,
    "selection": "各作品两个旧条件与两个新条件；条件轮换均衡，条件内等概率抽一条；不读取机器标签。",
    "purpose": "代理复核标签质量，非人工；不是总体错误率或漏报率的直接无偏估计。",
    "implementation": "原协议只规定40条；依用户明确授权的推荐执行细节落实均衡覆盖，不改变主分析。",
}


def choose(records, seed=SEED):
    rng = random.Random(seed)
    works = sorted({r["work_id"] for r in records})
    if len(works) != 10:
        raise ValueError("独立复核预期10部作品，不补造作品")
    rng.shuffle(works)
    old_cells = [("X", "S"), ("F_w", "S"), ("X", "C")]
    selected = []
    for index, work in enumerate(works):
        new_cells = ([("X", "A1"), ("F_w", "A0")] if index % 2 == 0
                     else [("X", "A0"), ("F_w", "A1")])
        cells = [("Q2", *c) for c in new_cells]
        cells += [("baseline", *c) for k, c in enumerate(old_cells) if k != index % 3]
        for phase, candidate, arm in cells:
            pool = sorted((r for r in records if (r["work_id"], r["phase"], r["candidate_type"], r["arm"])
                           == (work, phase, candidate, arm)), key=lambda r: r["id"])
            if not pool:
                raise ValueError("独立复核抽样格缺失：" + str((work, phase, candidate, arm)))
            chosen = dict(rng.choice(pool), probability_within_cell=1 / len(pool))
            selected.append(chosen)
    if len(selected) != 40 or len({r["id"] for r in selected}) != 40:
        raise ValueError("独立复核数或唯一性错误")
    rng.shuffle(selected)
    return selected


def build(out, source):
    blind_path = out / "stage2_independent_blind.json"
    key_path = out / "stage2_independent_key.json"
    if blind_path.exists() or key_path.exists():
        if not (blind_path.exists() and key_path.exists()):
            raise RuntimeError("独立盲表与映射只有一份存在，须核查，不重抽")
        blind, key = load(blind_path), load(key_path)
        if len(blind["records"]) != 40 or len(key["records"]) != 40:
            raise RuntimeError("已有独立盲表不完整，不重抽")
        return {"n": 40, "reused": True}
    rows = []
    rels, answers = {}, {}
    materials = {x["item_id"]: x for x in load(out / "factdiag7_stage2_materials.json")["items"]}
    for phase in ("baseline", "Q2"):
        _, rq = relation_inputs(out, source, phase)
        _, aq = answer_inputs(out, source, phase)
        rels[phase] = {q["id"]: q for q in rq}
        answers[phase] = {q["id"]: q for q in aq}
        originals = baseline_records(source) if phase == "baseline" else load(out / "stage2_Q2_generations.json")
        for row in originals:
            item = materials[row["conflict_id"]]
            # Q2的存储臂名由生成计划给定；不能凭相似文本改名。
            arm = row["arm"]
            if phase == "Q2" and arm.startswith("S+"):
                arm = arm[2:]
            rows.append(dict(id=identity(row), work_id=item["work_id"], phase=phase,
                             candidate_type=row["candidate_type"], arm=arm, row=row))
    selected = choose(rows)
    rng = random.Random(SEED + 1)
    packets, keys = [], []
    for selected_row in selected:
        key, phase, row = selected_row["id"], selected_row["phase"], selected_row["row"]
        blind_id = hashlib.sha256(("stage2-independent|" + key).encode()).hexdigest()[:16]
        item = materials[row["conflict_id"]]
        kinds = [row["candidate_type"], "GOLD"] + (["T"] if phase == "Q2" else [])
        views = []
        for kind in kinds:
            person = next(p for p in item["people"] if p["type"] == kind)
            q = rels[phase][key + "|" + kind]
            views.append(dict(candidate=person["name"], aliases=person["aliases"], prompt=q["prompt"]))
        rng.shuffle(views)
        packets.append(dict(blind_id=blind_id, views=views, answer_prompt=answers[phase][key]["prompt"]))
        keys.append({k: v for k, v in selected_row.items() if k != "row"} | {"blind_id": blind_id})
    protocol = load(out / "factdiag7_stage2_relation_protocol.json")["prompt"]
    answer_protocol = load(out / "factdiag7_stage2_label_protocol.json")["answer_prompt"]
    save(blind_path, dict(protocol=protocol, answer_protocol=answer_protocol, records=packets))
    save(key_path, dict(rule=RULE, seed=SEED, records=keys))
    return {"n": len(packets), "reused": False,
            "relation_views": sum(len(r["views"]) for r in packets), "rule": RULE}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(build(args.out, args.source), ensure_ascii=False))
