"""已批准的单一外层围栏解析次列；只比较C1/C2/C3质量，不计算关系总体。"""
from pathlib import Path
from collections import Counter
import json,re
from .judge_core import build_inputs,parse_result
from .blind_revision import scalar_agreement
from ..factdiag7.stage2_revision import load,save_new

def unwrap(raw):
    if not isinstance(raw,str):return None
    m=re.fullmatch(r'\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*',raw,re.S|re.I)
    if not m or '```' in m[1]:return None
    return m[1]

def run(pilot):
    p=Path(pilot)/'factdiag5_20261112';dest=p/'factdiag5_fenced_propositions_quality.json'
    if dest.exists():return load(dest)
    rows=load(p/'core_generations.json');material=load(p/'factdiag5_materials.json');reg=load(p/'factdiag5_prereg.json')
    queue=build_inputs(material,rows,reg)['queues']['legacy_propositions'];old=load(p/'core_legacy_reviews.json')
    if len(queue)!=1440:raise ValueError('冻结三命题输入规模改变')
    repaired={};by_response={};stats=Counter()
    for q in queue:
        o=old[q['id']]
        if o['input_sha256']!=q['input_sha256'] or o['completion']!='returned':raise ValueError('旧输入或完成状态不符')
        raw=o.get('raw');inner=unwrap(raw)
        result=parse_result(q,inner) if inner is not None else dict(missing=True,reason='not_single_outer_fence')
        repaired[q['id']]=dict(input_sha256=q['input_sha256'],result=result,source='single_outer_fence_only')
        by_response[q['request_id']]=(q,o['result'],result)
        stats['outer_fence_removed']+=inner is not None;stats['parsed']+=not result['missing']
    key=load(p/'factdiag5_independent_key.json')['records'];pairs={col:{c:[] for c in ('C1','C2','C3')} for col in ('original','fence_only')}
    def label(r,c):
        value=(r.get('propositions') or {}).get(c,{}).get('label')
        return None if r.get('missing') or value=='UNJUDGEABLE' else value
    for r in key:
        if r['request_id'] not in by_response:continue
        q,original,fixed=by_response[r['request_id']]
        a=load(p/'factdiag5_independent_labels'/(r['blind_id']+'.json'))['annotations']['propositions']
        reference=parse_result(q,json.dumps(a,ensure_ascii=False) if isinstance(a,dict) else a or '')
        for c in ('C1','C2','C3'):
            pairs['original'][c].append((label(original,c),label(reference,c)))
            pairs['fence_only'][c].append((label(fixed,c),label(reference,c)))
    report=dict(inputs=1440,syntax_counts=dict(stats),quality={col:{c:scalar_agreement(v) for c,v in metrics.items()} for col,metrics in pairs.items()},original_preserved=True,model_calls=0,population_rates_computed=False,interpretation='仅移除单一外层代码围栏；内部文本原样交既有解析器，原引文及命题标准不变。未知保留分母。不是全量关系放行。')
    save_new(p/'core_legacy_propositions_fence_only.json',repaired);save_new(dest,report)
    return report
