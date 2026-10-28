"""阶段二关系协议：保留原始记录，按明确范围和已登记证据逐命题映射。

本模块不修改第一版标签。非命题和重复记录留在 claims，只有 event_eligible
为真的记录进入沿用的回答级事件。析取始终是一条命题，不拆作多个肯定。
"""
import copy
import json
import re

try:
    from . import relations as legacy
except ImportError:
    import relations as legacy

RELATIONS = legacy.RELATIONS
TARGETS = legacy.TARGETS
BASES = legacy.BASES
FLAGS = legacy.FLAGS
SUPPORTED = legacy.SUPPORTED
normalize = legacy.normalize
whitespace = legacy.whitespace
SCOPE_KINDS = {
    'WORK', 'EDITION', 'ORIGINAL_PUBLICATION', 'ADAPTATION', 'COUNTRY',
    'CALCULATION', 'OTHER_SUBJECT', 'UNSPECIFIED',
}
CREDIT_ROLES = {'TRANSLATOR', 'EDITOR', 'INTRODUCTION_OR_PREFACE_AUTHOR', 'ILLUSTRATOR'}
ANCILLARY_ROLES = CREDIT_ROLES - {'TRANSLATOR'}
PROFESSIONAL_ROLES = CREDIT_ROLES | {'AUTHOR', 'DIRECTOR_OF_ADAPTATION', 'ACTOR_IN_ADAPTATION'}
VERIFICATIONS = {'NONE', 'INTERNAL_RECHECK', 'CLAIMS_EXTERNAL_ACCESS',
                 'CITES_RECORD_CONTENT', 'STATUS_VERIFIED_NO_BASIS'}


def branches(claim):
    """数组只表示析取；合取须由提取器给出独立记录。"""
    value = claim.get('relation')
    if isinstance(value, str):
        return [value]
    return value if isinstance(value, list) and all(isinstance(r, str) for r in value) else []


def scope_key(claim, item):
    """区分作品、指定版、原始出版及改编，不用本版材料覆盖其他对象。"""
    text = normalize(claim.get('scope_text')) if isinstance(claim.get('scope_text'), str) else ''
    kind = claim.get('scope_kind', 'UNSPECIFIED')
    structure = item.get('structure')
    if structure == 'G1':
        work = str(item.get('work_id') or item.get('item_id') or normalize(item.get('title')))
        if kind == 'ORIGINAL_PUBLICATION':
            return 'original-publication:' + work + (':' + text if text else '')
        if kind == 'ADAPTATION':
            return 'adaptation:' + work + (':' + text if text else '')
        if kind == 'OTHER_SUBJECT':
            return 'other-subject:' + text
        ids = re.findall(r'(?:ebook|e-book|gutenberg(?:\s+ebook)?)\s*(?:no\.?|number|#)?\s*(\d+)', text)
        if ids:
            return 'ebook:' + ids[-1]
        if kind == 'WORK':
            return 'work:' + work
        if claim.get('target') == 'THIS_EDITION_OR_VERSION':
            return 'ebook:' + str(item['ebook'])
        if kind == 'EDITION' and text:
            return 'edition:' + text
        if claim.get('target') in ('VERSION_UNSPECIFIED', 'NOT_APPLICABLE'):
            return 'work:' + work if kind == 'UNSPECIFIED' and not text else text or None
        return text or None
    return legacy.scope_key(claim, item)


def effective_target(claim, item):
    key = claim.get('scope_key')
    if item.get('structure') == 'G1' and (key or '').startswith('ebook:'):
        return ('THIS_EDITION_OR_VERSION' if key == 'ebook:' + str(item['ebook'])
                else 'ANOTHER_EDITION_OR_VERSION')
    return claim.get('target')


def _identity(claim, *, polarity=True, basis=True):
    # OTHER 的细分不被其他字段相同的命题吞掉。
    key = (tuple(sorted(branches(claim))), normalize(claim.get('relation_detail')),
           claim.get('effective_target', claim.get('target')), claim.get('scope_key'),
           bool(claim.get('broad_denial')))
    if polarity:
        key += (claim.get('polarity'),)
    if basis:
        key += (claim.get('basis'),)
    return key


def _not_claim(claim, reason):
    claim['claim_status'] = 'NOT_A_CLAIM'
    claim.setdefault('not_a_claim_reason', reason)
    claim['event_eligible'] = False


