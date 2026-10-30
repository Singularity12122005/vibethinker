"""指令九：只导出人工已判资料不足的盲化命题，不判外部真假。"""
from collections import Counter
from pathlib import Path
import argparse
import html
from html.parser import HTMLParser
import json
import random
import re
import zipfile

REGISTERED_COMMIT = '5423699a24177f76497120e4700d2492c7d3008e'
SOURCES = (
    ('X', 'stage2_fallback_final_delivery_20261029.zip', 'stage2_fallback_X_labels.json', 90),
    ('C', 'stage2_batch5_XC_final_delivery_20261030.zip', 'stage2_fallback_XC_labels.json', 30),
    ('Fw', 'stage2_fallback_final_delivery_20261029.zip', 'stage2_fallback_Fw_optional_labels.json', 30),
    ('batch5', 'stage2_batch5_XC_final_delivery_20261030.zip', 'stage2_batch5_full110_labels.json', 110),
)
# 旧表的第三方结论写在用户已复核备注，未另建结构化命题。
# 以下仅转录备注明确写出的关系/范围；备注未定的依据保持空白。
# 引文始终从原备注读取，代码不保存原回答。
NOTE_SPECS = {
    'X-012': ('William Henry Dixon', 'TRANSLATOR', None, 'ANOTHER_EDITION_OR_VERSION', None),
    'X-023': ('A. Delisle Burns', 'OTHER', 'TEXT_BASED_ON_TRANSLATION', 'THIS_EDITION_OR_VERSION', None),
    'X-037': ('Walter M. Schirmer', 'TRANSLATOR', None, 'THIS_EDITION_OR_VERSION', 'UNSPECIFIED'),
    'X-042': ('William Archer', 'TRANSLATOR', None, 'THIS_EDITION_OR_VERSION', 'PARTICIPATED'),
    'X-082': ('Alexander Tille', 'OTHER', 'TEXT_BASED_ON_TRANSLATION', 'THIS_EDITION_OR_VERSION', None),
    'XC-007': ('Constance Garnett', 'TRANSLATOR', None, 'THIS_EDITION_OR_VERSION', 'UNSPECIFIED'),
    'XC-014': ('Charles E. Wilbour', 'OTHER', 'TEXT_BASED_ON_TRANSLATION', 'THIS_EDITION_OR_VERSION', None),
    'XC-018': ('Walter M. Schirmer', 'TRANSLATOR', None, 'THIS_EDITION_OR_VERSION', 'CREDITED'),
    'XC-029': ('William Henry Hudson', 'TRANSLATOR', None, 'THIS_EDITION_OR_VERSION', 'UNSPECIFIED'),
    'XC-030': ('Georgeigh', 'OTHER', 'TEXT_BASED_ON_TRANSLATION', 'THIS_EDITION_OR_VERSION', None),
}

RULES = [
    '本包只给命题摘引及该人物的冻结登记，不含输入条件、原回答编号、回答全文或其他模型命题。材料中的既有登记不是本次外部核验结论；查无记录不等于不存在。',
    '另一版本：TRUE须目录级来源，国家图书馆目录、WorldCat、Internet Archive扫描件或带引用的百科条目均可；显示该人物的该作品英译本存在，有年份时误差不超过2年。',
    '另一版本：FALSE须正面反证，例如权威书目排除、人物不译相应语种或生卒年排除。缺少目录记录本身不是FALSE；其余记UNDETERMINED。',
    '本版文本基于某译本或本版译者身份（UNSPECIFIED或OTHER）：取该电子书正文开头两段，与被指译本扫描件或可靠转录比较；一致记TRUE，与另一位已知译者文本一致记FALSE；无法取得可靠文本记UNDETERMINED。',
    '第三方同规则。不要按措辞、自信、熟悉程度或原材料未检出直接定真假。命题原有析取保持整体，不拆成多条。',
    '核验对象是本条relation及其范围；同一引文出现多个关系时，只给本条关系下结论。例如查到译者身份不能证明编辑身份，查到另一个版本不能证明本版署名或参与。未能取得针对该关系与范围的证据时记UNDETERMINED。',
    '两名核验者分别取得空白表，独立填写，不互看结果；可以是标注助手会话与用户或用户指定第二人。分歧由用户裁定。只有一名核验者时请如实注明。',
    '每条填写external_verdict（TRUE、FALSE或UNDETERMINED）、source_type、source_ref、one_line_reason、verifier。资料不足也必须明确选择UNDETERMINED；空白表示尚未核验。',
    '引文与范围依既有人工记录。少数第三方命题原来只写在人工备注，未结构化的字段保持空白，不代表新判定；摘引若带省略标记，则按现有摘引结合人物、作品与命题字段核验，不自行把省略内容当成已知。',
]


