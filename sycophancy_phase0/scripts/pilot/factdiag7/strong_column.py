"""强提取器清单与保存入口；不调用模型，不计算分臂关系量。"""
from collections import Counter
from pathlib import Path
import hashlib
import json

from .stage2_revision import build_inputs, load, save_new
from .revision_runtime import atomic_save
from .relations_v3 import parse
from .mention_followup_checks import normalized_quote_column

PLAN = 'stage2_strong_plan.json'
OUTPUT = 'stage2_strong_extractions.json'
TEMPLATE_SHA = 'c564109ed400cfa75682dea7a0b9c09ab6f7c0e055be1c416697722148c30d27'
RULE = dict(model='gpt-6-astra', reasoning='xhigh', speed='standard', service_tier='default',
    pilot=200, layer1_credit_ceiling=3000, total_credit_ceiling=10000,
    balance_floor=6500, operating_reserve=5000, cache_floor=.80,
    cache_window=200, output_multiplier=2, checkpoint_every=500,
    layer3_requires_new_user_decision=True,
    layer_order=['candidate', 'Q2_translator', 'batch5_translator', 'gold'],
    temperature=None, max_output_tokens=None,
    unspecified_parameters='命令行不暴露；服务默认值未知，不声称与旧代理数值相同。')


def alternate(rows):
    a = sorted((q for q in rows if q['arm'] == 'S+A1'), key=lambda q:q['id'])
    b = sorted((q for q in rows if q['arm'] == 'S+A0'), key=lambda q:q['id'])
    if len(a) != len(b) or len(a)+len(b) != len(rows):
        raise ValueError('Q2两臂不能按完整对交替')
    return [q for pair in zip(a,b) for q in pair]


def ordered_layers(queues, reused):
    def fresh(phase, kind):
        return [q for q in queues[phase] if kind(q['kind']) and q['id'] not in reused]
    d = lambda k:k not in ('GOLD','T')
    return [alternate(fresh('Q2',d))+sorted(fresh('baseline',d),key=lambda q:q['id']),
            alternate(fresh('Q2',lambda k:k=='T')),
            list(queues['batch5']),
            alternate(fresh('Q2',lambda k:k=='GOLD'))+
            sorted(fresh('baseline',lambda k:k=='GOLD'),key=lambda q:q['id'])]


def prepare(pilot):
    out=Path(pilot)/'factdiag7_20261112';queues=build_inputs(pilot)
    blind=load(out/'stage2_fallback_independent_blind.json')
    if hashlib.sha256(blind['protocol'].encode()).hexdigest()!=TEMPLATE_SHA:
        raise ValueError('回退集冻结模板不符')
    key=load(out/'stage2_fallback_calibration_key.json')['records']
    independent=load(out/'stage2_fallback_independent_extractions.json')
    views={r['blind_id']:r['views'] for r in blind['records']}
    reused={}
    for r in key:
        stored={v['candidate']:v['extraction'] for v in independent[r['blind_id']]['extractions']}
        for v in views[r['blind_id']]:
            qs=[q for q in queues[r['phase']] if q['response_id']==r['response_id']
                and q['person']['name']==v['candidate']]
            if len(qs)!=1 or qs[0]['prompt']!=v['prompt'] or v['candidate'] not in stored:
                raise ValueError('回退视图或逐字提示未匹配')
            q=qs[0]
            extraction=parse(json.dumps(stored[v['candidate']],ensure_ascii=False),q['response'],
                             q['item'],q['person'],q['user_message'])
            reused[q['id']]=dict(completion='returned',source='fallback_independent_reuse',
                blind_id=r['blind_id'],input_sha256=q['input_sha256'],prompt_sha256=q['prompt_sha256'],
                template_sha256=TEMPLATE_SHA,raw=stored[v['candidate']],extraction=extraction,
                normalized_quote_extraction=normalized_quote_column(extraction,q['response']),
                runtime=dict(model='gpt-6-astra',reasoning='xhigh',speed=None,temperature=None,
                    max_output_tokens=None,tools_empty=False,
                    note='既有单个持续上下文代理经专用工具读取；用户授权复用，不冒称独立命令行调用。'),
                usage=None,usage_note='240视图仅有整代理累计词元，不伪造逐视图用量。')
    if len(reused)!=240:raise ValueError('必须恰好复用240个已有视图')
    layers=ordered_layers(queues,reused)
    if [len(x) for x in layers]!=[1440,960,1840,1440]:raise ValueError('四层规模不符')
    entries=[dict(id=q['id'],layer=i+1,phase=q['phase'],kind=q['kind'],arm=q['arm'],
        prompt_sha256=q['prompt_sha256'],input_sha256=q['input_sha256'])
        for i,layer in enumerate(layers) for q in layer]
    if len({r['id'] for r in entries}|set(reused))!=5920:raise ValueError('总清单不符')
    plan=dict(rule=RULE,template_sha256=TEMPLATE_SHA,total=5920,reused=240,new=5680,
        layers=[dict(layer=i+1,new=len(layer),by_phase=dict(Counter(q['phase'] for q in layer)))
                for i,layer in enumerate(layers)],reused_ids=sorted(reused),entries=entries)
    save_new(out/PLAN,plan)
    if (out/OUTPUT).exists():
        existing=load(out/OUTPUT)
        if any(existing.get(k)!=v for k,v in reused.items()):raise ValueError('已有复用结果不同，不覆盖')
    else:atomic_save(out/OUTPUT,reused)
    return {k:v for k,v in plan.items() if k not in ('entries','reused_ids')}


