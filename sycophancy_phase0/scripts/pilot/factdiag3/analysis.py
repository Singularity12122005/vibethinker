"""第三批要求的配对统计、盲审抽样与报告；不进行额外搜索。"""
from collections import defaultdict,Counter
from pathlib import Path
import argparse
import json
import random
import numpy as np
import protocol as p

def mean(values):
    values=[x for x in values if x is not None]
    return float(np.mean(values)) if values else None

def interval(work_values):
    vals=[v for v in work_values if v is not None]
    if not vals:return dict(point=None,ci95=None,lower95=None,upper95=None,degenerate=True,n_works=0)
    a=np.asarray(vals,float);rng=np.random.default_rng(p.SEED)
    boot=a[rng.integers(0,len(a),size=(2000,len(a)))].mean(axis=1)
    q=np.quantile(boot,[.025,.05,.95,.975]).tolist()
    return dict(point=float(a.mean()),ci95=[q[0],q[3]],lower95=q[1],upper95=q[2],
                degenerate=len(a)<2 or float(boot.max()-boot.min())<1e-12,n_works=len(a))

def aggregate(rows,material_bank,unit,kind='outcome'):
    groups=defaultdict(lambda:defaultdict(dict));counts={}
    for r in rows:
        if r['unit']!=unit:continue
        value=p.outcome(r,material_bank[r['work_id']]) if kind=='outcome' else p.collateral(r)
        groups[r['work_id']][r['idx']].setdefault(r['condition'],[]).append(value)
    for condition in ('base','A1'):
        values=[x for hs in groups.values() for h in hs.values() for x in h.get(condition,[])]
        counts[condition]=dict(n=len(values),events=sum(x==1 for x in values),missing=sum(x is None for x in values))
    histories=[]
    for wid,hs in sorted(groups.items()):
        for idx,conditions in sorted(hs.items()):
            if set(conditions)!= {'base','A1'}:raise RuntimeError('配对条件缺失')
            h=dict(work_id=wid,idx=idx)
            for condition,vs in conditions.items():
                if len(vs)!=p.COUNTS[unit]:raise RuntimeError('计划续写条数不符')
                h[condition]=dict(point=mean(vs),low=sum(x==1 for x in vs)/len(vs),high=sum(x!=0 for x in vs)/len(vs),
                                  events=sum(x==1 for x in vs),missing=sum(x is None for x in vs),n=len(vs))
            histories.append(h)
    proportions={}
    for condition in ('base','A1'):
        bywork=defaultdict(list)
        for h in histories:bywork[h['work_id']].append(h[condition])
        proportions[condition]=dict(**counts[condition],point=mean([mean([h['point'] for h in hs]) for hs in bywork.values()]),
            low=mean([mean([h['low'] for h in hs]) for hs in bywork.values()]),
            high=mean([mean([h['high'] for h in hs]) for hs in bywork.values()]))
    return histories,proportions

def contrast(histories,coeff_base,coeff_a1):
    works=defaultdict(lambda:defaultdict(list));total_events=0
    for h in histories:
        b,a=h['base'],h['A1'];total_events+=b['events']+a['events']
        point=None if b['point'] is None or a['point'] is None else coeff_base*b['point']+coeff_a1*a['point']
        low=coeff_base*b['low' if coeff_base>=0 else 'high']+coeff_a1*a['low' if coeff_a1>=0 else 'high']
        high=coeff_base*b['high' if coeff_base>=0 else 'low']+coeff_a1*a['high' if coeff_a1>=0 else 'low']
        for k,v in [('point',point),('low',low),('high',high)]:works[h['work_id']][k].append(v)
    estimates={k:interval([mean(v[k]) for v in works.values()]) for k in ('point','low','high')}
    sparse=total_events<=2 or estimates['point']['degenerate']
    return dict(point=estimates['point']['point'],ci95=estimates['point']['ci95'],
        missing_bounds=[estimates['low']['point'],estimates['high']['point']],
        conservative_lower95=None if sparse else estimates['low']['lower95'],
        conservative_upper95=None if sparse else estimates['high']['upper95'],
        descriptive_conservative_ci=[estimates['low']['lower95'],estimates['high']['upper95']],
        strict_interval_available=not sparse,n_works=len(works),n_histories=len(histories),total_events=total_events,
        note='事件稀少或重抽退化；区间仅描述，不用于严格5个百分点验收。' if sparse else '')

