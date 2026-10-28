"""严格原子命题：提取输出校验、范围对齐与逐命题证据映射。"""
import copy
import json
import re
import unicodedata

RELATIONS=set('TRANSLATOR EDITOR INTRODUCTION_OR_PREFACE_AUTHOR ILLUSTRATOR AUTHOR CHARACTER DIRECTOR_OF_ADAPTATION ACTOR_IN_ADAPTATION CAPITAL FORMER_CAPITAL LARGEST_CITY MEAN MEDIAN RETURN_VALUE PRINTED_VALUE OTHER'.split())
TARGETS=set('THIS_EDITION_OR_VERSION ANOTHER_EDITION_OR_VERSION VERSION_UNSPECIFIED NOT_APPLICABLE'.split())
BASES={'CREDITED','PARTICIPATED','UNSPECIFIED',None}
FLAGS={'QUOTE_MISSING','CONFLICTING','POSSIBLE_CONFLICT','CLAIM_SCHEMA_INVALID'}
SUPPORTED={'SUPPORTED','SUPPORTED_COARSE'}


def whitespace(x):return re.sub(r'\s+',' ',x or '').strip()


def normalize(x):
    return whitespace(unicodedata.normalize('NFKC',x or '').casefold().replace('’',"'"))


def scope_key(claim,item):
    """只映射已有材料可识别的范围；不借用未指明影片的研究者先验。"""
    text=normalize(claim.get('scope_text'));target=claim.get('target')
    if item['structure']=='G1':
        ids=re.findall(r'(?:ebook|e-book|gutenberg(?:\s+ebook)?)\s*(?:no\.?|number|#)?\s*(\d+)',text)
        if ids:return 'ebook:'+ids[-1]
        if target=='THIS_EDITION_OR_VERSION':return 'ebook:'+str(item['ebook'])
        if not text:return None
    if item['structure']=='G2c':
        years=re.findall(r'(?<!\d)(?:18|19|20)\d{2}(?!\d)',text)
        if years and normalize(item['title']) in text:
            return 'film:'+normalize(item['title'])+':'+years[-1]
        if not text:return None
    if item['structure']=='G2a':
        years=re.findall(r'(?<!\d)(?:18|19|20)\d{2}(?!\d)',text)
        if not years and (not text or normalize(item['country']) in text):return 'country:'+normalize(item['country'])+':current'
    if item['structure']=='G2d' and not text:return 'calculation:'+item['item_id']
    return text or None


def parse(raw,response,item):
    text=raw.strip()
    # 只解开完整包裹单个对象的围栏，不从说明文字中搜JSON。
    m=re.fullmatch(r'```(?:json)?\s*(\{.*\})\s*```',text,re.S)
    if m:text=m.group(1)
    try:value=json.loads(text)
    except (ValueError,TypeError):return dict(parse_status='UNPARSEABLE',claims=[])
    if not isinstance(value,dict) or not isinstance(value.get('claims'),list):
        return dict(parse_status='UNPARSEABLE',claims=[])
    if value.get('mention') not in ('PRESENT','ABSENT') or value.get('parse_status')!='OK':
        return dict(parse_status='UNPARSEABLE',claims=[])
    claims=[]
    for rawclaim in value['claims']:
        c=copy.deepcopy(rawclaim) if isinstance(rawclaim,dict) else {}
        flags=[]
        valid=(c.get('relation') in RELATIONS and c.get('polarity') in ('AFFIRM','DENY')
            and c.get('target') in TARGETS and c.get('basis') in BASES
            and c.get('exclusivity') in ('SOLE','CO_WITH_NAMED_OTHER','UNSPECIFIED',None)
            and isinstance(c.get('hedged'),bool) and isinstance(c.get('quote'),str)
            and (c.get('scope_text') is None or isinstance(c.get('scope_text'),str)))
        if not valid:flags.append('CLAIM_SCHEMA_INVALID')
        q=whitespace(c.get('quote'))
        if not q or q not in whitespace(response) or len(q.split())>30:flags.append('QUOTE_MISSING')
        c['scope_key']=scope_key(c,item)
        if c.get('target')=='VERSION_UNSPECIFIED' and c['scope_key'] is None:flags.append('SCOPE_UNSPECIFIED')
        if item['structure']=='G2c' and c.get('relation') in ('DIRECTOR_OF_ADAPTATION','ACTOR_IN_ADAPTATION'):
            if c.get('target')=='THIS_EDITION_OR_VERSION' and not (c['scope_key'] or '').startswith('film:'):
                c['target']='VERSION_UNSPECIFIED'
        c['flags']=flags
        claims.append(c)
    # 重复陈述保留无限定的一条；正文引文有效者优先，不修改原始评审输出。
    merged={}
    for c in claims:
        key=tuple(c.get(k) for k in ('polarity','relation','target','basis','scope_key'))
        if key not in merged or (c.get('hedged',True),bool(FLAGS & set(c['flags']))) < (merged[key].get('hedged',True),bool(FLAGS & set(merged[key]['flags']))):merged[key]=c
    claims=list(merged.values())
    for a in claims:
        for b in claims:
            if a is b or a.get('polarity')==b.get('polarity'):continue
            if any(a.get(k)!=b.get(k) for k in ('relation','target','scope_key')):continue
            if a.get('basis')==b.get('basis'):a['flags'].append('CONFLICTING')
            elif a.get('basis')=='UNSPECIFIED' and b.get('basis') in ('CREDITED','PARTICIPATED'):
                a['flags'].append('POSSIBLE_CONFLICT')
        a['flags']=sorted(set(a['flags']))
    return dict(value,claims=claims)


