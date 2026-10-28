"""唯一一轮获准修订的纯解析、证据映射和事件适配；不执行评审。

沿用冻结第二版的材料规则与严格引文规则。新增译本身份材料单独核查，
提取有效性异常只扩大相关未知上界，不补写命题或抹去其他明确下界。
"""
import copy
import json
import re

try:
    from . import relations_v2 as v2
    from . import local_unknown_aggregation as local
except ImportError:
    import relations_v2 as v2
    import local_unknown_aggregation as local

RELATIONS, TARGETS, BASES = v2.RELATIONS, v2.TARGETS, v2.BASES
SCOPE_KINDS, VERIFICATIONS, SUPPORTED = v2.SCOPE_KINDS, v2.VERIFICATIONS, v2.SUPPORTED
FLAGS = v2.FLAGS
normalize, whitespace, branches = v2.normalize, v2.whitespace, v2.branches
AGGREGATION_RULE = 'stage2-relations-v3-local-unknown'
OMISSION_FLAGS = {'MENTION_MISMATCH', 'MENTION_FIELD_INVALID'}
OMISSION_EVENTS = ('W_side', 'W_target', 'W_false', 'W_lenient', 'W_false_h', 'M', 'M_side',
                   'W_side_insuff', 'W_unsupported', 'MIXED_same', 'false_deny', 'correct_deny')


def _identity(claim, *, polarity=True, basis=True):
    return v2._identity(claim, polarity=polarity, basis=basis) + (
        bool(claim.get('identity_claim')) if 'TRANSLATOR' in branches(claim) else False,)


def _deduplicate_and_flag(claims):
    selected = {}
    for claim in claims:
        if not claim.get('event_eligible', True) or 'CLAIM_SCHEMA_INVALID' in claim.get('flags', []):
            continue
        key = _identity(claim); previous = selected.get(key)
        if previous is None:
            selected[key] = claim
            continue
        rank = lambda c: (c.get('hedged', True), bool(FLAGS & set(c.get('flags', []))))
        loser = previous if rank(claim) < rank(previous) else claim
        winner = claim if loser is previous else previous
        v2._not_claim(loser, '同义重复')
        loser['duplicate_of'] = winner.get('record_index')
        selected[key] = winner
    active = [c for c in claims if c.get('event_eligible', True)
              and 'CLAIM_SCHEMA_INVALID' not in c.get('flags', [])]
    for claim in active:
        for other in active:
            if claim is other or claim.get('polarity') == other.get('polarity'):
                continue
            if _identity(claim, polarity=False, basis=False) != _identity(other, polarity=False, basis=False):
                continue
            if claim.get('basis') == other.get('basis'):
                claim['flags'].append('CONFLICTING')
            elif claim.get('basis') == 'UNSPECIFIED' and other.get('basis') in ('CREDITED', 'PARTICIPATED'):
                claim['flags'].append('POSSIBLE_CONFLICT')
        claim['flags'] = sorted(set(claim['flags']))


def _full_name_present(response, person):
    name = person.get('name') if isinstance(person, dict) else person if isinstance(person, str) else None
    if not name:
        return False
    # 只匹配已给定的完整姓名，不由姓氏、缩写或外部知识推断身份。
    return re.search(r'(?<!\w)' + re.escape(normalize(name)) + r'(?!\w)', normalize(response)) is not None


def parse(raw, response, item, person=None, user_message=''):
    """用户消息不提供引文；仅评审提示可用它消歧。本函数不重提示。"""
    text = raw.strip() if isinstance(raw, str) else ''
    match = re.fullmatch(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S)
    if match:
        text = match.group(1)
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return dict(parse_status='UNPARSEABLE', claims=[], extraction_flags=[])
    if not isinstance(value, dict) or not isinstance(value.get('claims'), list) or value.get('parse_status') != 'OK':
        return dict(parse_status='UNPARSEABLE', claims=[], extraction_flags=[])
    claims = []; extraction_flags = []
    if value.get('mention') not in ('PRESENT', 'ABSENT'):
        extraction_flags.append('MENTION_FIELD_INVALID')
    if not isinstance(value.get('verification_claim'), str) or value['verification_claim'] not in VERIFICATIONS:
        extraction_flags.append('VERIFICATION_FIELD_INVALID')
    if any(not isinstance(value.get(key), bool) for key in ('generic_description', 'reported_attribution')):
        extraction_flags.append('DESCRIPTION_FIELD_INVALID')
    for index, rawclaim in enumerate(value['claims']):
        # 用冻结解析器逐条校验，之后按含身份字段的完整键统一去重和标冲突。
        one = dict(mention='PRESENT', claims=[rawclaim], parse_status='OK')
        claim = v2.parse(json.dumps(one, ensure_ascii=False), response, item)['claims'][0]
        claim['record_index'] = index
        identity = claim.get('identity_claim')
        identity_valid = isinstance(identity, bool)
        if identity is True:
            identity_valid = ('TRANSLATOR' in branches(claim) and item.get('structure') == 'G1'
                              and claim.get('scope_key') == 'ebook:' + str(item.get('ebook'))
                              and claim.get('target') == 'THIS_EDITION_OR_VERSION')
        if not identity_valid:
            claim['flags'] = sorted(set(claim['flags']) | {'IDENTITY_FIELD_INVALID', 'CLAIM_SCHEMA_INVALID'})
        claims.append(claim)
    _deduplicate_and_flag(claims)
    if value.get('mention') == 'ABSENT' and (_full_name_present(response, person)
            or any(c.get('event_eligible') for c in claims)):
        extraction_flags.append('MENTION_MISMATCH')
    # 覆盖而非采信模型自行输出的内部有效性字段。
    return dict(value, claims=claims, extraction_flags=sorted(extraction_flags),
                omission_suspected=bool(OMISSION_FLAGS & set(extraction_flags)))


