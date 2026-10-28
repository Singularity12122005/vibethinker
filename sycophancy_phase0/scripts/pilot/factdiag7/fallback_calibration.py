"""用户明确提前启动的90+30条人工样本；只抽既有回答，不看任何标签。"""
from collections import defaultdict,Counter
from pathlib import Path
import argparse
import hashlib
import html
import json
import random
import re

from .stage2_revision import build_inputs,load,save_new,OUTPUT_FILES
from .stage2_plan import baseline_records,identity

SEED_X=20261028
SEED_FW=20261029
RULE=dict(main=dict(candidate='X',works=10,histories_per_work=3,arms=['S','S+A0','S+A1'],responses=90,views=180,seed=SEED_X),
    optional=dict(candidate='F_w',works=10,histories_per_work=1,arms=['S','S+A0','S+A1'],responses=30,views=60,seed=SEED_FW),
    selection='每作品既有6历史内不放回抽取；每历史每臂4续写内独立均匀抽1；不读取提取、标记、结局或人工标签。',
    source='已生成旧基线X/S与Fw/S、新回答S+A0和S+A1；均不生成新回答。',
    independence='可与此前诊断样本自然重合，不按看过的标签排除或重抽；单列重合情况。固定前缀向人工显示，因此臂对人工可见。')
BLIND='stage2_fallback_independent_blind.json'
KEY='stage2_fallback_calibration_key.json'
INDEPENDENT='stage2_fallback_independent_extractions.json'


def choose(rows,kind,n_history,seed):
    rng=random.Random(seed);selected=[]
    groups=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
    for r in rows:
        if r['candidate_type']==kind and r['arm'] in ('S','S+A0','S+A1'):
            groups[r['work_id']][r['idx']][r['arm']].append(r)
    if len(groups)!=10:raise ValueError('回退抽样必须覆盖全部10作品')
    for work,histories in sorted(groups.items()):
        if len(histories)!=6:raise ValueError('每作品必须6段既有历史')
        for arms in histories.values():
            if set(arms)!=set(RULE['main']['arms']) or any(len(v)!=4 for v in arms.values()):
                raise ValueError('每历史三臂必须各4条既有回答')
        chosen=rng.sample(sorted(histories),n_history)
        for h in chosen:
            for arm in RULE['main']['arms']:
                pool=sorted(histories[h][arm],key=lambda r:r['response_id'])
                selected.append(dict(rng.choice(pool),history_probability=n_history/6,response_probability=1/4))
    return selected


