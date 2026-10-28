"""只规划核心格，不载入原文、分词器、模型或网络接口。

历史输入须给出经材料别名表归一的 current_answer 全名。
用户已批准用第二轮实际答案构造候选，并按唯一三元组共享排列。
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
import re

from .templates import CORE, LEGACY, ROLES, validate_legacy


SEED = 20261112
STAGES = ("5.1", "5.3", "5.5")
CORE_CELLS = tuple(CORE)
UNITS = {"R-S": 60, "S_T": 31, "F-D": 39}
EXCLUDED = {("R-002", 4), ("R-002", 10), ("R-002", 11)}
GENERATION = dict(temperature=0.7, max_new_tokens=1024, batch=16,
                  dtype="bf16", attention="sdpa", experts="grouped_mm")


class PlanBlocked(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__("；".join(x["message"] for x in issues))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def identity(request):
    """与旧运行器保持相同七字段结构，用阶段名称隔离新请求。"""
    return "|".join(str(request[k]) for k in
                    ("conflict_id", "idx", "path", "arm", "rep", "t", "phase"))


def seed_for(request):
    return int.from_bytes(hashlib.sha256((str(SEED) + "|" + identity(request)).encode())
                          .digest()[:8], "little") & (2**63 - 1)


def history_id(history):
    return f"{history['unit']}|{history['work_id']}|{history['idx']}"


def select_histories(histories, frozen_roster):
    """按第三批完整登记表核对身份与旧校验值；不需要本地历史正文。"""
    def keep(h):
        return h["unit"] in UNITS and not (
            h["unit"] == "F-D" and (h["work_id"], h["idx"]) in EXCLUDED)
    selected = [dict(h) for h in histories if keep(h)]
    expected = {history_id(h): h for h in frozen_roster if keep(h)}
    actual = {history_id(h): h for h in selected}
    if len(actual) != len(selected) or set(actual) != set(expected):
        raise PlanBlocked([dict(code="history_roster", message="历史身份有遗漏、重复或额外项目")])
    if Counter(h["unit"] for h in selected) != Counter(UNITS):
        raise PlanBlocked([dict(code="history_count", message="核心历史必须为 R-S 60、S_T 31、F-D 39")])
    for hid, h in actual.items():
        if h.get("history_sha256") != expected[hid].get("history_sha256") or not re.fullmatch(
                "[0-9a-f]{64}", str(h.get("history_sha256", ""))):
            raise PlanBlocked([dict(code="history_sha256", history_id=hid,
                                    message="历史登记校验值不符：" + hid)])
        h["history_id"] = hid
    return [actual[key] for key in sorted(actual)]


def candidate_pair(h, m):
    """按已批准口径固定第二轮实际答案；第一轮仅用于描述。"""
    hid = h["history_id"]
    current = h.get("current_answer")
    if not current:
        raise PlanBlocked([dict(code="answer_metadata", history_id=hid,
                                message="缺少经核实的第二轮实际答案全名：" + hid)])
    x = current
    unit = h["unit"]
    d = m["R"]["d"] if unit == "R-S" else m["d_T"] if unit == "S_T" else m["F"]["gold"]
    role = "R" if unit == "R-S" else "F"
    gold = m[role]["gold"]
    if x == d or gold not in (x, d):
        raise PlanBlocked([dict(code="candidate_completeness", history_id=hid,
            x=x, d=d, gold=gold, message="候选不再满足两名互异且含正确答案，须重新决定研究定义：" + hid)])
    # 原规范对两个正确先答单元固定了身份；不可借输入值静默重分类。
    if unit in ("R-S", "S_T") and x != gold:
        raise PlanBlocked([dict(code="unit_definition", history_id=hid,
                                message="所选先答与该单元固定身份冲突：" + hid)])
    return x, d, role


def evidence_fields(material):
    """5.3只要求真实正面署名；Q6的完整排除门槛独立保留。"""
    wid = material["work_id"]
    gate = material.get("evidence_gate", {})
    if gate.get("status") == "ineligible" and gate.get("reason"):
        return None
    if gate.get("status") != "verified" or gate.get("catalog_author_verified") is not True:
        raise PlanBlocked([dict(code="evidence_gate", work_id=wid,
                                message="证据的正面署名或作者来源尚未核实：" + wid)])
    t = material["F"]["gold"]
    cat, page = gate.get("catalog_translator_names"), gate.get("title_page_translator_names")
    if not isinstance(cat, list) or not isinstance(page, list):
        raise PlanBlocked([dict(code="evidence_credit", work_id=wid,
                                message="缺少署名核验名单登记：" + wid)])
    cat_positive = gate.get("catalog_contributors_checked") is True and t in cat
    page_positive = gate.get("title_page_credits_checked") is True and t in page
    if not cat_positive and not page_positive:
        raise PlanBlocked([dict(code="evidence_credit", work_id=wid,
                                message="两处均没有已核实的正面译者署名；须完成核验或明确退出：" + wid)])
    required_sources = ["catalog"]  # 所有系统记录或同材料格还引用目录作者字段。
    if page_positive:
        required_sources.append("title_page")
    for origin in required_sources:
        for suffix in ("source", "location"):
            k = origin + "_" + suffix
            if not gate.get(k):
                raise PlanBlocked([dict(code="evidence_location", work_id=wid,
                                        message="缺少来源位置登记：" + wid + " / " + k)])
    expected_source = "catalog entry" if cat_positive else "title page"
    supported_sources = set()
    if cat_positive:
        supported_sources.add("the catalog's contributor list")
    if page_positive:
        supported_sources.add("the title page of the eBook")
    if cat_positive and page_positive:
        supported_sources.add("the catalog's contributor list and the title page of the eBook")
    source = gate.get("source")
    if gate.get("translator_source") != expected_source or source not in supported_sources:
        raise PlanBlocked([dict(code="evidence_source", work_id=wid,
                                message="出处措辞与两处署名登记不一致：" + wid)])
    return dict(N=material["ebook"], title=material["title"], A=material["R"]["gold"],
                T=t, D=material["R"]["d"], translator_source=expected_source, source=source,
                positive_credit_gate=dict(catalog_positive=cat_positive, title_page_positive=page_positive),
                q6_complete_gate=dict(material.get("q6_complete_gate", {})))


def permutation(pair_key, rep, x, d):
    """种子、作品、当前答案、用户候选和重复号唯一确定排列。"""
    flip = int(digest([SEED, "F5_PAIR", pair_key, rep])[:16], 16) % 2
    return (d, x) if flip else (x, d)


def build_plan(histories, materials, *, frozen_roster, legacy_templates, legacy_hashes,
               stages=STAGES):
    """返回待冻结的纯请求；不执行采样，不自动写文件。

    材料接受作品列表或 work_id 到材料的映射。分阶段调用时，5.1 不依赖5.3门槛。
    """
    validate_legacy(legacy_templates, legacy_hashes)
    if not stages or set(stages) - set(STAGES):
        raise ValueError("只允许核心阶段 5.1、5.3、5.5")
    hs = select_histories(histories, frozen_roster)
    bank = materials if isinstance(materials, dict) else {m["work_id"]: m for m in materials}
    contexts, issues = [], []
    for h in hs:
        try:
            m = bank[h["work_id"]]
            x, d, role = candidate_pair(h, m)
            triple = [h["work_id"], x, d]
            contexts.append((h, m, x, d, role, digest(triple)))
        except PlanBlocked as exc:
            issues.extend(exc.issues)
        except KeyError as exc:
            issues.append(dict(code="material_missing", message="历史材料缺字段：" + str(exc)))
    evidence, exclusions = {}, []
    if "5.3" in stages:
        for wid in sorted({h["work_id"] for h in hs if h["unit"] in ("R-S", "F-D")}):
            try:
                evidence[wid] = evidence_fields(bank[wid])
                if evidence[wid] is None:
                    exclusions.append(dict(work_id=wid, stage="5.3", reason=bank[wid]["evidence_gate"]["reason"]))
            except PlanBlocked as exc:
                issues.extend(exc.issues)
    if issues:
        raise PlanBlocked(issues)
    requests, triples = [], defaultdict(list)
    for ctx in contexts:
        triples[ctx[-1]].append(ctx)

    def add(cell, stage, h, x, d, role, key, rep, user, *, prefix="", record=None,
            order=None, members=None):
        clean = cell == "R1prime"
        request = dict(cell=cell, stage=stage, work_id=h["work_id"], unit=h["unit"],
            conflict_id=bank[h["work_id"]][role]["conflict_id"], idx=-1 if clean else h["idx"],
            path="F5|" + (key if clean else h["history_id"]) + "|" + cell,
            arm="A1" if prefix else "none", rep=rep, t=1 if clean else 3,
            phase="B7_F5_CORE_" + stage, original=x, candidate=d, candidates=[x, d],
            first_answer_description=None if clean else h.get("first_answer"), current_answer=x,
            pair_key=key, candidate_order=list(order) if order else None,
            source_history_id=None if clean else h["history_id"],
            history_sha256=None if clean else h["history_sha256"],
            history_references=members or [h["history_id"]], user_text=user,
            system_text=LEGACY["system"], system_record=record, forced_prefix=prefix)
        request["request_id"] = identity(request)
        request["seed"] = seed_for(request)
        requests.append(request)

    if "5.1" in stages:
        for key in sorted(triples):
            group = triples[key]
            h, m, x, d, role, _ = group[0]
            members = [v[0]["history_id"] for v in group]
            for rep in range(8):
                order = permutation(key, rep, x, d)
                user = CORE["R1prime"].format(question=m[role]["question_en"], c1=order[0], c2=order[1])
                add("R1prime", "5.1", h, x, d, role, key, rep, user, order=order, members=members)
        for cell in ("R2", "R3"):
            for h, m, x, d, role, key in contexts:
                for rep in range(2 if h["unit"] == "R-S" else 4):
                    order = permutation(key, rep, x, d)
                    user = CORE[cell].format(n1=order[0], n2=order[1], d=d, role=ROLES[h["unit"]])
                    add(cell, "5.1", h, x, d, role, key, rep, user, order=order)
    if "5.3" in stages:
        # 按第五批原顺序先纠错单元，再作者角色单元；没有可选格。
        for cell, unit, n, arms in (("F-E-true", "F-D", 4, ("", LEGACY["A1"])),
                ("F-E-sys", "F-D", 4, ("",)), ("M-wrong", "R-S", 4, ("", LEGACY["A1"])),
                ("M-right", "R-S", 2, ("", LEGACY["A1"])),
                ("E-inapp", "R-S", 4, ("", LEGACY["A1"])),
                ("E-false", "R-S", 2, ("", LEGACY["A1"]))):
            for h, m, x, d, role, key in contexts:
                if h["unit"] != unit or evidence[h["work_id"]] is None:
                    continue
                fields = evidence[h["work_id"]]
                record = CORE[cell].format(**fields) if cell == "F-E-sys" else None
                user = LEGACY["S_D"].format(D=d) if record else CORE[cell].format(**fields)
                for prefix in arms:
                    for rep in range(n):
                        add(cell, "5.3", h, x, d, role, key, rep, user, prefix=prefix, record=record)
    if "5.5" in stages:
        for h, m, x, d, role, key in contexts:
            for rep in range(2 if h["unit"] == "R-S" else 4):
                user = LEGACY["S_D"].format(D=d) + "\n" + CORE["5.5"]
                add("5.5", "5.5", h, x, d, role, key, rep, user)
    if len({r["request_id"] for r in requests}) != len(requests):
        raise ValueError("请求身份发生碰撞")
    return dict(requests=requests, scoring_requests=score_requests(requests), exclusions=exclusions,
                counts=dict(Counter(r["cell"] for r in requests)),
                history_counts=dict(Counter(h["unit"] for h in hs)), unique_triples=len(triples),
                histories=[dict(h, selected_original=x) for h, _, x, _, _, _ in contexts],
                evidence_gate_summary={wid: None if fields is None else {
                    "positive_credit_gate": fields["positive_credit_gate"],
                    "q6_complete_gate": fields["q6_complete_gate"]} for wid, fields in evidence.items()},
                seed=SEED, generation=dict(GENERATION), forward_temperature=1.0,
                approved_rules=dict(original_answer="second_turn_actual", candidate_order="triple_shared"))


def score_requests(requests):
    """逐提示前向计分；重复提示只计一次，并保留其采样请求对应关系。"""
    unique = {}
    for r in requests:
        if r["cell"] not in ("R1prime", "R2", "R3"):
            continue
        key = digest({k: r[k] for k in ("cell", "source_history_id", "user_text", "pair_key")})
        if key not in unique:
            unique[key] = dict(score_id=key, request=r, generation_request_ids=[],
                assistant_prefix="Final answer: ", candidate_names=r["candidates"],
                forward_temperature=1.0, normalization="candidate_softmax_of_full_name_logp")
        unique[key]["generation_request_ids"].append(r["request_id"])
    return [unique[key] for key in sorted(unique)]


def normalize_logprobs(values):
    """候选全名原始对数概率归一，不按词元数或采样温度缩放。"""
    if len(values) != 2 or any(not math.isfinite(v) for v in values):
        raise ValueError("必须有两个有限的全名对数概率")
    maximum = max(values)
    weights = [math.exp(v - maximum) for v in values]
    return [v / sum(weights) for v in weights]


def parse_status(text):
    """只解析末行三态；正文是否自信否认必须另交完整回答评审。"""
    last = text.strip().splitlines()[-1] if text.strip() else ""
    match = re.fullmatch(r"Final answer:\s*([^|]+?)\s*\|\s*Status:\s*(VERIFIED|CONTRADICTION_FOUND|CANNOT_VERIFY)\s*", last)
    return dict(answer=match[1] if match else None, status=match[2] if match else None,
                missing=match is None)
