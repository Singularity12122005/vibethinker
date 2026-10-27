"""独立探索附录C：错误关系、最终错误及答案身份条件下的S/C配对。

只消费既有formal_events；不重评、不生成、不修改主分析。
"""
from collections import Counter,defaultdict
from itertools import combinations
from pathlib import Path
import argparse
import numpy as np
from core import load,save,rate,difference,SEED

CANDIDATES=('T','d_T','I','C','X','F_w')
IDENTITIES=('D','X','G','OTHER')
SPECIFIC={'AUTHOR','TRANSLATOR_OF_THIS_EDITION','TRANSLATOR_OF_ANOTHER_EDITION',
          'EDITOR_OR_INTRODUCER','ILLUSTRATOR','CHARACTER'}
KNOWN_ROLES={'TRUE_ROLE','FALSE_ROLE','NO_ROLE','DENIED','UNMENTIONED'}
METRICS=('wrong_relation_affirmed','final_error','true_role','denied','no_role','unmentioned','role_unknown')


def augment(row):
    r=dict(row);role=r['role'];known=role in KNOWN_ROLES
    if role=='FALSE_ROLE' and r['role_raw'] not in SPECIFIC:
        raise RuntimeError('错误角色标签不属于冻结明确具体角色集合')
    r['wrong_relation_affirmed']=None if not known else int(role=='FALSE_ROLE')
    r['final_error']=None if r['correct'] is None else 1-r['correct']
    for key,value in [('true_role','TRUE_ROLE'),('denied','DENIED'),('no_role','NO_ROLE'),('unmentioned','UNMENTIONED')]:
        r[key]=None if not known else int(role==value)
    r['role_unknown']=int(not known)
    if 'role_false' in r and r['wrong_relation_affirmed']!=r['role_false']:
        raise RuntimeError('与冻结错误角色派生值不一致')
    return r


def estimate(cells,get):
    """先候选条件、再历史、再项目平均；重抽保留完整项目簇。"""
    groups=defaultdict(lambda:defaultdict(list))
    for c in cells:groups[c['work_id']][c['history_id']].append(get(c))
    rows=[]
    for work,histories in sorted(groups.items()):
        row=dict(work_id=work,histories=len(histories))
        for key in ('point','lower','upper'):
            hv=[]
            for vals in histories.values():
                v=[x['point'] if key=='point' else x['bounds'][0 if key=='lower' else 1] for x in vals]
                v=[x for x in v if x is not None]
                if v:hv.append(float(np.mean(v)))
            row[key]=float(np.mean(hv)) if hv else None
            row[key+'_history_sum']=sum(hv);row[key+'_histories']=len(hv)
        rows.append(row)
    result=dict(projects=len(rows),histories=len({(c['work_id'],c['history_id']) for c in cells}),
                history_candidate_cells=len(cells),per_project=rows)
    if not rows:
        result.update(project_equal=dict(point=None,bounds=[None,None],ci95=None),history_equal=dict(point=None,bounds=[None,None],ci95=None))
        return result
    index=np.random.default_rng(SEED).integers(0,len(rows),(2000,len(rows)))
    for weighting in ('project_equal','history_equal'):
        estimates={};intervals={};counts={};reasons={}
        for key in ('point','lower','upper'):
            if weighting=='project_equal':
                num=np.array([r[key] if r[key] is not None else 0. for r in rows]);den=np.array([int(r[key] is not None) for r in rows])
            else:
                num=np.array([r[key+'_history_sum'] for r in rows]);den=np.array([r[key+'_histories'] for r in rows])
            estimates[key]=float(num.sum()/den.sum()) if den.sum() else None
            bnum=num[index].sum(1);bden=den[index].sum(1);bs=bnum[bden>0]/bden[bden>0]
            counts[key]=dict(valid_units=int(den.sum()),bootstrap_valid=len(bs))
            if len(rows)<2:
                intervals[key]=None;reasons[key]='仅一个项目，不能报告项目重抽不确定性'
            elif not len(bs):
                intervals[key]=None;reasons[key]='没有可计算的重抽'
            elif np.all(bs==bs[0]):
                intervals[key]=None;reasons[key]='经验重抽退化，未输出貌似严格的点区间'
            else:
                intervals[key]=np.quantile(bs,[.025,.975]).tolist();reasons[key]=None
        result[weighting]=dict(point=estimates['point'],bounds=[estimates['lower'],estimates['upper']],
            ci95=intervals['point'],lower_bound_ci95=intervals['lower'],upper_bound_ci95=intervals['upper'],
            denominators=counts,interval_notes=reasons)
    return result


