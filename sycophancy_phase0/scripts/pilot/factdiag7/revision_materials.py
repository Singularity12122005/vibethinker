"""第57、58项已批准修订的材料构造：只增加覆盖字段，不改旧材料。

本模块不访问网页、不读取回答、不加载模型，也不自行把检索未命中变为反证。
已有目录、前页与另一译本记录来自第五批冻结材料；新增直接证据须显式提供。
"""
from copy import deepcopy
import re

from .relations import normalize


IDENTITY_FIELD = 'translation_identity_records'
OTHER_FIELD = 'other_translation_records'
CATALOGUE_FIELD = 'translation_catalogue_coverage'
BASES = {'CREDITED', 'PARTICIPATED', 'UNSPECIFIED'}
RS_EVIDENCE = {'M-wrong', 'M-right', 'E-inapp', 'E-false'}


def _add(obj, key, value):
    if key in obj and obj[key] != value:
        raise ValueError('新增字段已存在且内容不同，不覆盖：' + key)
    obj[key] = value


def _nonempty(record, fields, label):
    if any(not isinstance(record.get(k), str) or not record[k].strip() for k in fields):
        raise ValueError(label + '缺少明确来源、位置或覆盖说明')


def validate_identity(record, item):
    _nonempty(record, ('source', 'location', 'source_kind'), '译本身份')
    if record.get('scope_key') != 'ebook:' + str(item['ebook']):
        raise ValueError('本电子书译本身份记录不能跨版本')
    names = record.get('translator_names')
    if not isinstance(names, list) or not names or len(names) != len(set(names)) or any(not isinstance(n, str) or not n.strip() for n in names):
        raise ValueError('译本身份须列明确完整姓名，不能只留互异标记')
    for key in ('verified', 'text_identity_explicit', 'exclusivity_verified'):
        if type(record.get(key)) is not bool:
            raise ValueError('译本身份核实状态必须显式登记：' + key)
    if record['exclusivity_verified']:
        if not record['verified'] or not record['text_identity_explicit']:
            raise ValueError('尚无直接译本身份，不能宣布互斥')
        _nonempty(record, ('exclusive_identity_basis',), '互斥归属反证')
        # 检索缺席或单纯姓名不同不能充当互斥归属的证据种类。
        if record.get('exclusivity_evidence_kind') != 'DIRECT_TEXT_IDENTITY_EXCLUSION':
            raise ValueError('互斥反证须单独登记直接文本身份排除证据')
    return record


def validate_catalogue(record, item, person):
    _nonempty(record, ('source', 'location', 'coverage_description'), '人物译作目录')
    if record.get('person_name') != person['name'] or record.get('relation') != 'TRANSLATOR':
        raise ValueError('人物目录必须绑定同一人物及翻译活动')
    bases = record.get('bases')
    if not isinstance(bases, list) or not bases or set(bases) - BASES or len(bases) != len(set(bases)):
        raise ValueError('人物目录须明确实际覆盖的署名/参与读法')
    keys = record.get('coverage_scope_keys')
    if not isinstance(keys, list) or any(not isinstance(k, str) or not k for k in keys):
        raise ValueError('人物目录须显式列覆盖范围键；未知可为空，不得猜测')
    for key in ('complete', 'activity_coverage_verified', 'excluded_work_verified'):
        if type(record.get(key)) is not bool:
            raise ValueError('人物目录核实状态缺失：' + key)
    if record['complete']:
        _nonempty(record, ('completeness_basis',), '目录完整性')
        if not keys or not record['activity_coverage_verified']:
            raise ValueError('完整目录仍须有活动与实际范围核实')
    if record['excluded_work_verified']:
        if not record['complete'] or record.get('excluded_work_id') != item['work_id']:
            raise ValueError('不能用不完整目录缺席或他作品缺席作反证')
        _nonempty(record, ('absence_check_basis',), '目录缺席核实')
    if record['complete'] and set(bases) & {'PARTICIPATED', 'UNSPECIFIED'}:
        _nonempty(record, ('participation_coverage_basis',), '参与覆盖')
    return record


def _current_identity(item, material):
    gate = material.get('evidence_gate', {})
    translator = material['F']['gold']
    catalog = gate.get('catalog_contributors_checked') is True and translator in gate.get('catalog_translator_names', [])
    page = gate.get('title_page_credits_checked') is True and translator in gate.get('title_page_translator_names', [])
    if not catalog and not page:
        raise ValueError('缺少既有核实的本人译者正面来源：' + item['work_id'])
    origin = 'catalog' if catalog else 'title_page'
    record = dict(scope_key='ebook:' + str(item['ebook']), translator_names=[translator],
        source=gate.get(origin + '_source'), location=gate.get(origin + '_location'),
        source_kind='PROJECT_GUTENBERG_CATALOG' if catalog else 'EBOOK_FRONT_MATTER',
        verified=True, text_identity_explicit=True,
        identity_basis='指定电子书自身的译者书目署名；支持本人完成该版翻译，不自动排除他人参与、借用或共同贡献。',
        exclusivity_verified=False, exclusive_identity_basis=None, exclusivity_evidence_kind=None,
        additional_verified_sources=[],
        positive_credit_verified=True, front_matter_verified=page,
        source_registration='factdiag5_materials.json / evidence_gate')
    if catalog and page:
        record['additional_verified_sources'].append(dict(source=gate.get('title_page_source'),
            location=gate.get('title_page_location'), source_kind='EBOOK_FRONT_MATTER'))
    return validate_identity(record, item)


