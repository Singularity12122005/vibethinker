"""仅绑定词元请求；复用旧引擎接口，不创建模型、不调用生成。

不能直接复用第六批正式运行器的 generate：它会重新计算第六批种子。
调用方应把 generation_arguments 的结果交给既有 GenRequest 构造器。
"""
import re

from .planning import GENERATION, PlanBlocked, digest, identity, seed_for
from .templates import LEGACY


def execution_blockers(state):
    """返回正式执行的必要门槛；纯规划不要求伪造已完成状态。"""
    issues = []
    for key, message in (("stage1_confirmed", "阶段一交付尚未获确认"),
                         ("step0_complete", "5.0 的全部离线分析尚未完成")):
        if state.get(key) is not True:
            issues.append(dict(code=key, message=message))
    for key, message in (("step0_commit", "5.0 尚未单独提交"),
                         ("prereg_commit", "材料、模板、规则和预测尚未冻结提交")):
        if not re.fullmatch("[0-9a-f]{40}", str(state.get(key, ""))):
            issues.append(dict(code=key, message=message))
    if state.get("step0_commit") and state.get("step0_commit") == state.get("prereg_commit"):
        issues.append(dict(code="separate_commits", message="5.0 与预注册须分开提交"))
    return issues


def bind_requests(engine, requests, sources):
    """sources 为 history_id 到原始第二轮 row；只在保有原文的远端调用。"""
    result = []
    if engine.builder.mode != "instruct":
        raise ValueError("原历史采用直接回答模式，不能更换模式")
    for request in requests:
        if request["request_id"] != identity(request) or request["seed"] != seed_for(request):
            raise ValueError("请求身份或新批种子不符")
        if request["system_text"] != LEGACY["system"]:
            raise ValueError("系统模板不符")
        source_id = request["source_history_id"]
        if source_id is None:
            # R1′已经包含专用末行指令，不得再套旧 x1 导致双重指令。
            ids = engine.first(request["user_text"])
            previous_length = 0
        else:
            if source_id not in sources:
                raise PlanBlocked([dict(code="source_missing", history_id=source_id,
                                        message="远端缺少对应原始历史：" + source_id)])
            row = sources[source_id]
            actual = digest({k: row[k] for k in ("prompt_ids", "assistant_ids", "assistant_text")})
            if actual != request["history_sha256"]:
                raise ValueError("原始历史与第三批冻结校验值不符：" + source_id)
            record = request["system_record"]
            if record:
                # next_turn 验证旧助手回合规范结束；随即以一个整体增量插入系统记录。
                engine.continue_from(row, request["user_text"])
                delta = ("\n<|im_start|>system\n" + record + "<|im_end|>"
                         "\n<|im_start|>user\n" + request["user_text"] +
                         "<|im_end|>\n<|im_start|>assistant\n")
                ids = list(row["prompt_ids"]) + list(row["assistant_ids"]) + engine.tok.encode(
                    delta, add_special_tokens=False)
            else:
                ids = engine.continue_from(row, request["user_text"])
            previous_length = row["n_new_tokens"]
        result.append(dict(request, prompt_ids=ids, previous_length=previous_length))
    return result


def generation_arguments(engine, tasks):
    """返回既有 GenRequest 的构造参数；不实例化、不执行推理。"""
    result = []
    for task in tasks:
        if task["seed"] != seed_for(task):
            raise ValueError("采样种子被替换")
        prefix = engine.tok.encode(task["forced_prefix"], add_special_tokens=False)
        result.append(dict(ids=list(task["prompt_ids"]) + prefix, seed=task["seed"],
                           temperature=GENERATION["temperature"],
                           max_new_tokens=GENERATION["max_new_tokens"]))
    return result


def teacher_forcing_inputs(engine, definition, sources):
    """全名位于助手回合起点；标记概率不进入候选分数。"""
    if definition["forward_temperature"] != 1.0:
        raise ValueError("前向必须使用未温度缩放的原始对数概率")
    task = bind_requests(engine, [definition["request"]], sources)[0]
    prefix = engine.tok.encode(definition["assistant_prefix"], add_special_tokens=False)
    suffixes = [engine.tok.encode(name, add_special_tokens=False)
                for name in definition["candidate_names"]]
    if any(not suffix for suffix in suffixes):
        raise ValueError("候选全名为空")
    return dict(seqs=[task["prompt_ids"] + prefix], suffixes=[suffixes], temperature=1.0)


def version_teacher_forcing_inputs(engine, definition):
    """V 使用同一旧系统模板的干净问句；不添加旧 x1 或推理正文。"""
    if definition["forward_temperature"] != 1.0 or definition["sample_count"] != 0:
        raise ValueError("版本读数仅允许原始前向计分")
    prompt = engine.first(definition["user_text"])
    marker = engine.tok.encode(definition["assistant_prefix"], add_special_tokens=False)
    suffixes = [engine.tok.encode(name, add_special_tokens=False)
                for name in definition["candidate_names"]]
    return dict(seqs=[prompt + marker], suffixes=[suffixes], temperature=1.0)
