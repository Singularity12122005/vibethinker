"""独立评审冻结文件的处理器准备与核对；不改c39d632的生成冻结。"""
from pathlib import Path
import argparse
import json
import re

from .freeze import canonical_bytes, git, sha256
from .judge_core import RECOMMENDED_ATOMIC_SCOPE, protocol_definition, queue_counts
from .prepare import load, save


GENERATION_COMMIT = "c39d632850dd946b0f666154cdb503b728f7ac98"
REVIEW_ORDER = ("legacy_stance", "legacy_propositions", "evidence_disputed", "relations_v2")
REVIEW_FILE = "factdiag5_review_protocol.json"
RUN_SETTINGS = {
    "model_path": "/output/sycophancy-phase0/judge-model", "batch": 8,
    "padding_side": "left", "dtype": "bf16", "device_map": "cuda", "attention": "sdpa",
    "do_sample": False, "temperature": None, "top_p": None, "top_k": None,
    "max_new_tokens": {"legacy_stance": 64, "legacy_propositions": 512,
                       "evidence_disputed": 64, "relations_v2": 2048},
}


def prepare_review_protocol(repo, destination=None):
    repo = Path(repo).resolve()
    public = repo / "docs/research/early-stage"
    folder = public / "factdiag5"
    destination = Path(destination) if destination else folder / REVIEW_FILE
    prereg = load(folder / "factdiag5_prereg.json")
    material = load(folder / "factdiag5_materials.json")
    relation = load(public / "factdiag7/factdiag7_stage2_relation_protocol.json")
    if relation["judge_runtime"]["batch"] != 8 or relation["judge_runtime"]["max_new_tokens"] != 2048 or relation["judge_runtime"]["do_sample"] is not False:
        raise ValueError("已冻结阶段二原子评审参数与已核对来源不符")
    protocol = protocol_definition(prereg, approved_atomic_scope=RECOMMENDED_ATOMIC_SCOPE)
    protocol.update(version="factdiag5-review-v1", generation_commit=GENERATION_COMMIT,
        status="prepared_for_review_commit", runtime=RUN_SETTINGS, order=list(REVIEW_ORDER),
        counts=queue_counts(material, approved_atomic_scope=RECOMMENDED_ATOMIC_SCOPE),
        execution_clarifications=[
            dict(id="minimal_atomic_scope", approved=True,
                 scope="1440条R-S证据回答加全部400条5.5；每回答只提取真译者T，共1840。",
                 limitation="只报告这些回答中关于该对象的关系与否认；不宣称覆盖第五批全部错误关系。",
                 authorization="协调任务依据用户‘明确推荐直接采用’授权明确采纳本最小范围；原第七批§5/§8未逐格给第五批对象范围。"),
            dict(id="blind_identity_total", approved=True,
                 scope="5.1身份复核保持总数10，只从已执行R1′、R2、R3核心回答抽；未执行R1″专项5条标不适用。",
                 authorization="协调任务明确要求保持原总数10；不伪造未执行格，不补生成。"),
            dict(id="independent_coverage", approved=True,
                 scope="第五批§8完整覆盖独立满足；阶段二40条为其协议配额，可重叠共享合格回答，不截断第五批覆盖。",
                 authorization="协调任务明确确认两套覆盖要求分别满足。")],
        runtime_sources={
            "model_and_stance": "scripts/pilot/rescore.py：LocalJudge.__init__/__call__，由factdiag4/launch_judge.py.load_judge_dependency隔离同名模块后载入。",
            "propositions": "scripts/pilot/factdiag3/runtime.py：PropositionClient，复用同一已载入客户端，仅最大新增词元改为512。",
            "atomic": "factdiag7_stage2_relation_protocol.json.judge_runtime及stage2_judge.py：8条、2048词元、确定性生成。",
            "evidence_disputed": "第五批§5只冻结YES/NO指令，未给唯一词元上限；明确推荐并按用户授权采用旧短答上限64和batch8，不另设采样参数。"},
        once_policy=dict(attempts=1, retry=False,
            prior_retry_override="本轮明确一次尝试，覆盖旧runtime4.py中的解析失败重试路径；原立场/命题提示、判定及引文显示修复不变。",
            crash_policy="在同一结果文件的唯一输入键登记已派发，再写该次返回；中断但结果未保存的输入保留缺失，不重新调用模型。",
            storage="旧口径与新关系协议分文件；不覆盖core_generations.json，不改旧批标签。"),
        blind=dict(identity_5_1=10, optional_R1doubleprime="专项5条不适用，不产生该格盲样",
            evidence_each_cell_arm_positive=2, evidence_each_cell_arm_negative=2,
            evidence_disputed=20, status_5_5=20, shared_stage2_protocol_quota=40,
            evidence_sampling_event="主身份采纳d为阳性、有效身份未采纳d为阴性；技术失败和身份缺失不作阴性。",
            draw="本入口只构造候选池及已选编号对应表；正式盲样须由独立协调按冻结规则另行选定。",
            missing="不足全取并报告实际条数；不补生成。"),
        relation_protocol=dict(version=relation["version"], prompt_sha256=relation["prompt_sha256"],
            original_prompt=relation["prompt"], fixed_context="本轮用户消息、系统引用记录及固定助手前缀，仅供消歧，不计模型命题或引文。"))
    resources = {
        "factdiag5_20261112/factdiag5_prereg.json": folder / "factdiag5_prereg.json",
        "factdiag5_20261112/factdiag5_materials.json": folder / "factdiag5_materials.json",
        "factdiag7_20261112/factdiag7_stage2_relation_protocol.json": public / "factdiag7/factdiag7_stage2_relation_protocol.json",
        "factdiag7_20261112/factdiag7_stage2_materials.json": public / "factdiag7/factdiag7_stage2_materials.json",
    }
    protocol["resource_sha256"] = {name: sha256(path) for name, path in resources.items()}
    code = ["scripts/pilot/factdiag5/" + name for name in (
        "judge_core.py", "blind_core.py", "review_protocol.py", "review_runtime.py", "continue_reviews.py",
        "test_judge_core.py", "test_review_runtime.py")]
    code += ["scripts/pilot/" + name for name in (
        "common.py", "rescore.py", "factdiag4/launch_judge.py", "factdiag4/design.py",
        "factdiag3/runtime.py", "factdiag7/relations.py", "factdiag7/relations_v2.py")]
    code += ["src/sycophancy_phase0/scoring/" + name for name in ("judge.py", "parse.py")]
    protocol["code_sha256"] = {name: sha256(repo / "sycophancy_phase0" / name) for name in code}
    save(destination, protocol)
    return protocol


