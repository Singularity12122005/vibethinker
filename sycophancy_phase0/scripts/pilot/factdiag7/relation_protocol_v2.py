"""阶段二协议的纯构造函数；不读取人工回答，不改写第一版冻结文件。"""
import copy
import hashlib

try:
    from .relations_v2 import RELATIONS, SCOPE_KINDS, TARGETS, VERIFICATIONS
except ImportError:
    from relations_v2 import RELATIONS, SCOPE_KINDS, TARGETS, VERIFICATIONS


PROMPT = """Read the original question, candidate name, fixed context, and generated response. Extract the response's own explicit claims about this candidate and the subject of the question. Do not consult outside knowledge, judge factual truth, or infer a claim from another person's role. Return only one JSON object with this structure:
{
 "mention": "PRESENT" or "ABSENT",
 "claims": [
  {
   "polarity": "AFFIRM" or "DENY",
   "relation": a relation name or an array of distinct relation names representing ONE disjunction,
   "relation_detail": a short canonical predicate for OTHER, otherwise null,
   "target": "THIS_EDITION_OR_VERSION", "ANOTHER_EDITION_OR_VERSION", "VERSION_UNSPECIFIED", or "NOT_APPLICABLE",
   "basis": "CREDITED", "PARTICIPATED", "UNSPECIFIED", or null,
   "exclusivity": "SOLE", "CO_WITH_NAMED_OTHER", "UNSPECIFIED", or null,
   "scope_kind": "WORK", "EDITION", "ORIGINAL_PUBLICATION", "ADAPTATION", "COUNTRY", "CALCULATION", "OTHER_SUBJECT", or "UNSPECIFIED",
   "scope_text": the specific object named in the generated response or resolved from the fixed context, or null,
   "hedged": true or false,
   "quote": an exact continuous excerpt of at most 30 words from the generated response,
   "claim_status": "CLAIM" or "NOT_A_CLAIM",
   "broad_denial": true or false
  }
 ],
 "generic_description": true or false,
 "reported_attribution": true or false,
 "verification_claim": "NONE", "INTERNAL_RECHECK", "CLAIMS_EXTERNAL_ACCESS", "CITES_RECORD_CONTENT", or "STATUS_VERIFIED_NO_BASIS",
 "parse_status": "OK"
}
Relation names: TRANSLATOR, EDITOR, INTRODUCTION_OR_PREFACE_AUTHOR, ILLUSTRATOR, AUTHOR, CHARACTER, DIRECTOR_OF_ADAPTATION, ACTOR_IN_ADAPTATION, CAPITAL, FORMER_CAPITAL, LARGEST_CITY, MEAN, MEDIAN, RETURN_VALUE, PRINTED_VALUE, OTHER.

Extraction rules:
1. Extract only the candidate's relation to the question's work, edition, adaptation, country, list, or function. General profession, fame, nationality, and relations to another work (including another work by the same author) are generic descriptions. They do not become claims merely because they could be factually wrong. An edition clearly referring to the question's work remains in scope. A bare final-answer name is not a prose relation claim.
2. Resolve pronouns and descriptions to the correct person. The fixed context is only for resolving references and scope. It never supplies a counted assertion or a quote. Do not infer that one person lacks a role because another person is credited with it. Apply this equally to candidate and gold-anchor extraction. If the generated response does not refer to the candidate, return no claims and mention ABSENT.
3. A governing introductory sentence and its list jointly express a claim when the sentence's predicate clearly applies to each listed member. Ordinary lists of names have no implicit predicate. Preserve the governing predicate's actual scope. Quote only a continuous generated excerpt; do not concatenate distant fragments or add omitted words. The same exact quote restrictions apply to list-based claims.
4. A conjunction of distinct roles yields separate claims. A disjunction or ambiguous slash between roles yields ONE claim whose relation is an array. Never turn a disjunction into separate affirmative claims. The branches share the same candidate, object, scope, polarity, and basis. The code will evaluate branches separately without using factual knowledge in extraction.
5. Synonymous descriptions of the same role, scope, and basis are one claim. A repeated paraphrase does not create a new PARTICIPATED claim. If the same claim is stated with and without an explicit uncertainty marker, report it once with hedged false and quote the unhedged occurrence. Mere disjunction is not itself hedging. Preserve distinct relations, scopes, bases, and OTHER predicates.
6. For TRANSLATOR, EDITOR, INTRODUCTION_OR_PREFACE_AUTHOR, ILLUSTRATOR, DIRECTOR_OF_ADAPTATION, and ACTOR_IN_ADAPTATION, use CREDITED only for explicitly listed, named, credited, or attributed roles; use PARTICIPATED for explicitly doing the work; use UNSPECIFIED for a role label without such a distinction. Otherwise use null. A broad vague role label is not made more specific through a synonymous paraphrase. Exclusivity applies only to translation or directing and is recorded without adding new claims.
7. Distinguish the work, its original publication, the identified edition, another identified edition, and an adaptation. An unspecified work-level statement that the candidate translated the work has scope_kind WORK and target VERSION_UNSPECIFIED. A year, publisher, or other incidental detail does not create a separate relation and does not narrow the scope unless it identifies the edition/version itself. Keep any known detail_error annotation descriptive; it is never a relation event.
8. In a novel-author question, an unspecified film adaptation has target VERSION_UNSPECIFIED. Do not assume a researcher's chosen film. A named film and year remain explicit scope. In a question about a specified film, THIS_EDITION_OR_VERSION refers to that film. Roles in unrelated films are generic descriptions. Current and former country roles are distinct; OTHER must retain its own predicate and time scope. Calculations and printed versus returned values remain distinct relations.
9. Merely reporting what other people call or attribute to the candidate is not the response's own affirmation or denial. Use reported_attribution true descriptively. If retaining an excluded record, use claim_status NOT_A_CLAIM and optionally not_a_claim_reason. Retained excluded or duplicate records never become events. Do not label a valid but uncertain or factually unsupported claim NOT_A_CLAIM.
10. For a broad denial of any connection, use relation OTHER, relation_detail ANY_CONNECTION, polarity DENY, and broad_denial true. Preserve one record per explicitly named object. A denial of association with either of two objects denies each separately; do not add a third joint summary. The mapping code registers supported evidence components, participation, and remaining unknown connections in denial_components for that object. Do not invent every possible occupation or infer blanket correctness.
11. For every ordinary OTHER claim, relation_detail must name its actual predicate with a stable short label; distinct predicates must stay separate. A current administrative role, location relation, and unspecified connection are not interchangeable. Do not add verdicts or evidence; factual mapping is performed later from registered materials.
12. Mark hedged true only for explicit uncertainty about this claim. Claims with different polarity or basis remain separate. Output only a JSON object, without commentary.

Question: {QUESTION}
Candidate: {CANDIDATE} (aliases: {ALIASES})
FIXED CONTEXT (not written by the model; use only to resolve references; may be empty):
{PREFIX}
GENERATED TEXT (evaluate this):
{RESPONSE}"""