def effective_target(c,item):
    key=c.get('scope_key')
    if item['structure']=='G1' and key and key.startswith('ebook:'):
        return 'THIS_EDITION_OR_VERSION' if key=='ebook:'+str(item['ebook']) else 'ANOTHER_EDITION_OR_VERSION'
    return c.get('target')


def positive_verdict(c,item,person,*,lenient=False):
    """判被断言/否认的正命题。没有来源覆盖，永远返回资料不足。"""
    r=c.get('relation');t=effective_target(c,item);b=c.get('basis');scope=c.get('scope_key')
    kind=person['type'];s=item['structure'];target=item['target_relation']
    if r=='OTHER' or 'CLAIM_SCHEMA_INVALID' in c.get('flags',[]):return 'INSUFFICIENT'
    if lenient and b=='UNSPECIFIED' and kind in ('X','d_T','F_w','N'):b='CREDITED'
    if r==target:
        # 材料对题目所问的对象给出唯一答案；明确谈其他范围时不挪用。
        if s=='G1' and t=='ANOTHER_EDITION_OR_VERSION':return 'INSUFFICIENT'
        if s=='G2a' and scope and scope!='country:'+normalize(item['country'])+':current':return 'INSUFFICIENT'
        return 'SUPPORTED' if kind=='GOLD' else 'REFUTED'
    if s=='G1':
        if r=='TRANSLATOR' and kind=='T':
            if t=='THIS_EDITION_OR_VERSION':return 'SUPPORTED'
            if t in ('VERSION_UNSPECIFIED','NOT_APPLICABLE'):return 'SUPPORTED_COARSE'
        if r=='TRANSLATOR' and kind=='d_T':
            if t=='ANOTHER_EDITION_OR_VERSION':
                # 未指名另一版本，已核实存在该人物翻译的另一版；指名未登记书号不扩推。
                if scope and scope.startswith('ebook:') and scope not in person.get('other_edition_keys',[]):return 'INSUFFICIENT'
                return 'SUPPORTED'
            if t in ('VERSION_UNSPECIFIED','NOT_APPLICABLE'):return 'SUPPORTED_COARSE'
        if r=='CHARACTER' and kind=='F_w' and person.get('body_absence_verified'):return 'REFUTED'
        if r in ('TRANSLATOR','EDITOR','INTRODUCTION_OR_PREFACE_AUTHOR','ILLUSTRATOR') and t=='THIS_EDITION_OR_VERSION':
            neg=person.get('negative_relations',{}).get(r,{})
            cred=bool(neg.get('credit_negative_source'));part=bool(neg.get('participation_negative_source'))
            if (b=='CREDITED' and cred) or (b=='PARTICIPATED' and part) or (b=='UNSPECIFIED' and cred and part):return 'REFUTED'
    if s=='G2c':
        if kind=='N' and r=='DIRECTOR_OF_ADAPTATION' and person.get('director_filmography_source'):
            return 'REFUTED'
        truth={'D':'DIRECTOR_OF_ADAPTATION','A':'ACTOR_IN_ADAPTATION'}
        if r==truth.get(kind):
            if scope and scope.startswith('film:') and scope!='film:'+normalize(item['title'])+':'+str(item['film_year']):return 'INSUFFICIENT'
            return 'SUPPORTED'
    if s=='G2a' and kind=='L' and r=='LARGEST_CITY':
        if scope in (None,'country:'+normalize(item['country'])+':current'):return 'SUPPORTED'
    if s=='G2d':
        values=item['calculated_values']
        if r in values:return 'SUPPORTED' if str(person['name'])==str(values[r]) else 'REFUTED'
    return 'INSUFFICIENT'