def validate_review(out, pilot, commit):
    if not re.fullmatch("[0-9a-f]{40}", commit) or commit == GENERATION_COMMIT:
        raise ValueError("需要协调端已核对的独立评审协议提交，不能复用生成提交")
    reg = load(Path(out) / REVIEW_FILE)
    if reg["generation_commit"] != GENERATION_COMMIT or reg["runtime"] != RUN_SETTINGS or tuple(reg["order"]) != REVIEW_ORDER:
        raise ValueError("评审协议的生成来源、参数或串行次序变化")
    if not all(c.get("approved") for c in reg["execution_clarifications"]):
        raise ValueError("评审范围尚未明确批准")
    for name, expected in {**reg["resource_sha256"], **reg["code_sha256"]}.items():
        path = Path(pilot) / name
        if not path.resolve().is_relative_to(Path(pilot).resolve()) or sha256(path) != expected:
            raise ValueError("评审冻结文件变化：" + name)
    return reg


def check_review_commit(repo, protocol_path, commit):
    """协调端提交后只读核对，不输出证明文件。"""
    repo = Path(repo).resolve()
    if not re.fullmatch("[0-9a-f]{40}", commit) or commit == GENERATION_COMMIT:
        raise ValueError("须提供独立评审提交")
    git(repo, "merge-base", "--is-ancestor", GENERATION_COMMIT, commit)
    protocol = load(protocol_path)
    names = [Path(protocol_path).resolve().relative_to(repo).as_posix()]
    names += ["sycophancy_phase0/" + name for name in protocol["code_sha256"]]
    for name in names:
        if git(repo, "show", commit + ":" + name) != canonical_bytes(repo / name):
            raise ValueError("提交未包含当前评审冻结内容：" + name)
    return dict(review_commit=commit, generation_commit=GENERATION_COMMIT, checked_files=len(names))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("prepare", "check-commit"))
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--protocol", type=Path)
    ap.add_argument("--commit")
    args = ap.parse_args()
    path = args.protocol or args.repo / "docs/research/early-stage/factdiag5" / REVIEW_FILE
    if args.action == "prepare":
        reg = prepare_review_protocol(args.repo, path)
        print(json.dumps(reg["counts"], ensure_ascii=False))
    else:
        print(json.dumps(check_review_commit(args.repo, path, args.commit or ""), ensure_ascii=False))