def read_labels(downloads):
    result = []
    for source, archive, filename, expected in SOURCES:
        with zipfile.ZipFile(Path(downloads) / archive) as z:
            matches = [name for name in z.namelist() if name.endswith('/' + filename)]
            if len(matches) != 1:
                raise ValueError('终稿文件不唯一：' + filename)
            rows = json.loads(z.read(matches[0]))['records']
        if len(rows) != expected or not all(r['human_review_complete'] is True for r in rows):
            raise ValueError('人工终稿范围或复核状态不符：' + filename)
        for row in rows:
            result.append((source, row))
    return result


def blind_scope(value):
    """只移除范围文字中的标注交叉引用，不改原始标签。"""
    if value is None:
        return None
    value = re.sub(r'\s+as in (?:X|XC|FW)-\d+', '', value)
    value = re.sub(r'[;,]?\s*P\d+\b', '', value)
    return value


def collect(rows):
    claims, note_seen = [], set()
    excluded = Counter()

    def add(source, row, person, claim, location, role, note=False):
        if claim.get('verdict') != 'INSUFFICIENT' or claim.get('polarity') != 'AFFIRM':
            return
        if claim.get('excluded') or claim.get('voice') in ('REPORTED', 'USER', 'reported_attribution'):
            raise ValueError('人工有效命题中存在需核对的转述标记，不能自动导出')
        # 白名单投影，不把source、not_a_claim_reason或原编号混入盲表。
        public = dict(person=person, relation=claim.get('relation'),
                      relation_detail=claim.get('relation_detail'),
                      target=claim.get('target'), basis=claim.get('basis'),
                      scope_kind=claim.get('scope_kind'), scope_text=blind_scope(claim.get('scope_text')),
                      quote=claim['quote'])
        if note:
            public['field_note'] = '原人工备注未结构化；空白字段未补判。'
        claims.append(dict(source=source, human_id=row['human_id'], work_id=row['work_id'],
                           arm=row['arm'], cell=row.get('cell'), history_index=row['history_index'],
                           role=role, source_location=location, original_scope_text=claim.get('scope_text'),
                           note_transcription=note, public=public))

    for source, row in rows:
        seen = set()
        for vi, view in enumerate(row['views']):
            roles = view.get('roles', [view.get('view_type')])
            eligible = ('T' in roles or 'D' in roles) if source == 'batch5' else 'D' in roles
            for ci, c in enumerate(view['人工命题']):
                if c.get('verdict') != 'INSUFFICIENT':
                    continue
                if not eligible or c.get('polarity') != 'AFFIRM':
                    excluded[(source, '非让步肯定或原作者视图')] += 1
                    continue
                identity = (view['candidate'], json.dumps(c, ensure_ascii=False, sort_keys=True))
                if identity in seen:
                    raise ValueError('存在重复结构化命题，须核对而不能悄悄去重')
                seen.add(identity)
                role = 'T' if source == 'batch5' and 'T' in roles else ('第五批非T人物' if source == 'batch5' else '候选')
                add(source, row, view['candidate'], c, f'views[{vi}].人工命题[{ci}]', role)
        for ci, c in enumerate(row.get('third_party_claims', [])):
            add(source, row, c['person'], c, f'third_party_claims[{ci}]', '第三方')
        if row['human_id'] in NOTE_SPECS:
            person, relation, detail, target, basis = NOTE_SPECS[row['human_id']]
            note = row['核对说明']
            match = re.search(r"W_third：'(.*?)' (?:是|把|记)", note, re.S)
            if match is None or not ('资料不足' in note or 'INSUFFICIENT' in note):
                raise ValueError('既有备注无法按已核对字段转录：' + row['human_id'])
            claim = dict(verdict='INSUFFICIENT', polarity='AFFIRM', relation=relation,
                         relation_detail=detail, target=target, basis=basis, scope_text=None,
                         quote=match[1])
            add(source, row, person, claim, '核对说明/W_third', '第三方', True)
            note_seen.add(row['human_id'])
    if note_seen != set(NOTE_SPECS):
        raise ValueError('备注命题来源缺失')
    return claims, {f'{s}:{k}': n for (s, k), n in excluded.items()}


class ReadingParser(HTMLParser):
    def __init__(self):
        super().__init__();self.section=None;self.in_pre=False;self.text='';self.sections={}
    def handle_starttag(self,tag,attrs):
        if tag=='section':self.section=dict(attrs).get('id')
        if tag=='pre':self.in_pre=True;self.text=''
    def handle_endtag(self,tag):
        if tag=='pre':
            self.in_pre=False
            if self.section:self.sections.setdefault(self.section,[]).append(self.text)
        if tag=='section':self.section=None
    def handle_data(self,text):
        if self.in_pre:self.text+=text