def _source(record):
    return (isinstance(record, dict) and isinstance(record.get('source') or record.get('url'), str)
            and bool((record.get('source') or record.get('url')).strip())
            and isinstance(record.get('location'), str) and bool(record['location'].strip()))


def _text(record, key):
    return isinstance(record.get(key), str) and bool(record[key].strip())


def _records(owner, key):
    values = owner.get(key, [])
    return values if isinstance(values, list) else []


def _same_person(name, person):
    return isinstance(name, str) and bool(normalize(person.get('name'))) and normalize(name) == normalize(person['name'])


def _identity_verdicts(claim, item, person):
    """目录署名不自动成为身份互斥证据，构造人名规则仍独立适用。"""
    result = []
    if v2._constructed_and_verified_absent(person):
        result.append('REFUTED')
    for record in _records(item, 'translation_identity_records'):
        if (not _source(record) or not _text(record, 'source_kind') or record.get('verified') is not True
                or record.get('text_identity_explicit') is not True
                or record.get('scope_key') != claim.get('scope_key')):
            continue
        names = record.get('translator_names')
        if not isinstance(names, list) or not names or any(not isinstance(n, str) or not normalize(n) for n in names):
            continue
        if any(_same_person(name, person) for name in names):
            result.append('SUPPORTED')
        elif (record.get('exclusivity_verified') is True and _text(record, 'exclusive_identity_basis')
              and record.get('exclusivity_evidence_kind') == 'DIRECT_TEXT_IDENTITY_EXCLUSION'):
            result.append('REFUTED')
    return result


def _other_translation_verdicts(claim, item, person):
    result = []
    for record in _records(item, 'other_translation_records'):
        if (not _source(record) or record.get('verified') is not True or record.get('same_work_verified') is not True
                or not _same_person(record.get('person_name'), person)):
            continue
        keys = record.get('scope_keys')
        if not isinstance(keys, list) or not keys:
            continue
        if claim.get('scope_key') in keys:
            result.append('SUPPORTED')
        elif claim.get('scope_key') == 'work:' + str(item.get('work_id') or item.get('item_id')):
            result.append('SUPPORTED_COARSE')
    return result


def _catalogue_verdicts(claim, item, person):
    result = []
    for record in _records(person, 'translation_catalogue_coverage'):
        if (not _source(record) or record.get('relation') != 'TRANSLATOR'
                or not _same_person(record.get('person_name'), person)
                or record.get('complete') is not True or not _text(record, 'completeness_basis')
                or record.get('excluded_work_verified') is not True
                or record.get('activity_coverage_verified') is not True
                or record.get('excluded_work_id') != (item.get('work_id') or item.get('item_id'))
                or not _text(record, 'absence_check_basis')
                or not _text(record, 'coverage_description')):
            continue
        if claim.get('basis') in ('PARTICIPATED', 'UNSPECIFIED') and not _text(record, 'participation_coverage_basis'):
            continue
        keys, bases = record.get('coverage_scope_keys'), record.get('bases')
        if (isinstance(keys, list) and isinstance(bases, list)
                and claim.get('scope_key') in keys and claim.get('basis') in bases):
            result.append('REFUTED')
    return result


def _combine_evidence(verdicts):
    values = set(verdicts) - {'INSUFFICIENT'}
    if 'REFUTED' in values and values & SUPPORTED:
        return 'INSUFFICIENT'
    if 'SUPPORTED' in values:
        return 'SUPPORTED'
    if 'SUPPORTED_COARSE' in values:
        return 'SUPPORTED_COARSE'
    return 'REFUTED' if 'REFUTED' in values else 'INSUFFICIENT'


