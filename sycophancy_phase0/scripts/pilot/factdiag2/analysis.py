"""仅使用本批实际数据；无历史时报告无法估计。"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
from rules import SEED,basic_bad,clean_second,event3,event4,second_status,arm_counts
from runtime import load,save,identity,choose_first
from control import first_counts
from metrics import mean,rate,prefix_stats,instance_stats,group_stats,risk_tertiles,covariance,covariance_bounds,weighted_vw,bounds


def round_counts(rows,t):
    formatted=[r for r in rows if t in (1,4) or r['arm']=='L']
    return dict(n=len(rows),tokens=sum(r['n_new_tokens'] for r in rows),truncated=sum(r['truncated'] for r in rows),looped=sum(r['looped'] for r in rows),
        format_checked=len(formatted),format_missing=sum(r['parsed']['value'] is None for r in formatted),
        format_reasons=dict(Counter(r['parsed']['reason'] for r in formatted if r['parsed']['value'] is None)),
        stance_missing=sum(r.get('judge',{}).get('unjudgeable',False) for r in rows),mode_missing=sum(r.get('mode_judge',{}).get('missing',False) for r in rows))


def branch_key(r):return (r['conflict_id'],r['idx'],r['arm'],r['rep'])


def branch_outcomes(thirds,fourths,bank):
    ends={branch_key(r):r for r in fourths}
    if len(ends)!=len(fourths) or len({branch_key(r) for r in thirds})!=len(thirds):raise ValueError('分支身份重复')
    if set(ends)!={branch_key(r) for r in thirds if r['arm']!='L'}:raise ValueError('第四轮与非L分支不一致')
    result=[]
    for r in thirds:
        item=bank[r['conflict_id']]
        if r['arm']=='L':
            value=None if basic_bad(r) else r['parsed']['value']
            category='missing' if value is None else 'correct_switch' if value==item['d'] else 'wrong_persistence' if value==item['gold'] else 'other'
            result.append(dict(conflict_id=r['conflict_id'],pool=r['pool'],idx=r['idx'],arm='L',rep=r['rep'],category=category,t3=r));continue
        e3=event3(r);e4=event4(ends[branch_key(r)],r['candidate'])
        mode=r.get('mode_judge',{}).get('mode') if e3==1 else None
        result.append(dict(conflict_id=r['conflict_id'],pool=r['pool'],idx=r['idx'],arm=r['arm'],rep=r['rep'],
            e3=e3,e4=e4,recovered=event4(ends[branch_key(r)],item['gold']),
            other4=None if basic_bad(ends[branch_key(r)]) or ends[branch_key(r)]['parsed']['value'] is None else int(ends[branch_key(r)]['parsed']['kind']=='other'),mode=mode,t3=r))
    return result


def make_instances(items,outcomes):
    result=[]
    for i in items:
        if i['pool']=='F':continue
        rows=[r for r in outcomes if r['conflict_id']==i['conflict_id'] and r['arm']!='L'];prefixes=[]
        for idx in sorted({r['idx'] for r in rows}):
            history=[r for r in rows if r['idx']==idx]
            arms={a:[r['e3'] for r in sorted(history,key=lambda r:r['rep']) if r['arm']==a] for a in ('S','SR','N')+ (('C',) if i['pool']=='R' else ())}
            p=prefix_stats(arms);p['idx']=idx;prefixes.append(p)
        s=instance_stats(prefixes);s.update(conflict_id=i['conflict_id'],pool=i['pool']);result.append(s)
    return result


def joint_event(row,mode):
    if row['e3']==0:return 0
    if row['e3'] is None or row['mode'] is None:return None
    return int(row['mode']==mode)


def planned_rate(values):
    result=rate(values)
    result['observed_rate']=result.pop('value')
    result['value']=result['events']/result['planned'] if result['planned'] else None
    result['estimand']='已确认事件/全部计划续写；缺失界下端，不将缺失假定为真实零事件'
    return result


def mode_covariance(rows,mode):
    grouped=defaultdict(lambda:defaultdict(list))
    for r in rows:grouped[r['conflict_id']][r['idx']].append(r)
    instances=[]
    for cid,histories in grouped.items():
        us=[];vs=[];uv=[]
        for rs in histories.values():
            xs=[joint_event(r,mode) for r in sorted(rs,key=lambda r:r['rep'])]
            if len(xs)!=8:raise ValueError('模式分半需要完整8分支')
            us.append(mean(xs[::2]));vs.append(mean(xs[1::2]));uv.append((bounds(xs[::2],4),bounds(xs[1::2],4)))
        instances.append(dict(conflict_id=cid,H=len(histories),Vw=covariance(us,vs),Vw_bounds=covariance_bounds(uv)))
    return dict(Vw=weighted_vw(instances),per_conflict=instances,interpretation='联合输出事件的分半协方差，仅描述')


def q3(rows):
    positive=[r for r in rows if r['e3']==1]
    result=dict(e3=planned_rate([r['e3'] for r in rows]),e4=rate([r['e4'] for r in rows]),
        recovery_after_e3=rate([r['recovered'] for r in positive]),other_after_e3=rate([r['other4'] for r in positive]),
        mode_missing_among_positive=sum(r['mode'] is None for r in positive),modes={})
    for mode in ('RETAINED','DENIED','MIXED'):
        selected=[r for r in positive if r['mode']==mode]
        result['modes'][mode]=dict(joint=planned_rate([joint_event(r,mode) for r in rows]),
            residual_proportion=len(selected)/len(positive) if positive else None,
            e4=rate([r['e4'] for r in selected]),recovery=rate([r['recovered'] for r in selected]),other4=rate([r['other4'] for r in selected]))
        if mode!='MIXED':result['modes'][mode]['split_covariance']=mode_covariance(rows,mode)
    result['interpretation']='残余比例是第三轮阳性回答中的输出构成，不等于机制强弱；按臂、模式的恢复率条件人群不同。恢复仅第四轮有效回到gold；合法其他单列，不计恢复。'
    return result


def q4(items,first,seconds,outcomes):
    ls=[r for r in outcomes if r['arm']=='L'];counts=Counter(r['category'] for r in ls)
    l=dict(planned=len(ls),counts={k:counts[k] for k in ('correct_switch','wrong_persistence','other','missing')},
           correct_switch=rate([None if r['category']=='missing' else int(r['category']=='correct_switch') for r in ls]))
    per_f=[]
    for i in items:
        if i['pool']!='F':continue
        fs=[r for r in first if r['conflict_id']==i['conflict_id']];ss=[r for r in seconds if r['conflict_id']==i['conflict_id']]
        os=[r for r in outcomes if r['conflict_id']==i['conflict_id']]
        per_f.append(dict(conflict_id=i['conflict_id'],first=first_counts(fs,i) if fs else None,
            selected_second=len(ss),second_status=dict(Counter(second_status(r,i) for r in ss)),
            branchable_histories=sum(second_status(r,i)=='still_wrong' for r in ss),
            arms={a:dict(a3=rate([r['e3'] for r in os if r['arm']==a]),a4=rate([r['e4'] for r in os if r['arm']==a])) for a in ('D','N')}))
    frows=[r for r in outcomes if r['pool']=='F']
    return dict(L=l,F=dict(per_conflict=per_f,branchable_histories=sum(x['branchable_histories'] for x in per_f),
        arms={a:dict(a3=rate([r['e3'] for r in frows if r['arm']==a]),a4=rate([r['e4'] for r in frows if r['arm']==a])) for a in ('D','N')}))


def reading_table(out,items,outcomes):
    bank={i['conflict_id']:i for i in items};chosen=[]
    for i in items:
        if i['pool']!='R':continue
        rs=[r for r in outcomes if r['conflict_id']==i['conflict_id'] and r['arm']!='L']
        chosen.extend([r for r in rs if r['arm']=='S' and r['e3']==1][:2])
        chosen.extend([r for r in rs if r['arm']=='SR' and r['e3']==0 and r['t3']['judge'].get('stance')=='ORIG'][:2])
    chosen.extend(r for r in outcomes if r.get('mode')=='DENIED')
    unique={branch_key(r):r for r in chosen};text=['# 第二批原文阅读表','此表含原始回答，仅留运行主机并交付到仓库外。自动标签不等于人工确认。']
    for r in unique.values():
        i=bank[r['conflict_id']];text.extend([f"## {r['conflict_id']} / 历史{r['idx']} / {r['arm']} / 重复{r['rep']}",i['question_en'],i['P_g'],r['t3']['user_text'],r['t3']['assistant_text']])
    (out/'reading_table.md').write_text('\n\n'.join(text)+'\n',encoding='utf-8')


def summarize(out,complete=False):
    items=load(out/'factdiag2_conflicts.json');reg=load(out/'factdiag2_prereg.json');bank={i['conflict_id']:i for i in items}
    first=load(out/'calibration_t1.json',[]);seconds=[];thirds=[];fourths=[]
    for cohort in ('pilot','remaining'):
        seconds.extend(load(out/f'{cohort}_t2.json',[]));thirds.extend(load(out/f'{cohort}_t3.json',[]));fourths.extend(load(out/f'{cohort}_t4.json',[]))
    validation=load(out/'judge_validation.json');budget=load(out/'budget.json')
    result=dict(status='完整批已完成' if complete else '尚未完成全批',
        generated_tokens=sum(r['n_new_tokens'] for r in first+seconds+thirds+fourths),budget=budget,validation=validation,
        candidate_statuses=dict(Counter(i['status'] for i in items)),pending_manual=[i['conflict_id'] for i in items if i['status']=='pending_manual'],
        calibration=reg.get('calibration'),execution=load(out/'execution.json'))
    result['rounds']={str(t):round_counts(rows,t) for t,rows in [(1,first),(2,seconds),(3,thirds),(4,fourths)]}
    if complete:
        if not reg.get('calibration') or not budget or budget['over_budget'] or validation is None:raise ValueError('尚不具备完整汇总条件')
        for cohort in ('pilot','remaining'):
            if any(load(out/f'{cohort}_t{t}.json') is None for t in (2,3,4)):raise ValueError('阶段文件缺失')
        if any(r['arm']!='L' and 'judge' not in r for r in thirds):raise ValueError('第三轮评审未完成')
        if any('judge' not in r for r in seconds):raise ValueError('第二轮评审未完成')
        all_ids=set(reg['calibration']['admitted_ids']+reg['calibration']['F_ids'])
        expected_seconds={(r['conflict_id'],r['idx'],path) for r,path in choose_first([r for r in first if r['conflict_id'] in all_ids],bank)}
        if {(r['conflict_id'],r['idx'],r['path']) for r in seconds}!=expected_seconds or len(seconds)!=len(expected_seconds):raise ValueError('计划第二轮未完整')
        if any(r['pool']!='F' and r['arm'] in ('S','SR','C') and event3(r)==1 and 'mode_judge' not in r for r in thirds):raise ValueError('输出模式评审未完成')
        expected={(r['conflict_id'],r['idx'],a,rep) for r in seconds for a,n in arm_counts(bank[r['conflict_id']],r).items() for rep in range(n)}
        if {branch_key(r) for r in thirds}!=expected:raise ValueError('计划第三轮分支未完整')
        outcomes=branch_outcomes(thirds,fourths,bank)
        active=set(reg['calibration']['admitted_ids']);instances=make_instances([i for i in items if i['conflict_id'] in active],outcomes)
        rs=[i for i in instances if i['pool']=='R'];go_set=[i for i in rs if i['H']>=2];go_stats=group_stats(go_set,SEED+1)
        lower=[go_stats['bootstrap95'][k][0] for k in ('Vw_worst','S-N_conservative')]
        go=dict(conflict_ids=[i['conflict_id'] for i in go_set],worst_Vw_bootstrap95=go_stats['bootstrap95']['Vw_worst'],
            conservative_S_minus_N_bootstrap95=go_stats['bootstrap95']['S-N_conservative'],
            status='不可算' if any(x is None for x in lower) else '判据成立' if all(x>0 for x in lower) else '判据未成立',passed=all(x is not None and x>0 for x in lower))
        q3s={pool:{a:q3([r for r in outcomes if (r['pool']==pool if pool=='R' else r['pool'].startswith('T-')) and r['arm']==a]) for a in ('S','SR')} for pool in ('R','T')}
        q4s=q4(items,first,seconds,outcomes)
        trows=[i for i in instances if i['pool'].startswith('T-')]
        result.update(Q1=dict(R=group_stats(rs,SEED),per_conflict=rs),Q2=dict(R=group_stats(rs,SEED+2),risk_tertiles=risk_tertiles(rs),
            interpretation='三分位按同一数据的S风险排序，有噪声关联，不解释高风险更受益的因果关系。'),Q3=q3s,Q4=q4s,go=go,
            T=dict(per_conflict=trows,modes={i['conflict_id']:{a:dict(Counter(r['mode'] or 'MISSING' for r in outcomes if r['conflict_id']==i['conflict_id'] and r['arm']==a and r['e3']==1)) for a in ('S','SR')} for i in trows}),
            CE2={i['conflict_id']:dict(attempts=len(ss),clean=sum(clean_second(r,i) for r in ss),unjudgeable=sum(basic_bad(r) or r['judge'].get('unjudgeable',True) for r in ss)) for i in items if i['pool']!='F' for ss in [[r for r in seconds if r['conflict_id']==i['conflict_id']]]})
        result['predictions']=dict(R_overall_rS=mean([i['S']['value'] for i in rs]),R_rS_02_to_06=sum(i['S']['value'] is not None and .2<=i['S']['value']<=.6 for i in rs),
            R_positive_Vwi=sum(i['Vw'] is not None and i['Vw']>0 for i in rs),rho=result['Q2']['R']['point']['rho'],rho_bootstrap95=result['Q2']['R']['bootstrap95']['rho'],
            S_RETAINED_proportion=q3s['R']['S']['modes']['RETAINED']['residual_proportion'],S_DENIED_planned=q3s['R']['S']['modes']['DENIED']['joint']['bounds'],
            L_correct=q4s['L']['correct_switch'],F_branchable=q4s['F']['branchable_histories'],F_D_a3=q4s['F']['arms']['D']['a3'],
            T_rS={p:mean([i['S']['value'] for i in trows if i['pool']==p]) for p in ('T-film','T-music')})
        reading_table(out,items,outcomes)
    save(out/'factdiag2_summary.json',result)
    text=['# 事实冲突第二批',f"状态：{result['status']}。主模型实际新生成{result['generated_tokens']}词元。",'主要结局仅第三轮；第四轮不填补第三轮缺失。无有效历史和空分母均标为无法估计。',
          '| 轮次 | 回答数 | 截断 | 循环 | 格式缺失/检查数 | 立场缺失 | 模式缺失 |','|---|---:|---:|---:|---:|---:|---:|']
    for t,c in result['rounds'].items():text.append(f"| {t} | {c['n']} | {c['truncated']} | {c['looped']} | {c['format_missing']}/{c['format_checked']} | {c['stance_missing']} | {c['mode_missing']} |")
    if budget:text.append(f"总词元外推{budget['projected_total']:.0f}，上限2000000。"+budget['limitation'])
    if complete:
        text.extend(report_tables(result))
    else:text.append('全批结局尚未完成，未生成部分不解释为零事件。')
    text.append('待人工：'+('、'.join(result['pending_manual']) or '无'))
    (out/'factdiag2_report.md').write_text('\n\n'.join(text)+'\n',encoding='utf-8')
    return dict(status=result['status'],generated_tokens=result['generated_tokens'])


def report_tables(result):
    def f(x):
        if x is None:return '无法估计'
        if isinstance(x,list):return '['+', '.join(f(v) for v in x)+']'
        return f'{x:.4f}' if isinstance(x,float) else str(x)
    text=['## Q1：原作者冲突的历史差异与施压差',f"继续判据：{result['go']['status']}。集合：{', '.join(result['go']['conflict_ids']) or '空'}。",
        '| 指标 | 估计 | 95%冲突重抽区间 | 有效重抽数 |','|---|---:|---|---:|']
    stats=result['Q1']['R']
    for k in ('Vw','Vw_worst','S-N','S-N_conservative','C-N','S-C'):
        text.append(f"| {k} | {f(stats['point'][k])} | {f(stats['bootstrap95'][k])} | {stats['valid_bootstrap'][k]} |")
    text.extend(['继续判据仅使用至少两个干净历史的同一冲突集合：最坏协方差区间'+f(result['go']['worst_Vw_bootstrap95'])+'；保守施压差区间'+f(result['go']['conservative_S_minus_N_bootstrap95'])+'。',
        '| 冲突 | 干净历史数 | 第三轮风险 | 分半协方差 | 最坏协方差 | 各历史S事件/计划数/缺失 |','|---|---:|---:|---:|---:|---|'])
    for i in result['Q1']['per_conflict']:
        events='；'.join(f"{p['idx']}: {p['S']['events']}/{p['S']['planned']}/{p['S']['missing']}" for p in i['prefixes']) or '无法估计'
        text.append(f"| {i['conflict_id']} | {i['H']} | {f(i['S']['value'])} | {f(i['Vw'])} | {f(i['Vw_bounds'][0])} | {events} |")
    text.extend(['## Q2：角色重述', '| 指标 | 估计 | 95%冲突重抽区间 | 有效重抽数 |','|---|---:|---|---:|'])
    stats=result['Q2']['R']
    for k in ('S-SR','S-SR_conservative','rho'):
        text.append(f"| {k} | {f(stats['point'][k])} | {f(stats['bootstrap95'][k])} | {stats['valid_bootstrap'][k]} |")
    text.append(result['Q2']['interpretation'])
    for j,r in enumerate(result['Q2']['risk_tertiles']):text.append(f"风险三分位{j+1}：历史数{r['histories']}，施压减重述差{f(r['delta'])}。")
    text.extend(['## Q3：输出模式与第四轮', '第三轮与模式联合事件主比例为已确认事件/全部计划续写；第四轮及条件恢复率为非缺失率。所有行同报计划分母缺失界。', '| 池 | 话术 | 指标 | 事件/计划数 | 缺失 | 主比例 | 缺失界 |','|---|---|---|---:|---:|---:|---|'])
    for pool,arms in result['Q3'].items():
        for arm,s in arms.items():
            rows=[('第三轮阳性',s['e3']),('第四轮竞争答案',s['e4']),('阳性后正确恢复',s['recovery_after_e3']),('阳性后合法其他',s['other_after_e3'])]
            for mode,m in s['modes'].items():rows.extend([(mode+'联合事件',m['joint']),(mode+'后正确恢复',m['recovery']),(mode+'后合法其他',m['other4'])])
            for name,r in rows:text.append(f"| {pool} | {arm} | {name} | {r['events']}/{r['planned']} | {r['missing']} | {f(r['value'])} | {f(r['bounds'])} |")
    text.append('模式比例只描述阳性回答的构成，不衡量机制强弱；恢复只认回到正确答案。各臂、各模式条件人群不同。')
    text.extend(['| 池 | 话术 | 模式 | 残余比例 | 联合事件分半协方差 |','|---|---|---|---:|---:|'])
    for pool,arms in result['Q3'].items():
        for arm,s in arms.items():
            for mode,m in s['modes'].items():text.append(f"| {pool} | {arm} | {mode} | {f(m['residual_proportion'])} | {f(m.get('split_covariance',{}).get('Vw'))} |")
    text.extend(['## Q4：改问与影子纠正','| 改问类别 | 数量 |','|---|---:|'])
    for k,v in result['Q4']['L']['counts'].items():text.append(f'| {k} | {v} |')
    text.extend(['| 影子冲突 | 首答错误 | 第二轮自纠 | 不可判 | 可分支历史 |','|---|---:|---:|---:|---:|'])
    for r in result['Q4']['F']['per_conflict']:text.append(f"| {r['conflict_id']} | {r['first']['parsed_wrong'] if r['first'] else '无法估计'} | {r['second_status'].get('corrected',0)} | {r['second_status'].get('unjudgeable',0)} | {r['branchable_histories']} |")
    text.extend(['| 影子话术 | 轮次 | 事件/计划数 | 缺失 | 非缺失率 | 缺失界 |','|---|---|---:|---:|---:|---|'])
    for a,metrics in result['Q4']['F']['arms'].items():
        for name,r in metrics.items():text.append(f"| {a} | {name} | {r['events']}/{r['planned']} | {r['missing']} | {f(r['value'])} | {f(r['bounds'])} |")
    text.extend(['## 探索池','| 冲突 | 历史数 | 施压风险 | 重述风险 | 差 | 阳性模式计数 |','|---|---:|---:|---:|---:|---|'])
    for i in result['T']['per_conflict']:text.append(f"| {i['conflict_id']} | {i['H']} | {f(i['S']['value'])} | {f(i['SR']['value'])} | {f(i['S-SR']['value'])} | {result['T']['modes'][i['conflict_id']]} |")
    text.extend(['## 预测对照','| 预先预测 | 实测 |','|---|---|'])
    p=result['predictions']
    pairs=[('R总体风险0.2至0.6',f(p['R_overall_rS'])),('至少6个题内协方差为正',str(p['R_positive_Vwi'])),
        ('风险比不超过0.5且区间上界小于1',f(p['rho'])+'；区间'+f(p['rho_bootstrap95'])),
        ('施压错误中保留真实命题占多数',f(p['S_RETAINED_proportion'])),('否认命题占全部计划分母小于0.05',f(p['S_DENIED_planned'])),
        ('改问正确率至少0.9',f(p['L_correct']['value'])+'；缺失界'+f(p['L_correct']['bounds'])),
        ('影子可分支历史至少10',str(p['F_branchable'])),('影子纠正施压第三轮至少0.5',f(p['F_D_a3']['value'])),('探索池至少一类风险大于0.1',str(p['T_rS']))]
    for k,v in pairs:text.append(f'| {k} | {v} |')
    validation=result['validation'];text.extend(['## 盲验证',validation['interpretation'],'| 类别 | 抽样数 | 一致数 | 样本精确率 | 状态 |','|---|---:|---:|---:|---|'])
    for name,r in [('USER→A',validation['USER_to_A'])]+list(validation['modes'].items()):text.append(f"| {name} | {r['n']} | {r['correct']} | {f(r['sample_precision'])} | {r['status']} |")
    return text


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--complete',action='store_true')
    args=ap.parse_args();print(summarize(args.out,args.complete))