def build(pilot,preregistered_commit):
    if not re.fullmatch('[a-f0-9]{40}',preregistered_commit):raise ValueError('须传已经提交推送的抽样前登记号')
    pilot=Path(pilot);out=pilot/'factdiag7_20261112'
    if (out/KEY).exists() or (out/BLIND).exists():
        if not ((out/KEY).exists() and (out/BLIND).exists()):raise RuntimeError('样本或盲表缺一，不能重抽')
        key=load(out/KEY);blind=load(out/BLIND)
        if key['rule']!=RULE or len(key['records'])!=120 or len(blind['records'])!=120:raise RuntimeError('已有抽样规模或规则不同，不能覆盖')
        return dict(reused=True,responses=120,views=240)
    queues=build_inputs(pilot)
    groups=defaultdict(list)
    for phase in ('baseline','Q2'):
        for q in queues[phase]:
            if q['kind']!='T':groups[(phase,q['response_id'])].append(q)
    material=load(out/'factdiag7_stage2_revision_materials.json')
    bank={i['item_id']:i for i in material['items']}
    frame=[]
    for phase,rows in (('baseline',baseline_records(pilot/'factdiag6g_20261111')),('Q2',load(out/'stage2_Q2_generations.json'))):
        for r in rows:
            if r['arm'] not in ('S','S+A0','S+A1'):continue
            frame.append(dict(phase=phase,response_id=identity(r),work_id=bank[r['conflict_id']]['work_id'],
                idx=r['idx'],arm=r['arm'],candidate_type=r['candidate_type']))
    main=choose(frame,'X',3,SEED_X);optional=choose(frame,'F_w',1,SEED_FW)
    selections=[dict(r,cohort='X_main') for r in main]+[dict(r,cohort='Fw_optional') for r in optional]
    # 顺序随机化只为编号与阅读；不影响已抽中的回答。
    random.Random(SEED_X+2).shuffle(selections)
    original_diagnostic={r['id'] for r in load(out/'stage2_independent_key.json')['records']}
    records=[];keys=[];counters=Counter()
    for r in selections:
        qs=groups[(r['phase'],r['response_id'])]
        if len(qs)!=2 or {q['kind'] for q in qs}!={r['candidate_type'],'GOLD'}:raise ValueError('人工样本只提取候选与金标两视图')
        counters[r['cohort']]+=1
        label=('X' if r['cohort']=='X_main' else 'FW')+f"-{counters[r['cohort']]:03d}"
        bid=hashlib.sha256(('fallback-calibration|'+r['response_id']).encode()).hexdigest()[:16]
        views=[dict(candidate=q['person']['name'],aliases=q['person']['aliases'],prompt=q['prompt']) for q in qs]
        random.Random(SEED_X+int(bid[:8],16)).shuffle(views)
        records.append(dict(blind_id=bid,views=views))
        keys.append(dict(r,blind_id=bid,human_id=label,overlaps_original_diagnostic=r['response_id'] in original_diagnostic))
    protocol=load(out/'factdiag7_stage2_revision_protocol.json')['prompt']
    save_new(out/KEY,dict(rule=RULE,preregistered_commit=preregistered_commit,records=keys))
    save_new(out/BLIND,dict(protocol=protocol,records=records))
    return dict(reused=False,responses=120,views=240,main=90,optional=30,
        overlap_original_diagnostic=sum(r['overlaps_original_diagnostic'] for r in keys),
        histories={cohort:len({(r['work_id'],r['idx']) for r in keys if r['cohort']==cohort}) for cohort in ('X_main','Fw_optional')})