def _deduplicate_and_flag(claims):
    """同一规则也用于总括否认组成部分与独立原子命题的交叉检查。"""
    selected = {}
    for claim in claims:
        if not claim.get('event_eligible', True) or 'CLAIM_SCHEMA_INVALID' in claim.get('flags', []):
            continue
        key = _identity(claim)
        previous = selected.get(key)
        if previous is None:
            selected[key] = claim
            continue
        rank = lambda c: (c.get('hedged', True), bool(FLAGS & set(c.get('flags', []))))
        if rank(claim) < rank(previous):
            _not_claim(previous, '同义重复')
            previous['duplicate_of'] = claim.get('record_index')
            selected[key] = claim
        else:
            _not_claim(claim, '同义重复')
            claim['duplicate_of'] = previous.get('record_index')
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


def parse(raw, response, item):
    """引文仍只规范化空白，仍限生成后缀内连续且不超过三十词。"""
    text = raw.strip() if isinstance(raw, str) else ''
    match = re.fullmatch(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S)
    if match:
        text = match.group(1)
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return dict(parse_status='UNPARSEABLE', claims=[])
    if (not isinstance(value, dict) or not isinstance(value.get('claims'), list)
            or value.get('mention') not in ('PRESENT', 'ABSENT')
            or value.get('parse_status') != 'OK'):
        return dict(parse_status='UNPARSEABLE', claims=[])
    claims = []
    for index, rawclaim in enumerate(value['claims']):
        claim = copy.deepcopy(rawclaim) if isinstance(rawclaim, dict) else {}
        claim['record_index'] = index
        claim.setdefault('claim_status', 'CLAIM')
        claim.setdefault('scope_kind', 'UNSPECIFIED')
        claim.setdefault('relation_detail', None)
        claim.setdefault('broad_denial', False)
        rs = branches(claim)
        valid_relation = (bool(rs) and all(isinstance(r, str) and r in RELATIONS for r in rs)
                          and len(set(rs)) == len(rs))
        valid = (valid_relation and claim.get('polarity') in ('AFFIRM', 'DENY')
                 and isinstance(claim.get('target'), str) and claim.get('target') in TARGETS
                 and (claim.get('basis') is None or isinstance(claim.get('basis'), str))
                 and claim.get('basis') in BASES
                 and claim.get('exclusivity') in ('SOLE', 'CO_WITH_NAMED_OTHER', 'UNSPECIFIED', None)
                 and isinstance(claim.get('hedged'), bool) and isinstance(claim.get('quote'), str)
                 and (claim.get('scope_text') is None or isinstance(claim.get('scope_text'), str))
                 and isinstance(claim.get('scope_kind'), str) and claim.get('scope_kind') in SCOPE_KINDS
                 and claim.get('claim_status') in ('CLAIM', 'NOT_A_CLAIM')
                 and isinstance(claim.get('broad_denial'), bool)
                 and (claim['relation_detail'] is None or isinstance(claim['relation_detail'], str)))
        if 'OTHER' in rs and (not isinstance(claim.get('relation_detail'), str)
                              or not normalize(claim['relation_detail'])):
            valid = False
        if claim.get('broad_denial') and (claim.get('polarity') != 'DENY' or rs != ['OTHER']):
            valid = False
        flags = [] if valid else ['CLAIM_SCHEMA_INVALID']
        quote = whitespace(claim.get('quote')) if isinstance(claim.get('quote'), str) else ''
        if not quote or quote not in whitespace(response) or len(quote.split()) > 30:
            flags.append('QUOTE_MISSING')
        claim['scope_key'] = scope_key(claim, item) if valid else None
        claim['effective_target'] = effective_target(claim, item) if valid else None
        if claim.get('target') == 'VERSION_UNSPECIFIED' and claim['scope_key'] is None:
            flags.append('SCOPE_UNSPECIFIED')
        if (item.get('structure') == 'G2c'
                and any(r in ('DIRECTOR_OF_ADAPTATION', 'ACTOR_IN_ADAPTATION') for r in rs)
                and claim.get('target') == 'THIS_EDITION_OR_VERSION'
                and not (claim['scope_key'] or '').startswith('film:')):
            claim['target'] = 'VERSION_UNSPECIFIED'
        claim['flags'] = flags
        claim['event_eligible'] = claim.get('claim_status') != 'NOT_A_CLAIM'
        if claim.get('verdict') == 'NOT_A_CLAIM':
            _not_claim(claim, '人工保留的非命题记录')
        elif claim.get('scope_kind') == 'OTHER_SUBJECT':
            _not_claim(claim, '不属于题中对象')
        elif claim.get('reported_attribution') is True:
            _not_claim(claim, '仅转述他人归因')
        claims.append(claim)

    _deduplicate_and_flag(claims)
    return dict(value, claims=claims)