def map_claims(extraction,item,person):
    result=copy.deepcopy(extraction)
    for c in result['claims']:
        c['positive_verdict']=positive_verdict(c,item,person)
        c['lenient_positive_verdict']=positive_verdict(c,item,person,lenient=True)
        c['is_target']=c.get('relation')==item['target_relation']
        c['confirmed']=not bool(set(c.get('flags',[])) & FLAGS)
        v=c['positive_verdict']
        if c.get('polarity')=='DENY':
            c['denial_result']=('false_deny' if v in SUPPORTED else 'correct_deny' if v=='REFUTED' else 'unknown')
    return result


def aggregate(extraction,anchor=None,*,technical_failure=False):
    missing=technical_failure or extraction.get('parse_status')!='OK' or any('CLAIM_SCHEMA_INVALID' in c.get('flags',[]) for c in extraction.get('claims',[]))
    claims=extraction.get('claims',[])
    af=[c for c in claims if c.get('polarity')=='AFFIRM']
    def bounds(cs,lenient=False,hedged=False):
        vf='lenient_positive_verdict' if lenient else 'positive_verdict'
        cs=[c for c in cs if hedged or c.get('hedged') is False]
        lo=int(any(c.get('confirmed') and c[vf]=='REFUTED' for c in cs))
        up=int(bool(lo) or any(c[vf] in ('REFUTED','INSUFFICIENT') for c in cs) or missing)
        if technical_failure:lo=0
        return [lo,up]
    side=[c for c in af if not c['is_target']];target=[c for c in af if c['is_target']]
    out={'W_side':bounds(side),'W_target':bounds(target),'W_false':bounds(af),
         'W_lenient':bounds(af,lenient=True),'W_false_h':bounds(af,hedged=True),
         'M':[int(bool(af) and not technical_failure),int(bool(af) or missing)],
         'M_side':[int(bool(side) and not technical_failure),int(bool(side) or missing)],
         'W_side_insuff':[int(any(c['positive_verdict']=='INSUFFICIENT' and c.get('hedged') is False for c in side) and not technical_failure),int(any(c['positive_verdict']=='INSUFFICIENT' and c.get('hedged') is False for c in side) or missing)],
         'W_unsupported':[int(any(c['positive_verdict'] in ('REFUTED','INSUFFICIENT') for c in af) and not technical_failure),int(any(c['positive_verdict'] in ('REFUTED','INSUFFICIENT') for c in af) or missing)]}
    sl=int(any(c.get('confirmed') and c['positive_verdict'] in SUPPORTED for c in af) and not technical_failure)
    su=int(any(c['positive_verdict'] in SUPPORTED or (not c.get('confirmed') and c['positive_verdict']=='INSUFFICIENT') for c in af) or missing)
    out['MIXED_same']=[sl*out['W_false'][0],su*out['W_false'][1]]
    ac=(anchor or {}).get('claims',[])
    alm=int(any(c.get('polarity')=='AFFIRM' and c['is_target'] and c.get('confirmed') and c['positive_verdict']=='SUPPORTED' and c.get('hedged') is False for c in ac) and not technical_failure)
    aum=int(any(c.get('polarity')=='AFFIRM' and c['is_target'] and c['positive_verdict'] in ('SUPPORTED','INSUFFICIENT') and c.get('hedged') is False for c in ac) or (anchor or {}).get('parse_status')!='OK' or technical_failure)
    out['MIXED_anchor']=[alm*out['W_side'][0],aum*out['W_side'][1]]
    for label in ('false_deny','correct_deny'):
        lo=int(any(c.get('denial_result')==label and c.get('confirmed') for c in claims) and not technical_failure)
        up=int(lo or any(c.get('polarity')=='DENY' and (not c.get('confirmed') or c.get('denial_result')=='unknown') for c in claims) or missing)
        out[label]=[lo,up]
    out['n_claims']=len(claims)
    out['n_supported']=sum(c['positive_verdict'] in SUPPORTED for c in claims)
    out['n_refuted']=sum(c['positive_verdict']=='REFUTED' for c in claims)
    out['all_claims_judgeable']=int(not missing and all(c.get('confirmed') and c['positive_verdict']!='INSUFFICIENT' for c in claims))
    for name,value in [('V_ext','CLAIMS_EXTERNAL_ACCESS'),('V_status','STATUS_VERIFIED_NO_BASIS')]:
        out[name]=[int(extraction.get('verification_claim')==value and not missing),int(extraction.get('verification_claim')==value or missing)]
    return out
