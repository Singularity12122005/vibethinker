"""干预修订二的新40留出；完成重提示后才能抽样，不计算分臂关系量。"""
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import random

from .stage2_revision import load,save_new,validate_freeze,OUTPUT_FILES
from .mention_reprompt import PLAN,OUTPUT,require_original_complete,next_attempt
from .mention_diagnostic import classify

SEED=20261028
BLIND='stage2_mention_holdout_blind.json'
KEY='stage2_mention_holdout_key.json'
INDEPENDENT='stage2_mention_holdout_extractions.json'
RULE=dict(new_holdout=40,original_diagnostic_in_gate=0,works=10,new_per_work=4,
    old_per_work=2,new_response_per_work=2,seed=SEED,
    gate='新40固定分母；任方未知或缺失不一致；主列80%，次列仅并列敏感性分析。',
    sampling='排除原40；作品顺序随机打乱，旧三格与新四格按2*i+j轮换；格内等概率抽样，不看标记或标签。')


def ready(pilot):
    require_original_complete(pilot)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:args=(proc/'cmdline').read_bytes().split(b'\0')
        except OSError:continue
        if b'scripts.pilot.factdiag7.mention_reprompt' in args:
            raise RuntimeError('重提示仍活动，不能抽留出或将其在途结果当永久缺失')
    out=Path(pilot)/'factdiag7_20261112'
    plan=load(out/PLAN)
    saved=load(out/OUTPUT) if (out/OUTPUT).exists() else {}
    if set(saved)!={r['id'] for r in plan['entries']}:
        raise RuntimeError('重提示尚未完整派发')
    if any(next_attempt(r) for r in saved.values()):
        raise RuntimeError('不可解析例外重试尚未执行完毕')
    return plan,saved


def choose(frame,excluded,seed=SEED):
    rng=random.Random(seed);works=sorted({r['work_id'] for r in frame})
    if len(works)!=10:raise ValueError('留出抽样要求10作品')
    rng.shuffle(works)
    cells={'baseline':[('X','S'),('F_w','S'),('X','C')],
           'Q2':[('X','A0'),('F_w','A1'),('X','A1'),('F_w','A0')]}
    selected=[]
    for i,work in enumerate(works):
        for phase in ('baseline','Q2'):
            for j in (0,1):
                kind,arm=cells[phase][(2*i+j)%len(cells[phase])]
                pool=sorted((r for r in frame if r['response_id'] not in excluded and
                    (r['work_id'],r['phase'],r['candidate_type'],r['arm'])==(work,phase,kind,arm)),key=lambda r:r['response_id'])
                if not pool:raise ValueError('留出抽样格不足，不换格或补生成')
                selected.append(dict(rng.choice(pool),probability_within_cell=1/len(pool),cohort='new_holdout'))
    if len(selected)!=40 or len({r['response_id'] for r in selected})!=40:raise ValueError('留出数量或唯一性错误')
    return selected


def build(pilot):
    pilot=Path(pilot);out=pilot/'factdiag7_20261112'
    ready(pilot)
    if (out/BLIND).exists() or (out/KEY).exists():
        if not ((out/BLIND).exists() and (out/KEY).exists()):raise RuntimeError('盲表与映射缺一，不重抽')
        blind,key=load(out/BLIND),load(out/KEY)
        if len(blind['records'])!=40 or len(key['records'])!=40 or key['rule']!=RULE:raise RuntimeError('已有留出表不是此次40条规则')
        return dict(n=40,reused=True)
    _,queues=validate_freeze(pilot)
    grouped=defaultdict(list)
    for phase in ('baseline','Q2'):
        for q in queues[phase]:grouped[(phase,q['response_id'])].append(q)
    frame=[]
    for (phase,key),qs in grouped.items():
        candidate=next(q['kind'] for q in qs if q['kind'] not in ('GOLD','T'))
        frame.append(dict(response_id=key,phase=phase,work_id=qs[0]['work_id'],candidate_type=candidate,
            arm=qs[0]['arm'].removeprefix('S+') if phase=='Q2' else qs[0]['arm']))
    old=load(out/'stage2_independent_key.json')['records'];excluded={r['id'] for r in old}
    if len(old)!=40 or len(excluded)!=40:raise ValueError('原40诊断编号有误')
    selected=choose(frame,excluded);rng=random.Random(SEED+2);rng.shuffle(selected)
    records=[];keys=[]
    for row in selected:
        bid=hashlib.sha256(('mention-holdout40|'+row['response_id']).encode()).hexdigest()[:16]
        views=[dict(candidate=q['person']['name'],aliases=q['person']['aliases'],prompt=q['prompt'])
               for q in grouped[(row['phase'],row['response_id'])]]
        rng.shuffle(views)
        records.append(dict(blind_id=bid,views=views));keys.append(dict(row,blind_id=bid))
    if sum(len(r['views']) for r in records)!=100:raise ValueError('40条应对应100人物视图')
    save_new(out/BLIND,dict(protocol=load(out/'factdiag7_stage2_revision_protocol.json')['prompt'],records=records))
    save_new(out/KEY,dict(rule=RULE,records=keys))
    return dict(n=40,views=100,reused=False)


