"""机械诊断补充：载荷摘要/正文、旧独立视图、启发式与引文次列；不计算关系事件。"""
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import random
import re
import unicodedata

from .stage2_revision import build_inputs,load,OUTPUT_FILES
from .mention_diagnostic import classify,name_matches,normalize_text,dimensions,CATEGORIES,MARKER,quote_passes

SEED=20261028


def normalize_quote(text):
    text=normalize_text(text)
    text=''.join('-' if unicodedata.category(c)=='Pd' or c=='−' else c for c in text)
    return text.casefold()


def normalized_quote_check(claim,response):
    q=normalize_quote(str(claim.get('quote') or ''))
    substring=bool(q) and q in normalize_quote(response)
    length_ok=len(re.sub(r'\s+',' ',str(claim.get('quote') or '')).split())<=30
    return dict(substring=substring,length_ok=length_ok,eligible=substring and length_ok)


def normalized_quote_column(extraction,response):
    e=deepcopy(extraction)
    for c in e.get('claims',[]):
        if 'QUOTE_MISSING' in c.get('flags',[]) and normalized_quote_check(c,response)['eligible']:
            c['flags']=[f for f in c['flags'] if f!='QUOTE_MISSING']
    return e


def with_quote_flags(extraction,response):
    e=deepcopy(extraction)
    for c in e.get('claims',[]):
        flags=set(c.get('flags',[]))
        if not quote_passes(c,response):flags.add('QUOTE_MISSING')
        c['flags']=sorted(flags)
    return e


def mark_counts(rows):
    return dict(denominator=len(rows),categories={c:sum(r['category']==c for r in rows) for c in CATEGORIES},
                omissions=sum(r['category'] in CATEGORIES[:3] for r in rows))


