"""只汇总已经完成的G1条件；按既定权重、缺失界与作品重抽报告。"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse
import numpy as np
from core import load,save,rate,weighted,avg,difference,SEED,ideal_event,exact_role_event
from screen import identity
from joint_data import outcomes


def bootstrap(values):
    values=[v for v in values if v is not None]
    # 单作品没有作品间重抽信息；全零/全一不输出貌似精确的退化区间。
    if len(values)<2 or all(v==0 for v in values) or all(v==1 for v in values):return None
    rng=np.random.default_rng(SEED);a=np.array(values,dtype=float)
    samples=a[rng.integers(0,len(a),size=(2000,len(a)))].mean(axis=1)
    return np.quantile(samples,[.025,.975]).tolist()


def measure(rows,event):
    groups=defaultdict(list)
    for row in rows:groups[(row['work_id'],row['history_id'])].append(row[event])
    histories=[dict(work_id=w,history_id=h,value=rate(v)) for (w,h),v in groups.items()]
    works=defaultdict(list)
    for h in histories:works[h['work_id']].append(h['value'])
    estimate=weighted(histories,'value')
    estimate['counts']=rate([r[event] for r in rows])
    estimate['work_equal']['ci95']=bootstrap([avg([v['point'] for v in vs]) for vs in works.values()])
    estimate['per_work']=[dict(work_id=w,histories=len(vs),point=avg([v['point'] for v in vs]),
        bounds=[avg([v['bounds'][j] for v in vs]) for j in (0,1)]) for w,vs in sorted(works.items())]
    return estimate


def paired(rows,left,right,event):
    groups=defaultdict(lambda:defaultdict(list))
    for r in rows:
        if r['arm'] in (left,right):groups[(r['work_id'],r['history_id'])][r['arm']].append(r[event])
    histories=[]
    for (w,h),arms in groups.items():
        if set(arms)!={left,right}:raise RuntimeError('配对条件不完整')
        histories.append(dict(work_id=w,history_id=h,value=difference(rate(arms[left]),rate(arms[right]))))
    result=weighted(histories,'value');works=defaultdict(list)
    for h in histories:works[h['work_id']].append(h['value']['point'])
    result['work_equal']['ci95']=bootstrap([avg(v) for v in works.values()])
    return result


def summarize(out):
    plan=load(out/'factdiag6g_materials.json')['plan'];items={i['item_id']:i for i in plan['items']}
    rows=load(out/'formal_g1_non_a0_generations.json');labels=load(out/'formal_g1_non_a0_labels.json')
    if len(rows)!=plan['counts']['g1_non_a0']:raise RuntimeError('G1非A0未完成，不汇总部分项目')
    features={r['history_id']+'|'+r['candidate_type']:r['values'] for r in load(out/'common_features.json')['rows']}
    data=[];mismatch=[]
    for row in rows:
        item=items[row['conflict_id']];c=next(v for v in item['candidates'] if v['type']==row['candidate_type']);key=identity(row)
        stance=labels['stance'][key]['result'];role=labels['role'][key]['result']
        prop=(labels['proposition'][key]['result'] or {}).get('label') if c.get('proposition') else 'N/A'
        value=outcomes(row,item,c,row['original'],role,prop)
        f=features[row['source_history_id']+'|'+c['type']]
        bad=row['truncated'] or row['looped'];ident=value['identity'];mapped=value['role']
        d=dict(work_id=row['work_id'],history_id=row['source_history_id'],candidate_type=c['type'],
            arm=row['arm'],exposed=f['exposed'],adopt=ident['adopt'],correct=ident['correct'],
            role=mapped,role_true=None if bad else exact_role_event(mapped),
            role_false=None if bad or mapped in (None,'UNKNOWN','TRUE_ROLE_COARSE','OTHER') else int(mapped=='FALSE_ROLE'),
            proposition=value['proposition'],proposition_deny=None if bad or prop in (None,'UNJUDGEABLE','N/A') else int(prop=='DENY'),
            role_denied=None if bad or mapped in (None,'UNKNOWN','TRUE_ROLE_COARSE','OTHER') else int(mapped=='DENIED'),
            ideal=ideal_event(ident['correct'],value['proposition']),
            stance=None if bad or stance.get('unjudgeable') else stance.get('stance'),
            final_identity=ident['category'])
        if d['adopt'] is not None and d['stance'] is not None and d['adopt']!=int(d['stance']=='USER'):
            mismatch.append(dict(id=key,candidate_type=c['type'],arm=row['arm'],identity=d['final_identity'],stance=d['stance']))
        data.append(d)
    tables=[]
    for scope in ('unexposed','all'):
        selected=[r for r in data if scope=='all' or not r['exposed']]
        for kind in ('T','d_T','I','C','X','F_w'):
            block=[r for r in selected if r['candidate_type']==kind]
            if not block:continue
            table=dict(scope=scope,candidate_type=kind,arms={})
            for arm in sorted({r['arm'] for r in block}):
                a=[r for r in block if r['arm']==arm]
                metrics={k:measure(a,k) for k in ('adopt','correct','role_true','role_false','role_denied')}
                if kind in ('T','d_T','I'):
                    metrics.update({k:measure(a,k) for k in ('proposition_deny','ideal')})
                accepted=[r for r in a if r['adopt']==1]
                # 这里只列原始交叉计数，不能删除零事件历史后再称作原总体的作品等权条件率。
                metrics['roles_among_adoptions']=dict(counts=dict(Counter(str(r['role']) for r in accepted)))
                table['arms'][arm]=metrics
            if 'C' in table['arms']:table['pressure_minus_suggestion']=paired(block,'S','C','adopt')
            if 'S+A1' in table['arms']:table['pressure_minus_A1']=paired(block,'S','S+A1','adopt')
            tables.append(table)
    result=dict(scope='G1非A0已完整；只用冻结定义，不改标签或后续实验。独立盲审尚未完成。',
        tables=tables,identity_stance_disagreements=mismatch)
    a0=out/'formal_g1_a0_generations.json'
    if a0.exists():
        sampled=load(a0);result['A0_completed']=len(sampled)
        if len(sampled)==plan['counts']['g1_a0']:
            a0data=[]
            for r in sampled:
                item=items[r['conflict_id']];c=next(c for c in item['candidates'] if c['type']==r['candidate_type'])
                ident=outcomes(r,item,c,r['original'],None,'N/A')['identity']
                a0data.append(dict(work_id=r['work_id'],history_id=r['source_history_id'],adopt=ident['adopt'],arm='S+A0'))
            baseline=[r for r in data if r['candidate_type']=='T' and r['arm']=='S']
            result['A0']=dict(final_identity_only=True,rate=measure(a0data,'adopt'),
                pressure_minus_A0=paired([*baseline,*a0data],'S','S+A0','adopt'))
    save(out/'g1_completed_results.json',result)
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path)
    result=summarize(ap.parse_args().out)
    for table in result['tables']:
        print(table['scope'],table['candidate_type'],{arm:v['adopt']['work_equal'] for arm,v in table['arms'].items()},flush=True)
    if 'A0' in result:print('A0',result['A0'],flush=True)
