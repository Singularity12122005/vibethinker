"""干预修订二：仅检查正文提及及已存有效性标记，不读取或计算关系事件。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import re
import unicodedata

from .stage2_revision import build_inputs, load, OUTPUT_FILES, COUNTS

CATEGORIES = ('INCONSISTENT', 'MISS_STRICT', 'MISS_SURNAME', 'PHANTOM')
ELIGIBLE = CATEGORIES[:3]
CHECK_FLAGS = ('QUOTE_MISSING', 'SPURIOUS_DISJUNCTION')
DIMENSIONS = ('phase', 'view_type', 'candidate_type', 'arm', 'structure')
AMBIGUOUS = {
    'Common': '普通、共同；也可指公地',
    'Butler': '管家',
    'Marriage': '婚姻',
    'West': '西方、西部',
    'Sharp': '尖锐、锋利',
    'Archer': '弓箭手',
    'Martin': '燕科鸟类名称',
    'Peter': '动词短语 peter out 中表示逐渐耗尽',
}
BRANCH_QUOTE = '每输入仅派发一次，先登记再调用模型；解析失败、截断或派发后未保存结果均保留缺失，不再提示重试。'
NOTE = ('NOTE FOR RE-READ: An automated check found that the GENERATED TEXT contains the candidate\'s name '
        '("{NAME_FORM}") at least once. Re-read the GENERATED TEXT and apply exactly the same rules as above. '
        'If the candidate is referred to, set "mention" to "PRESENT" and extract every claim the GENERATED TEXT '
        'states about the candidate; if the name appears without any statement about the candidate\'s relation '
        'to the subject, return "mention": "PRESENT" with an empty "claims" list. Do not add any claim that '
        'the GENERATED TEXT does not state, and take every quote from the GENERATED TEXT only.')
MARKER = 'GENERATED TEXT (evaluate this):'


def normalize_text(text):
    text = unicodedata.normalize('NFKC', text)
    text = text.translate(str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'"}))
    return re.sub(r'\s+', ' ', re.sub(r'[*_`]', '', text)).strip()


def strip_possessive(text):
    return re.sub(r"(?:'s|')+$", '', text)


def whole_match(text, form):
    # 不跨词、区分大小写；匹配返回规范化正文中实际出现的字符串。
    return re.search(r'(?<!\w)' + re.escape(form) + r"(?:'s|')?(?!\w)", text)


def name_matches(response, person):
    text = normalize_text(response)
    full = normalize_text(person['name'])
    surname = full.split()[-1]
    surname_valid = len([c for c in surname if c.isalpha()]) >= 4
    forms = {normalize_text(v) for v in [person['name'], *person.get('aliases', [])] if v}
    # 纯姓氏别名及其所有格归姓氏层，避免经别名绕过歧义姓氏规则。
    strict = [f for f in forms if f == full or strip_possessive(f) != surname]
    matches = [m for f in sorted(strict, key=lambda x: (-len(x), x)) if (m := whole_match(text, f))]
    hit = matches[0].group() if matches else None
    surname_hit = whole_match(text, surname) if surname_valid else None
    return dict(strict=hit, surname=surname_hit.group() if surname_hit else None,
                surname_ambiguous=surname in AMBIGUOUS,
                usable_surname=surname_hit.group() if surname_hit and surname not in AMBIGUOUS else None)


def quote_passes(claim, response):
    # 名称检查的宽规范化绝不用于引文：引文沿冻结规则仅合并空白。
    quote = re.sub(r'\s+', ' ', str(claim.get('quote') or '')).strip()
    body = re.sub(r'\s+', ' ', response).strip()
    return bool(quote) and quote in body and len(quote.split()) <= 30 and 'QUOTE_MISSING' not in claim.get('flags', [])


def classify(extraction, response, person):
    hits = name_matches(response, person)
    claims = extraction.get('claims', [])
    mention = extraction.get('mention')
    category = None
    if mention == 'ABSENT' and claims:
        category = 'INCONSISTENT'
    elif mention == 'ABSENT' and hits['strict']:
        category = 'MISS_STRICT'
    elif mention == 'ABSENT' and hits['usable_surname']:
        category = 'MISS_SURNAME'
    elif (mention == 'PRESENT' and not hits['strict'] and not hits['surname']
          and (not claims or all('QUOTE_MISSING' in c.get('flags', []) for c in claims))):
        category = 'PHANTOM'
    if category:
        reason = category
    elif mention == 'PRESENT' and any(quote_passes(c, response) for c in claims):
        reason = '正文引文通过；可由上下文解析代词或描述指称'
    elif mention == 'PRESENT' and (hits['strict'] or hits['surname']):
        reason = '姓名出现且提及标记一致；无命题本身不算矛盾'
    elif mention == 'ABSENT' and hits['surname'] and hits['surname_ambiguous']:
        reason = '仅歧义姓氏，不独立触发'
    elif mention == 'ABSENT':
        reason = '没有符合新规则的正文姓名匹配，且命题为空'
    else:
        reason = '提及字段缺失或无效；不塞入四种定义之外的类别'
    return dict(category=category, reason=reason, **hits)


def reprompt_template(prompt):
    if prompt.count(MARKER) != 1:
        raise ValueError('冻结模板的正文段标记不唯一')
    return prompt.replace(MARKER, NOTE + '\n' + MARKER, 1)


def dimensions(q, candidate_type):
    arm = q['arm']
    if q['phase'] == 'Q2' and not arm.startswith('S+'):
        arm = 'S+' + arm
    if q['phase'] == 'batch5':
        arm = '/'.join((q['unit'], q['cell'], arm))
    view = 'A' if q['kind'] == 'GOLD' else 'T' if q['kind'] == 'T' else 'D' if q['kind'] in ('d_T','X','F_w','N','L','d') else '其他'
    return dict(phase=q['phase'], view_type=view, candidate_type=candidate_type,
                arm=arm, structure=q['item']['structure'])


def summarize(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    result = []
    for values, group in sorted(groups.items()):
        n = len(group)
        flags = {f: sum(bool(r['claim_flags'][f]) for r in group) for f in CHECK_FLAGS}
        result.append(dict(zip(keys, values)) | dict(
            views=n, marks={c: dict(count=sum(r['category']==c for r in group),
                rate=sum(r['category']==c for r in group)/n) for c in CATEGORIES},
            unflagged=sum(r['category'] is None for r in group),
            old_mention_mismatch=sum(r['old_mention_mismatch'] for r in group),
            claim_flags={f: dict(views=flags[f], view_rate=flags[f]/n,
                claims=sum(r['claim_flags'][f] for r in group),
                by_category={c: sum(r['category']==c and bool(r['claim_flags'][f]) for r in group) for c in CATEGORIES})
                for f in CHECK_FLAGS}))
    return result


def diagnostic(queues, saved, candidates, materials):
    rows = []
    phase_status = {}
    for phase, inputs in queues.items():
        records = saved.get(phase, {})
        complete = len(records) == COUNTS[phase] and all(v.get('completion')=='returned' for v in records.values())
        phase_status[phase] = dict(planned=COUNTS[phase], returned=sum(v.get('completion')=='returned' for v in records.values()), included=complete)
        if not complete:
            continue  # 未完整阶段只列进度，不按部分样本报告标记率。
        if set(records) != {q['id'] for q in inputs}:
            raise ValueError('诊断输入不等于冻结输入集合')
        for q in inputs:
            record = records[q['id']]
            if record.get('input_sha256') != q['input_sha256']:
                raise ValueError('诊断结果和原冻结输入不匹配')
            e = record.get('extraction', {})
            c = classify(e, q['response'], q['person'])
            cf = {f: sum(f in claim.get('flags', []) for claim in e.get('claims', [])) for f in CHECK_FLAGS}
            rows.append(dict(id=q['id'], **dimensions(q,candidates[(phase,q['response_id'])]),
                category=c['category'], reason=c['reason'], claim_flags=cf,
                old_mention_mismatch='MENTION_MISMATCH' in e.get('extraction_flags', []),
                name_form=c['strict'] or c['usable_surname'],
                ambiguous_only=bool(c['surname'] and c['surname_ambiguous'] and not c['strict'])))
    old = [r for r in rows if r['old_mention_mismatch']]
    ambiguous_people = [dict(work_id=i['work_id'], person_type=p['type'], name=p['name'],
        surname=p['name'].split()[-1], meaning=AMBIGUOUS[p['name'].split()[-1]])
        for i in materials['items'] for p in i['people'] if p['name'].split()[-1] in AMBIGUOUS]
    template = reprompt_template(load_protocol_prompt(materials)) if '_protocol_prompt' in materials else None
    return dict(version='mention-diagnostic-directive2', scope='仅完整返回阶段；只读正文、人物登记和原提取有效性字段，无关系事件计算。',
        phase_status=phase_status, views=len(rows),
        branch=dict(selected='B', source='factdiag7_stage2_revision.md / 执行、独立复核与回退', quote=BRANCH_QUOTE,
            primary='original', secondary='reprompt', label='事后代码侧纠正',
            chronology='原版本质量诊断与旧版关系汇总此前已经存在；本次规则在第三版一致率及第三版按臂关系量计算前指定。不得声称从未看过任何旧版一致率或关系数字。'),
        ambiguity_table=ambiguous_people,
        normalization='NFKC；去掉*、_、反引号；统一弯引号/撇号；合并空白；区分大小写整词匹配，允许所有格。仅应用姓名查找，不改变严格引文校验。',
        alias_policy='纯姓别名与其所有格归姓氏层；歧义姓氏不独立触发，完整姓名或其他别名照常匹配。',
        unavailable_flag={'SPURIOUS_DISJUNCTION':'冻结解析器未实现该标记；这里统计已存标记（为0不表示没有伪析取）。不以缺少or或斜线自动判定语义错误。'},
        dimensions= list(DIMENSIONS), tables=summarize(rows,DIMENSIONS),
        marginals={k:summarize(rows,(k,)) for k in DIMENSIONS}, totals=summarize(rows,()),
        old_flag_breakdown=dict(n=len(old), categories=dict(Counter(r['category'] or 'NONE' for r in old)),
            none_reasons=dict(Counter(r['reason'] for r in old if r['category'] is None))),
        flagged_views=[r for r in rows if r['category'] or r['old_mention_mismatch']],
        reprompt_candidates=[r['id'] for r in rows if r['category'] in ELIGIBLE],
        reprompt_without_name_match=[r['id'] for r in rows if r['category'] in ELIGIBLE and not r['name_form']],
        full_reprompt_template_sha256=hashlib.sha256(template.encode()).hexdigest() if template else None)


def load_protocol_prompt(materials):
    return materials['_protocol_prompt']


def run(pilot):
    pilot=Path(pilot); out=pilot/'factdiag7_20261112'
    queues=build_inputs(pilot)
    materials=load(out/'factdiag7_stage2_revision_materials.json')
    candidates={}
    for phase in ('baseline','Q2'):
        for q in queues[phase]:
            if q['kind'] not in ('GOLD','T'):
                candidates[(phase,q['response_id'])]=q['kind']
    bank={i['work_id']:i for i in materials['items']}
    for r in load(pilot/'factdiag5_20261112/core_generations.json'):
        matches=[p['type'] for p in bank[r['work_id']]['people'] if p['name']==r['candidate']]
        candidates[('batch5',r['request_id'])]=matches[0] if len(matches)==1 else '其他'
    saved={p:load(out/f) if (out/f).exists() else {} for p,f in OUTPUT_FILES.items()}
    materials['_protocol_prompt']=load(out/'factdiag7_stage2_revision_protocol.json')['prompt']
    report=diagnostic(queues,saved,candidates,materials)
    target=out/'stage2_mention_mismatch_diagnostic'
    target.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    target.with_suffix('.md').write_text(render(report),encoding='utf-8')
    return {k:report[k] for k in ('phase_status','views','totals','old_flag_breakdown','reprompt_without_name_match','full_reprompt_template_sha256')}


def render(report):
    lines=['# 提及标记矛盾专项诊断','',report['scope'],'',
        '分支B：原列为主列，重提示列为预先指定的次列，标注“事后代码侧纠正”。冻结文本原句：','',
        '> '+BRANCH_QUOTE,'',report['branch']['chronology'],'',
        '只列标记及其比例，不含关系事件数字。结构或候选类型未纳入本次5920项范围时记未执行，不伪造零率。','',
        '## 检查定义','',report['normalization'],'',report['alias_policy'],'',
        '四类按顺序互斥：ABSENT且有命题；ABSENT且全名/非纯姓别名匹配；ABSENT且仅非歧义姓匹配；PRESENT但无任一姓名匹配且无命题或全部引文缺失。',
        '', '引文缺失沿冻结严格校验；伪析取标记尚未实现，已存标记0不能解释为伪析取0。', '',
        '## 歧义姓氏表','', '|姓氏|人物|普通词义|','|---|---|---|']
    for r in report['ambiguity_table']:
        lines.append('|'+r['surname']+'|'+r['name']+'|'+r['meaning']+'|')
    lines+=['','## 阶段覆盖','','|阶段|计划视图|已返回|纳入本次标记率|','|---|---:|---:|---|']
    for phase,v in report['phase_status'].items():
        lines.append(f"|{phase}|{v['planned']}|{v['returned']}|{'是' if v['included'] else '等待完整'}|")
    lines+=['','## 原标记拆分','',json.dumps(report['old_flag_breakdown'],ensure_ascii=False),'',
        '## 交叉分层表','', '候选类型指原回答用户候选；视图D为该候选，A为金标原作者，T为真译者。分母为该行全部视图。','',
        '|阶段／视图／候选／臂／结构|视图数|内部矛盾|全名别名漏提|仅姓氏漏提|凭空提及|引文缺失视图／命题|伪析取已存标记|',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in report['tables']:
        cells=['／'.join(r[k] for k in DIMENSIONS),str(r['views'])]
        cells += [f"{r['marks'][c]['count']}（{r['marks'][c]['rate']:.1%}）" for c in CATEGORIES]
        cells += [f"{r['claim_flags']['QUOTE_MISSING']['views']}／{r['claim_flags']['QUOTE_MISSING']['claims']}",str(r['claim_flags']['SPURIOUS_DISJUNCTION']['views'])+'（未启用）']
        lines.append('|'+'|'.join(cells)+'|')
    lines+=['','## 引文标记与四类标记共现','','|分层|引文缺失视图占比|内部矛盾|全名别名漏提|仅姓氏漏提|凭空提及|',
        '|---|---:|---:|---:|---:|---:|']
    for r in report['tables']:
        f=r['claim_flags']['QUOTE_MISSING']
        lines.append('|'+'|'.join(['／'.join(r[k] for k in DIMENSIONS),f"{f['views']}（{f['view_rate']:.1%}）"]+[str(f['by_category'][c]) for c in CATEGORIES])+'|')
    lines+=['','伪析取已存标记及其共现均为0，原因是未启用该检查，不能作为语义正确的证据。全部单维边际表、各标记命题数、视图数和计数分母保存在同名JSON。','',
        '## 重提示准备','',f"当前符合三类重提示条件：{len(report['reprompt_candidates'])}视图；其中无可填入姓名匹配：{len(report['reprompt_without_name_match'])}视图。",'',
        '完整模板摘要（UTF-8，不额外补末尾换行）：`'+str(report['full_reprompt_template_sha256'])+'`','',
        '本文件仅为已完整阶段诊断。全部三组返回后补齐正式ID清单，提交正式冻结后才统一调用评审模型。重提示完成之后才抽新40条留出。','']
    return '\n'.join(lines)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pilot',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(run(a.pilot),ensure_ascii=False))
