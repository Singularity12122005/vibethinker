"""获准的局部分类未知包络；不修改冻结提取、映射或原聚合器。

等价性：固定所有命题及正命题真值，每个跨类记录只增加一个 is_target
二值分类变量，整条析取仍然是一个记录。W_target 的两个端点随候选变量
逐坐标单调增；W_side、M_side、W_side_insuff 逐坐标单调减。
MIXED_anchor 是候选旁支端点与锚点目标支持端点的非负乘积，随候选
变量单调减、随锚点变量单调增。其他原事件及计数不使用这些变量。
所以所有候选未知记录同取 False/True、锚点同取 False/True 的至多
四个角点，给出逐事件全部独立分类可能性的准确最小下界和最大上界。
此包络是各事件的边际界，不声称所有事件端点能在同一个分类下同时实现。
"""
import copy
from itertools import product

try:
    from .relations_v2 import legacy
except ImportError:
    from relations_v2 import legacy

AGGREGATION_RULE = 'stage2-local-taxonomy-unknown-v1'
RELATION_EVENTS = tuple(name for name, value in legacy.aggregate({'parse_status': 'OK', 'claims': []}).items()
                        if isinstance(value, list))


def event_view(extraction):
    """沿冻结事件视图过滤非命题、展开已有否认组件；不拒绝分类未知。"""
    result = copy.deepcopy(extraction)
    active = []

    def collect(claim):
        if (not claim.get('event_eligible', True) or claim.get('claim_status') == 'NOT_A_CLAIM'
                or claim.get('positive_verdict') == 'NOT_A_CLAIM'):
            return
        if claim.get('aggregate_via_components'):
            for component in claim.get('denial_components', []):
                collect(component)
        else:
            active.append(claim)

    for claim in result.get('claims', []):
        collect(claim)
    result['claims'] = active
    return result


def _assigned(view, is_target):
    result = copy.deepcopy(view)
    if result is not None:
        for claim in result['claims']:
            if claim.get('taxonomy_unresolved'):
                claim['is_target'] = is_target
    return result


def aggregate(extraction, anchor=None, *, technical_failure=False):
    """逐事件分类包络；每个情形仍调用冻结旧聚合器，原输入保持不变。"""
    candidate_view = event_view(extraction)
    anchor_view = event_view(anchor) if anchor is not None else None
    counts = [sum(bool(c.get('taxonomy_unresolved')) for c in (view or {}).get('claims', []))
              for view in (candidate_view, anchor_view)]
    cases = [legacy.aggregate(_assigned(candidate_view, candidate_target),
                              _assigned(anchor_view, anchor_target), technical_failure=technical_failure)
             for candidate_target, anchor_target in product(*[(False, True) if n else (False,) for n in counts])]
    result = copy.deepcopy(cases[0])
    for event in RELATION_EVENTS:
        result[event] = [min(case[event][0] for case in cases), max(case[event][1] for case in cases)]
    for name in set(result) - set(RELATION_EVENTS):
        if any(case[name] != result[name] for case in cases):
            raise ValueError('原非事件字段意外依赖分类：' + name)
    result.update(n_records=len(extraction.get('claims', [])),
                  n_not_a_claim=sum(not c.get('event_eligible', True) or c.get('claim_status') == 'NOT_A_CLAIM'
                                   for c in extraction.get('claims', [])),
                  aggregation_rule=AGGREGATION_RULE, n_taxonomy_unknown=sum(counts),
                  n_taxonomy_unknown_candidate=counts[0], n_taxonomy_unknown_anchor=counts[1],
                  n_classification_cases=len(cases))
    return result