def condition_table(rows):
    grouped=defaultdict(list)
    for r in rows:grouped[(r['work_id'],r['history_id'],r['candidate_type'])].append(r)
    cells=[]
    for (work,hid,c),rs in sorted(grouped.items()):
        cells.append(dict(work_id=work,history_id=hid,candidate_type=c,n=len(rs),
            metrics={m:rate([r[m] for r in rs]) for m in METRICS},
            identity_counts=dict(Counter(r['final_identity'] for r in rs)),
            role_counts=dict(Counter(str(r['role']) for r in rs))))
    return dict(observations=len(rows),projects=len({r['work_id'] for r in rows}),
        histories=len({r['history_id'] for r in rows}),
        metrics={m:dict(estimate=estimate(cells,lambda c,m=m:c['metrics'][m]),counts=rate([r[m] for r in rows])) for m in METRICS},
        identity_counts=dict(Counter(r['final_identity'] for r in rows)),
        raw_role_counts=dict(Counter(str(r['role_raw']) for r in rows)),
        role_counts=dict(Counter(str(r['role']) for r in rows)),per_history=cells)


def pair_cells(rows,candidate=None,identity=None):
    grouped=defaultdict(lambda:defaultdict(list))
    for r in rows:
        if r['arm'] not in ('S','C') or (candidate is not None and r['candidate_type']!=candidate):continue
        grouped[(r['work_id'],r['history_id'],r['candidate_type'])][r['arm']].append(r)
    cells=[];support=Counter();excluded=[]
    for (work,hid,cand),arms in sorted(grouped.items()):
        if set(arms)!={'S','C'}:
            support['no_C_or_S_condition']+=1;continue
        support['matched_history_candidate_conditions']+=1
        support['S_identity_unknown']+=sum(r['final_identity'] not in IDENTITIES for r in arms['S'])
        support['C_identity_unknown']+=sum(r['final_identity'] not in IDENTITIES for r in arms['C'])
        selected={a:[r for r in rs if identity is None or r['final_identity']==identity] for a,rs in arms.items()}
        left,right=selected['S'],selected['C']
        if not left or not right:
            state='only_S_support' if left else 'only_C_support' if right else 'neither_arm_support'
            support[state]+=1
            excluded.append(dict(work_id=work,history_id=hid,candidate_type=cand,status=state,S_n=len(left),C_n=len(right)))
            continue
        support['common_supported_history_candidate_conditions']+=1
        support['S_observations_common_support']+=len(left);support['C_observations_common_support']+=len(right)
        metrics={}
        for m in METRICS:
            a,b=rate([r[m] for r in left]),rate([r[m] for r in right])
            metrics[m]=dict(S=a,C=b,S_minus_C=difference(a,b))
        cells.append(dict(work_id=work,history_id=hid,candidate_type=cand,S_n=len(left),C_n=len(right),
            S_role_counts=dict(Counter(str(r['role']) for r in left)),C_role_counts=dict(Counter(str(r['role']) for r in right)),metrics=metrics))
    result=dict(candidate_type=candidate or 'all_available_matched',identity=identity or 'unconditional',support=dict(support),
        common_support_projects=len({c['work_id'] for c in cells}),common_support_histories=len({c['history_id'] for c in cells}),
        excluded_support=excluded,per_history=cells,metrics={})
    for m in METRICS:
        result['metrics'][m]={side:estimate(cells,lambda c,m=m,side=side:c['metrics'][m][side]) for side in ('S','C','S_minus_C')}
        result['metrics'][m]['point_supported_cells']=sum(c['metrics'][m]['S_minus_C']['point'] is not None for c in cells)
    result['support_note']=('两臂该最终身份没有共同支持，不能估计条件差' if not cells else
        '只有一个项目有共同支持，不能作跨项目推断' if result['common_support_projects']==1 else
        '逐项报告共同支持分母；不设事后最小样本阈值，有限样本条件选择限制仍存在')
    return result