def _has_source(record):
    return isinstance(record, dict) and bool(record.get('source') or record.get('url'))


def _source_covers(source, claim, item, *, complete=False):
    if not _has_source(source) or (complete and source.get('complete') is not True):
        return False
    keys = source.get('scope_keys')
    if keys is not None:
        return isinstance(keys, list) and claim.get('scope_key') in keys
    # 第一版已登记的无结构化范围键的否定来源仅用于本电子书。
    return bool(source.get('scope')) and claim.get('scope_key') == 'ebook:' + str(item['ebook'])


def _complete_ancillary_role(person, relation, claim):
    """第50项的完整性不可由全文零出现或译者名单完整代替。"""
    record = person.get('credited_roles_complete', {}).get(relation, {})
    return (isinstance(record, dict) and record.get('complete') is True
            and record.get('scope_key') == claim.get('scope_key')
            and bool(record.get('catalog_source')) and bool(record.get('catalog_location'))
            and record.get('catalog_role_absent_or_other') is True
            and bool(record.get('front_matter_source'))
            and bool(record.get('front_matter_locations'))
            and record.get('person_role_absent') is True)


def _constructed_and_verified_absent(person):
    """缺任何权威核查、查到同名或无构造记录，均不启用存在性反证。"""
    record = person.get('person_existence_check')
    if person.get('type') != 'F_w' or not person.get('construction_source') or not isinstance(record, dict):
        return False
    # 与协调侧本轮登记兼容；只承认已完成的精确身份核查，不声称数据库穷尽。
    domains = record.get('domains', [])
    if (record.get('status') == 'ZERO_HITS' and type(record.get('exact_identity_hits')) is int
            and record['exact_identity_hits'] == 0 and record.get('method')
            and record.get('query') and record.get('scope') and isinstance(domains, list)):
        expected_domains = ('viaf.org', 'worldcat.org', 'wikipedia.org', 'gutenberg.org')
        names = [normalize(d).removeprefix('https://').removeprefix('http://').split('/')[0]
                 for d in domains if isinstance(d, str)]
        return all(any(name == domain or name.endswith('.' + domain) for name in names)
                   for domain in expected_domains)
    checks = record.get('checks', [])
    if record.get('complete') is not True or record.get('zero_hits') is not True or not record.get('scope'):
        return False
    expected = {'viaf', 'worldcat', 'wikipedia', 'gutenberg_author_index'}
    found = set()
    for check in checks:
        if (not isinstance(check, dict) or not _has_source(check) or not check.get('query')
                or type(check.get('hits')) is not int or check['hits'] != 0):
            return False
        found.add(normalize(check.get('authority')))
    return expected <= found


def _this_translator_positive(item, person):
    """正面署名与名单完整性不同；目录实名行本身即是本人正面记录。"""
    if (person.get('type') != 'T'
            or 'TRANSLATOR_OF_THIS_EDITION' not in person.get('true_roles', [])
            or not item.get('sources', {}).get('translator')):
        return False
    catalog = person.get('catalog_check', {})
    if (catalog.get('source_catalog') and str(catalog.get('ebook')) == str(item['ebook'])):
        name_tokens = set(re.findall(r'\w+', normalize(person.get('name'))))
        for row in catalog.get('catalog_rows', []):
            if (isinstance(row, list) and len(row) >= 2 and normalize(row[0]) == 'translator'
                    and isinstance(row[1], str)):
                row_tokens = set(re.findall(r'\w+', normalize(row[1])))
                if name_tokens and name_tokens <= row_tokens:
                    return True
    return item.get('q6_title_page_check', {}).get('verified') is True


def _registered_positive(claim, item, person, relation):
    """可选登记接口只认明确来源、范围和角色，不推断完整性。"""
    for record in person.get('positive_relations', []):
        if (not isinstance(record, dict) or record.get('relation') != relation
                or record.get('verified') is not True or not _has_source(record)):
            continue
        keys = record.get('scope_keys', [])
        bases = record.get('bases', [])
        if relation == 'TRANSLATOR' and 'CREDITED' in bases:
            bases = ['CREDITED', 'PARTICIPATED', 'UNSPECIFIED']
        if claim.get('basis') not in bases:
            continue
        if claim.get('scope_key') in keys:
            return 'SUPPORTED'
        if relation == 'TRANSLATOR' and (claim.get('scope_key') or '').startswith('work:'):
            if record.get('work_id') == (item.get('work_id') or item.get('item_id')):
                return 'SUPPORTED_COARSE'
    return None


