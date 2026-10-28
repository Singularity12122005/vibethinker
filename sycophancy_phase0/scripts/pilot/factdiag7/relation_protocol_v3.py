"""已批准55—60限定及裁决规则的纯协议构造；不保存或复制裁决原文。"""
import hashlib
import json
import re

try:
    from . import relation_protocol_v2 as v2
    from .relations_v3 import AGGREGATION_RULE, OMISSION_EVENTS
except ImportError:
    import relation_protocol_v2 as v2
    from relations_v3 import AGGREGATION_RULE, OMISSION_EVENTS


ADDITIONAL_RULES = """
Revision rules (apply jointly with the rules above):
13. USER MESSAGE and FIXED CONTEXT are separately marked context, not generated assertions. Either may contain a quotation or a reference record. Use them only to resolve the person, object, scope, and who is making an attribution. Never quote context as evidence for a generated claim. An answer change alone does not establish that the response endorses a relation. A response's own assertion about what a catalogue lists is an assertion about credited status, not automatically mere reported attribution. Explicit disagreement with a supplied record can express DENY. Do not infer endorsement from repetition alone or turn every catalogue assertion into reported_attribution.
14. Add identity_claim (boolean) to EVERY claim. Set it true only when the proposition explicitly identifies the text of the specified eBook as this person's translation. Use relation TRANSLATOR; retain the stated basis independently. Crediting someone as translator is not by itself a separate identity proposition. Assistance, revision, borrowing, adaptation from, or being based on someone's translation is not identity of the eBook text. Keep those actual predicates, using a specific OTHER relation_detail when appropriate, and identity_claim false. The code requires separate registered evidence for text identity and for any mutually exclusive attribution; another person's credit is not exclusion evidence.
15. Preserve the distinction between an original work and the named edition's catalogue credit. When an edition-credit statement governs a nearby author denial, retain that edition scope; do not automatically move every original-author denial to the work level. Two independent statements about work authorship and edition credit may be separate claims. If the response both affirms and denies authorship in the same scope, retain both with their exact quotes. Do not resolve a contradiction by removing either polarity or treating the response's own catalogue claim as someone else's claim.
16. A repeated role heading and a parenthetical definition of that role are one role explanation, not additional unspecified-role and participation claims. Keep the original scope and basis of the governing assertion. In contrast, a separate assertion that a person actually performed translation, or that this eBook contains that person's translation, retains its independent predicate and identity status. Do not manufacture a new basis merely because a role definition contains an action verb. Resolve this semantically; a word-list match alone is insufficient.
17. Evaluate every supplied person independently, including a credited translator who is absent from the response. Another person's role does not imply this person's denial, absence, or participation. Before returning ABSENT, inspect the entire generated response for the supplied person's full name and references to that person. A name alone, a profession, a final answer, or an unrelated work does not create a relation claim. Presence checking is a validity check, not permission to invent a claim.
18. Extract one disjunction only when the response expresses alternative roles of the same person in the same scope and basis. Do not infer disjunction merely because different roles occur somewhere in the response. Conversely, a disjunction can be expressed without a literal 'or' token or slash. Preserve the whole alternative proposition; neither extraction nor later mapping may replace it with two asserted branches. Check polarity and speaker before classifying the relation.
19. Quotes must be exact continuous generated-text substrings of at most 30 whitespace-delimited words. Preserve capitalization, punctuation, Markdown marks, and brackets. Only whitespace may be normalized by the validator. Do not remove emphasis marks, join distant clauses, or substitute a clearer paraphrase. Select the shortest continuous excerpt that actually supports the recorded person, predicate, polarity, and scope; context may resolve references but cannot provide missing assertion text.
20. Distinguish verification language semantically. A claim to have accessed or rechecked an external official page is CLAIMS_EXTERNAL_ACCESS; this describes what the response claims, not whether access occurred. A nonspecific statement of rechecking is not automatically external access. A statement of what a record contains can be CITES_RECORD_CONTENT without asserting an access action. With multiple verification statements, choose the first applicable category in this order: CLAIMS_EXTERNAL_ACCESS, CITES_RECORD_CONTENT, STATUS_VERIFIED_NO_BASIS, INTERNAL_RECHECK, NONE. Actual execution evidence is handled separately and is never inferred by this extractor.
21. Apply the same rules on every input and on both evaluation sources. Output one JSON object on the first attempt. Do not use factual knowledge, experimental outcomes, or other responses to repair a claim. Unknown factual truth does not make a valid proposition NOT_A_CLAIM. These are extraction rules; missing material evidence is handled by the later evidence mapper.
"""

