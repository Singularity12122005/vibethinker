"""第五批公开材料、全部原文规则与预注册的处理器入口，不连接模型。"""
from pathlib import Path
from collections import Counter
import argparse
import json

from .analysis_spec import specification
from .freeze import CODE_PREFIX, git, check_committed, sha256
from .materials import attach_evidence_gates
from .planning import build_plan
from .templates import CORE, LEGACY, ROLES, VERSION_QUESTION, WORDING_QUESTION, template_hashes
from .version_materials import attach_version_materials
from .version_scores import build_version_scores


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    pending.replace(path)


def reject_raw(value):
    """公开材料不得意外混入原回答或原词元。"""
    if isinstance(value, dict):
        forbidden = {"assistant_text", "assistant_ids", "prompt_ids", "raw_response", "full_text"} & value.keys()
        if forbidden:
            raise ValueError("公开输入含原文或词元字段：" + ",".join(sorted(forbidden)))
        for item in value.values():
            reject_raw(item)
    elif isinstance(value, list):
        for item in value:
            reject_raw(item)


def public_materials(inputs, relation, third):
    reject_raw(inputs)
    roster = third["phase2"]["history_list"]
    if len(roster) != 193:
        raise ValueError("第三批必须为原193项登记")
    rules = third["frozen"]["rules"]
    materials = attach_version_materials(attach_evidence_gates(inputs["materials"], relation))
    plan = build_plan(inputs["histories"], materials, frozen_roster=roster,
                      legacy_templates=rules["templates"], legacy_hashes=rules["template_sha256"])
    versions = build_version_scores(materials, plan["histories"])
    if len(plan["requests"]) != 3364 or plan["unique_triples"] != 32 or len(versions) != 30:
        raise ValueError("真实输入与已批准的核心规模不符")
    # 解析只继承已登记姓名与别名；不引入新候选，不根据结果改名。
    people = {}
    for item in relation["items"]:
        if item.get("structure") == "G1":
            people[item["work_id"]] = [dict(name=p["name"], aliases=p.get("aliases", [])) for p in item["people"]]
    result = dict(materials=materials, plan=plan, version_scores=versions, registered_people=people,
                  source_roster_count=193, selected_count=130,
                  display_name_source=inputs.get("display_name_source"),
                  original_text_location="A100 only",
                  arm_counts={cell: dict(Counter(r["arm"] for r in plan["requests"] if r["cell"] == cell))
                              for cell in plan["counts"]})
    reject_raw(result)
    return result


def prepare(repo, inputs, relation, out, *, approve_analysis=False):
    repo, out = Path(repo).resolve(), Path(out).resolve()
    source = repo / "docs/research"
    third_path = source / "early-stage/factdiag3/factdiag3_prereg.json"
    materials = public_materials(load(inputs), load(relation), load(third_path))
    save(out / "factdiag5_materials.json", materials)
    step0 = git(repo, "rev-parse", "5b2b4e3^{commit}").decode().strip()
    stage2a = git(repo, "rev-parse", "e530279^{commit}").decode().strip()
    # 保存完整规范原文，所有可选预测也保留并以执行范围区分，不挑选预测。
    sources = {name: (source / name).read_text(encoding="utf-8") for name in (
        "sycophancy-phase0-batch5-execution-prompt.md", "sycophancy-phase0-batch7-execution-prompt.md")}
    code = {p.relative_to(repo).as_posix(): sha256(p)
            for p in (repo / CODE_PREFIX / "factdiag5").glob("*.py") if p.name != "step0.py" and p.name != "test_step0.py"}
    # 直接复用的旧接口与共同预算也固定，旧文件不修改。
    for name in ("factdiag/rules.py", "factdiag2/rules.py", "factdiag2/runtime.py", "factdiag3/protocol.py",
                 "factdiag3/analysis.py", "factdiag3/exploratory_stats.py", "factdiag3/quote_repair.py",
                 "factdiag4/common.py", "factdiag6g/legacy.py", "factdiag7/stage2_budget.py"):
        code[CODE_PREFIX + name] = sha256(repo / CODE_PREFIX / name)
    reg = dict(schema="factdiag5-core-v1", step0_complete=True, step0_commit=step0,
        stage1_confirmed=True, stage2a_freeze_commit=stage2a,
        frozen_files={"factdiag5_materials.json": sha256(out / "factdiag5_materials.json")},
        code_sha256=code, templates=dict(legacy=LEGACY, core=CORE, roles=ROLES,
            V_scope_other=VERSION_QUESTION, V_wording=WORDING_QUESTION), template_sha256=template_hashes(),
        original_rules_and_predictions=sources, analysis_freeze=specification(approve_analysis),
        selected_scope=list(CORE), optional_scope_status="未运行，全部原预测仍在完整原文中保留；本次不自动补采。",
        approved_rules=materials["plan"]["approved_rules"],
        generation=materials["plan"]["generation"], seed=20261112, forward_temperature=1.0,
        order=["R1prime", "R1prime_forward", "V_forward", "R2", "R2_forward", "R3", "R3_forward",
               "budget_checkpoint", "F-E-true", "F-E-sys", "M-wrong", "M-right", "E-inapp", "E-false", "5.5"],
        counts=dict(generations=3364, unique_triples=32, histories=130, registered_histories=193,
                    identification_forward=len(materials["plan"]["scoring_requests"]), V_forward=30, V_samples=0),
        remote_interface=dict(module="sycophancy_phase0.inference.hf_engine",
            function="confidence_features(model, seqs, suffix_ids, top_k=50, pad_id=None, temperature=TEMPERATURE)",
            result="suffix_logp: 二维数组，行为提示，列为完整姓名后缀",
            verified_source="/output/sycophancy-phase0/pilot/src/sycophancy_phase0/inference/hf_engine.py",
            temperature_argument=1.0),
        review_protocol="第五批原立场、explicit、命题评审按旧口径并列；第七批关系主张另用阶段二已冻结协议。完整回答留A100待评审。",
        storage=dict(remote_output="/output/sycophancy-phase0/pilot/factdiag5_20261112",
            generation_file="core_generations.json", identification_forward_file="core_forward.json",
            V_forward_file="version_forward.json", raw_text="A100 only"))
    save(out / "factdiag5_prereg.json", reg)
    return reg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("prepare", "check-commit"))
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--inputs", type=Path)
    ap.add_argument("--relation", type=Path)
    ap.add_argument("--approve-analysis", action="store_true",
                    help="仅在已获核对批准时把固定建议写为待提交的冻结规则")
    ap.add_argument("--freeze-commit")
    args = ap.parse_args()
    if args.action == "prepare":
        if not args.inputs or not args.relation:
            ap.error("准备需要真实输入与关系材料路径")
        reg = prepare(args.repo, args.inputs, args.relation, args.out, approve_analysis=args.approve_analysis)
        print(json.dumps(dict(counts=reg["counts"], analysis_status=reg["analysis_freeze"]["status"]), ensure_ascii=False))
    else:
        if not args.freeze_commit:
            ap.error("提交核对需要真实冻结提交号")
        print(json.dumps(check_committed(args.repo, args.out, args.freeze_commit), ensure_ascii=False))


if __name__ == "__main__":
    main()