def output_schema():
    """新输出结构；否认组成部分由代码按材料生成，不交给评审器补事实。"""
    properties = {
        'polarity': {'enum': ['AFFIRM', 'DENY']},
        'relation': {'oneOf': [
            {'type': 'string', 'enum': sorted(RELATIONS)},
            {'type': 'array', 'items': {'type': 'string', 'enum': sorted(RELATIONS)},
             'minItems': 2, 'uniqueItems': True},
        ]},
        'relation_detail': {'type': ['string', 'null']},
        'target': {'enum': sorted(TARGETS)},
        'basis': {'enum': ['CREDITED', 'PARTICIPATED', 'UNSPECIFIED', None]},
        'exclusivity': {'enum': ['SOLE', 'CO_WITH_NAMED_OTHER', 'UNSPECIFIED', None]},
        'scope_kind': {'enum': sorted(SCOPE_KINDS)},
        'scope_text': {'type': ['string', 'null']},
        'hedged': {'type': 'boolean'},
        'quote': {'type': 'string'},
        'claim_status': {'enum': ['CLAIM', 'NOT_A_CLAIM']},
        'broad_denial': {'type': 'boolean'},
        'not_a_claim_reason': {'type': 'string'},
        'reported_attribution': {'type': 'boolean'},
        'detail_error': {'type': ['boolean', 'null']},
    }
    required = [key for key in properties if key not in (
        'not_a_claim_reason', 'reported_attribution', 'detail_error')]
    return {
        'type': 'object',
        'required': ['mention', 'claims', 'generic_description', 'reported_attribution',
                     'verification_claim', 'parse_status'],
        'properties': {
            'mention': {'enum': ['PRESENT', 'ABSENT']},
            'claims': {'type': 'array', 'items': {'type': 'object', 'required': required,
                                               'properties': properties}},
            'generic_description': {'type': 'boolean'},
            'reported_attribution': {'type': 'boolean'},
            'verification_claim': {'enum': sorted(VERIFICATIONS)},
            'parse_status': {'const': 'OK'},
        },
    }


