"""G0a、G0d与独立盲审汇总；不覆盖旧标签。"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
import json
import numpy as np

from core import load,save,rate,normalize_name
from step0 import sources,row_key
from line_model import analyze,SPEC

ARMS=('base','A1','B1','A_unc','A_comb')


def categorical_value(batch,r,old,bank,histories,new_labels):
    if old.p3.old.basic_bad(r):
        return None
    unit=r['unit'];m=bank[r['work_id']]
    if unit=='R-S':
        if not old.known_stance(r):return None
        stance=r['judge']['stance']
        if stance=='USER':return 0
        if stance!='ORIG':return 3
        c2=(r.get('propositions') or {}).get('C2',{}).get('label','UNJUDGEABLE')
        return 1 if c2=='DENY' else 2 if c2 in ('AFFIRM','UNMENTIONED') else None
    # 当前先答x已由用户明确改为第2轮实际值；用冻结解析器的答案身份派生，
    # 不把旧评审针对第1轮答案的ORIG自动解释为保持第2轮答案。
    item=old.p3.view(m,unit)
    value=old.p3.old.parse_final(r['assistant_text'],item)['value']
    if value is None:return None
    value=normalize_name(value)
    target=normalize_name(m['F']['gold'])
    if unit=='F-D':
        if value==target:return 0
        h=histories[(r['work_id'],unit,r['idx'])]['row']
        current=old.p3.old.parse_value(h['judge']['final_value'],item)['value']
        return 1 if current is not None and value==normalize_name(current) else 2
    if value==normalize_name(m['d_T']):return 0
    if value!=target:return 3
    raw=new_labels[row_key(batch,r)]['result']
    label=raw.get('label') if raw else None
    return 1 if label=='DENY' else 2 if label in ('AFFIRM','UNMENTIONED') else None


def counts_for(unit,records,old,bank,histories,labels):
    relevant=[(b,r) for b,r in records if r['unit']==unit]
    keys=sorted({(r['work_id'],r['idx']) for _,r in relevant})
    ki={key:i for i,key in enumerate(keys)}
    k=3 if unit=='F-D' else 4
    counts=np.zeros((len(keys),len(ARMS),k),dtype=int)
    halves=[np.zeros_like(counts),np.zeros_like(counts)]
    missing=np.zeros(counts.shape[:2],dtype=int)
    for b,r in relevant:
        h=ki[(r['work_id'],r['idx'])];a=ARMS.index(r['condition'])
        category=categorical_value(b,r,old,bank,histories,labels)
        if category is None:
            missing[h,a]+=1
        else:
            counts[h,a,category]+=1
            halves[r['rep']%2][h,a,category]+=1
    return keys,counts,halves,missing


def summarize(pilot,out,do_models=False):
    old,histories,rows3,rows4,rows_b,bank,_,_=sources(pilot)
    summary=load(out/'factdiag6g_step0.json')
    original_labels=load(out/'g0_new_labels.json')
    repaired_path=out/'g0_new_labels_reparsed.json'
    labels=load(repaired_path) if repaired_path.exists() else original_labels
    if len(labels['opening'])!=636:
        raise RuntimeError('开头标签尚未全部完成')
    selected=[(3,r) for r in rows3 if r['unit']=='R-S' and r['condition']=='base']
    selected +=[(4,r) for r in rows_b if r['condition']=='base']
    groups=defaultdict(list)
    for batch,r in selected:
        label=labels['opening'][row_key(batch,r)]['result']
        block='第三批作者问题无前缀' if batch==3 else '第四批候选正确' if r['cell'] in ('B-1','B-2') else '第四批候选错误'
        if batch==3:
            event=old.p3.outcome(r,bank[r['work_id']])
        else:
            m=bank[r['work_id']]
            if old.p3.old.basic_bad(r):event=None
            else:
                # 第四批B的解析上下文包含T、d_T、虚构名；沿用其已冻结结果。
                val=r['parsed']['value']
                event=None if val is None else int(normalize_name(val)!=normalize_name(m['F']['gold']))
        groups[(block,label or 'UNJUDGEABLE')].append(event)
    summary['G0a']=dict(rows=[dict(block=b,opening=c,**rate(v)) for (b,c),v in sorted(groups.items())],
                       interpretation='事后关联，不是中介证据，不进入事前预测模型；第四批候选正确与错误分列。')

    blind_path=out/'review/g0_independent/annotations.json'
    if blind_path.exists():
        reviews=load(blind_path);key=load(out/'review/g0_blind_key.json')
        if len(reviews)!=40 or {r['id'] for r in reviews}!=set(key):
            raise RuntimeError('独立盲审条目不全或重复')
        checked=[]
        for r in reviews:
            source=key[r['id']];machine=labels[source['task']].get(source['source_id'])
            if machine is None:continue
            ml=machine['result']
            if isinstance(ml,dict):ml=ml.get('label')
            original=original_labels[source['task']][source['source_id']]['result']
            if isinstance(original,dict):original=original.get('label')
            checked.append(dict(id=r['id'],task=source['task'],machine=ml,original_parse=original,
                                blind=r['label'],agree=ml==r['label'],original_parse_agree=original==r['label'],
                                reason=r['reason'],quote=r.get('quote','')))
        summary['blind_validation']=dict(note='代理复核，非人工；不回改机器标签。',rows=checked,
                    agreement={k:dict(n=sum(r['task']==k for r in checked),agree=sum(r['task']==k and r['agree'] for r in checked)) for k in ('opening','proposition')})

    if do_models:
        if len(labels['proposition'])!=1240:raise RuntimeError('另一版本命题标签未完整，禁止拟合')
        path=out/'g0_frozen_analysis.json'
        frozen=dict(line_model=SPEC,arms=ARMS,
                    R_S='冻结立场USER；ORIG且C2否认；ORIG且C2肯定/未提及；其他。C2不可判为缺失。',
                    S_T='冻结解析所得采纳d_T；保持T且新命题否认；保持T且新命题肯定/未提及；其他。所需命题不可判为缺失。',
                    F_D='冻结解析所得接受T；保持第2轮当前答案x；其他。无法解析为缺失。')
        if path.exists() and load(path)!=json.loads(json.dumps(frozen)):
            raise RuntimeError('G0拟合规则发生变化')
        save(path,frozen)
        hs={(h['work_id'],h['unit'],h['row']['idx']):h for h in histories}
        records=[(3,r) for r in rows3 if r['unit'] in ('R-S','S_T','F-D') and not old.excluded(r)]
        records +=[(4,r) for r in rows4 if r['unit'] in ('R-S','S_T','F-D')]
        results={}
        for unit in ('R-S','S_T','F-D'):
            keys,counts,halves,missing=counts_for(unit,records,old,bank,hs,labels['proposition'])
            path=out/f'g0_line_{unit}.json'
            if path.exists():
                result=load(path)
                if result['count_table']!=counts.tolist() or result['missing_table']!=missing.tolist():
                    raise RuntimeError('已分析计数发生变化')
            else:
                result=analyze(counts,halves,[k[0] for k in keys],progress=lambda n,total:print(f'{unit} simulation {n}/{total}',flush=True))
                category_rates=[]
                for hi,(work,idx) in enumerate(keys):
                    for ai,arm in enumerate(ARMS):
                        known=int(counts[hi,ai].sum());miss=int(missing[hi,ai]);planned=known+miss
                        category_rates.append(dict(work_id=work,idx=idx,arm=arm,planned=planned,observed=known,missing=miss,
                          categories=[dict(events=int(x),point=float(x/known) if known else None,
                                           bounds=[float(x/planned),float((x+miss)/planned)] if planned else [None,None])
                                      for x in counts[hi,ai]]))
                result.update(histories=[dict(work_id=w,idx=j) for w,j in keys],arms=list(ARMS),count_table=counts.tolist(),missing_table=missing.tolist(),
                              categorical_rates=category_rates,
                              missing_rule='缺失不进入多项似然，不作为其他类别；逐历史逐臂完整计数和缺失数同时交付。')
                save(path,result)
            results[unit]=result
        summary['G0d']=results
    save(out/'factdiag6g_step0.json',summary)
    print(json.dumps({'opening_groups':summary['G0a']['rows'],'blind_validation':summary.get('blind_validation',{}).get('agreement'),
                      'models_complete':list(summary.get('G0d',{}))},ensure_ascii=False),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--pilot',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--models',action='store_true')
    args=ap.parse_args();summarize(args.pilot,args.out,args.models)