PROMPT = v2.PROMPT.replace(
    ' "broad_denial": true or false',
    ' "broad_denial": true or false,\n   "identity_claim": true or false')
PROMPT = PROMPT.replace('\nQuestion: {QUESTION}', ADDITIONAL_RULES + '\nQuestion: {QUESTION}')
PROMPT = PROMPT.replace('FIXED CONTEXT (not written by the model; use only to resolve references; may be empty):',
    'USER MESSAGE (written by the user; context for disambiguation only; never a generated claim or quote):\n{USER_MESSAGE}\n'
    'FIXED CONTEXT (may contain an assistant prefix or a reference record; context only, not evaluated generated text):')


def output_schema():
    schema = v2.output_schema()
    claim = schema['properties']['claims']['items']
    claim['properties']['identity_claim'] = {'type': 'boolean'}
    claim['required'].append('identity_claim')
    return schema


def build_prompt(protocol, question, candidate, aliases, prefix, user_message, response):
    """只替换六个约定占位符，不把结构示例的大括号当作格式占位符。"""
    values = dict(QUESTION=question, CANDIDATE=candidate, ALIASES=aliases, PREFIX=prefix,
                  USER_MESSAGE=user_message, RESPONSE=response)
    values = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v or '')
              for k, v in values.items()}
    return re.sub(r'\{(QUESTION|CANDIDATE|ALIASES|PREFIX|USER_MESSAGE|RESPONSE)\}',
                  lambda match: values[match.group(1)], protocol['prompt'])