def _other_translation(item, material):
    version = material.get('version_check')
    if not isinstance(version, dict) or version.get('other_translator') != material['d_T']:
        raise ValueError('另一译本缺少冻结版本核验记录或人物不一致：' + item['work_id'])
    description = version.get('E_prime')
    if not description or description != material.get('E_prime'):
        raise ValueError('另一译本的精确版本标识不一致')
    number = re.search(r'\beBook\s+(\d+)\b', description, flags=re.I)
    keys = ['ebook:' + number[1]] if number else ['edition:' + normalize(description)]
    verified = version.get('other_translator_verified') is True
    record = dict(person_name=material['d_T'], version_description=description,
        scope_keys=keys, scope_aliases=[description], source=version.get('source'),
        location=version.get('location'), verified=verified, same_work_verified=verified,
        finding=version.get('finding'),
        source_registration='factdiag5_materials.json / version_check；沿用factdiag5/version_materials.py登记',
        additional_sources=[version[k] for k in ('additional_source', 'original_source') if version.get(k)],
        text_identity_exclusion_of_current_ebook=False,
        limitation='本记录不证明与指定电子书文本互斥，不自动补足参与反证；未核实署名保持资料不足。')
    _nonempty(record, ('source', 'location'), '另一译本')
    return record


def _existing_catalogue(item, person):
    old = person.get('source_check', {})
    sources = old.get('sources', [])
    if not sources:
        raise ValueError('X缺少既有实际核查来源：' + item['work_id'])
    # 来源列表含零散正面书目及指定作品检索；它们不是经过完整性核验的全译作目录。
    entry = dict(title=old.get('work'), author=old.get('other_author'),
        activity_year=old.get('activity_year'), language=old.get('language'),
        verification_status='既有冻结source_check中的译作登记；本次未重新逐页核验，未声称列表完整',
        source_registration='原材料people[X].source_check')
    record = dict(person_name=person['name'], relation='TRANSLATOR', bases=['CREDITED'],
        source=sources[0], additional_sources=sources[1:],
        location='既有source_check登记的单项译作书目及指定作品检索；各原网址保留',
        entries=[entry], search_queries=deepcopy(old.get('queries', [])),
        coverage_description='仅所列来源的已登记单项译作与检索结果；未覆盖该人物全部译作、所有版本或所有参与活动。',
        coverage_scope_keys=[], complete=False, completeness_basis=None,
        activity_coverage_verified=False, excluded_work_verified=False,
        excluded_work_id=None, absence_check_basis=None, participation_coverage_basis=None,
        previous_finding=old.get('finding'), previous_negative_limit=old.get('negative_claim'),
        source_registration='原factdiag7_stage2_materials.json / people[X].source_check')
    return validate_catalogue(record, item, person)


def coverage_summary(materials):
    rows = []
    for item in materials['items']:
        identities = item.get(IDENTITY_FIELD, [])
        other = item.get(OTHER_FIELD, [])
        people = [p for p in item['people'] if p['type'] == 'X']
        catalogues = [r for p in people for r in p.get(CATALOGUE_FIELD, [])]
        rows.append(dict(work_id=item['work_id'], ebook=str(item['ebook']),
            direct_identity_sources=sum(r['verified'] and r['text_identity_explicit'] for r in identities),
            front_matter_verified=any(r.get('front_matter_verified') for r in identities),
            identity_exclusions=sum(r['exclusivity_verified'] for r in identities),
            other_translations_verified=sum(r['verified'] and r['same_work_verified'] for r in other),
            other_translations_unverified=sum(not r['verified'] for r in other),
            X_people=len(people), X_catalogue_records=len(catalogues),
            X_complete_catalogues=sum(r['complete'] for r in catalogues),
            X_absence_refutations=sum(r['complete'] and r['activity_coverage_verified'] and r['excluded_work_verified'] for r in catalogues)))
    totals = {key: sum(r[key] for r in rows) for key in rows[0] if key not in ('work_id', 'ebook')} if rows else {}
    return dict(approved_rules=[57, 58], works=len(rows), by_work=rows, totals=totals,
        limits=['旧字段全部保留；新增覆盖字段不回改旧标签。',
                '本人译者署名支持本人，不从姓名不同或目录缺席自动推出身份互斥、未参与或未借用。',
                '另一译本仅对登记范围有效；未核实版本不成为反证。',
                '未取得完整人物译作目录时，完整性与缺席反证均保持false。'])