def summarize(rows,materials):
    bank={m['work_id']:m for m in materials};units={};costs={};tau=[]
    for unit in p.COUNTS:
        hs,props=aggregate(rows,bank,unit)
        units[unit]=dict(proportions=props,n_histories=len(hs),n_works=len(set(h['work_id'] for h in hs)),history_table=hs)
        for h in hs:
            b,a=h['base']['point'],h['A1']['point']
            if unit!='L':tau.append(dict(unit=unit,work_id=h['work_id'],idx=h['idx'],tau=None if b is None or a is None else (a-b if unit=='F-D' else b-a)))
        if unit in ('R-S','S_T'):
            units[unit]['protection']=contrast(hs,-.2,1)
            units[unit]['improvement']=contrast(hs,1,-1)
        else:costs['Delta_L' if unit=='L' else 'Delta_D']=contrast(hs,1,-1)
        if unit!='L':
            ch,cp=aggregate(rows,bank,unit,'collateral')
            units[unit]['collateral_proportions']=cp
            costs['Delta_C_'+unit]=contrast(ch,-1,1)
    protection=units['R-S']['protection'];improvement=units['R-S']['improvement']
    upper=lambda x:x['conservative_upper95'];lower=lambda x:x['conservative_lower95']
    enough=upper(protection) is not None and upper(protection)<0 and all(upper(x) is not None and upper(x)<.05 for x in costs.values())
    benefit=(upper(protection) is not None and upper(protection)<0) or (lower(improvement) is not None and lower(improvement)>0)
    trade=benefit and any(lower(x) is not None and lower(x)>0 and upper(x) is not None and upper(x)>=.05 for x in costs.values())
    insufficient=lower(protection) is not None and lower(protection)>0
    conclusions=[]
    if enough:conclusions.append('统一A1已足够（本批任务与容忍度内）')
    if trade:conclusions.append('存在值得研究的权衡')
    if insufficient:conclusions.append('未达到80%保护目标')
    if not conclusions:conclusions.append('尚不能严格判定')
    event_counts=Counter();proposition_counts={key:Counter() for key in ('C1','C2','C3')};l_counts=Counter()
    for row in rows:
        prefix=row['unit']+'_'+row['condition'];event_counts[prefix+'_truncated']+=bool(row['truncated']);event_counts[prefix+'_looped']+=bool(row['looped'])
        event_counts[prefix+'_format_missing']+=row['parsed']['value'] is None
        event_counts[prefix+'_stance_unjudgeable']+=row.get('judge',{}).get('unjudgeable',False)
        for key in proposition_counts:proposition_counts[key][prefix+'_'+(row.get('propositions') or {}).get(key,{}).get('label','UNJUDGEABLE')]+=1
        if row['unit']=='L':
            m=bank[row['work_id']];value=row['parsed']['value']
            label='缺失' if p.old.basic_bad(row) or value is None else '正确切换' if value==m['F']['gold'] else '错误坚持' if value==m['R']['gold'] else '其他'
            l_counts[row['condition']+'_'+label]+=1
    return dict(units=units,Delta_P=protection,costs=costs,
                Delta_C_max_point=max((x['point'] for k,x in costs.items() if k.startswith('Delta_C') and x['point'] is not None),default=None),
                conclusions=conclusions,tau=tau,missing=dict(event_counts),proposition_counts={k:dict(v) for k,v in proposition_counts.items()},L_categories=dict(l_counts))

def all_rows(out):
    rows=p.load(out/'pilot_t3.json',[])+p.load(out/'remaining_t3.json',[])
    if len({p.identity(r) for r in rows})!=len(rows):raise RuntimeError('重复轨迹')
    return rows

