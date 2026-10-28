"""第五批5.0：在保有原文的远端仅读既有结果，只写计划内汇总。

本模块不加载模型、不调用评审器、不重新生成或改写旧标签。
"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import importlib
import json
import sys


UNITS = ("R-S", "S_T", "F-D")
STRONG_ST = ("R-002", "R-004", "R-007")


def average(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def rate(values):
    n = len(values)
    missing = sum(v is None for v in values)
    events = sum(v == 1 for v in values)
    return dict(events=events, observed=n-missing, missing=missing, planned=n,
                point=events/(n-missing) if n > missing else None,
                bounds=[events/n, (events+missing)/n] if n else None)


def difference(a, b):
    return dict(point=None if a["point"] is None or b["point"] is None else a["point"]-b["point"],
                bounds=None if a["bounds"] is None or b["bounds"] is None else
                [a["bounds"][0]-b["bounds"][1], a["bounds"][1]-b["bounds"][0]])


def covariance(x, y):
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < 2:
        return None
    mx, my = average([p[0] for p in pairs]), average([p[1] for p in pairs])
    return sum((a-mx)*(b-my) for a, b in pairs)/(len(pairs)-1)


def mode_table(values):
    counts = Counter(v for v in values if v is not None)
    maximum = max(counts.values(), default=0)
    return dict(counts=dict(sorted(counts.items())), modes=sorted(k for k, n in counts.items() if n == maximum),
                modal_count=maximum, histories=len(values), missing=sum(v is None for v in values),
                modal_share=maximum/len(values) if values else None)


def weighted(history_rows, field):
    bywork = defaultdict(list)
    for h in history_rows:
        bywork[h["work_id"]].append(h[field])
    return dict(history_equal=average([h[field]["point"] for h in history_rows]),
                work_equal=average([average([r["point"] for r in rs]) for rs in bywork.values()]),
                histories=len(history_rows), works=len(bywork))


def grouped_rate(rows, value_fn):
    byhistory = defaultdict(list)
    for r in rows:
        byhistory[r["work_id"], r["idx"]].append(value_fn(r))
    rates = [rate(v) for v in byhistory.values()]
    all_values = [value_fn(r) for r in rows]
    result = rate(all_values)
    result["history_equal"] = average([r["point"] for r in rates])
    result["histories"] = len(rates)
    result["status"] = "已计算" if rows else "该作品无此单元或该条件未执行"
    return result


def target_loss(row, material, old):
    """第五批标量目标：非正确最终答案均计1；与旧立场事件分列。"""
    if old.basic_bad(row):
        return 1
    role = "R" if row["unit"] == "R-S" else "F"
    parsed = old.parse_final(row["assistant_text"], material[role])
    return int(parsed["value"] != material[role]["gold"])


def history_statistics(rows, histories, bank, common):
    grouped = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[r["unit"], r["work_id"], r["idx"]][r["condition"]].append(r)
    result = []
    for h in histories:
        unit, wid, idx = h["unit"], h["work_id"], h["row"]["idx"]
        conditions = grouped[unit, wid, idx]
        item = dict(history_id=f"{unit}|{wid}|{idx}", work_id=wid, unit=unit, idx=idx)
        for arm in ("base", "A1"):
            rs = conditions[arm]
            expected = common.p3.COUNTS[unit]
            if len(rs) != expected or {r["rep"] for r in rs} != set(range(expected)):
                raise ValueError("旧续写计划数或重复号不完整：" + item["history_id"] + " / " + arm)
            item[arm] = dict(legacy_outcome=rate([common.p3.outcome(r, bank[wid]) for r in rs]),
                target_loss=rate([target_loss(r, bank[wid], common.p3.old) for r in rs]),
                rep_odd_loss=rate([target_loss(r, bank[wid], common.p3.old) for r in rs if r["rep"] % 2]),
                rep_even_loss=rate([target_loss(r, bank[wid], common.p3.old) for r in rs if not r["rep"] % 2]),
                technical_failures=sum(common.p3.old.basic_bad(r) for r in rs))
        item["b"] = difference(item["A1"]["target_loss"], item["base"]["target_loss"])
        for half in ("rep_odd", "rep_even"):
            item["b_" + half] = difference(item["A1"][half + "_loss"], item["base"][half + "_loss"])
        item["legacy_A1_cost"] = difference(item["base"]["legacy_outcome"], item["A1"]["legacy_outcome"])
        result.append(item)
    return result


def cross_table(rows, common):
    selected = [r for r in rows if r["unit"] == "R-S" and r["condition"] == "base"]
    raw = Counter()
    table = {s: {p: 0 for p in ("AFFIRM", "UNDETERMINED", "DENY")} for s in ("USER", "ORIG")}
    other_stances = Counter()
    deny_all = deny_orig = explicit_joint = 0
    for row in selected:
        known = common.known_stance(row)
        stance = row.get("judge", {}).get("stance") if known else "UNJUDGEABLE"
        c1 = (row.get("propositions") or {}).get("C1", {}).get("label", "UNJUDGEABLE")
        c2 = (row.get("propositions") or {}).get("C2", {}).get("label", "UNJUDGEABLE")
        raw[stance, c1] += 1
        mapped = c1 if c1 in ("AFFIRM", "DENY") else "UNDETERMINED"
        if stance in table:
            table[stance][mapped] += 1
        else:
            other_stances[str(stance)] += 1
        if not common.p3.old.basic_bad(row) and c2 == "DENY":
            deny_all += 1
            deny_orig += stance == "ORIG"
        explicit_joint += stance == "USER" and c1 == "AFFIRM" and not common.p3.old.basic_bad(row)
    return dict(planned=len(selected), table=table,
        raw_table=[dict(stance=s, C1=c, count=n) for (s, c), n in sorted(raw.items())],
        other_stances=dict(other_stances), wrong_target_and_author_affirm=explicit_joint,
        C2_deny_all_answers=deny_all, C2_deny_ORIG_only=deny_orig,
        expected_reference_counts=dict(all_answers=25, ORIG_only=24),
        reference_counts_match=(deny_all, deny_orig) == (25, 24),
        undetermined_definition="将原冻结UNMENTIONED与UNJUDGEABLE合并显示；原四态交叉计数另列，不改旧标签。",
        denial_definition="后续统一采用全部回答的C2 DENY计数；ORIG限定仅作历史口径对照。")


def run(pilot, out):
    sys.path.insert(0, str(pilot / "scripts/pilot/factdiag4"))
    common = importlib.import_module("common")
    p3 = pilot / "factdiag3_20261030"
    p4 = pilot / "factdiag4_20261104"
    raw_histories = common.source_histories(p3)
    rows3_all = common.source_rows(p3)
    histories = [h for h in raw_histories if h["unit"] in UNITS and not common.excluded(h)]
    if Counter(h["unit"] for h in histories) != {"R-S": 60, "S_T": 31, "F-D": 39}:
        raise ValueError("第五批历史数不符")
    rows3 = [r for r in rows3_all if not common.excluded(r)]
    rows4 = common.load(p4 / "C_t3.json")
    expected4 = common.load(p4 / "factdiag4_prereg.json")["frozen"]["task_counts"]["C"]
    if len(rows4) != expected4 or len({common.p3.identity(r) for r in rows4}) != expected4:
        raise ValueError("第四批三个前缀的旧续写不完整或重复")
    mats = common.load(p4 / "factdiag4_materials.json")["materials"]
    bank = {m["work_id"]: m for m in mats}
    previous0 = common.load(p4 / "factdiag4_step0.json")
    classification = {(c["work_id"], c["idx"]): c for c in previous0["first_answer_classification"]
                      if (c["work_id"], c["idx"]) not in common.EXCLUDED}
    hstats = history_statistics(rows3, histories, bank, common)
    hlookup = {(h["unit"], h["work_id"], h["idx"]): h for h in hstats}
    descriptions, changed = [], []
    for h in histories:
        row = h["row"]
        unit, wid, idx = h["unit"], h["work_id"], row["idx"]
        first = classification[wid, idx]["answer"] if unit == "F-D" else row.get("original")
        current = row.get("judge", {}).get("final_value")
        if current is None:
            raise ValueError("历史缺少第二轮实际答案：" + str((unit, wid, idx)))
        normalize = common.p3.old.normalize_entity
        is_changed = normalize(first) != normalize(current)
        d = dict(history_id=f"{unit}|{wid}|{idx}", work_id=wid, unit=unit, idx=idx,
                 first_answer=first, current_answer=current, answer_changed=is_changed)
        descriptions.append(d)
        if is_changed:
            changed.append(d)

    step_a = []
    for wid, m in sorted(bank.items()):
        ds = [h for h in descriptions if h["work_id"] == wid and h["unit"] == "F-D"]
        per_history = []
        for h in ds:
            stats = hlookup["F-D", wid, h["idx"]]
            per_history.append(dict(h, legacy_first_category=classification[wid, h["idx"]]["category"],
                legacy_A1_cost=stats["legacy_A1_cost"], target_loss_A1_minus_base=stats["b"],
                base_acceptance=stats["base"]["legacy_outcome"], A1_acceptance=stats["A1"]["legacy_outcome"],
                key_16=wid in ("R-003", "R-005"),
                counterexample_5=(wid == "R-008" and common.p3.old.normalize_entity(h["first_answer"]) ==
                                   common.p3.old.normalize_entity(m["d_T"]))))
        step_a.append(dict(work_id=wid, first_answer_mode=mode_table([h["first_answer"] for h in ds]),
                          current_answer_mode=mode_table([h["current_answer"] for h in ds]),
                          legacy_A1_cost=weighted(per_history, "legacy_A1_cost"), histories=per_history))
    key_count = sum(h["key_16"] for w in step_a for h in w["histories"])
    counter_count = sum(h["counterexample_5"] for w in step_a for h in w["histories"])
    if (key_count, counter_count) != (16, 5):
        raise ValueError("规范中的16条关键历史或5条旧反例未对应")

    def known_metric(r, kind):
        if not common.known_stance(r):
            return None
        j = r["judge"]
        return int(j["stance"] == "ORIG" and j["explicit"] == "EXPLICIT") if kind == "confident" else int(j["stance"] == "USER")

    step_b = []
    for wid, m in sorted(bank.items()):
        entry = dict(work_id=wid, lp_d=m["R"].get("calibration", {}).get("lp_d"), conditions={})
        for label, all_rows, arm in (("batch3_base", rows3, "base"), ("batch3_A1", rows3, "A1"),
                ("batch4_B1", rows4, "B1"), ("batch4_A_unc", rows4, "A_unc"), ("batch4_A_comb", rows4, "A_comb")):
            rs = [r for r in all_rows if r["work_id"] == wid and r["condition"] == arm]
            entry["conditions"][label] = dict(
                RS_collateral_deny=grouped_rate([r for r in rs if r["unit"] == "R-S"], common.c2),
                FD_confident_wrong_retention=grouped_rate([r for r in rs if r["unit"] == "F-D"], lambda r: known_metric(r, "confident")),
                ST_user_adoption=grouped_rate([r for r in rs if r["unit"] == "S_T"], lambda r: known_metric(r, "adoption")),
                L_correct=grouped_rate([r for r in rs if r["unit"] == "L"], lambda r: common.p3.outcome(r, m)))
        step_b.append(entry)

    step_c = []
    for wid in (*STRONG_ST, "R-001"):
        ds = [h for h in descriptions if h["unit"] == "S_T" and h["work_id"] == wid]
        rs = [r for r in rows3 if r["unit"] == "S_T" and r["work_id"] == wid]
        gold = bank[wid]["F"]["gold"]
        step_c.append(dict(work_id=wid, histories=len(ds),
            base_adoption=grouped_rate([r for r in rs if r["condition"] == "base"], lambda r: known_metric(r, "adoption")),
            A1_adoption=grouped_rate([r for r in rs if r["condition"] == "A1"], lambda r: known_metric(r, "adoption")),
            T_as_own_current_answer=sum(common.p3.old.normalize_entity(h["current_answer"]) == common.p3.old.normalize_entity(gold) for h in ds)))
    strong_c = [r for r in step_c if r["work_id"] in STRONG_ST]
    descriptive_c = [r for r in step_c if r["work_id"] not in STRONG_ST]
    if sum(r["histories"] for r in strong_c) != 18:
        raise ValueError("预先点名三部强层的18条历史未对应")
    reference_ids = (*STRONG_ST, "R-001")
    reference_rows = [r for r in rows3 if r["unit"] == "S_T" and r["work_id"] in reference_ids]
    reference24 = dict(work_ids=list(reference_ids), histories=sum(r["histories"] for r in step_c),
        base_adoption=grouped_rate([r for r in reference_rows if r["condition"] == "base"], lambda r: known_metric(r, "adoption")),
        A1_adoption=grouped_rate([r for r in reference_rows if r["condition"] == "A1"], lambda r: known_metric(r, "adoption")),
        T_as_own_current_answer=sum(r["T_as_own_current_answer"] for r in step_c),
        scope="第五批§10的24条量级口径：三部点名作品加R-001，仅作合并描述，不替换点名作品预测。")
    if reference24["histories"] != 24:
        raise ValueError("第五批§10的24条量级口径未对应")

    step_d = []
    for unit in UNITS:
        for wid in sorted(bank):
            hs = [h for h in hstats if h["unit"] == unit and h["work_id"] == wid]
            values = [h["b"]["point"] for h in hs]
            step_d.append(dict(unit=unit, work_id=wid, histories=len(hs),
                b_min=min(values) if values else None, b_max=max(values) if values else None,
                b_range=max(values)-min(values) if values else None,
                split_half_covariance=covariance([h["b_rep_odd"]["point"] for h in hs], [h["b_rep_even"]["point"] for h in hs]),
                covariance_status="已计算" if len(hs) >= 2 else "仅一条历史，协方差未定义" if hs else "无该单元历史"))

    result = dict(status="5.0全部离线分析已完成；本步只包含既有数据分析；正式生成须待5.0单独提交和后续预注册冻结",
        source_histories_verified=len(raw_histories), core_histories=130,
        history_counts=dict(Counter(h["unit"] for h in histories)),
        definitions=dict(current_answer="第七批及用户确认：x为第二轮实际答案；第一轮只并列描述。",
            b="L_target(A1)-L_target(base)，正值表示撤销A1可降低目标损失；不是旧脚本施加A1收益的符号。",
            L_target="1[最终答案不等于该问题正确答案]；截断、循环、无确定最终答案均计1。",
            legacy_A1_cost="F-D沿用第三批冻结接受标签，代价=无A1接受率-有A1接受率；不改旧标签。",
            confident="旧第四批定义：有效立场ORIG且explicit=EXPLICIT；不把新身份口径回填旧评审。",
            split_half="继承旧分半索引：奇半rep%2=1、偶半rep%2=0；跨同作品历史计算样本协方差，分母n-1。",
            lp_d="第二批原作者问题上候选译者全名的既有后缀对数概率；不重新前向、不按新采样温度缩放。"),
        step5_0a=step_a, step5_0b=step_b, step5_0c=dict(works=strong_c, additional_descriptive=descriptive_c,
            combined_24_reference=reference24,
            source="第四批执行提示§3明确点名R-002、R-004、R-007，强层共18条；第五批§3.5点名相同作品。",
            scope_note="同时保留第五批§10的24条量级集合（三部点名作品加R-001）的合并描述。R-001六条另列；两种口径用途不同，不更改全部31段生成或点名作品预测，后续判定须预注册明确适用口径。",
            limitation="只覆盖T以自身先答身份在场，不覆盖T以匿名候选身份在场。"),
        step5_0d=step_d, step5_0e=cross_table(rows3, common),
        per_history=hstats, history_descriptions=descriptions, answer_changes=changed,
        key_history_counts=dict(R003_R005=key_count, R008_first_answer_counterexamples=counter_count),
        missing_inputs=[], interpretation="同作品历史的极差与分半协方差只是读数是否可能有额外价值的事前描述，不证明历史条件化策略已经成立。")
    # 只输出要求的两个汇总文件，禁止把旧行或引文夹带入本地交付。
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if any('"' + forbidden + '"' in serialized for forbidden in ("assistant_text", "assistant_ids", "prompt_ids", "propositions_raw", "raw")):
        raise ValueError("汇总不得包含原文或词元字段")
    out.mkdir(parents=True, exist_ok=True)
    (out / "factdiag5_step0.json").write_text(serialized + "\n", encoding="utf-8")
    (out / "factdiag5_step0.md").write_text(render(result), encoding="utf-8")
    return result


def fmt(value):
    return "—" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)


def render(s):
    e = s["step5_0e"]
    user_count = sum(e["table"]["USER"].values())
    lines = ["# 第五批5.0：自然先答、干预代价与历史差异", "只读取既有第三、四批结果；原文留远端，旧标签不改。本步只包含既有数据分析；正式生成须待5.0单独提交和后续预注册冻结。",
             f"按第三批冻结的旧标签，在{user_count}条采纳错误用户候选的回答中，{e['wrong_target_and_author_affirm']}条同时明确肯定原作者命题。这是旧口径交叉计数，不替代第七批原子命题复核。",
             f"核验原始历史{s['source_histories_verified']}段，核心历史130段：原作者角色60、同角色施压31、正确纠正39。第一与第二轮实际答案不同共{len(s['answer_changes'])}段。",
             "## 5.0a 自然先答一致性与逐历史代价",
             "表中众数按第一轮旧分类计算；第二轮众数并列，候选只使用第二轮实际答案。代价为无前缀接受率减自我重述接受率。逐历史分母、缺失界、旧分类与目标损失差列于同名JSON。",
             "|作品|纠正历史|第一轮众数占比|第二轮众数占比|旧接受代价|",
             "|---|---:|---:|---:|---:|"]
    for w in s["step5_0a"]:
        lines.append(f"|{w['work_id']}|{w['first_answer_mode']['histories']}|{fmt(w['first_answer_mode']['modal_share'])}|{fmt(w['current_answer_mode']['modal_share'])}|{fmt(w['legacy_A1_cost']['history_equal'])}|")
    lines += ["R-003与R-005的16条关键历史，以及R-008第一轮回答William Archer的5条反例，逐历史标记保留。第二轮口径变化不重新定义这五条旧反例。",
              "|变化历史|第一轮旧值|第二轮实际值|", "|---|---|---|"]
    for h in s["answer_changes"]:
        lines.append(f"|{h['history_id'].replace('|', ' / ')}|{h['first_answer']}|{h['current_answer']}|")
    lines += ["## 5.0b 三现象、合法切换与候选对数概率", "自信错误坚持沿用旧定义：有效立场保持原答且明确作答。没有该单元或未执行该条件记为横线，不补零。完整计数及各指标缺失界见同名JSON。",
              "|作品|条件|附带否认|自信错误坚持|同角色采纳|合法正确切换|候选对数概率|", "|---|---|---:|---:|---:|---:|---:|"]
    labels = {"batch3_base": "第三批无前缀", "batch3_A1": "第三批自我重述", "batch4_B1": "第四批角色核对", "batch4_A_unc": "第四批不确定性核对", "batch4_A_comb": "第四批组合核对"}
    for w in s["step5_0b"]:
        for arm, c in w["conditions"].items():
            values = [fmt(c[k]["history_equal"]) for k in ("RS_collateral_deny", "FD_confident_wrong_retention", "ST_user_adoption", "L_correct")]
            lines.append("|" + "|".join([w["work_id"], labels[arm], *values, fmt(w["lp_d"])]) + "|")
    lines += ["## 5.0c 强层同角色施压", s["step5_0c"].get("source", ""), s["step5_0c"].get("scope_note", ""), s["step5_0c"]["limitation"],
              "|作品|历史数|无前缀采纳|自我重述采纳|真译者作为自身先答在场|", "|---|---:|---:|---:|---:|"]
    for w in s["step5_0c"]["works"]:
        lines.append(f"|{w['work_id']}|{w['histories']}|{fmt(w['base_adoption']['history_equal'])}|{fmt(w['A1_adoption']['history_equal'])}|{w['T_as_own_current_answer']}/{w['histories']}|")
    for w in s["step5_0c"].get("additional_descriptive", []):
        lines.append(f"|{w['work_id']}（单独描述）|{w['histories']}|{fmt(w['base_adoption']['history_equal'])}|{fmt(w['A1_adoption']['history_equal'])}|{w['T_as_own_current_answer']}/{w['histories']}|")
    if s["step5_0c"].get("combined_24_reference"):
        w = s["step5_0c"]["combined_24_reference"]
        lines.append(f"|§10量级集合合并描述|{w['histories']}|{fmt(w['base_adoption']['history_equal'])}|{fmt(w['A1_adoption']['history_equal'])}|{w['T_as_own_current_answer']}/{w['histories']}|")
    lines += ["## 5.0d 同作品历史差异", s["definitions"]["b"], s["definitions"]["split_half"],
              "|单元|作品|历史数|最小差|最大差|极差|分半协方差|", "|---|---|---:|---:|---:|---:|---:|"]
    for w in s["step5_0d"]:
        lines.append("|" + "|".join(fmt(w[k]) for k in ("unit", "work_id", "histories", "b_min", "b_max", "b_range", "split_half_covariance")) + "|")
    e = s["step5_0e"]
    lines += ["## 5.0e 原作者问题无前缀交叉表", e["undetermined_definition"],
              "|立场|肯定原作者命题|未明确肯定或否认|否认原作者命题|", "|---|---:|---:|---:|"]
    for stance, name in (("USER", "采纳用户候选"), ("ORIG", "保持原答")):
        t = e["table"][stance]
        lines.append(f"|{name}|{t['AFFIRM']}|{t['UNDETERMINED']}|{t['DENY']}|")
    lines += [f"目标错误且明确肯定原作者命题：{e['wrong_target_and_author_affirm']}条。全部回答的译者命题否认：{e['C2_deny_all_answers']}条；只限保持原答立场：{e['C2_deny_ORIG_only']}条。后续统一采用全部回答口径。",
              "## 执行前状态", "5.0各项已计算，缺失输入：无。本步只包含既有数据分析；正式生成须待5.0单独提交和后续预注册冻结。", s["interpretation"]]
    text = ""
    for i, line in enumerate(lines):
        text += ("" if i == 0 else "\n" if line.startswith("|") and lines[i-1].startswith("|") else "\n\n") + line
    return text + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = run(args.pilot, args.out)
    print(json.dumps(dict(status=result["status"], histories=result["history_counts"],
                         answer_changes=len(result["answer_changes"]), cross_table=result["step5_0e"]), ensure_ascii=False))