def run(pilot):
    pilot=Path(pilot);out=pilot/'factdiag7_20261112';queues=build_inputs(pilot)
    saved={p:load(out/f) if (out/f).exists() else {} for p,f in OUTPUT_FILES.items()}
    base=queues['baseline'];base_saved=saved['baseline']
    if len(base_saved)!=1200 or any(r.get('completion')!='returned' for r in base_saved.values()):raise ValueError('首组未完整')
    marks={q['id']:classify(base_saved[q['id']]['extraction'],q['response'],q['person']) for q in base}
    flagged=[q for q in base if marks[q['id']]['category'] in CATEGORIES[:3]]
    unflagged=sorted([q for q in base if marks[q['id']]['category'] is None],key=lambda q:q['id'])
    sampled=random.Random(SEED).sample(unflagged,100)
    mismatches=[]
    for q in flagged+sampled:
        record=base_saved[q['id']]
        digest_ok=hashlib.sha256(q['prompt'].encode('utf-8')).hexdigest()==record.get('prompt_sha256')
        pos=len(q['prompt'])-len(q['response'])
        marker_ok=q['prompt'][:pos].endswith(MARKER+'\n')
        byte_ok=q['prompt'][pos:].encode('utf-8')==q['response'].encode('utf-8')
        if not (digest_ok and marker_ok and byte_ok):mismatches.append(dict(id=q['id'],digest_ok=digest_ok,marker_ok=marker_ok,byte_ok=byte_ok))
    payload=dict(flagged=len(flagged),random_unflagged=100,seed=SEED,checked=len(flagged)+100,
        mismatch_count=len(mismatches),mismatches=mismatches,
        limitation='派发登记只保存完整提示摘要，没有独立的发送载荷正文副本；用冻结构造器重建并核对登记摘要，再比较正文UTF-8字节。发送器源码直接消费该q.prompt。支持排除已登记输入/正文错接，不能冒称比较过一份未保存的独立在途载荷。')
    if mismatches:raise RuntimeError('载荷绑定出现不一致，不能继续重提示：'+json.dumps(payload,ensure_ascii=False))

    oldkeys=load(out/'stage2_independent_key.json')['records']
    independent=load(out/'stage2_independent_extractions.json')
    original_machine={p:load(out/('stage2_'+p+'_extractions.json')) for p in ('baseline','Q2')}
    grouped=defaultdict(list)
    for phase in ('baseline','Q2'):
        for q in queues[phase]:grouped[(phase,q['response_id'])].append(q)
    sets=defaultdict(list);paired=[]
    for row in oldkeys:
        ind={e['candidate']:e['extraction'] for e in independent[row['blind_id']]['extractions']}
        for q in grouped[(row['phase'],row['id'])]:
            i=classify(with_quote_flags(ind[q['person']['name']],q['response']),q['response'],q['person'])
            old=original_machine[row['phase']][q['prior_id']]
            oe=old.get('extraction',old.get('result',{}).get('extraction',{}))
            if not oe:raise ValueError('原机器提取字段未识别')
            o=classify(with_quote_flags(oe,q['response']),q['response'],q['person'])
            sets['independent_original_100'].append(i);sets['machine_v2_same_100'].append(o)
            current=saved[row['phase']].get(q['id'])
            if current and current.get('completion')=='returned':
                n=classify(current['extraction'],q['response'],q['person'])
                sets['machine_v3_available'].append(n);sets['independent_paired_to_v3'].append(i)
                paired.append(dict(phase=row['phase'],machine=n['category'],independent=i['category']))
    comparison={k:mark_counts(v) for k,v in sets.items()}
    comparison['v3_not_yet_returned']=100-len(sets['machine_v3_available'])
    comparison['limits']='原独立代理按第二版协议提取；四类代码检查相同不代表提示语义与第三版完全相同。第三版未返回视图不补跑，不把不同分母的率直接相减。'

    stem=0;reported_cues_only=0;sentence_name_not_found=0
    for q in flagged:
        body=normalize_text(q['response'])
        sentences=re.split(r'(?<![A-Z]\.)(?<=[.!?])\s+|\n+',body)
        names=[s for s in sentences if (lambda m:bool(m['strict'] or m['usable_surname']))(name_matches(s,q['person']))]
        stem+=any(re.search(r'\b(?:translat|edit|author|credit|list|attribut)\w*',s,re.I) for s in names)
        reported_cues_only+=bool(names) and all(re.search(r'\b(?:you|your|people|others|mentioned|suggest\w*)\b',s,re.I) for s in names)
        sentence_name_not_found+=not names
    lengths=sorted({q['response_id']:len(q['response'].split()) for q in base}.values())
    cuts=[lengths[int((len(lengths)-1)*v)] for v in (.25,.5,.75)]
    bins=defaultdict(list)
    for q in base:
        words=len(q['response'].split());b=next((i for i,c in enumerate(cuts,1) if words<=c),4)
        bins[b].append(marks[q['id']])
    heuristics=dict(views=len(flagged),relation_stem_in_name_sentence=stem,
        all_name_sentences_have_user_cue=reported_cues_only,sentence_split_name_not_found=sentence_name_not_found,
        length_quantile_word_cutoffs=cuts,length_quantiles={str(k):mark_counts(v) for k,v in sorted(bins.items())},
        limitation='词干和用户提示词只作句子级启发式，不判定事实、极性或仅转述；没有名称匹配的分句单列。长度四分位按600条唯一正文空白分词数定义，边界相同长度归低一档。')

    candidate_kind={q['response_id']:q['kind'] for phase in ('baseline','Q2') for q in queues[phase] if q['kind'] not in ('GOLD','T')}
    quote_groups=defaultdict(Counter)
    for q in base:
        dim=dimensions(q,candidate_kind[q['response_id']]);key=tuple(dim[k] for k in ('view_type','candidate_type','arm'))
        for c in base_saved[q['id']]['extraction'].get('claims',[]):
            if 'QUOTE_MISSING' not in c.get('flags',[]):continue
            check=normalized_quote_check(c,q['response'])
            quote_groups[key]['strict_missing']+=1
            quote_groups[key]['normalized_substring_pass' if check['substring'] else 'normalized_substring_fail']+=1
            quote_groups[key]['normalized_eligible' if check['eligible'] else 'normalized_still_invalid']+=1
    qtable=[dict(zip(('view_type','candidate_type','arm'),k))|dict(v) for k,v in sorted(quote_groups.items())]
    qtotals=Counter()
    for v in quote_groups.values():qtotals.update(v)
    quote_report=dict(primary='strict',secondary='normalized_quote',source_column='original，不与重提示列合并',
        normalization='NFKC，删*_反引号，弯引号/撇号转直，所有Unicode破折号及减号统一为ASCII连字符，合并空白，casefold后子串；空引文不通过，原30词上限不变。',
        totals=dict(qtotals),strata=qtable,changes_original_labels=False)

    livegroups=defaultdict(list)
    for q in queues['Q2']:
        record=saved['Q2'].get(q['id'])
        if not record or record.get('completion')!='returned':continue
        d=dimensions(q,candidate_kind[q['response_id']])
        livegroups[(d['arm'],d['view_type'],d['candidate_type'])].append(classify(record['extraction'],q['response'],q['person']))
    live=[dict(zip(('arm','view_type','candidate_type'),key))|mark_counts(rows) for key,rows in sorted(livegroups.items())]
    report=dict(payload_check=payload,original_40_comparison=comparison,heuristics=heuristics,
        normalized_quote=quote_report,Q2_returned_counts=live,
        models=dict(machine={'name':'Qwen2.5-32B-Instruct','decoding':'do_sample=False，确定性；temperature不用于采样','max_new_tokens':2048},
            independent={'name':'gpt-6-astra','reasoning_effort':'xhigh','temperature':'运行记录未暴露，不能填写0','max_output_tokens':'运行记录未暴露；不把模型支持上限冒充本次上限'}),
        no_relation_events_computed=True)
    (out/'stage2_mention_followup_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'stage2_mention_followup_checks.md').write_text(render(report),encoding='utf-8')
    return report


def render(r):
    p=r['payload_check'];q=r['normalized_quote']
    lines=['# 提及诊断补充检查','',f"载荷检查：{p['flagged']}个标记视图加随机{p['random_unflagged']}个未标记视图，共{p['checked']}个；记录摘要或正文字节不一致{p['mismatch_count']}个。",'',p['limitation'],'',
        '## 原独立复核的同视图对照','','|提取来源|分母|内部矛盾|全名别名漏提|仅姓氏漏提|凭空提及|漏提合计|','|---|---:|---:|---:|---:|---:|---:|']
    for name,v in r['original_40_comparison'].items():
        if isinstance(v,dict):lines.append('|'+'|'.join([name,str(v['denominator'])]+[str(v['categories'][c]) for c in CATEGORIES]+[str(v['omissions'])])+'|')
    lines+=['',r['original_40_comparison']['limits'],'','机器为Qwen2.5-32B-Instruct，确定性解码，最大新输出2048。原独立代理为GPT-6 Astra，推理强度xhigh；运行记录未暴露温度及最大输出配置，不能把未知填成0或2048。两者不是同模型同配置实验。','',
        '## 姓名所在句与长度线索','',json.dumps(r['heuristics'],ensure_ascii=False,indent=2),'',
        '## 规范化引文次列','',q['normalization'],'',json.dumps(q['totals'],ensure_ascii=False),'',
        '|视图／候选／臂|严格引文缺失|规范化子串通过|仍非子串|兼容30词上限的通过|','|---|---:|---:|---:|---:|']
    for v in q['strata']:lines.append('|'+ '/'.join(v[k] for k in ('view_type','candidate_type','arm'))+'|'+'|'.join(str(v.get(k,0)) for k in ('strict_missing','normalized_substring_pass','normalized_substring_fail','normalized_eligible'))+'|')
    lines+=['','这是原列的独立次列二，不与重提示合并，不修改原始提取，不放宽人工连续带标记引文要求。','',
        '## 新回答已返回视图标记计数','', '以下只列已返回分母；串行队列的部分样本不代表完整臂。','',
        '|臂／视图／候选|已返回|内部矛盾|全名别名漏提|仅姓氏漏提|凭空提及|','|---|---:|---:|---:|---:|---:|']
    for v in r['Q2_returned_counts']:lines.append('|'+ '/'.join(v[k] for k in ('arm','view_type','candidate_type'))+'|'+'|'.join([str(v['denominator'])]+[str(v['categories'][c]) for c in CATEGORIES])+'|')
    return '\n'.join(lines)+'\n'