def get_inputs(pilot, ids, retry_missing=None):
    out=Path(pilot)/'factdiag7_20261112';plan=load(out/PLAN)
    allowed={r['id']:r for r in plan['entries']};queues=build_inputs(pilot)
    bank={q['id']:q for rows in queues.values() for q in rows};saved=load(out/OUTPUT)
    rows=[]
    for key in ids:
        if key not in allowed:raise ValueError('输入未登记')
        if key in saved:
            old=saved[key]
            if (key!=retry_missing or old.get('completion')!='attempted_result_missing'
                    or old.get('attempts')!=1 or old.get('previous_attempts')):
                raise ValueError('已有结果不属于本次获准的首次缺失重试')
        q=bank[key]
        if q['prompt_sha256']!=allowed[key]['prompt_sha256']:raise ValueError('提示变化')
        rows.append(q)
    return rows


def save_result(pilot, key, result, retry_missing=None):
    out=Path(pilot)/'factdiag7_20261112';plan=load(out/PLAN)
    q=next(r for r in plan['entries'] if r['id']==key)
    if result['input_sha256']!=q['input_sha256'] or result['prompt_sha256']!=q['prompt_sha256']:
        raise ValueError('结果错接输入')
    saved=load(out/OUTPUT)
    if key in saved:
        old=saved[key]
        if old==result:return
        if (key!=retry_missing or old.get('completion')!='attempted_result_missing'
                or old.get('attempts')!=1 or old.get('previous_attempts')
                or result.get('attempts')!=2 or not result.get('retry_authorization')):
            raise ValueError('不覆盖已有强提取结果')
        # 用户明确批准重试缺失项；保留原失败记录，只让本次返回成为有效结果。
        result=dict(result,previous_attempts=[old])
    saved[key]=result;atomic_save(out/OUTPUT,saved)


def safety_stop(start_balance,balance,cache_ratios,outputs,pilot_output=None):
    if balance is None:return '无法读取积分余额'
    if balance<6500:return '积分余额低于6500'
    if start_balance-balance>=10000:return '从本次启动起账号积分下降已达10000'
    # 账号差值含其他工作，作为提取消耗的保守上界，不精确归因。
    if len(cache_ratios)>=200 and all(x<.8 for x in cache_ratios[-200:]):
        return '连续200视图缓存比例低于80%'
    if pilot_output and outputs and sum(outputs)/len(outputs)>2*pilot_output:
        return '平均输出超过先导两倍'
    return None


def pilot_decision(before,after,usage,layer1=1440):
    n=len(usage);total_input=sum(x['input_tokens'] for x in usage)
    ratio=sum(x['cached_input_tokens'] for x in usage)/total_input if total_input else 0
    delta=float(before['credits']['balance'])-float(after['credits']['balance'])
    allowance_changed=before.get('primary')!=after.get('primary')
    included_available=any((v.get('primary') or {}).get('usedPercent',0)<100 for v in (before,after))
    reasons=[]
    if n!=200:reasons.append('先导未完整返回200视图')
    if ratio<.8:reasons.append('缓存输入比例不足80%')
    if delta<=0 or allowance_changed or included_available:
        reasons.append('自带额度变化或积分差无法识别纯积分单视图成本')
    projection=delta/n*layer1 if delta>0 and n else None
    if projection is not None and projection>3000:reasons.append('第一层外推超过3000积分')
    return dict(views=n,cache_ratio=ratio,account_credit_decrease=delta,
        projection_first_layer=projection,projection_scope='第一层1440个新调用；旧120不重复计费',
        allowance_changed=allowance_changed,allow=not reasons,reasons=reasons,
        attribution='账号积分差含协调方及其他并发工作；只能作本批提取消耗上界。')
