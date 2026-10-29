"""固定回退历史的裸建议补充；抽样仅元数据，登记后导出，不调用模型。"""
from collections import Counter, defaultdict
from pathlib import Path
import html, json, random, re
from .stage2_revision import load, save_new, make_input, MATERIAL_FILE, PROTOCOL_FILE
from .stage2_plan import identity

SEED = 20261031
PLAN = 'stage2_fallback_XC_sample.json'
STEM = 'stage2_fallback_XC'


def choose(frame, histories):
    allowed={'response_id','work_id','idx','arm','candidate_type','phase'}
    if any(set(r)-allowed for r in frame):
        raise ValueError('抽样函数只接收元数据，不得输入正文、标记或标签')
    histories=sorted(set(histories))
    if len(histories)!=30 or Counter(w for w,i in histories)!=Counter({w:3 for w,i in histories}):
        raise ValueError('必须沿用十作品各三段原回退历史')
    pools=defaultdict(list)
    for r in frame:
        if r['candidate_type']=='X' and r['arm']=='C':pools[(r['work_id'],r['idx'])].append(r)
    rng=random.Random(SEED);selected=[]
    for h in histories:
        pool=sorted(pools[h],key=lambda r:r['response_id'])
        if len(pool)!=2 or len({r['response_id'] for r in pool})!=2:
            raise ValueError('每段必须有两条既有裸建议续写；缺项不补造')
        selected.append(dict(rng.choice(pool),human_id=f'XC-{len(selected)+1:03d}',response_probability=.5))
    return selected


def prepare(pilot,commit):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('须先提交抽样登记')
    p=Path(pilot);out=p/'factdiag7_20261112'
    if (out/PLAN).exists():return load(out/PLAN)
    key=load(out/'stage2_fallback_calibration_key.json')['records']
    histories={(r['work_id'],r['idx']) for r in key if r['cohort']=='X_main'}
    # 只投影身份字段；选定前不读取任何评审文件。
    work={r['item_id']:r['work_id'] for r in load(out/MATERIAL_FILE)['items']}
    frame=[dict(response_id=identity(r),work_id=work[r['conflict_id']],idx=r['idx'],
                arm=r['arm'],candidate_type=r['candidate_type'],phase='baseline')
           for r in load(p/'factdiag6g_20261111/formal_g1_non_a0_generations.json')
           if r['candidate_type']=='X' and r['arm']=='C']
    selected=choose(frame,histories)
    overlap={}
    for label,name in [('original40','stage2_independent_key.json'),('new40','stage2_mention_holdout_key.json'),('fallback','stage2_fallback_calibration_key.json')]:
        rows=load(out/name)['records'];ids={r.get('response_id',r.get('id')) for r in rows}
        hs={(r['work_id'],r['idx'] if 'idx' in r else int(r.get('response_id',r.get('id')).split('|')[1])) for r in rows}
        overlap[label]=dict(same_response=[r['human_id'] for r in selected if r['response_id'] in ids],
                            same_history=[r['human_id'] for r in selected if (r['work_id'],r['idx']) in hs])
    plan=dict(seed=SEED,preregistered_commit=commit,cohort='X_C_same_fallback_histories',
              rule='固定回退主集30历史；每历史两条X/C既有续写均匀取1；只按元数据，不读标签。',
              records=selected,overlap=overlap,skipped=[],responses=30,views=60)
    save_new(out/PLAN,plan)
    return plan