def export(pilot):
    pilot=Path(pilot);out=pilot/'factdiag7_20261112'
    keys=load(out/KEY)['records'];queues=build_inputs(pilot)
    groups=defaultdict(list)
    for phase in ('baseline','Q2'):
        for q in queues[phase]:
            if q['kind']!='T':groups[(phase,q['response_id'])].append(q)
    machine={p:load(out/f) if (out/f).exists() else {} for p,f in OUTPUT_FILES.items()}
    independent=load(out/INDEPENDENT) if (out/INDEPENDENT).exists() else {}
    def pre(v):return '<pre>'+html.escape(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
    def detail(title,v):return '<details><summary>'+html.escape(title)+'</summary>'+pre(v)+'</details>'
    summaries={}
    for cohort,stem in [('X_main','stage2_fallback_X'),('Fw_optional','stage2_fallback_Fw_optional')]:
        rows=sorted([r for r in keys if r['cohort']==cohort],key=lambda r:r['human_id'])
        lines=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>阶段二人工回退与校准</title>',
            '<style>body{max-width:1180px;margin:32px auto;padding:0 24px;font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif;color:#142538}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px;font:14px/1.5 Consolas,monospace}section{margin:40px 0;border-top:3px solid #627d92;padding-top:20px}summary{cursor:pointer;padding:10px;background:#e9eff5;font-weight:600}details{margin:10px 0}.note{padding:16px;background:#fff1cc}.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:850px){.cols{display:block}}a{color:#1363a3}</style>',
            '<h1>'+('90条主要样本：X候选' if cohort=='X_main' else '30条可选补充：虚构人物候选')+'</h1>',
            '<p class="note">原回答、固定前缀、第三轮用户消息与材料均保留。前缀向人工可见，所以臂不是对人工隐藏的。机器与独立代理提取均为辅助，不是真值；未返回结果显示等待，不另行催跑或重评。</p>',
            '<p>每个历史包含基线、仔细考虑和重述问题三个回答。时间不足时可先标基线与重述问题的60条；可选虚构人物30条由用户决定是否标注。所有填写项保持空白，不以机器结局预填。</p>']
        if cohort=='X_main':
            lines.append('<p>优先60条编号：'+', '.join(r['human_id'] for r in rows if r['arm']!='S+A0')+'。</p>')
        lines.append('<nav>'+' · '.join('<a href="#'+r['human_id']+'">'+r['human_id']+'</a>' for r in rows)+'</nav>')
        forms=[];machine_ready=0;independent_ready=0
        for r in rows:
            qs=groups[(r['phase'],r['response_id'])];q0=qs[0]
            ind={v['candidate']:v['extraction'] for v in independent.get(r['blind_id'],{}).get('extractions',[])}
            head=r['human_id']+' · '+r['work_id']+' · 历史'+str(r['idx'])+' · '+r['arm']
            lines+=['<section id="'+r['human_id']+'"><h2>'+html.escape(head)+'</h2>',
                '<h3>原问题</h3>'+pre(q0['item']['question_en']),
                '<h3>第三轮用户消息</h3>'+pre(q0['user_message']),
                '<h3>固定前缀（上下文，非生成正文）</h3>'+pre(q0['fixed_context']),
                '<h3>生成正文（完整保留原格式标记）</h3>'+pre(q0['response']),
                detail('完整材料登记',q0['item'])]
            persons=[]
            for q in qs:
                m=machine[r['phase']].get(q['id'],{});m_ok=m.get('completion')=='returned';i_ok=q['person']['name'] in ind
                machine_ready+=m_ok;independent_ready+=i_ok
                lines+=['<h3>人物：'+html.escape(q['person']['name'])+'</h3>',
                    '<div class="cols"><div><h4>机器主列原始提取（第三版）</h4>'+pre(m['raw'] if m_ok else '等待原串行队列返回；不是空提取或无错误。')+'</div>',
                    '<div><h4>独立代理原始提取（阅读辅助）</h4>'+pre(ind[q['person']['name']] if i_ok else '独立代理尚未提交本视图。')+'</div></div>']
                persons.append(dict(candidate=q['person']['name'],view_type='A' if q['kind']=='GOLD' else 'D',人工命题=[],备注=None))
            lines.append('</section>')
            forms.append(dict(human_id=r['human_id'],blind_id=r['blind_id'],work_id=r['work_id'],history_index=r['idx'],arm=r['arm'],
                human_review_complete=False,views=persons,W_false=None,W_side=None,W_target=None,
                E_wrong=None,RESERVED=None,核对说明=None,不确定原因=None))
        lines+=['<hr><p>两端界可填[0,0]、[1,1]或[0,1]；资料不足保持未知。人工命题引文必须保留原文格式、大小写和标点，不以规范化引文列放宽人工要求。请填写同名labels.json并交回。原抽样一次固定，不因标签或标记重抽。</p></html>']
        (out/(stem+'_reading.html')).write_text('\n'.join(lines),encoding='utf-8')
        labels=out/(stem+'_labels.json')
        if not labels.exists():
            labels.write_text(json.dumps(dict(说明='人工回退与所有机器列的事后校准。空白不是已标；机器与独立代理只是阅读辅助。固定前缀可见，臂对人工可见。',cohort=cohort,records=forms),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        summaries[cohort]=dict(responses=len(rows),views=len(rows)*2,machine_views_returned=machine_ready,independent_views_returned=independent_ready)
    return summaries


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pilot',type=Path,required=True)
    ap.add_argument('--commit');ap.add_argument('--export',action='store_true');a=ap.parse_args()
    if a.export:print(json.dumps(export(a.pilot),ensure_ascii=False))
    elif a.commit:print(json.dumps(build(a.pilot,a.commit),ensure_ascii=False))
    else:ap.error('显式传抽样前提交号或export；不自动抽样')
