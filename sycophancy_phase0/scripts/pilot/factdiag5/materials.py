"""把已有公开材料登记接到第五批接口；不查询网络、不补造核验结果。"""
from copy import deepcopy

from .planning import PlanBlocked


def attach_evidence_gates(materials, relation_materials):
    items = {item["work_id"]: item for item in relation_materials["items"]
             if item.get("structure") == "G1"}
    result, issues = [], []
    for original in materials:
        m = deepcopy(original)
        wid = m["work_id"]
        item = items.get(wid)
        if item is None:
            issues.append(dict(code="relation_material_missing", work_id=wid,
                               message="缺少该作品已核实的关系材料：" + wid))
            continue
        people = [person for person in item["people"] if person.get("type") == "T"]
        if len(people) != 1 or people[0]["name"] != m["F"]["gold"]:
            issues.append(dict(code="translator_identity", work_id=wid,
                               message="关系材料真译者与第五批材料不一致：" + wid))
            continue
        person = people[0]
        check = person.get("catalog_check", {})
        rows = check.get("catalog_rows", [])
        author_rows = [row for row in rows if row[0] == "Author"]
        translator_rows = [row for row in rows if row[0] == "Translator"]
        catalog_positive = bool(translator_rows and
            "TRANSLATOR_OF_THIS_EDITION" in person.get("true_roles", []) and
            check.get("name_checks", {}).get("T", {}).get("name") == person["name"])
        author_verified = bool(author_rows and item["gold"] == m["R"]["gold"])
        page_check = deepcopy(item.get("q6_title_page_check", {}))
        page_positive = page_check.get("verified") is True
        # 两处核验结果可以都保留，5.3本次引用已有明确字段的目录来源。
        translator_source = "catalog entry" if catalog_positive else "title page"
        source = "the catalog's contributor list" if catalog_positive else "the title page of the eBook"
        m["evidence_gate"] = dict(status="verified" if catalog_positive or page_positive else "pending",
            catalog_contributors_checked=bool(rows), title_page_credits_checked=page_positive,
            catalog_author_verified=author_verified,
            catalog_translator_names=[person["name"]] if catalog_positive else [],
            title_page_translator_names=[person["name"]] if page_positive else [],
            catalog_source=check.get("source_catalog"), catalog_location="Author; Translator",
            title_page_source=check.get("source_text"),
            title_page_location=page_check.get("location") or ("扉页译者署名" if page_positive else None),
            translator_source=translator_source, source=source,
            catalog_author_rows=author_rows, catalog_translator_rows=translator_rows)
        m["q6_complete_gate"] = dict(title_page_check=page_check,
            catalog_checked=bool(rows), complete_record_verified=None,
            note="保留原有前页核验结果；此适配不把正面署名推成完整排除结论。")
        # 姓名别名只继承已有登记；不扩展未知人名，不把首字母猜成全名。
        aliases = list(dict.fromkeys([m["F"]["gold"], *m["F"].get("gold_aliases", []),
                                     *person.get("aliases", [])]))
        m["F"]["gold_aliases"] = aliases
        m["R"]["d_aliases"] = aliases
        result.append(m)
    if issues:
        raise PlanBlocked(issues)
    return result
