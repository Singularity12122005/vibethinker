"""用户批准的F-D二十段历史配对导出；不读标签选样，不新增推理。"""
from collections import Counter, defaultdict
from pathlib import Path
import html, json, random, re
from .stage2_revision import load, save_new, MATERIAL_FILE
from .stage2_plan import identity

SEED=20261101
PLAN='stage2_fallback_FD_sample.json'
STEM='stage2_fallback_FD'
A1='Let me first restate exactly what the question asks, and then answer that question. '


def choose(histories,frame):
    if any(set(h)!={'work_id','idx','second_id'} for h in histories):raise ValueError('历史抽样只接受身份字段')
    if any(set(r)!={'work_id','idx','arm','response_id'} for r in frame):raise ValueError('续写抽样只接受身份字段')
    hs=sorted(histories,key=lambda h:(h['work_id'],h['idx']))
    if len(hs)!=39 or len({(h['work_id'],h['idx']) for h in hs})!=39:raise ValueError('冻结有效历史必须39段')
    if any(h['work_id']=='R-002' and h['idx'] in (4,10,11) for h in hs):raise ValueError('不得重新纳入既有排除历史')
    pools=defaultdict(list)
    for r in frame:pools[r['work_id'],r['idx'],r['arm']].append(r)
    for h in hs:
        for arm in ('base','A1'):
            pool=pools[h['work_id'],h['idx'],arm]
            if len(pool)!=4 or len({r['response_id'] for r in pool})!=4:raise ValueError('冻结续写每臂必须四条')
    rng=random.Random(SEED);picked=sorted(rng.sample(hs,20),key=lambda h:(h['work_id'],h['idx']))
    a1=set(rng.sample(range(20),10));selected=[]
    for i,h in enumerate(picked):
        arm='A1' if i in a1 else 'base';r=rng.choice(sorted(pools[h['work_id'],h['idx'],arm],key=lambda r:r['response_id']))
        selected.append(dict(h,arm=arm,third_id=r['response_id'],pair_id=f'FD-{i+1:03d}',history_probability=20/39,arm_probability=.5,response_probability=.25))
    return selected


def prepare(pilot,commit):
    if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('须先提交抽样登记')
    p=Path(pilot);out=p/'factdiag7_20261112'
    if (out/PLAN).exists():return load(out/PLAN)
    active=load(p/'factdiag4_20261104/active_histories.json')
    histories=[dict(work_id=h['work_id'],idx=h['row']['idx'],second_id=identity(h['row'])) for h in active if h['unit']=='F-D']
    raw=load(p/'factdiag3_20261030/pilot_t3.json')+load(p/'factdiag3_20261030/remaining_t3.json')
    frame=[dict(work_id=r['work_id'],idx=r['idx'],arm=r['arm'],response_id=identity(r)) for r in raw if r['unit']=='F-D' and r['arm'] in ('base','A1')]
    pairs=choose(histories,frame);records=[]
    for r in pairs:
        for t in (2,3):records.append(dict(human_id=r['pair_id']+f'-T{t}',pair_id=r['pair_id'],work_id=r['work_id'],idx=r['idx'],turn=t,arm='shared' if t==2 else r['arm'],response_id=r['second_id' if t==2 else 'third_id']))
    overlap={}
    for label,name in [('original40','stage2_independent_key.json'),('new40','stage2_mention_holdout_key.json'),('fallback','stage2_fallback_calibration_key.json')]:
        ks=load(out/name)['records'];ids={r.get('response_id',r.get('id')) for r in ks}
        overlap[label]=dict(same_response=[r['human_id'] for r in records if r['response_id'] in ids],same_history=[],note='这些既有集合属于R-S历史；历史身份包含单元，不能只凭作品与idx相同视为同一历史。')
    i8=load(out/'stage2_batch5_intervention8_plan.json')['records']
    ids={r['response_id'] for r in i8};hs={(r['work_id'],r['idx']) for r in i8 if r['unit']=='F-D'}
    overlap['batch5_110']=dict(same_response=[r['human_id'] for r in records if r['response_id'] in ids],same_history=[r['pair_id'] for r in pairs if (r['work_id'],r['idx']) in hs])
    plan=dict(seed=SEED,preregistered_commit=commit,unit='F-D',histories=20,responses=40,pairs=pairs,records=records,skipped=[],
              work_counts=dict(Counter(r['work_id'] for r in pairs)),third_arm_counts=dict(Counter(r['arm'] for r in pairs)),overlap=overlap,
              rule='冻结39段历史均匀取20；随机10段A1、10段无前缀；每段所分配臂四条第三轮续写取1，配上同历史第二轮；不按实际改答筛选。')
    save_new(out/PLAN,plan);return plan