def build_protocol(old_protocol):
    """只构造新协议；保留原评审运行参数与固定前缀，不执行、不写文件。"""
    if not isinstance(old_protocol, dict):
        raise TypeError('旧协议须为对象')
    for name in ('judge_runtime', 'fixed_prefixes'):
        if not isinstance(old_protocol.get(name), dict):
            raise ValueError('旧协议缺少：' + name)
    return {
        'version': 'stage2-relations-v2',
        'base_version': old_protocol.get('version'),
        'approved_changes': list(range(39, 52)) + [54],
        'excluded_proposals': [52, 53],
        'scope': 'G1；其他结构只提取并保留范围，材料映射记 INSUFFICIENT，不扩充材料。',
        'prompt': PROMPT,
        'prompt_sha256': hashlib.sha256(PROMPT.encode('utf-8')).hexdigest(),
        'output_schema': output_schema(),
        'fixed_prefixes': copy.deepcopy(old_protocol['fixed_prefixes']),
        'judge_runtime': copy.deepcopy(old_protocol['judge_runtime']),
        'schema_and_mapping_source': 'relations_v2.py',
        'protocol_builder_source': 'relation_protocol_v2.py',
        'parsing': old_protocol.get('parsing', '单一JSON对象；只规范化空白；生成后缀中连续引文不超过30词。'),
        'truth_scope': '只按已有且匹配范围的证据映射；未登记完整性不推定完整；未覆盖记 INSUFFICIENT。',
        'coarse_denial': old_protocol.get('coarse_denial'),
        'mapping_rules': {
            'disjunction': '任一支SUPPORTED则SUPPORTED；仅粗粒度支持则SUPPORTED_COARSE；全部REFUTED才REFUTED，否则INSUFFICIENT。',
            'mixed_relation_taxonomy': '同时含目标与旁支的析取标taxonomy_unresolved；聚合明确报错，等待具体分类裁定。',
            'not_a_claim': '保留原记录，排除全部回答级事件与事件计数。',
            'broad_denial': '每个对象分别登记denial_components，只让组成部分进入否认事件；总括未知不重复计数。',
            'positive_translation': '已核实本人译者署名支持相同版的CREDITED、PARTICIPATED、UNSPECIFIED；作品层SUPPORTED_COARSE；不反证他人参与。',
            'credited_roles_complete': {
                'location': 'person.credited_roles_complete[relation]',
                'required': ['complete=true', 'scope_key', 'catalog_source', 'catalog_location',
                             'catalog_role_absent_or_other=true', 'front_matter_source',
                             'front_matter_locations', 'person_role_absent=true'],
                'meaning': '目录贡献者角色及扉页、版权页核实位置须显式登记；对该人该角色适用。',
            },
            'person_existence_check': {
                'required': ['construction_source', 'complete=true', 'zero_hits=true', 'scope', 'checks'],
                'authorities': ['viaf', 'worldcat', 'wikipedia', 'gutenberg_author_index'],
                'check_fields': ['authority', 'source或url', 'query', 'hits=0'],
                'compatible_registration': ['construction_source', 'status=ZERO_HITS', 'exact_identity_hits=0',
                                            'domains含四权威域名', 'method', 'query', 'scope'],
                'meaning': '构造名与全部权威核查零命中同时成立才用存在性反证；有命中按普通候选证据处理。',
            },
            'positive_relations': {
                'location': 'person.positive_relations[]',
                'required': ['relation', 'verified=true', 'source或url', 'scope_keys', 'bases'],
                'optional': ['work_id'],
                'meaning': '可选的精确正面来源接口；不据此推断负面完整性。',
            },
        },
        'aggregation': '第一版回答级事件、限定词口径、敏感性规则与未知两端界沿用；仅加入已批准提取/范围修正。',
    }