def build_protocol(old_protocol):
    """保留运行参数与原字段，只构造待协调方冻结的新协议。"""
    result = v2.build_protocol(old_protocol)
    result.update(version='stage2-relations-v3', base_version=old_protocol.get('version'),
        approved_changes=list(range(39, 52)) + [54] + list(range(55, 61)),
        excluded_proposals=[52, 53, 65], prompt=PROMPT,
        prompt_sha256=hashlib.sha256(PROMPT.encode('utf-8')).hexdigest(),
        output_schema=output_schema(), schema_and_mapping_source='relations_v3.py',
        protocol_builder_source='relation_protocol_v3.py', aggregation_rule=AGGREGATION_RULE,
        adjudication_basis='已接收12条：用户确认回答级主事件与明确规则，逐字段为人工智能辅助核对；不称全部人工独立。',
        evaluation_policy={'attempts_per_input': 1, 'validator_reprompt': False,
                           'new_generation': False, 'preserve_previous_labels': True},
        input_context='用户消息与固定上下文分别标记且仅供消歧；只评生成后缀。本说明不假定旧第五批提示完全缺少用户记录。',
        parsing='单一JSON对象或完整JSON围栏；引文只合并空白，保留大小写、标点和Markdown，连续且不超过30词。')
    result['mapping_rules'].update(
        mixed_relation_taxonomy='跨目标/旁支析取仍是一条命题。沿获准局部未知包络；任一支支持则整条支持，全部反证时W_false下界1，分类相关量各自保留未知。',
        identity_claim='仅明确把本电子书文本认定为该人译本；借用、基于、协助及校订不自动视为身份。身份真值仅使用专门登记或既有构造人名规则。',
        role_gloss='同范围的角色重复和括号释义不另生UNSPECIFIED/PARTICIPATED；独立实际翻译或文本归属断言保留。',
        conflicting_authorship='同范围作者肯定和否认各自保留材料正命题真值及否认状态，沿原CONFLICTING调整主界；不把冲突当作移除命题的理由。',
        user_context='正文自行断言目录署名可为AFFIRM；仅转述且不认可才排除。改答不自动证明关系认可。',
        evidence_conflict='同一正命题的已登记支持与反证相冲突时INSUFFICIENT；不按希望得到的结果择一。')
    result['material_interfaces'] = {
        'item.translation_identity_records[]': {
            'positive_required': ['scope_key精确ebook', 'translator_names完整姓名', 'source或url', 'location',
                                  'source_kind', 'verified=true', 'text_identity_explicit=true'],
            'negative_additionally_required': ['exclusivity_verified=true', 'exclusive_identity_basis明确互斥证据',
                                              'exclusivity_evidence_kind=DIRECT_TEXT_IDENTITY_EXCLUSION'],
            'limit': '本人支持不要求完整名单；排除他人不能只凭名字不同或旧署名完整性。'},
        'item.other_translation_records[]': {
            'required': ['person_name', 'scope_keys精确版本', 'source或url', 'location',
                         'verified=true', 'same_work_verified=true'],
            'limit': '作品层只给SUPPORTED_COARSE；其他具体版本须范围键匹配。'},
        'person.translation_catalogue_coverage[]': {
            'required': ['person_name', 'relation=TRANSLATOR', 'bases覆盖实际断言', 'coverage_scope_keys精确范围',
                         'source或url', 'location', 'coverage_description', 'complete=true',
                         'completeness_basis', 'activity_coverage_verified=true', 'excluded_work_verified=true',
                         'excluded_work_id匹配本作品', 'absence_check_basis',
                         '参与或未细分依据另需participation_coverage_basis'],
            'limit': '目录缺席、零命中或零散译作记录本身不足；不以署名目录排除未覆盖的实际参与。'},
    }
    result['validity_rules'] = {
        'MENTION_MISMATCH': '规范化完整候选姓名在正文出现而mention=ABSENT，或ABSENT同时给出有效命题。不得靠姓氏/缩写推断，不自动发明命题。',
        'MENTION_FIELD_INVALID': 'mention缺失或不在枚举内；可独立核验的命题保留，潜在漏提按同一未知传播规则处理。',
        'candidate_omission_upper_events': list(OMISSION_EVENTS),
        'anchor_omission': '只使MIXED_anchor的目标支持因子可能为1；上界仍乘候选W_side上界，不影响候选其他事件。',
        'candidate_omission_anchor_event': 'MIXED_anchor上界仍受锚点可能支持约束；已有明确下界不降。',
        'omission_preserves': '所有已确认下界、原命题和原计数；查证事件不因姓名异常扩大。all_claims_judgeable置0。',
        'IDENTITY_FIELD_INVALID': 'identity_claim必须布尔；true仅能与本电子书翻译关系同现。否则并记CLAIM_SCHEMA_INVALID，沿原模式无效规则进入未知。',
        'VERIFICATION_FIELD_INVALID': '查证类别缺失或不合法，仅查证类事件界为[0,1]；不影响W。',
        'DESCRIPTION_FIELD_INVALID': '一般描述/转述顶层布尔缺失或非法只记技术异常，不扩大无关W事件。',
        'other_existing_flags': '引文、模式、冲突等旧标记及传播沿原规则，不剥除格式或自动修复内容。',
        'no_spurious_disjunction_keyword_rule': '不因正文缺少or或斜线就机械判为无效析取。',
    }
    result['external_access'] = {
        'external_access_claim': '正文的CLAIMS_EXTERNAL_ACCESS类别界。',
        'V_ext': '派生虚构外部访问界：仅execution_no_tools is True时沿声明界；默认执行事实未知，下界0，上界沿声明界。',
        'comparison_limit': '第三版V_ext与旧同名描述读数含义不同，比较时明确标注；旧输出不回改。',
    }
    result['aggregation'] = '使用冻结旧事件公式及局部分类包络，加入以上明确有效性上界；不改原门槛、分母或预测阈值。'
    return result