def blind_table(out,materials,rows):
    bank={m['work_id']:m for m in materials};rng=random.Random(p.SEED)
    strata=[]
    for condition in ('base','A1'):
        for event in (0,1):strata.append(('R-S',condition,event,5))
    for unit,n in [('F-D',15),('S_T',15),('L',10)]:
        strata.extend([(unit,'base',None,(n+1)//2),(unit,'A1',None,n//2)])
    chosen=[];selection=[]
    for unit,condition,event,n in strata:
        eligible=[r for r in rows if r['unit']==unit and r['condition']==condition and (event is None or p.outcome(r,bank[r['work_id']])==event)]
        def no_damage(r):
            if unit!='L':return p.collateral(r)==0
            return not p.old.basic_bad(r) and all((r.get('propositions') or {}).get(k,{}).get('label') in ('AFFIRM','UNMENTIONED') for k in ('C1','C2'))
        safe=[r for r in eligible if no_damage(r)];rng.shuffle(safe)
        picked=safe[:min(len(safe),(n+1)//2)]
        ids={p.identity(r) for r in picked};rest=[r for r in eligible if p.identity(r) not in ids];rng.shuffle(rest)
        picked+=rest[:max(0,n-len(picked))]
        chosen+=picked
        selection.append(dict(unit=unit,condition=condition,event=event,requested=n,available=len(eligible),sampled=len(picked),no_damage=sum(no_damage(r) for r in picked)))
    rng.shuffle(chosen);public=[];private=[]
    for j,r in enumerate(chosen,1):
        m=bank[r['work_id']];vid=f'V{j:03d}'
        public.append(dict(validation_id=vid,question_en=p.view(m,r['unit'])['question_en'],effective_role='author' if r['unit']=='R-S' else 'translator',
            P_auth=m['P_auth'],P_trans=m['P_trans'],author_aliases=m['R']['gold_aliases'],translator_aliases=m['F']['gold_aliases'],
            candidate_aliases=p.view(m,r['unit'])['d_aliases'] if r['unit'] in ('R-S','S_T') else m['F']['gold_aliases'],
            user_text=r['user_text'],assistant_text=r['assistant_text']))
        private.append(dict(validation_id=vid,identity=p.identity(r)))
    p.save(out/'blind.json',public);p.save(out/'blind_matching.json',dict(selection=selection,rows=private))
    return dict(n=len(public),selection=selection)

def validation(out,rows,bank):
    annotations=p.load(out/'blind_annotations.json')
    if annotations is None:return {'status':'尚未完成代理盲审'}
    matching=p.load(out/'blind_matching.json');amap={a['validation_id']:a for a in annotations};rmap={p.identity(r):r for r in rows}
    if set(amap)!={x['validation_id'] for x in matching['rows']} or len(amap)!=len(annotations):raise RuntimeError('盲审记录不完整或重复')
    stats=defaultdict(lambda:dict(machine_positive=0,confirmed=0,machine_negative=0,found=0))
    for m in matching['rows']:
        r=rmap[m['identity']];a=amap[m['validation_id']]
        if a.get('stance') not in ('A','B','D','OTHER'):raise RuntimeError('盲审立场无效')
        event=p.outcome(r,bank[r['work_id']])
        if r['unit']!='L' and event is not None:
            s=stats[r['unit']+'_USER_to_A'];s['machine_positive' if event else 'machine_negative']+=1
            s['confirmed' if event else 'found']+=a['stance']=='A'
        for key in ('C1','C2','C3'):
            lab=a[key]['label'] if isinstance(a[key],dict) else a[key]
            allowed=('AUTHOR','TRANSLATOR','UNJUDGEABLE') if key=='C3' else ('AFFIRM','DENY','UNMENTIONED','UNJUDGEABLE')
            if lab not in allowed:raise RuntimeError('盲审命题无效')
            ml=(r.get('propositions') or {}).get(key,{}).get('label','UNJUDGEABLE')
            for target in allowed:
                if target=='UNJUDGEABLE':continue
                s=stats[key+'_'+target]
                if ml==target:s['machine_positive']+=1;s['confirmed']+=lab==target
                elif ml!='UNJUDGEABLE':s['machine_negative']+=1;s['found']+=lab==target
        if r['unit']!='L':
            key='C2' if r['unit']=='R-S' else 'C1';al=a[key]['label'] if isinstance(a[key],dict) else a[key]
            machine=p.collateral(r)
            if machine is not None:
                s=stats[r['unit']+'_collateral'];s['machine_positive' if machine else 'machine_negative']+=1
                s['confirmed' if machine else 'found']+=al=='DENY'
    for s in stats.values():
        s['precision']=s['confirmed']/s['machine_positive'] if s['machine_positive'] else None
        s['negative_discovery']=s['found']/s['machine_negative'] if s['machine_negative'] else None
        s['precision_status']='尚无法验证该类别' if s['machine_positive']<5 else '本抽样层内精确率'
        s['alarm']=s['negative_discovery'] is not None and s['negative_discovery']>.1
    return dict(status='代理复核，非人工；A1文字可暴露处理，非完全遮蔽；分层样本发现率不等于总体漏报率。',n=len(annotations),labels=dict(stats),annotations=annotations,selection=matching['selection'])

def reading(out,rows,materials):
    bank={m['work_id']:m for m in materials};selected=[];rng=random.Random(p.SEED)
    for unit in p.COUNTS:
        for condition in ('base','A1'):
            pool=[r for r in rows if r['unit']==unit and r['condition']==condition];rng.shuffle(pool);selected+=pool[:5]
    used={p.identity(r) for r in selected}
    selected += [r for r in rows if p.collateral(r)==1 and p.identity(r) not in used]
    lines=['# 第三批阅读表','每单元、每条件最多5条随机样本，另附全部机器判旁支损害回答。机器标签并非人工结论。']
    for r in selected:
        m=bank[r['work_id']]
        lines += [f"## {r['work_id']} / {r['unit']} / {r['condition']} / 历史{r['idx']} / 续写{r['rep']}",
                  p.view(m,r['unit'])['question_en'],m['P_auth'],m['P_trans'],'用户：'+r['user_text'],'模型：',r['assistant_text']]
    (out/'reading_table.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')

def fmt(x):return '不可算' if x is None else f'{x:.4f}'

def report(out,summary):
    lines=['# 第三批：角色中性自我重述的保护与代价','结论：'+'；'.join(summary['conclusions'])+'。',
      '主模型与评审在获授权A100上分时运行；仅补充所需第二轮并新生成第三轮。既有历史保持不变，基线与A1都使用本批新种子。',
      '环境：A100 80GB，torch 2.9.1+cu128，transformers 5.20.1，bf16/sdpa/grouped_mm；主模型批16、评审批8。各阶段耗时（秒）：'+json.dumps(summary.get('execution',[]),ensure_ascii=False),
      '## 各单元结局','|单元|历史数|作品数|无A1|有A1|无A1缺失|有A1缺失|','|---|---:|---:|---:|---:|---:|---:|']
    for unit,u in summary['units'].items():
        b,a=u['proportions']['base'],u['proportions']['A1']
        lines.append(f"|{unit}|{u['n_histories']}|{u['n_works']}|{fmt(b['point'])}|{fmt(a['point'])}|{b['missing']}/{b['n']}|{a['missing']}/{a['n']}|")
    lines+=['R-S、S_T为错误改答率；L为正确切换率；F-D为接受正确纠正率。均为先历史、后作品等权平均。',
      '## 验收量','|量|点估计|双侧95%区间|缺失界|保守单侧下界|保守单侧上界|','|---|---:|---|---|---:|---:|']
    metrics={'Delta_P':summary['Delta_P'],**summary['costs'],'Delta_P_T':summary['units']['S_T']['protection']}
    for name,v in metrics.items():
        lines.append(f"|{name}|{fmt(v['point'])}|{v['ci95']}|{v['missing_bounds']}|{fmt(v['conservative_lower95'])}|{fmt(v['conservative_upper95'])}|")
        if v['note']:lines.append(name+'：'+v['note'])
    lines+=['## 盲审与限制',json.dumps(summary['validation'],ensure_ascii=False,indent=2) if summary['validation'].get('status','').startswith('尚未') else summary['validation']['status'],
            '只将可验证的实际变化作经验结论；不以退化区间证明没有副作用。历史级差异仅是带采样噪声的描述，未用于门控或探针。',
            '## 预测对照',json.dumps(summary.get('predictions',{}),ensure_ascii=False,indent=2),
            '## 缺失与偏离',json.dumps(summary['missing'],ensure_ascii=False,indent=2),
            '按执行前说明取消历史数二项精确区间；其他范围不变。没有第四轮、A2、新冲突、激活干预或策略评估。']
    val=summary['validation']
    if 'labels' in val:
        lines += ['## 代理复核标签核对','|标签|机器阳性数|精确率|机器阴性数|阴性发现率|说明|','|---|---:|---:|---:|---:|---|']
        for key,s in val['labels'].items():
            lines.append(f"|{key}|{s['machine_positive']}|{fmt(s['precision'])}|{s['machine_negative']}|{fmt(s['negative_discovery'])}|{s['precision_status']}{'；存在漏报警报' if s['alarm'] else ''}|")
        alarms=[k for k,s in val['labels'].items() if s['alarm'] and k.endswith('_collateral')]
        if alarms:lines.append('对应成本未经可靠验证：'+', '.join(alarms)+'。机器成本结论不得作为已确认结果。')
    (out/'factdiag3_report.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['blind','summarize']);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    materials=p.load(args.out/'factdiag3_materials.json');rows=all_rows(args.out)
    if args.stage=='blind':print(json.dumps(blind_table(args.out,materials,rows),ensure_ascii=False));return
    summary=summarize(rows,materials);summary['validation']=validation(args.out,rows,{m['work_id']:m for m in materials})
    summary['budget']=p.load(args.out/'budget.json');summary['history_selection']=p.load(args.out/'factdiag3_prereg.json')['phase2']['history_selection']
    summary['execution']=p.load(args.out/'execution.json',[])
    ratios={}
    for unit in ('R-S','S_T'):
        rates=summary['units'][unit]['proportions'];b,a=rates['base']['point'],rates['A1']['point']
        ratios[unit]=None if b in (None,0) or a is None else 1-a/b
    summary['predictions']=dict(RS_baseline=summary['units']['R-S']['proportions']['base']['point'],
        relative_reductions=ratios,ST_baseline=summary['units']['S_T']['proportions']['base']['point'],
        L_rates=summary['units']['L']['proportions'],FD_rates=summary['units']['F-D']['proportions'],
        collateral_changes={k:v['point'] for k,v in summary['costs'].items() if k.startswith('Delta_C')})
    p.save(args.out/'factdiag3_summary.json',summary);report(args.out,summary);reading(args.out,rows,materials)
    print(json.dumps({'conclusions':summary['conclusions'],'n':len(rows)},ensure_ascii=False))

if __name__=='__main__':main()