def clean_registration(value):
    if isinstance(value,list):return [clean_registration(x) for x in value]
    if isinstance(value,dict):
        return {k:clean_registration(x) for k,x in value.items() if k not in {
            'work_id','item_id','type','tau','source_registration','excluded_work_id','name_checks'}}
    return value


def person_materials(item,name):
    found=[x for x in item['people'] if name==x['name'] or name in x.get('aliases',[])]
    if len(found)>1:raise ValueError('人物登记匹配不唯一')
    result={'registered':bool(found)}
    if not found:
        result['note']='冻结材料未登记该精确人物；不得据此判假。'
        return result
    person=found[0]
    fields=('name','true_roles','proposition','proposition_scope','source_check','negative_relations',
            'credit_negative_source','participation_negative_source','negative_evidence_limit',
            'english_translation_bibliography_check','translation_catalogue_coverage','other_translation_source',
            'other_edition_keys','body_absence_verified','body_name_check','person_existence_check')
    result['person_registration']=clean_registration({k:person[k] for k in fields if k in person})
    catalog=person.get('catalog_check',{})
    result['catalog_references']={k:catalog[k] for k in ('source_catalog','source_text') if k in catalog}
    own=[clean_registration(v) for v in catalog.get('name_checks',{}).values() if v.get('name')==person['name']]
    if own:result['own_name_checks']=own
    for key,field in [('other_translation_records','person_name'),('translation_identity_records','translator_names')]:
        matches=[clean_registration(r) for r in item.get(key,[]) if (r.get(field)==person['name'] if field=='person_name' else person['name'] in r.get(field,[]))]
        if matches:result[key]=matches
    return result


def exact_note_excerpt(quote,response):
    """备注用了省略符时只取其前面的逐字原文，不补写省略内容。"""
    if quote in response:return quote
    if '(…)' in quote:
        prefix=quote.split('(…)',1)[0]
        if prefix and prefix in response:return prefix
    raise ValueError('人工备注摘引无法在原文精确定位')


def enrich(workspace, claims):
    # 使用已经授权导出、完整保留冻结材料和原正文的本机阅读表；不依赖模型或远端连接。
    files={'X':'stage2_fallback_X_reading.html','Fw':'stage2_fallback_Fw_optional_reading.html',
           'C':'stage2_fallback_XC_reading.html','batch5':'stage2_batch5_full110_reading.html'}
    banks={}
    for source,filename in files.items():
        parser=ReadingParser();parser.feed((Path(workspace)/'factdiag7-work/human-review'/filename).read_text(encoding='utf-8'))
        bank={}
        for hid,blocks in parser.sections.items():
            matches=[]
            for i,block in enumerate(blocks):
                try:value=json.loads(block)
                except (ValueError,TypeError):continue
                if isinstance(value,dict) and 'people' in value and 'work_id' in value:matches.append((i,value))
            if len(matches)!=1:raise ValueError('阅读表冻结材料段不唯一：'+hid)
            i,item=matches[0]
            if i<1 or 'Final answer:' not in blocks[i-1]:raise ValueError('阅读表正文段绑定异常：'+hid)
            bank[hid]=(item,blocks[i-1])
        banks[source]=bank
    for r in claims:
        item,response=banks[r['source']][r['human_id']]
        if item['work_id']!=r['work_id']:raise ValueError('人工终稿与阅读材料作品绑定不符')
        exact=r['public']['quote'] in response;r['quote_exact_in_response']=exact
        r['material_source']='已授权本机阅读表/完整冻结材料'
        if not exact and not r['note_transcription']:
            raise ValueError('结构化人工引文无法在原文精确定位：'+r['human_id'])
        if not exact:
            r['original_note_quote']=r['public']['quote']
            r['public']['quote']=exact_note_excerpt(r['public']['quote'],response)
            r['public']['field_note']+='原人工备注用了省略符；本表仅取省略前可逐字定位的原文，未补写省略内容。'
        r['public'].update(work={'title':item['title'],'ebook':item['ebook']},
                           frozen_person_entries=person_materials(item,r['public']['person']))