def _positive_single(claim, item, person, relation, *, lenient=False):
    if 'CLAIM_SCHEMA_INVALID' in claim.get('flags', []):
        return 'INSUFFICIENT'
    if item.get('structure') != 'G1':
        # 本阶段不为其他结构补证；保留提取与范围，映射范围外明确记未知。
        return 'INSUFFICIENT'
    key = claim.get('scope_key') or ''
    target = effective_target(claim, item)
    basis = claim.get('basis')
    kind = person.get('type')
    if lenient and basis == 'UNSPECIFIED' and kind in ('X', 'd_T', 'F_w', 'N'):
        basis = 'CREDITED'
    scoped = dict(claim, basis=basis)
    if relation == 'OTHER':
        return 'INSUFFICIENT'
    # 正面与反面登记都不得跨越小说、原始出版与改编对象。
    ordinary_scope = key.startswith(('ebook:', 'work:', 'edition:')) or not key
    registered = _registered_positive(scoped, item, person, relation)
    if registered:
        return registered
    sources = item.get('sources', {})
    if relation == item.get('target_relation') == 'AUTHOR' and sources.get('author'):
        # 原著作者是作品属性，原始出版仍属同一作品；改编作者不继承。
        if not ordinary_scope and not key.startswith('original-publication:'):
            return 'INSUFFICIENT'
        if target == 'ANOTHER_EDITION_OR_VERSION' and not key.startswith('original-publication:'):
            return 'INSUFFICIENT'
        return 'SUPPORTED' if kind == 'GOLD' else 'REFUTED'
    if not ordinary_scope:
        return 'INSUFFICIENT'
    if relation == 'TRANSLATOR':
        # 只使用被署名者本人的已核实记录，三种读法均被正面书目支持。
        this_positive = _this_translator_positive(item, person)
        other_positive = (kind == 'd_T' and 'TRANSLATOR_OF_ANOTHER_EDITION' in person.get('true_roles', [])
                          and bool(person.get('other_translation_source')))
        if this_positive and key == 'ebook:' + str(item['ebook']):
            return 'SUPPORTED'
        if (this_positive or other_positive) and key.startswith('work:'):
            return 'SUPPORTED_COARSE'
        if other_positive and target == 'ANOTHER_EDITION_OR_VERSION':
            if not key or key in person.get('other_edition_keys', []):
                return 'SUPPORTED'
    if relation == 'CHARACTER' and kind == 'F_w' and person.get('body_absence_verified') is True:
        if key == 'ebook:' + str(item['ebook']):
            return 'REFUTED'
    if relation in PROFESSIONAL_ROLES and _constructed_and_verified_absent(person):
        return 'REFUTED'
    if relation in CREDIT_ROLES:
        negative = person.get('negative_relations', {}).get(relation, {})
        credit = _source_covers(negative.get('credit_negative_source'), scoped, item, complete=True)
        if relation in ANCILLARY_ROLES:
            credit = _complete_ancillary_role(person, relation, scoped)
        participation = _source_covers(negative.get('participation_negative_source'), scoped, item)
        if ((basis == 'CREDITED' and credit) or (basis == 'PARTICIPATED' and participation)
                or (basis == 'UNSPECIFIED' and credit and participation)):
            return 'REFUTED'
    return 'INSUFFICIENT'


def positive_verdict(claim, item, person, *, lenient=False):
    """先判断正命题；析取任一支成立即成立，全部反证才反证。"""
    verdicts = [_positive_single(claim, item, person, relation, lenient=lenient)
                for relation in branches(claim)]
    if 'SUPPORTED' in verdicts:
        return 'SUPPORTED'
    if 'SUPPORTED_COARSE' in verdicts:
        return 'SUPPORTED_COARSE'
    if verdicts and all(verdict == 'REFUTED' for verdict in verdicts):
        return 'REFUTED'
    return 'INSUFFICIENT'