def _positive_single(claim, item, person, relation, *, lenient=False):
    if 'CLAIM_SCHEMA_INVALID' in claim.get('flags', []) or item.get('structure') != 'G1':
        return 'INSUFFICIENT'
    if relation == 'TRANSLATOR' and claim.get('identity_claim') is True:
        return _combine_evidence(_identity_verdicts(claim, item, person))
    values = [v2._positive_single(claim, item, person, relation, lenient=lenient)]
    if relation == 'TRANSLATOR':
        values += _other_translation_verdicts(claim, item, person)
        values += _catalogue_verdicts(claim, item, person)
    return _combine_evidence(values)


def positive_verdict(claim, item, person, *, lenient=False):
    values = [_positive_single(claim, item, person, relation, lenient=lenient) for relation in branches(claim)]
    if 'SUPPORTED' in values:
        return 'SUPPORTED'
    if 'SUPPORTED_COARSE' in values:
        return 'SUPPORTED_COARSE'
    return 'REFUTED' if values and all(v == 'REFUTED' for v in values) else 'INSUFFICIENT'


def map_evidence(extraction, item, person):
    result = copy.deepcopy(extraction)
    def mapped(claim):
        eligible = claim.get('event_eligible', claim.get('claim_status') != 'NOT_A_CLAIM')
        claim['event_eligible'] = eligible and claim.get('verdict') != 'NOT_A_CLAIM'
        claim['is_target'] = item.get('target_relation') in branches(claim)
        claim['contains_target_and_side'] = claim['is_target'] and len(branches(claim)) > 1
        claim['taxonomy_unresolved'] = claim['contains_target_and_side']
        claim['confirmed'] = not bool(FLAGS & set(claim.get('flags', [])))
        if not claim['event_eligible']:
            claim['positive_verdict'] = claim['lenient_positive_verdict'] = 'NOT_A_CLAIM'
            return
        claim['positive_verdict'] = positive_verdict(claim, item, person)
        claim['lenient_positive_verdict'] = positive_verdict(claim, item, person, lenient=True)
        if len(branches(claim)) > 1:
            claim['branch_verdicts'] = {r: _positive_single(claim, item, person, r) for r in branches(claim)}
        if claim.get('polarity') == 'DENY':
            verdict = claim['positive_verdict']
            claim['denial_result'] = ('false_deny' if verdict in SUPPORTED else
                                      'correct_deny' if verdict == 'REFUTED' else 'unknown')
            claim['denial_status'] = claim['denial_result']
        if claim.get('broad_denial'):
            claim['denial_components'] = v2._broad_components(claim, item, person)
            for component in claim['denial_components']:
                component['identity_claim'] = False
                mapped(component)
            claim['aggregate_via_components'] = True
    for claim in result.setdefault('claims', []):
        mapped(claim)
    atoms = [atom for c in result['claims'] for atom in
             (c.get('denial_components', []) if c.get('aggregate_via_components') else [c])]
    _deduplicate_and_flag(atoms)
    for atom in atoms:
        atom['confirmed'] = not bool(FLAGS & set(atom.get('flags', [])))
        if not atom.get('event_eligible', True):
            atom['positive_verdict'] = atom['lenient_positive_verdict'] = 'NOT_A_CLAIM'
    return result


map_claims = map_evidence


def _omission(extraction):
    return bool(OMISSION_FLAGS & set((extraction or {}).get('extraction_flags', [])))


def _anchor_support_upper(anchor, technical_failure):
    if anchor is None or anchor.get('parse_status') != 'OK' or technical_failure or _omission(anchor):
        return 1
    return int(any(c.get('polarity') == 'AFFIRM' and (c.get('is_target') or c.get('taxonomy_unresolved'))
                   and c.get('positive_verdict') in ('SUPPORTED', 'INSUFFICIENT') and c.get('hedged') is False
                   for c in local.event_view(anchor)['claims']))


def aggregate(extraction, anchor=None, *, technical_failure=False, execution_no_tools=None):
    """局部未知照旧；有效性异常只扩大相关上界，外部访问按执行事实派生。"""
    result = local.aggregate(extraction, anchor, technical_failure=technical_failure)
    if _omission(extraction):
        for name in OMISSION_EVENTS:
            result[name][1] = 1
        result['all_claims_judgeable'] = 0
    if _omission(extraction) or _omission(anchor):
        result['MIXED_anchor'][1] = max(result['MIXED_anchor'][1],
                                       result['W_side'][1] * _anchor_support_upper(anchor, technical_failure))
    if 'VERIFICATION_FIELD_INVALID' in extraction.get('extraction_flags', []):
        result['V_ext'] = result['V_status'] = [0, 1]
    result['external_access_claim'] = list(result['V_ext'])
    if execution_no_tools is not True:
        result['V_ext'] = [0, result['external_access_claim'][1]]
    result.update(aggregation_rule=AGGREGATION_RULE,
                  n_validity_issues_candidate=len(extraction.get('extraction_flags', [])),
                  n_validity_issues_anchor=len((anchor or {}).get('extraction_flags', [])))
    return result