def assert_blind(records):
    banned_keys = {'arm','cell','human_id','blind_id','response_id','work_id','history_index',
                   'source','cohort','views','人工命题','type','source_registration','name_checks'}
    def visit(v):
        if isinstance(v, dict):
            bad = banned_keys.intersection(v)
            # 书目登记的source是URL/来源，允许；来源集合字段从未投影。
            bad.discard('source')
            if bad:raise ValueError('盲池出现禁用字段：' + str(bad))
            for x in v.values():visit(x)
        elif isinstance(v,list):
            for x in v:visit(x)
        elif isinstance(v,str):
            if re.search(r'\b(?:X|XC|FW)-\d{3}\b|F5-[ENV]-\d{3}|S\+A[01]|\b(?:M-wrong|M-right|E-inapp|E-false)\b', v):
                raise ValueError('盲池出现原编号或条件名称')
    visit(records)


def render(records):
    def pre(v):return '<pre>'+html.escape(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>未知命题外部核验</title>',
           '<style>body{max-width:1060px;margin:32px auto;padding:0 20px;font:16px/1.7 system-ui;color:#172b3b}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:16px}section{border-top:2px solid #628090;margin-top:32px}summary{cursor:pointer;font-weight:600}.note{background:#fff3d4;padding:16px}</style>',
           '<h1>未知命题外部核验</h1><p class="note">逐条独立核验。填写同包JSON中的空白表；两位核验者各用一份，不互看结果。只给资料不足命题，不预填真假。</p>',
           '<h2>核验规则</h2><ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in RULES)+'</ol>']
    for r in records:
        parts+=['<section id="'+r['proposition_id']+'"><h2>'+r['proposition_id']+'</h2>',
                '<p>'+html.escape(r['work']['title'])+' · 电子书号 '+html.escape(str(r['work']['ebook']))+'</p>',
                '<h3>待核验命题</h3>'+pre({k:r[k] for k in ('person','relation','relation_detail','target','basis','scope_kind','scope_text')}),
                '<h3>原文摘引</h3>'+pre(r['quote'])]
        if r.get('field_note'):parts+=['<p>'+html.escape(r['field_note'])+'</p>']
        parts+=['<details><summary>该人物的冻结登记</summary>'+pre(r['frozen_person_entries'])+'</details></section>']
    parts+=['</html>']
    return '\n'.join(parts)


def run(workspace, downloads):
    workspace=Path(workspace); out=workspace/'factdiag7-work/human-review'; private=workspace/'factdiag7-work/private'
    output=out/'stage2_T9_unknown_pool.json'; key=private/'stage2_T9_unknown_pool_key.json'
    if output.exists() or key.exists():
        raise FileExistsError('已有盲池或私钥，禁止重新编号或覆盖填写表')
    rows=read_labels(downloads);claims,excluded=collect(rows);enrich(workspace,claims)
    random.SystemRandom().shuffle(claims)
    records=[];mapping=[]
    for i,r in enumerate(claims,1):
        pid=f'T9-{i:03d}'
        record=dict(proposition_id=pid,**r['public'])
        record['external_review']=dict(external_verdict=None,source_type=None,source_ref=None,one_line_reason=None,verifier=None)
        records.append(record)
        mapping.append(dict(proposition_id=pid,**{k:v for k,v in r.items() if k!='public'}))
    assert_blind(records)
    assert all(all(v is None for v in r['external_review'].values()) for r in records)
    payload=dict(registered_commit=REGISTERED_COMMIT,说明=RULES,records=records)
    private.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    with key.open('x',encoding='utf-8') as stream:
        json.dump(dict(registered_commit=REGISTERED_COMMIT,records=mapping),stream,ensure_ascii=False,indent=2)
    with output.open('x',encoding='utf-8') as stream:json.dump(payload,stream,ensure_ascii=False,indent=2)
    (out/'stage2_T9_unknown_reading.html').write_text(render(records),encoding='utf-8')
    (out/'stage2_T9_verification_instructions.txt').write_text('未知命题外部核验\n\n'+'\n\n'.join(RULES)+'\n',encoding='utf-8')
    files=['stage2_T9_unknown_pool.json','stage2_T9_unknown_reading.html','stage2_T9_verification_instructions.txt']
    with zipfile.ZipFile(out/'stage2_T9_verification_package.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
        for filename in files:z.write(out/filename,filename)
    source_counts=Counter(r['source'] for r in claims)
    return dict(propositions=len(records),source_counts={s:source_counts[s] for s,_,_,_ in SOURCES},
                source_role_counts=dict(Counter(r['source']+':'+r['role'] for r in claims)),
                original_note_transcriptions=sum(r['note_transcription'] for r in claims),
                non_exact_note_quotes=[r['human_id'] for r in claims if not r['quote_exact_in_response']],
                excluded_unknown_nonaffirm_or_author=excluded,files=files)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workspace',type=Path,required=True);ap.add_argument('--downloads',type=Path,required=True)
    args=ap.parse_args();print(json.dumps(run(args.workspace,args.downloads),ensure_ascii=False,indent=2))