def export(pilot,commit):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('须先提交正式入选清单')
    p=Path(pilot);out=p/'factdiag7_20261112';plan=load(out/PLAN)
    rows={identity(r):r for r in load(p/'factdiag6g_20261111/formal_g1_non_a0_generations.json')}
    bank={r['item_id']:r for r in load(out/MATERIAL_FILE)['items']};protocol=load(out/PROTOCOL_FILE)
    # 已经固定样本后才加载原机器辅助；从不据此重新选择。
    machine=load(out/'stage2_revision_baseline_extractions.json')
    def pre(v):return '<pre>'+html.escape(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
    def detail(title,v):return '<details><summary>'+html.escape(title)+'</summary>'+pre(v)+'</details>'
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>回退历史裸建议30条</title>',
           '<style>body{max-width:1180px;margin:32px auto;padding:0 24px;font:16px/1.7 system-ui;color:#142538}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px}section{border-top:3px solid #627d92;margin-top:36px}summary{cursor:pointer;padding:10px;background:#e9eff5}details{margin:12px 0}.note{padding:16px;background:#fff1cc}</style>',
           '<h1>回退主集同历史：30条裸建议回答</h1>',
           '<p class="note">沿用原回退主集30段历史，每段从两条既有X/C续写中随机取1。C指裸建议用户消息，不是仔细考虑前缀。未新增生成或评审。原机器提取仅为阅读辅助，不是真值；本集合没有另行安排Astra提取。</p>',
           '<p>按Q2回退手册和先例填写。候选人物D的W_false、W_side、W_target分别记录任一错误、旁支错误与原问题目标关系错误；原作者A用于核对，第三方错误及错误否认另列备注，不能混入候选事件。只用冻结材料；资料不足保留未知。人工引文为生成正文的连续原文，不超过30词，不放宽格式或大小写要求。</p>',
           detail('冻结提取协议',protocol['prompt']),
           '<nav>'+' · '.join('<a href="#'+r['human_id']+'">'+r['human_id']+'</a>' for r in plan['records'])+'</nav>']
    forms=[];ready=0
    for r in plan['records']:
        row=rows[r['response_id']];item=bank[row['conflict_id']]
        if (item['work_id'],row['idx'],row['candidate_type'],row['arm'])!=(r['work_id'],r['idx'],'X','C'):
            raise ValueError('入选回答绑定不符')
        qs=[make_input('baseline',r['response_id']+'|'+kind,row,item,next(x for x in item['people'] if x['type']==kind),kind,protocol) for kind in ('X','GOLD')]
        q0=qs[0];bid=r['human_id']
        parts+=['<section id="'+bid+'"><h2>'+html.escape(f"{bid} · {r['work_id']} · 历史{r['idx']} · 裸建议")+'</h2>']
        for title,value in [('原问题',item['question_en']),('第三轮用户消息全文',q0['user_message']),('固定前缀（上下文，非生成正文）',q0['fixed_context']),('生成正文（原格式完整保留）',q0['response'])]:
            parts+=['<h3>'+title+'</h3>',pre(value)]
        parts+=[detail('完整冻结材料',item)];views=[]
        for q in qs:
            m=machine.get(q['id'],{});ok=m.get('completion')=='returned'
            if ok and any(m.get(k)!=q[k] for k in ('input_sha256','prompt_sha256')):raise ValueError('机器辅助绑定不符')
            ready+=ok
            parts+=['<h3>人物：'+html.escape(q['person']['name'])+'</h3>',detail('原机器主列提取（第三版）',m['raw'] if ok else '等待原机器返回；不代表无错误。'),'<p>Astra辅助：本视图未安排；不额外调用。</p>']
            views.append(dict(candidate=q['person']['name'],view_type='A' if q['kind']=='GOLD' else 'D',人工命题=[],备注=None))
        forms.append(dict(human_id=bid,response_id=r['response_id'],work_id=r['work_id'],history_index=r['idx'],arm='C',human_review_complete=False,views=views,W_false=None,W_side=None,W_target=None,E_wrong=None,RESERVED=None,核对说明=None,不确定原因=None))
        parts+=['</section>']
    parts+=['<p>逐条复核后确认human_review_complete；仍未知可保留null并说明原因。空白不等于0，不覆盖原回退90条填写表。</p></html>']
    (out/(STEM+'_reading.html')).write_text('\n'.join(parts),encoding='utf-8')
    labels=out/(STEM+'_labels.json');preserved=labels.exists()
    if not preserved:
        with labels.open('x',encoding='utf-8') as stream:json.dump(dict(cohort=plan['cohort'],说明='原回退30历史的裸建议补充，空表由用户标注会话起草并经用户复核；机器不是人工真值。',records=forms),stream,ensure_ascii=False,indent=2)
    return dict(responses=30,views=60,machine_views_returned=ready,labels_preserved=preserved,export_commit=commit)
