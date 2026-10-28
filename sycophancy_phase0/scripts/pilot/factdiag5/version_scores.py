"""版本限定的零生成读数；同版本重述采用第五批正文给出的示例。"""
from .planning import PlanBlocked, digest
from .templates import VERSION_QUESTION, WORDING_QUESTION


def build_version_scores(materials, histories):
    """仅返回前向定义，绝不产生 V 采样请求。

    E_prime 必须来自冻结材料；适用性为显式布尔字段，不凭版本编号推断。
    每个问题同时保留 T、d_T 与有关历史的 x 全名原始分数；z_scope 使用 x
    的原始对数概率，不能误用两候选归一值代替。
    """
    bank = materials if isinstance(materials, dict) else {m["work_id"]: m for m in materials}
    definitions, issues = [], []
    for wid, m in sorted(bank.items()):
        if not m.get("E_prime") or type(m.get("version_control_applicable")) is not bool:
            issues.append(dict(code="version_material", work_id=wid,
                               message="缺少冻结的另一版本标识或版本对照适用性：" + wid))
            continue
        names = [m["F"]["gold"], m["d_T"]]
        refs = []
        for h in histories:
            if h["work_id"] == wid:
                if not h.get("selected_original"):
                    issues.append(dict(code="version_x", message="版本读数缺少已决定的自身先答：" + h["history_id"]))
                    continue
                names.append(h["selected_original"])
                refs.append(dict(history_id=h["history_id"], original=h["selected_original"]))
        names = list(dict.fromkeys(names))
        questions = dict(scope_original=m["F"]["question_en"],
            scope_other=VERSION_QUESTION.format(title=m["title"], E_prime=m["E_prime"]),
            wording=WORDING_QUESTION.format(title=m["title"], N=m["ebook"]))
        for kind, question in questions.items():
            definitions.append(dict(score_id=digest(["B7_F5_V", wid, kind]), work_id=wid,
                kind=kind, user_text=question, assistant_prefix="Final answer: ",
                candidate_names=names, comparison_candidates=[m["F"]["gold"], m["d_T"]],
                history_references=refs, forward_temperature=1.0, sample_count=0,
                version_control_applicable=m["version_control_applicable"],
                score_definition="full_name_raw_logprob"))
    if issues:
        raise PlanBlocked(issues)
    return definitions