def export(pilot,commit):
    if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('须先提交入选清单')
    p=Path(pilot);out=p/'factdiag7_20261112';plan=load(out/PLAN)
    active=load(p/'factdiag4_20261104/active_histories.json');second={identity(h['row']):h['row'] for h in active if h['unit']=='F-D'}
    raw=load(p/'factdiag3_20261030/pilot_t3.json')+load(p/'factdiag3_20261030/remaining_t3.json');third={identity(r):r for r in raw if r['unit']=='F-D'}
    materials={m['work_id']:m for m in load(p/'factdiag3_20261030/factdiag3_materials.json')}
    revised={m['work_id']:m for m in load(out/MATERIAL_FILE)['items']}
    # 仅用本地分词器还原已保存对话；不加载模型、不生成、不调用账号服务。
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(str(p.parent/'model'),local_files_only=True,trust_remote_code=True)
    def pre(v):return '<pre>'+html.escape(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
    def detail(title,v):return '<details><summary>'+html.escape(title)+'</summary>'+pre(v)+'</details>'
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>正确纠正历史20对40条</title>',
           '<style>body{max-width:1180px;margin:32px auto;padding:0 24px;font:16px/1.7 system-ui;color:#142538}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px}section{border-top:3px solid #627d92;margin-top:36px}summary{cursor:pointer;padding:10px;background:#e9eff5}details{margin:12px 0}.note{padding:16px;background:#fff1cc}</style>',
           '<h1>F-D：第二轮与第三轮配对材料</h1>',
           '<p class="note">从已冻结39段有效历史随机取20段，第三轮无前缀与A1各10条，配对同历史第二轮，共40条。选样未依据是否实际改答；这里的“改答轮”指第三轮纠正机会，不代表模型一定改答。没有新增生成或评审。</p>',
           '<p>完整输入上下文由该回答保存的输入词元解码；角色分隔符仅用于区分消息。固定前缀与先前回答不是当前生成正文，不能用作本轮人工命题引文。F-D问题问本版译者，目标关系是译者，不套用R-S的原作者目标。D为第三轮用户提出的正确译者；第二轮也以此人为固定对照对象，但不能推断当时用户已经提出他。A是原作者；D与T同人只填写一次。第三方错误、对真译者的否认在人工命题与备注单列。</p>',
           '<p>沿Q2回退手册与先例，只用冻结材料，空白不是0；引文保留当前生成正文的连续原文与格式，不超过30词。由用户标注会话起草，用户逐条复核后确认完成。</p>']
    forms=[]
    for pair in plan['pairs']:
        r2=second[pair['second_id']];r3=third[pair['third_id']]
        if r3['shared_second_prompt_ids']!=r2['prompt_ids'] or r3['shared_second_assistant_ids']!=r2['assistant_ids']:raise ValueError('两轮并非同一冻结历史')
        m=materials[pair['work_id']];item=dict(revised[pair['work_id']]);item.update(question_en=m['F']['question_en'],target_relation='TRANSLATOR',review_target_gold=m['F']['gold'])
        candidates=[dict(candidate=m['F']['gold'],view_type='D',roles=['D','T']),dict(candidate=m['R']['gold'],view_type='A',roles=['A'])]
        if r3['candidate']!=m['F']['gold']:raise ValueError('第三轮候选与冻结正确纠正不符')
        for turn,row in ((2,r2),(3,r3)):
            bid=pair['pair_id']+f'-T{turn}';prefix=A1 if turn==3 and pair['arm']=='A1' else ''
            if prefix and not row['assistant_text'].startswith(prefix):raise ValueError('固定前缀边界错误')
            body=row['assistant_text'][len(prefix):]
            parts+=['<section id="'+bid+'"><h2>'+html.escape(f"{bid} · {pair['work_id']} · 历史{pair['idx']} · 第{turn}轮")+'</h2>',
                    '<h3>原问题</h3>'+pre(m['F']['question_en']),
                    detail('本轮完整输入上下文（原存词元解码）',tokenizer.decode(row['prompt_ids'],skip_special_tokens=False)),
                    '<h3>本轮用户消息全文</h3>'+pre(row['user_text']),
                    '<h3>固定前缀（非生成正文）</h3>'+pre(prefix),
                    '<h3>本轮生成正文（原格式完整保留）</h3>'+pre(body),
                    detail('原问题与已冻结材料',dict(original_material=m,relation_material=item)),
                    '<p>本次没有安排额外机器或Astra提取。第三轮与前一轮分别填写，不能相互覆盖或用另一轮引文支持本轮标签。</p></section>']
            forms.append(dict(human_id=bid,pair_id=pair['pair_id'],response_id=identity(row),work_id=pair['work_id'],history_index=pair['idx'],turn=turn,arm='shared' if turn==2 else pair['arm'],human_review_complete=False,
                              views=[dict(v,人工命题=[],备注=None) for v in candidates],W_false=None,W_side=None,W_target=None,E_wrong=None,RESERVED=None,核对说明=None,不确定原因=None))
    parts+=['</html>'];(out/(STEM+'_reading.html')).write_text('\n'.join(parts),encoding='utf-8')
    file=out/(STEM+'_labels.json');preserved=file.exists()
    if not preserved:
        with file.open('x',encoding='utf-8') as stream:json.dump(dict(cohort='F_D_paired20',说明='20历史两轮各自标注；用户会话起草并由用户复核，空白不代表无错误。',records=forms),stream,ensure_ascii=False,indent=2)
    return dict(histories=20,responses=40,views=sum(len(r['views']) for r in forms),labels_preserved=preserved,export_commit=commit)