def column_extraction(q,original,reprompt,selected):
    """返回适配副本：不改原结果或重提示结果；未重提示项在次列复用。"""
    values={}
    for column in ('original','reprompt'):
        record=original
        if column=='reprompt' and q['id'] in selected:
            record=reprompt.get(q['id'],{}).get('attempts',[{}])[-1]
        e=deepcopy(record.get('extraction',{})) if record.get('completion')=='returned' else {}
        if not e:e=dict(parse_status='UNPARSEABLE',claims=[],extraction_flags=[])
        d=classify(e,q['response'],q['person'])
        flags=set(e.get('extraction_flags',[]))
        # 独立新标记不覆盖原标记；两列同样扩大受影响事件的未知范围。
        if d['category'] in ('INCONSISTENT','MISS_STRICT','MISS_SURNAME') or (
            q['id'] in selected and e.get('mention')=='ABSENT'):
            flags.add('MENTION_MISMATCH')
        if d['category']=='PHANTOM':flags.add('MENTION_FIELD_INVALID')
        e['extraction_flags']=sorted(flags)
        values[column]=e
    return values


def compare(pilot):
    # 只比较新40门槛；本入口不输出任何臂/格的关系率。
    from .relations_v3 import parse,map_evidence,aggregate
    from .revision_review import agreement
    from .revision_runtime import atomic_save
    pilot=Path(pilot);out=pilot/'factdiag7_20261112'
    plan,reprompt=ready(pilot);selected={r['id'] for r in plan['entries']}
    _,queues=validate_freeze(pilot)
    key=load(out/KEY)['records'];blind={r['blind_id']:r for r in load(out/BLIND)['records']}
    independent=load(out/INDEPENDENT)
    if len(key)!=40 or set(independent)!=set(blind) or set(blind)!={r['blind_id'] for r in key}:
        raise ValueError('新40独立提取尚未齐全，不能判门槛')
    saved={p:load(out/OUTPUT_FILES[p]) for p in ('baseline','Q2')}
    groups=defaultdict(list)
    for phase in saved:
        for q in queues[phase]:groups[(phase,q['response_id'])].append(q)
    pairs=defaultdict(list);private=[]
    for row in key:
        bid=row['blind_id'];qs=groups[(row['phase'],row['response_id'])]
        rec=independent[bid]
        if rec['blind_id']!=bid or [e['candidate'] for e in rec['extractions']]!=[v['candidate'] for v in blind[bid]['views']]:
            raise ValueError('独立人物顺序或编号不符')
        entries={e['candidate']:e['extraction'] for e in rec['extractions']}
        if len(entries)!=len(qs) or set(entries)!={q['person']['name'] for q in qs}:raise ValueError('独立人物集合不符')
        mapped={label:{} for label in ('original','reprompt','independent')}
        for q in qs:
            original=saved[row['phase']][q['id']]
            if original['input_sha256']!=q['input_sha256']:raise ValueError('原列绑定不符')
            cols=column_extraction(q,original,reprompt,selected)
            e=parse(json.dumps(entries[q['person']['name']],ensure_ascii=False),q['response'],q['item'],person=q['person'],user_message=q['user_message'])
            # 独立提取也用同一姓名有效性检查，不对它运行补读提示。
            e=column_extraction(q,{'completion':'returned','extraction':e},{},set())['original']
            for label,value in dict(cols,independent=e).items():mapped[label][q['kind']]=map_evidence(value,q['item'],q['person'])
        candidate=next(q['kind'] for q in qs if q['kind'] not in ('GOLD','T'))
        events={label:aggregate(v[candidate],v['GOLD'],technical_failure=qs[0]['technical_failure'],execution_no_tools=True)['W_false'] for label,v in mapped.items()}
        for column in ('original','reprompt'):pairs[column].append((events[column],events['independent']))
        private.append(dict(blind_id=bid,events=events))
    stats={column:agreement(value) for column,value in pairs.items()}
    report=dict(n=40,views=100,threshold=.8,primary='original',secondary='reprompt',branch='B',
        status='通过' if stats['original']['raw_agreement']>=.8 else '未通过',columns=stats,
        primary_passed=stats['original']['raw_agreement']>=.8,
        reviewer='无上下文独立代理，非人工；原40仅既有诊断，未并入门槛。',
        secondary_label='事后代码侧纠正',
        rule='未知/缺失计不一致，全40分母；主列决定报告与回退，次列不替换主列。')
    atomic_save(out/'stage2_mention_holdout_comparison_private.json',private)
    atomic_save(out/'stage2_mention_holdout_review.json',report)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pilot',type=Path,required=True)
    ap.add_argument('--compare',action='store_true');a=ap.parse_args()
    print(json.dumps(compare(a.pilot) if a.compare else build(a.pilot),ensure_ascii=False))