def candidate_comparisons(rows,tables):
    result={}
    for arm in ('S','C','S+A1','S+A0'):
        available=[c for c in CANDIDATES if (c,arm) in tables]
        if not available:continue
        metrics={m:{c:tables[(c,arm)]['metrics'][m]['estimate']['project_equal']['point'] for c in available} for m in ('wrong_relation_affirmed','final_error')}
        ranking={m:sorted(vals,key=lambda c:(-vals[c],CANDIDATES.index(c))) for m,vals in metrics.items()}
        comparisons=[]
        for a,b in combinations(available,2):
            da=metrics['wrong_relation_affirmed'][a]-metrics['wrong_relation_affirmed'][b]
            de=metrics['final_error'][a]-metrics['final_error'][b]
            concordance='相反' if da*de<0 else '一致' if da*de>0 else '至少一项并列'
            comparisons.append(dict(left=a,right=b,wrong_relation_difference=da,final_error_difference=de,ordering=concordance))
        result[arm]=dict(candidate_rates=metrics,descending_order=ranking,pairwise_ordering=comparisons,
            note='这是实际可用项目上的描述次序；I只来自一部作品，不能解释成同一总体的精确类别排名；并列不强分先后。')
    # 各类别在同一历史都有S结果时，再做相同支持上的类别差。
    matched=[];source=defaultdict(dict)
    for (c,arm),table in tables.items():
        if arm!='S':continue
        for cell in table['per_history']:source[(cell['work_id'],cell['history_id'])][c]=cell
    for a,b in combinations(CANDIDATES,2):
        cells=[]
        for (work,hid),cs in sorted(source.items()):
            if a not in cs or b not in cs:continue
            cells.append(dict(work_id=work,history_id=hid,candidate_type=a+' minus '+b,
                metrics={m:difference(cs[a]['metrics'][m],cs[b]['metrics'][m]) for m in ('wrong_relation_affirmed','final_error')}))
        matched.append(dict(left=a,right=b,metrics={m:estimate(cells,lambda c,m=m:c['metrics'][m]) for m in ('wrong_relation_affirmed','final_error')},
            note='先在同一历史对类别作差，再作历史及项目平均；I相关比较只有一个共同作品。'))
    return dict(available_candidate_rankings=result,S_common_history_candidate_differences=matched)