def build_revision_materials(original, fifth, *, identity_supplements=None, catalogue_supplements=None):
    """返回兼容旧item bank的独立材料；默认只使用已登记来源，不写文件。

    两种补充输入分别为work_id→记录列表、(work_id,person_name)→记录列表。
    明确核实的补充证据可启用新增判定；没有补充时不会创造互斥或完整目录。
    """
    output = deepcopy(original)
    bank = {m['work_id']: m for m in fifth['materials']}
    if len(bank) != len(fifth['materials']) or len({i['work_id'] for i in output['items']}) != len(output['items']):
        raise ValueError('材料作品重复')
    identity_supplements = identity_supplements or {}
    catalogue_supplements = catalogue_supplements or {}
    used_catalogues = set()
    for item in output['items']:
        if item.get('structure') != 'G1' or item['work_id'] not in bank:
            raise ValueError('本次修订仅登记已有G1文学作品')
        m = bank[item['work_id']]
        if str(m['ebook']) != str(item['ebook']) or m['title'] != item['title']:
            raise ValueError('第五批与阶段二指定作品/电子书不一致')
        translator = next(p for p in item['people'] if p['type'] == 'T')
        if translator['name'] != m['F']['gold']:
            raise ValueError('指定电子书译者身份不一致')
        identities = [_current_identity(item, m)]
        for record in identity_supplements.get(item['work_id'], []):
            identities.append(validate_identity(deepcopy(record), item))
        _add(item, IDENTITY_FIELD, identities)
        _add(item, OTHER_FIELD, [_other_translation(item, m)])
        for person in item['people']:
            if person['type'] != 'X':
                continue
            key = item['work_id'], person['name']
            catalogue = [_existing_catalogue(item, person)]
            for record in catalogue_supplements.get(key, []):
                catalogue.append(validate_catalogue(deepcopy(record), item, person))
            used_catalogues.add(key)
            _add(person, CATALOGUE_FIELD, catalogue)
    if set(identity_supplements) - {i['work_id'] for i in output['items']} or set(catalogue_supplements) - used_catalogues:
        raise ValueError('补充证据含本轮范围外作品或人物')
    _add(output, 'revision_materials_coverage', coverage_summary(output))
    return output


def build_materials(old_materials, fifth_materials=None, *, identity_supplements=None, catalogue_supplements=None):
    """供修订冻结入口调用；缺第五批版本来源时明确报缺，不猜书目。"""
    if fifth_materials is None:
        raise ValueError('本次完整材料登记需传第五批冻结材料，才能保留已核实的另一译本来源与未核实状态')
    return build_revision_materials(old_materials, fifth_materials,
        identity_supplements=identity_supplements, catalogue_supplements=catalogue_supplements)


def fifth_scope_summary(fifth, rows=None):
    """只核对原1840范围与第三轮话术；有真实回答时仅在A100调用，不返回正文。"""
    planned = fifth['plan']['requests']
    bank = {r['request_id']: r for r in planned}
    if len(bank) != len(planned):
        raise ValueError('第五批计划身份重复')
    selected = [r for r in planned if r['cell'] == '5.5' or r['unit'] == 'R-S' and r['cell'] in RS_EVIDENCE]
    from collections import Counter
    expected = {'M-wrong': 480, 'M-right': 240, 'E-inapp': 480, 'E-false': 240, '5.5': 400}
    if Counter(r['cell'] for r in selected) != expected or len(selected) != 1840:
        raise ValueError('不得扩大或削减原1840关系输入范围')
    if any(r.get('t') != 3 or not r.get('user_text') for r in selected):
        raise ValueError('第三轮用户消息缺失或回合身份错误')
    checked = False
    if rows is not None:
        actual = {r['request_id']: r for r in rows}
        if len(actual) != len(rows) or set(actual) != set(bank):
            raise ValueError('完整第五批生成登记未与原计划逐一对应')
        fields = ('work_id', 'unit', 'cell', 'arm', 't', 'user_text', 'forced_prefix', 'system_record')
        for r in selected:
            if any(actual[r['request_id']].get(k) != r.get(k) for k in fields):
                raise ValueError('真实第三轮输入与冻结请求变化：' + r['request_id'])
        checked = True
    return dict(total=1840, cells=expected, unique_requests=len({r['request_id'] for r in selected}),
        third_turn_user_text_complete=True, actual_rows_checked=checked,
        fixed_prefix_rows=sum(bool(r['forced_prefix']) for r in selected),
        system_record_rows=sum(bool(r['system_record']) for r in selected),
        candidate='每回答仅本作品T',
        context_rule='直接读取本请求user_text，只供消歧；固定前缀独立标出，不计作生成断言；5.5正文完整保留。',
        excluded='F-D证据468及其余生成不纳入；S_T证据未执行。')
