"""盲表覆盖清单与构造器；不抽样、不判断回答，不调用模型。"""
from collections import defaultdict
from copy import deepcopy

from .judge_core import RS_EVIDENCE, _validated_rows


def coverage_pools(material, rows, *, identity_core_quota=10):
    """只登记候选池；已批准保留总数10，从已执行核心条件抽取。"""
    if identity_core_quota != 10:
        raise ValueError("本轮已明确5.1核心身份复核为10条，不能改成5条")
    rows = _validated_rows(material, rows)
    pools = []
    def add(key, required, eligible, description):
        ids = [r["request_id"] for r in eligible]
        pools.append(dict(quota_id=key, required=required, available=len(ids),
                          request_ids=ids, description=description))
    add("identity_5_1", identity_core_quota, [r for r in rows if r["stage"] == "5.1"],
        "只含已执行R1′、R2、R3的身份核对；保留解析缺失与技术失败供复核。")
    cells = defaultdict(list)
    for row in rows:
        if row["stage"] == "5.3":
            cells[row["cell"], row["arm"]].append(row)
    for (cell, arm), values in sorted(cells.items()):
        for positive in (True, False):
            eligible = [r for r in values if not r["truncated"] and not r["looped"]
                        and r["parsed"].get("answer_identity") in ("x", "d", "other")
                        and (r["parsed"]["answer_identity"] == "d") == positive]
            add(f"evidence|{cell}|{arm}|{int(positive)}", 2, eligible,
                "阳性为主身份解析采纳d，阴性为有效身份未采纳d；缺失不作阴性。")
    add("evidence_disputed", 20, [r for r in rows if r["cell"] == "E-false"],
        "证据质疑20条；原文未要求正负各半，不按预期标签筛掉缺失。")
    add("status_5_5", 20, [r for r in rows if r["cell"] == "5.5"],
        "三态声明与完整正文一起复核，不只截取末行。")
    return dict(pools=pools,
        unexecuted=[dict(cell="R1doubleprime", originally_requested=5, status="专项不适用；核心身份总数仍为10，不补生成或伪造该格"),
                    dict(stage="5.2", status="可选执行器均未执行，无其阳性/阴性配额")],
        stage2_agent_review=dict(shared_total=40, assigned_to_fifth=None,
            policy="阶段二40条可与第五批覆盖表共享回答；它不是第五批覆盖清单的总上限，分配由协调明确。"),
        selection_policy="仅提供候选池；独立协调按预先固定规则选定编号与顺序，再调用构造器。")


def validate_selection(coverage, selected_by_quota):
    pools = {p["quota_id"]: p for p in coverage["pools"]}
    if set(selected_by_quota) != set(pools):
        raise ValueError("覆盖配额遗漏或多出，不能跳过难例或未满足项")
    details, unique = [], set()
    for key, pool in pools.items():
        ids = selected_by_quota[key]
        if len(ids) != len(set(ids)) or not set(ids) <= set(pool["request_ids"]):
            raise ValueError("所选编号重复或不属于候选池：" + key)
        required = min(pool["required"], pool["available"])
        if len(ids) != required:
            raise ValueError("须满足配额或不足时全取；本接口不自动抽取：" + key)
        unique.update(ids)
        details.append(dict(quota_id=key, requested=pool["required"], available=pool["available"],
                            selected=len(ids), shortage=pool["required"] - len(ids)))
    return dict(details=details, unique_request_ids=sorted(unique), actual_unique=len(unique))


def build_blind_table(material, rows, review_inputs, coverage, selected_by_quota, ordered_request_ids,
                      *, stage2_shared_request_ids=()):
    """只转换外部已选定的编号；调用者提供盲表顺序，函数绝不抽正式样本。"""
    report = validate_selection(coverage, selected_by_quota)
    if len(ordered_request_ids) != len(set(ordered_request_ids)) or set(ordered_request_ids) != set(report["unique_request_ids"]):
        raise ValueError("须提供覆盖并集的完整外部顺序，不能由构造器暗中补抽或删样")
    if not set(stage2_shared_request_ids) <= set(ordered_request_ids) or len(set(stage2_shared_request_ids)) > 40:
        raise ValueError("阶段二共享复核编号须来自已选回答，且不能超过阶段总额40")
    rs = {r["request_id"]: r for r in _validated_rows(material, rows)}
    bank = {m["work_id"]: m for m in material["materials"]}
    tasks = defaultdict(dict)
    for kind, queue in review_inputs["queues"].items():
        for q in queue:
            tasks[q["request_id"]][kind] = q["prompt"]
    # 明确要求原子复核时，不能拿没有原子输入的回答虚报第七批配额。
    if any("relations_v2" not in tasks[key] for key in stage2_shared_request_ids):
        raise ValueError("共享第七批原子复核的回答缺少已确认范围的原子输入")
    public, private = [], []
    for index, key in enumerate(ordered_request_ids, 1):
        row = rs[key]
        m = bank[row["work_id"]]
        question = m["R" if row["unit"] == "R-S" else "F"]["question_en"]
        validation_id = f"F5B{index:04d}"
        card = dict(validation_id=validation_id, question=question,
            user_text=row["user_text"], system_record=row["system_record"],
            assistant_text=row["assistant_text"], review_instructions=deepcopy(tasks[key]),
            annotation=dict(supported_answer=None, stance=None, explicit=None))
        if "legacy_propositions" in tasks[key]:
            card["annotation"]["propositions"] = None
        if "evidence_disputed" in tasks[key]:
            card["annotation"]["evidence_disputed"] = None
        if "relations_v2" in tasks[key]:
            card["annotation"]["relations"] = None
        if row["cell"] == "5.5":
            card["annotation"]["status"] = None
        public.append(card)
        private.append(dict(validation_id=validation_id, request_id=key,
            quota_ids=[quota for quota, ids in selected_by_quota.items() if key in ids],
            stage2_shared=key in stage2_shared_request_ids))
    return dict(blind=public, matching=private, coverage_report=report,
        stage2_shared_count=len(set(stage2_shared_request_ids)),
        storage="盲表和私有对应表均只留A100；独立新会话复核，不向复核者提供机器标签、条件名或预期。")