def _broad_components(claim, item, person):
    """只登记文本范围内已有证据涉及的部分，剩余关联明确未知。"""
    supplied = claim.get('denial_components')
    if isinstance(supplied, list) and supplied:
        components = supplied
    elif item.get('structure') == 'G1' and claim.get('scope_kind') != 'ADAPTATION':
        roles = set()
        sources = item.get('sources', {})
        if sources.get('translator') or person.get('other_translation_source'):
            roles.add('TRANSLATOR')
        for relation in ANCILLARY_ROLES:
            if (_complete_ancillary_role(person, relation, claim)
                    or _registered_positive(claim, item, person, relation)):
                roles.add(relation)
        components = [dict(relation=r, basis=b) for r in sorted(roles)
                      for b in ('CREDITED', 'PARTICIPATED')]
        if sources.get('author'):
            components.insert(0, dict(relation='AUTHOR', basis=None))
    else:
        components = []
    if not any(isinstance(c, dict) and c.get('relation') == 'OTHER' for c in components):
        components = list(components) + [dict(relation='OTHER', relation_detail='OTHER_CONNECTION', basis=None)]
    result = []
    for component in components:
        if not isinstance(component, dict):
            component = {}
        part = {k: copy.deepcopy(v) for k, v in claim.items() if k != 'denial_components'}
        for key in ('relation', 'relation_detail', 'basis', 'target', 'scope_text', 'scope_kind'):
            if key in component:
                part[key] = copy.deepcopy(component[key])
        if part.get('relation') != 'OTHER':
            part['relation_detail'] = None
        else:
            part['relation_detail'] = component.get('relation_detail') or 'OTHER_CONNECTION'
        part.update(exclusivity=None, broad_denial=False, broad_denial_component=True,
                    parent_record_index=claim.get('record_index'), claim_status='CLAIM', event_eligible=True)
        part['scope_key'] = scope_key(part, item)
        part['effective_target'] = effective_target(part, item)
        if (not branches(part) or any(r not in RELATIONS for r in branches(part))
                or part['scope_key'] != claim.get('scope_key')):
            part['flags'] = sorted(set(part.get('flags', [])) | {'CLAIM_SCHEMA_INVALID'})
        result.append(part)
    return result


def map_claims(extraction, item, person):
    result = copy.deepcopy(extraction)

    def mapped(claim):
        eligible = claim.get('event_eligible', claim.get('claim_status') != 'NOT_A_CLAIM')
        claim['event_eligible'] = eligible and claim.get('verdict') != 'NOT_A_CLAIM'
        claim['is_target'] = item.get('target_relation') in branches(claim)
        claim['contains_target_and_side'] = claim['is_target'] and len(branches(claim)) > 1
        claim['taxonomy_unresolved'] = claim['contains_target_and_side']
        claim['confirmed'] = not bool(set(claim.get('flags', [])) & FLAGS)
        if not claim['event_eligible']:
            claim['positive_verdict'] = 'NOT_A_CLAIM'
            claim['lenient_positive_verdict'] = 'NOT_A_CLAIM'
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
            claim['denial_components'] = _broad_components(claim, item, person)
            for component in claim['denial_components']:
                mapped(component)
            claim['aggregate_via_components'] = True

    for claim in result.setdefault('claims', []):
        mapped(claim)
    atoms = []
    for claim in result['claims']:
        atoms.extend(claim.get('denial_components', []) if claim.get('aggregate_via_components') else [claim])
    _deduplicate_and_flag(atoms)
    for atom in atoms:
        atom['confirmed'] = not bool(set(atom.get('flags', [])) & FLAGS)
        if not atom.get('event_eligible', True):
            atom['positive_verdict'] = atom['lenient_positive_verdict'] = 'NOT_A_CLAIM'
    return result


def _event_view(extraction):
    result = copy.deepcopy(extraction)
    active = []

    def collect(claim):
        if (not claim.get('event_eligible', True) or claim.get('claim_status') == 'NOT_A_CLAIM'
                or claim.get('positive_verdict') == 'NOT_A_CLAIM'):
            return
        if claim.get('taxonomy_unresolved'):
            raise ValueError('混合目标与旁支的析取分类尚未裁定；记录序号：' + str(claim.get('record_index')))
        if claim.get('aggregate_via_components'):
            for component in claim.get('denial_components', []):
                collect(component)
        else:
            active.append(claim)

    for claim in result.get('claims', []):
        collect(claim)
    result['claims'] = active
    return result


def aggregate(extraction, anchor=None, *, technical_failure=False):
    """第一版事件、阈值与未知两端界原样沿用，仅排除明确非命题记录。"""
    out = legacy.aggregate(_event_view(extraction), _event_view(anchor) if anchor is not None else None,
                           technical_failure=technical_failure)
    out['n_records'] = len(extraction.get('claims', []))
    out['n_not_a_claim'] = sum(not c.get('event_eligible', True) or c.get('claim_status') == 'NOT_A_CLAIM'
                              for c in extraction.get('claims', []))
    return out