def main(out,destination):
    source=load(out/'formal_events.json')
    rows=[augment(r) for r in source if r['structure']=='G1']
    if len(rows)!=2220:raise RuntimeError('G1全部正式事件数不符')
    tables={}
    for candidate in CANDIDATES:
        for arm in ('S','C','S+A1','S+A0'):
            rs=[r for r in rows if r['candidate_type']==candidate and r['arm']==arm]
            if rs:tables[(candidate,arm)]=condition_table(rs)
    contrasts=[]
    for candidate in (*CANDIDATES,None):
        for identity in (None,*IDENTITIES):contrasts.append(pair_cells(rows,candidate,identity))
    identity_tables=[]
    for candidate,arm in tables:
        for identity in IDENTITIES:
            rs=[r for r in rows if r['candidate_type']==candidate and r['arm']==arm and r['final_identity']==identity]
            identity_tables.append(dict(candidate_type=candidate,arm=arm,identity=identity,**condition_table(rs)))
    result=dict(status='完成',analysis='独立探索附录C，主报告提交后的新分析，不回写冻结主分析',
        definitions=dict(wrong_relation_affirmed='既有FALSE_ROLE且原始标签为冻结G1明确具体角色；是机器角色归属事件，不保证人工意义上的显式肯定。',
            final_error='1−派生correct；未知correct仍未知，绝不统一替换为P(D)。',
            known_negative='TRUE_ROLE、NO_ROLE、DENIED、UNMENTIONED是错误关系肯定的已知非事件；DENIED另报，不混成错误肯定。',
            unknown='OTHER、版本未明、CONFLICTING、缺失或截断均未知；按既有映射保留。',
            conditioning='同一历史/候选在S与C均存在；身份层再要求两臂均至少一条已知该身份回答。D/X/G/OTHER互斥；不按结果调整门槛。',
            weighting='每历史先平均可用候选条件，再项目平均；历史等权并列。每次保留整个作品全部历史和续写，重抽2000次。',
            missing_bounds='每个历史候选条件按未知全非事件/全事件取界，S−C取左下减右上、左上减右下。条件层未定身份单列不分配；本批G1身份未知为0。',
            intervals='单项目或退化经验重抽不输出置信区间；点与缺失两端界仍保留。',
            selection='最终答案身份是处理后变量；共同支持选择后的差不能直接解释为压力对角色的因果作用。零差/跨零也不是条件分布相同的证明。',
            scope='按全部G1正式回答；S/C是核心匹配比较，A1和A0仅按实际可用总体另列。F_w无C，不构造。'),
        source_counts=dict(G1=len(rows),final_identity=dict(Counter(r['final_identity'] for r in rows)),
            role=dict(Counter(str(r['role']) for r in rows)),raw_specific_error_labels=sorted(SPECIFIC)),
        conditions=[dict(candidate_type=c,arm=a,**v) for (c,a),v in tables.items()],
        within_arm_identity_conditions=identity_tables,
        candidate_ordering=candidate_comparisons(rows,tables),paired_S_C=contrasts,
        limitations=['角色独立盲审13/20一致，版本归属存在误分；保持机器标签，不能把本分析当作可靠角色事实的重新标注。',
            'S通常4条、C通常2条，每历史身份支持有限；共同支持样本是处理后选择，不能外推到被排除身份/历史。',
            '多个候选、身份和角色事件的探索区间未作同时覆盖或多重比较校正，不能据单个区间作未经限定的全局机制结论。'])
    save(destination,result)
    print('探索C汇总完成',len(rows),'条；',len(tables),'个实际条件；',len(contrasts),'个配对/支持层',flush=True)


def self_test():
    def row(work,hid,arm,identity,correct,role,raw):
        return augment(dict(work_id=work,history_id=hid,candidate_type='T',arm=arm,
            final_identity=identity,correct=correct,role=role,role_raw=raw))
    assert row('a','a','S','D',1,'DENIED','DENIED_ANY_ROLE')['final_error']==0
    assert row('a','a','S','OTHER',0,'DENIED','DENIED_ANY_ROLE')['final_error']==1
    unknown=row('a','a','S','X',1,'UNKNOWN','CONFLICTING')
    assert unknown['wrong_relation_affirmed'] is None and unknown['role_unknown']==1
    denied=row('a','a','S','X',1,'DENIED','DENIED_ANY_ROLE')
    assert denied['wrong_relation_affirmed']==0 and denied['denied']==1
    sample=[row('a','a','S','X',1,'FALSE_ROLE','AUTHOR'),row('a','a','C','X',1,'TRUE_ROLE','TRANSLATOR_OF_THIS_EDITION'),
            row('b','b','S','D',0,'FALSE_ROLE','AUTHOR'),row('b','b','C','X',1,'TRUE_ROLE','TRANSLATOR_OF_THIS_EDITION')]
    p=pair_cells(sample,'T','X')
    assert p['common_support_histories']==1 and p['support']['only_C_support']==1
    assert p['metrics']['wrong_relation_affirmed']['S_minus_C']['project_equal']['point']==1
    assert p['metrics']['wrong_relation_affirmed']['S_minus_C']['project_equal']['ci95'] is None
    cells=[dict(work_id=w,history_id=h,value=rate([v])) for w,h,v in [('a','a1',1),('a','a2',1),('b','b1',0)]]
    e=estimate(cells,lambda c:c['value'])
    assert e['project_equal']['point']==.5 and e['history_equal']['point']==2/3
    missing=difference(rate([1,None]),rate([0,None]))
    assert missing['point']==1 and missing['bounds']==[0,1]
    print('探索C必要定义、配对、双权重和缺失界检查通过')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path);ap.add_argument('--destination',type=Path)
    ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
    if a.self_test:self_test()
    if a.out is not None:
        if a.destination is None:raise RuntimeError('须指定聚合输出')
        main(a.out,a.destination)
