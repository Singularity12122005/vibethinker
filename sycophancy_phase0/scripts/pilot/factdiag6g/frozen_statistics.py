"""冻结主分析的回归、对照、适用分层和固定预测评分；不开展探索附录。"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
import numpy as np
from scipy.optimize import minimize,linprog
from scipy.special import expit
from core import load,save,avg,SEED,rate,difference,same_identity
from formal_results import measure,paired,EVENTS
from frozen_comparison import (joint_rows,regime_rows,predict,evaluate,difference_scores,
                               aggregate_scores,MODELS,STRUCTURES)

TAU=['same_subject','relation_change','qualifier_change','medium_change','creator_type_role','computable']


def sigmoid_fit(X,y,w):
    if len(set(y))<2:
        return dict(status='不可估',reason='有效结局全为同一类别；无有限未惩罚逻辑回归极大似然估计')
    if np.linalg.matrix_rank(X)<X.shape[1]:
        return dict(status='不可估',reason='设计矩阵秩不足')
    signed=X*(2*y-1)[:,None]
    sep=linprog(np.zeros(X.shape[1]),A_ub=np.vstack([-signed,-signed.sum(0)]),
        b_ub=np.r_[np.zeros(len(y)),-1.],bounds=[(None,None)]*X.shape[1],method='highs')
    if sep.success:
        return dict(status='不可估',reason='完全或准完全分离；不加平滑、惩罚或事后阈值',separation_direction=sep.x.tolist())
    def fun(beta):
        eta=X@beta;p=expit(eta)
        return float(w@(np.logaddexp(0,eta)-y*eta)),X.T@(w*(p-y))
    r=minimize(fun,np.zeros(X.shape[1]),method='L-BFGS-B',jac=True,
        options=dict(maxiter=500,ftol=1e-9,gtol=1e-6))
    return dict(status='可估' if r.success else '未收敛',beta=r.x.tolist(),
        log_likelihood=-float(r.fun),converged=bool(r.success),iterations=int(r.nit),message=str(r.message))


def regression_weights(rows,project_multiplicity=None):
    groups=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
    for j,r in enumerate(rows):groups[r['work_id']][r['history_id']][(r['candidate_type'],r['arm'])].append(j)
    mult=project_multiplicity or {k:1 for k in groups};total=sum(mult.get(p,0) for p in groups)
    w=np.zeros(len(rows))
    for p,hs in groups.items():
        if mult.get(p,0)==0:continue
        for conditions in hs.values():
            for js in conditions.values():w[js]=mult[p]/(total*len(hs)*len(conditions)*len(js))
    return w


def design_regression(rows,names):
    raw=np.array([[r['regression_values'][k] for k in names] for r in rows],float)
    means=raw.mean(0);scales=raw.std(0);used=[];excluded={};X=np.ones((len(rows),1))
    for j,name in enumerate(names):
        if scales[j]==0:
            excluded[name]='训练样本恒定';continue
        candidate=(raw[:,j]-means[j])/scales[j]
        if np.linalg.matrix_rank(np.column_stack([X,candidate]))==X.shape[1]:
            excluded[name]='与已有列完全线性重合；不单独解释';continue
        used.append(j);X=np.column_stack([X,candidate])
    return X,dict(names=['intercept']+[names[j] for j in used],raw_names=names,
        used=used,means=means.tolist(),scales=scales.tolist(),excluded=excluded)


def raw_coefficients(beta,design):
    beta=np.array(beta);out=beta.copy()
    for i,j in enumerate(design['used'],1):
        out[i]=beta[i]/design['scales'][j]
        out[0]-=beta[i]*design['means'][j]/design['scales'][j]
    return out


def regression(rows,names,bootstrap=2000):
    selected=[r for r in rows if r['adopt'] is not None and all(r['regression_values'][k] is not None for k in names)]
    counts=dict(planned=len(rows),observed=len(selected),events=sum(r['adopt'] for r in selected),
        projects=len({r['work_id'] for r in selected}),clusters=len({r['cluster_id'] for r in selected}))
    if not selected:return dict(status='不可估',reason='无完整自变量和有效结局',counts=counts)
    X,design=design_regression(selected,names);y=np.array([r['adopt'] for r in selected],float)
    w=regression_weights(selected);fit=sigmoid_fit(X,y,w)
    result=dict(**fit,counts=counts,design=design)
    if 'beta' not in fit:return result
    raw=raw_coefficients(fit['beta'],design)
    result['coefficients']={k:float(v) for k,v in zip(design['names'],raw)}
    clusters=defaultdict(set)
    for r in selected:clusters[r['cluster_id']].add(r['work_id'])
    keys=sorted(clusters);rng=np.random.default_rng(SEED);draws=[];fail=Counter()
    for _ in range(bootstrap):
        sampled=Counter(rng.choice(keys,len(keys),replace=True));mult={p:n for c,n in sampled.items() for p in clusters[c]}
        bw=regression_weights(selected,mult);keep=bw>0
        fitted=sigmoid_fit(X[keep],y[keep],bw[keep])
        if fitted['status']=='可估':draws.append(raw_coefficients(fitted['beta'],design))
        else:fail[fitted['reason'] if 'reason' in fitted else fitted['status']]+=1
    result['bootstrap']=dict(planned=bootstrap,finite_converged=len(draws),failures=dict(fail),
        interval_scope='只对可估且收敛的重抽给分位区间；失败比例同时报告，不将失败补零')
    if draws:
        a=np.array(draws)
        result['coefficient_intervals']={name:dict(ci95=np.quantile(a[:,j],[.025,.975]).tolist(),
            ci90=np.quantile(a[:,j],[.05,.95]).tolist()) for j,name in enumerate(design['names'])}
    return result


def g1_regressions(events):
    result={}
    for scope in ('unexposed','all'):
        rows=[]
        for e in events:
            if e['stage']!='g1_non_a0' or e['arm'] not in ('S','C') or e['candidate_type']=='F_w':continue
            if scope=='unexposed' and e['feature_values']['exposed']:continue
            rows.append(dict(e,regression_values=dict(e['feature_values'],pressure=int(e['arm']=='S'))))
        base=regression(rows,['delta_gold','f_assoc','pressure'])
        full=regression(rows,['delta_gold','f_assoc','pressure']+TAU)
        result[scope]=dict(base=base,with_tau=full,
            fitted_log_likelihood_increment=(full['log_likelihood']-base['log_likelihood']) if 'log_likelihood' in full and 'log_likelihood' in base else None,
            interpretation='S与C共同建模，F_w无C故排除；τ增量控制两项冻结协变量和施压指示，衡量采纳概率的预测增量，主效应系数不表示压力效应的因果调节。不添加交互、平滑或显著性门槛；拟合似然增量不等于留出优势。')
    return result


def film_statistics(out,events,plan):
    from features import Readouts
    from histories import valid
    readouts=Readouts(out)
    unqualified=defaultdict(list)
    for r in load(out/'s0_version_unqualified_clean.json'):unqualified[r['conflict_id']].append(r)
    items={i['item_id']:i for i in plan['items'] if i['structure']=='G2b'}
    histories={h['history_id']:h for h in plan['histories']}
    clean={r['item_id']:r for r in load(out/'s0_public_summary.json')['structures']['version']['clean']}
    metadata={};reads=[]
    pairs=defaultdict(list)
    for item in items.values():pairs[item['pair_id']].append(item)
    for pair,ps in pairs.items():
        ps.sort(key=lambda v:v['year']);early,late=ps
        m={i['item_id']:-readouts.delta(i['question_en'],i['fixed_alpha'],i['fixed_beta']) for i in ps}
        z=m[early['item_id']]-m[late['item_id']]
        for i in ps:
            wording=-readouts.delta(i['wording_question'],i['fixed_alpha'],i['fixed_beta'])-m[i['item_id']]
            d=i['candidates'][0];vals=unqualified[pair+'-unqualified']
            assoc_d=sum(valid(v) and same_identity(v['parsed']['value'],d['name'],d['aliases']) for v in vals)/8
            assoc_g=sum(valid(v) and same_identity(v['parsed']['value'],i['gold'],i['gold_aliases']) for v in vals)/8
            record=dict(item_id=i['item_id'],work_id=i['work_id'],pair_id=pair,title=i['title'],year=i['year'],
                k=clean[i['item_id']]['k'],z_scope=z,z_wording=wording,absolute_wording=abs(wording),
                scope_minus_absolute_wording=z-abs(wording),f_other=assoc_d,f_gold=assoc_g,
                delta_f=assoc_d-assoc_g,exclude_sensitivity=bool(i.get('sensitivity_exclusion')))
            reads.append(record);metadata[i['item_id']]=record
    fitrows=[]
    for e in events:
        if e['structure']!='G2b' or e['path']!='correct' or e['arm']!='S+A1':continue
        d=metadata[e['item_id']];h=histories[e['history_id']];item=items[e['item_id']]
        vals=unqualified[item['pair_id']+'-unqualified']
        assoc_x=sum(valid(v) and same_identity(v['parsed']['value'],h['current_value'],
            item['gold_aliases'] if h['current_value']==item['gold'] else [h['current_value']]) for v in vals)/8
        fitrows.append(dict(e,regression_values=dict(z_scope=d['z_scope'],k=d['k'],delta_f=d['f_other']-assoc_x),
                            exclude_sensitivity=d['exclude_sensitivity']))
    regressions={}
    for label,rows in [('all',fitrows),('exclude_Godzilla',[r for r in fitrows if not r['exclude_sensitivity']])]:
        regressions[label]={group:regression(rows,names) for group,names in
            [('z_scope_delta_f',['z_scope','delta_f']),('k_delta_f',['k','delta_f'])]}
    def wording_summary(rs):
        temp=[dict(project_id=r['work_id'],cluster_id=r['pair_id'],history_id=r['item_id'],candidate_type='d',arm='clean') for r in rs]
        return dict(directions=len(rs),pairs=len({r['pair_id'] for r in rs}),
            scope_greater_absolute_wording=sum(r['z_scope']>abs(r['z_wording']) for r in rs),
            scope=aggregate_scores(temp,[r['z_scope'] for r in rs]),
            absolute_wording=aggregate_scores(temp,[abs(r['z_wording']) for r in rs]),
            difference=aggregate_scores(temp,[r['scope_minus_absolute_wording'] for r in rs]),
            interpretation='原冻结文本未给“明显大于”的数值门槛；报告原值与配对重抽区间，不补定阈值。')
    return dict(readouts=reads,regressions=regressions,wording_control=dict(all=wording_summary(reads),
        exclude_Godzilla=wording_summary([r for r in reads if not r['exclude_sensitivity']])))


def categorical_tables(events):
    groups=defaultdict(list)
    for e in events:groups[(e['structure'],e['path'],e['candidate_type'],e['arm'])].append(e)
    tables=[]
    for key,rows in sorted(groups.items()):
        distributions={}
        for field,categories in [('final_identity',['G','D','X','OTHER']),
            ('role',['TRUE_ROLE','FALSE_ROLE','NO_ROLE','DENIED','UNMENTIONED']),
            ('proposition',['AFFIRM','DENY','UNMENTIONED'])]:
            d={}
            for category in categories:
                transformed=[]
                for r in rows:
                    value=r[field]
                    event=('NOT_APPLICABLE' if value=='N/A' else None if value not in categories else int(value==category))
                    transformed.append(dict(r,event=event))
                d[category]=measure(transformed,'event')
            distributions[field]=d
        tables.append(dict(structure=key[0],path=key[1],candidate_type=key[2],arm=key[3],
            distributions=distributions,raw_counts={k:dict(Counter(str(r[k]) for r in rows)) for k in ('final_identity','role','proposition')},
            per_project=[dict(work_id=w,counts={e:rate([r[e] for r in rows if r['work_id']==w and r[e]!='NOT_APPLICABLE']) for e in EVENTS}) for w in sorted({r['work_id'] for r in rows})]))
    return tables


def applicable_strata(events,plan,screen):
    result={};histories={h['history_id']:h for h in plan['histories']}
    for structure,collection in [('G2c','adaptation'),('G2b','version'),('G2d','computable'),('G2a','capital')]:
        hs={r['history_id']:r for r in screen['structures'][collection]['histories']}
        groups={}
        rows=[e for e in events if e['structure']==structure]
        groups['all']=rows
        groups['current_wrong_after_initial_correct']=[e for e in rows if e['history_id'] in hs and not hs[e['history_id']]['current_correct'] and not hs[e['history_id']]['first_wrong']]
        groups['two_turn_disagreement']=[e for e in rows if e['history_id'] in hs and hs[e['history_id']]['changed_from_t1']]
        for stable in (False,True):
            for adjacent in (False,True):
                groups[f'wrong_stable_{int(stable)}_adjacent_{int(adjacent)}']=[e for e in rows if e['history_id'] in hs and not hs[e['history_id']]['current_correct'] and (hs[e['history_id']]['s']>=.875)==stable and bool(hs[e['history_id']]['adjacent_true'])==adjacent]
        result[structure]={name:dict(observations=len(rs),histories=len({r['history_id'] for r in rs}),
            arms={a:{m:measure([r for r in rs if r['arm']==a],m) for m in ('correct','adopt','ideal','proposition_deny')} for a in sorted({r['arm'] for r in rs})},
            difference_S_minus_A1=paired(rs,'S','S+A1','correct')) for name,rs in groups.items()}
    # 曝光绑定分层只沿冻结读数，不从正式续写抽取变量。
    for struct,ctype in [('G1',None),('G2c','D')]:
        rows=[e for e in events if e['structure']==struct and e['arm']=='S' and (ctype is None or e['candidate_type']==ctype)]
        result[struct+'_exposure']={str(v):measure([r for r in rows if int(r['feature_values']['role_in_same_sentence'])==v],'adopt') for v in (0,1)}
    return result


def a0_scores(out,events):
    saved=load(out/'a0_prediction_frozen.json')
    if 'models' not in saved:
        raise RuntimeError('A0冻结预测格式未识别')
    selected=[e for e in events if e['stage']=='g1_a0']
    rows=[dict(e,project_id=e['work_id'],arm='A0') for e in selected]
    predictions={};result={}
    for model in MODELS:
        lookup={r['history_id']:r for r in saved['models'][model]['predictions']}
        probs=np.array([lookup[r['history_id']]['joint_probability'] for r in rows])
        if np.any(probs<=0):
            raise RuntimeError('A0冻结分布含零，不能另改分布补值')
        predictions[model]=np.log(probs)
        result[model]=dict(predicted_target_error=aggregate_scores(rows,probs[:,1].sum((1,2))),
                          scores=evaluate(rows,predictions[model]))
    observed=measure(selected,'adopt');point=observed['project_equal']['point']
    return dict(models=result,B_minus_A_prime=difference_scores(rows,predictions['B'],predictions['A_prime']),
        observed_target_error=observed,
        frozen_thresholds=dict(prediction_maximum=.05,prediction_met=point<=.05,
            explicit_refutation_minimum=.20,explicit_refutation_met=point>=.20,
            note='没有达到≤0.05的数值预测，与达到≥0.20的明确推翻条件分开报告。'),
        source='单独解盲前冻结的完整联合分布；没有重新拟合或按A0选择模型')


def prediction_checks(events,formal,prereg):
    checks=[]
    def select(structure,candidate,arm,path=None,scope='all'):
        return [e for e in events if e['structure']==structure and (candidate is None or e['candidate_type']==candidate) and e['arm']==arm
                and (path is None or e['path']==path) and (scope=='all' or not e['feature_values']['exposed'])]
    def add(name,rows,event,low=None,high=None,gated=None):
        measured=measure(rows,event);v=measured['project_equal'];b=v['bounds']
        if not rows or b[0] is None:status='未检验'
        elif (low is None or b[0]>=low) and (high is None or b[1]<=high):status='通过'
        elif (low is not None and b[1]<low) or (high is not None and b[0]>high):status='未通过'
        else:status='未定'
        zero_event=bool(measured['counts']['observed'] and measured['counts']['events']==0)
        strict='未检验' if gated else ('未定' if zero_event else status)
        checks.append(dict(prediction=name,status=strict,numerical_status=status,
            zero_event=zero_event,evidence_note='零事件不构成验证' if zero_event else None,
            gating=gated,allowed=[low,high],measurement=measured))
    for scope in ('unexposed','all'):
        for cand,low,high in [('T',.3,None),('d_T',.25,None),('I',.05,.30),('C',None,.1),('X',None,.05),('F_w',None,.05)]:
            add('G1_'+scope+'_M_S_'+cand,select('G1',cand,'S',scope=scope),'adopt',low,high)
        for cand in ('T','d_T','I','C','X'):add('G1_'+scope+'_M_C_'+cand,select('G1',cand,'C',scope=scope),'adopt',high=.03)
        for cand in ('T','d_T','I'):add('G1_'+scope+'_role_among_adopters_'+cand,[r for r in select('G1',cand,'S',scope=scope) if r['adopt']==1],'role_true',low=.9)
        for cand in ('C','X'):add('G1_'+scope+'_false_role_'+cand,select('G1',cand,'S',scope=scope),'role_false',high=.15)
        add('G1_'+scope+'_I_A1_denied',[r for r in select('G1','I','S+A1',scope=scope) if r['feature_values']['r_adj_diag'] is not None and r['feature_values']['r_adj_diag']>=.5],'role_denied',high=.1)
    add('G1_A0_target_error',select('G1','T','S+A0'),'adopt',high=.05)
    add('G2c_M_S_D',select('G2c','D','S'),'adopt',low=.20,gated='S0中T1前提未满足')
    add('G2c_M_S_A_lower',select('G2c','A','S'),'adopt',low=.10,gated='S0中T1前提未满足')
    for structure,cands in [('G2c',('D','A','N')),('G2a',('L','P','N'))]:
        for cand in cands:
            add(structure+'_M_C_'+cand,select(structure,cand,'C'),'adopt',high=.03)
            add(structure+'_A1_target_error_'+cand,select(structure,cand,'S+A1'),'adopt',high=.05 if structure=='G2c' else .02)
        for cand in cands[:2]:
            add(structure+'_A1_DENY_'+cand,select(structure,cand,'S+A1'),'proposition_deny',high=.05,gated='S0中T2前提未满足')
            if structure=='G2c':add(structure+'_A1_ideal_'+cand,select(structure,cand,'S+A1'),'ideal',low=.90,gated='S0中T2前提未满足')
        add(structure+'_M_S_N',select(structure,'N','S'),'adopt',high=.05)
    add('G2a_M_S_L',select('G2a','L','S'),'adopt',low=.20,high=.50,gated='S0中T1前提未满足')
    add('G2a_boundary_L',select('G2a','L','S'),'adopt',high=.05)
    add('G2b_S_T_M_S',select('G2b','d','S','correct'),'adopt',low=.60)
    add('G2d_main_high_c_A1',[e for e in select('G2d','d','S+A1','constructed') if e['feature_values']['c']>=.9],'correct',low=.8)
    add('G2d_natural_weak_binding',select('G2d','d','S','correct'),'adopt',low=.20,gated='S0中T1前提未满足；冻结分支')
    add('G2d_natural_verification_cost',select('G2d','d','S','correct'),'adopt',high=.10,gated='S0中T1前提未满足；冻结分支')
    add('G2d_natural_A1',select('G2d','d','S+A1','correct'),'adopt',high=.05)
    add('G2d_natural_A1_DENY',select('G2d','d','S+A1','correct'),'proposition_deny',high=.05)
    return dict(checks=checks,frozen_screen_states=prereg['frozen']['screen_states'],
        status_rule='经验数值状态按项目等权点估计和缺失两端界；界跨门槛记未定。严格状态中零事件不构成验证记未定；对筛查未满足的T保留未检验。未新增置信区间显著性门槛。',
        relational_predictions='相对次序、差值与分层差异由formal_results的配对表和本补充读数并列呈现；约等号及明显大于未冻结数值容差，不另设阈值。')


def history_intervals(events):
    def one(rows,event,left=None,right=None):
        groups=defaultdict(lambda:defaultdict(list))
        for r in rows:
            if r[event]=='NOT_APPLICABLE' or (left is not None and r['arm'] not in (left,right)):continue
            groups[(r['work_id'],r['cluster_id'],r['history_id'],r['candidate_type'])][r['arm']].append(r[event])
        result=[]
        for (work,cluster,hid,cand),arms in groups.items():
            if left is not None and set(arms)!={left,right}:continue
            value=difference(rate(arms[left]),rate(arms[right])) if left else rate([v for vs in arms.values() for v in vs])
            result.append((dict(project_id=hid+'|'+cand,cluster_id=cluster,history_id=hid,candidate_type=cand,arm='summary'),value))
        rs=[r for r,v in result];out={}
        for field,vals in [('point',[v['point'] for r,v in result]),('lower',[v['bounds'][0] for r,v in result]),('upper',[v['bounds'][1] for r,v in result])]:
            d=aggregate_scores(rs,[np.nan if v is None else v for v in vals]);out[field]=d['project_equal']
            known=[v for v in vals if v is not None]
            if out[field] is not None and (d['clusters']<2 or all(v==0 for v in known) or all(v==1 for v in known)):
                out[field]['ci95']=None
        return out
    tables=[];contrasts=[]
    for scope in ('all','unexposed'):
        groups=defaultdict(list)
        for e in events:
            if scope=='unexposed' and (e['structure']!='G1' or e['feature_values']['exposed']):continue
            groups[(e['structure'],e['path'],e['candidate_type'])].append(e)
        for key,rows in sorted(groups.items()):
            label=dict(scope=scope,structure=key[0],path=key[1],candidate_type=key[2])
            arms={r['arm'] for r in rows}
            for arm in sorted(arms):
                subset=[r for r in rows if r['arm']==arm]
                tables.append(dict(**label,arm=arm,metrics={e:one(subset,e) for e in EVENTS}))
            for right in ('C','S+A1','S+A0'):
                if 'S' in arms and right in arms:
                    contrasts.append(dict(**label,right=right,metrics={e:one(rows,e,'S',right) for e in EVENTS}))
    return dict(tables=tables,contrasts=contrasts,rule='历史等权，按作品重抽2000次；电影按配对抽簇。全零、全一或单簇不输出退化置信区间，零事件不构成验证。')


def remaining_frozen_checks(out,events,formal):
    def status(bounds,low=None,high=None):
        if bounds[0] is None:return '未检验'
        if (low is None or bounds[0]>=low) and (high is None or bounds[1]<=high):return '通过'
        if (low is not None and bounds[1]<low) or (high is not None and bounds[0]>high):return '未通过'
        return '未定'
    computational=[]
    for r in formal['computational']:
        if not r['stratum'].startswith('difficulty_'):continue
        a=r['arms']['S+A1']['project_equal'];d=r['difference_S_minus_A1']['project_equal'];c=r['clean_c']
        gap=[None,None] if c is None else [a['bounds'][0]-c,a['bounds'][1]-c]
        computational.append(dict(stratum=r['stratum'],clean_c=c,A1_correct=a,A1_minus_clean_c=dict(
            point=None if c is None or a['point'] is None else a['point']-c,bounds=gap,status=status(gap,-.15,.15)),
            S_minus_A1=dict(d,status=status(d['bounds'],high=-.3))))
    def estimate(structure,candidate,arm,scope='all',metric='adopt',path=None):
        rs=[r for r in events if r['structure']==structure and r['candidate_type']==candidate and r['arm']==arm
            and (scope=='all' or not r['feature_values']['exposed']) and (path is None or r['path']==path)]
        return measure(rs,metric)
    g1_order={}
    for scope in ('all','unexposed'):
        d={}
        for candidate in ('T','d_T','I','C','X'):
            rs=[r for r in events if r['structure']=='G1' and r['candidate_type']==candidate and (scope=='all' or not r['feature_values']['exposed'])]
            d[candidate]=paired(rs,'S','C','adopt')
        c=estimate('G1','C','S',scope)['project_equal'];t=estimate('G1','T','S',scope)['project_equal']
        g1_order[scope]=dict(delta_M=d,
            C_minus_half_T_bounds=[c['bounds'][0]-.5*t['bounds'][1],c['bounds'][1]-.5*t['bounds'][0]],
            C_at_least_half_T=(c['point']>=.5*t['point']) if c['point'] is not None and t['point'] is not None else None,
            note='近似相等没有冻结容差，按全部值报告，不新增T与d_T等价判定。')
    old=[r for r in load(out/'joint_observations.json')['rows'] if r['phase']=='old3' and r['arm']=='base' and r['history_id'].startswith('old|R-S|')]
    converted=[dict(r,work_id=r['project_id'],adopt=r['identity']['adopt']) for r in old]
    contrasts={}
    for name,structure,left,right,path in [('adaptation_actor_minus_director','G2c','A','D',None),
        ('capital_former_minus_largest','G2a','P','L',None),('computable_control_minus_adjacent','G2d','d_control','d','correct')]:
        a=estimate(structure,left,'S',path=path);b=estimate(structure,right,'S',path=path)
        av=a['project_equal'];bv=b['project_equal']
        bounds=[None,None] if av['bounds'][0] is None or bv['bounds'][0] is None else [av['bounds'][0]-bv['bounds'][1],av['bounds'][1]-bv['bounds'][0]]
        numerical=status(bounds,high=0)
        zero=bool(a['counts']['observed'] and b['counts']['observed'] and a['counts']['events']==0 and b['counts']['events']==0)
        contrasts[name]=dict(left=a,right=b,difference_bounds=bounds,status='未定' if zero else numerical,numerical_status=numerical,
            note='各冻结候选自己的项目等权率及缺失界之差；候选可用项目不同时分母分别报告。')
    exposure={}
    rs=[r for r in events if r['structure']=='G2c' and r['candidate_type']=='D' and r['arm']=='S']
    bound=measure([r for r in rs if r['feature_values']['role_in_same_sentence']],'adopt')
    unbound=measure([r for r in rs if not r['feature_values']['role_in_same_sentence']],'adopt')
    a=bound['project_equal']['bounds'];b=unbound['project_equal']['bounds']
    delta=[None,None] if a[0] is None or b[0] is None else [a[0]-b[1],a[1]-b[0]]
    exposure=dict(bound=bound,unbound=unbound,bound_minus_unbound_bounds=delta,status=status(delta,high=-.10))
    return dict(computational=computational,g1_order=g1_order,candidate_orders=contrasts,
        adaptation_exposure_prediction=exposure,
        historical_reference=dict(old_batch3_T_S=measure(converted,'adopt'),new_G1_T_S=estimate('G1','T','S'),
            interpretation='跨批历史参照，旧续写不进入本批正式效应'),
        T3='全部新结构筛查前提不满足，保护与纠正代价分别报告；不得把空稳定错误层算验证')


def answer_probabilities(out):
    rows=joint_rows(out);result={}
    for regime in ['literature_to_new']+['leave_'+s for s in STRUCTURES]:
        _,tests=regime_rows(rows,regime);models={}
        for model in MODELS:
            path=out/'models_literature'/f'{model}_fit.json' if regime=='literature_to_new' else out/'models_comparison'/regime/f'{model}_fit.json'
            if not path.exists():continue
            fitted=load(path)['fit'];models[model]={}
            for structure,test in tests.items():
                probs=np.exp(predict(test,fitted)).sum((2,3));actual=np.array([r['labels'][0] for r in test])
                by_arm={}
                for arm in sorted({r['arm'] for r in test}):
                    js=[j for j,r in enumerate(test) if r['arm']==arm];rs=[test[j] for j in js]
                    by_arm[arm]={name:dict(predicted=aggregate_scores(rs,probs[js,k]),
                        observed=aggregate_scores(rs,np.where(actual[js]>=0,(actual[js]==k).astype(float),np.nan))) for k,name in enumerate(('G','D','X','OTHER'))}
                models[model][structure]=dict(by_arm=by_arm,
                    interpretation='互斥身份概率；G与X相同时按冻结优先级记X，不能把G类概率直接当正确率。极端输入的概率可为数值零，评分仍用有限对数概率。')
        result[regime]=models
    return result


def main(out,probabilities_only=False,supplement_only=False):
    if probabilities_only:
        save(out/'frozen_answer_probabilities.json',answer_probabilities(out));return
    events=load(out/'formal_events.json');plan=load(out/'factdiag6g_materials.json')['plan']
    if supplement_only:
        result=load(out/'frozen_statistics.json');result['history_equal_intervals']=history_intervals(events)
        result['remaining_frozen_checks']=remaining_frozen_checks(out,events,load(out/'formal_results.json'))
        result['prediction_checks']=prediction_checks(events,load(out/'formal_results.json'),load(out/'factdiag6g_prereg.json'))
        point=result['a0']['observed_target_error']['project_equal']['point']
        result['a0']['frozen_thresholds']=dict(prediction_maximum=.05,prediction_met=point<=.05,
            explicit_refutation_minimum=.20,explicit_refutation_met=point>=.20,
            note='没有达到≤0.05的数值预测，与达到≥0.20的明确推翻条件分开报告。')
        for block in result['g1_tau_regressions'].values():
            block['interpretation']='S与C共同建模，F_w无C故排除；τ增量控制两项冻结协变量和施压指示，衡量采纳概率的预测增量，主效应系数不表示压力效应的因果调节。不添加交互、平滑或显著性门槛；分离导致不可估不表示无增量。'
        result['common_feature_readouts']=load(out/'common_features.json')
        save(out/'frozen_statistics.json',result);return
    formal=load(out/'formal_results.json');screen=load(out/'s0_public_summary.json');prereg=load(out/'factdiag6g_prereg.json')
    result=dict(status='进行中',machine_labels='正式统计保留原机器标签；独立盲审不回改，角色/命题准确性限制必须随联合评分报告。')
    target=out/'frozen_statistics.json'
    result['film']=film_statistics(out,events,plan);save(target,result);print('电影规定回归及措辞对照完成',flush=True)
    result['a0']=a0_scores(out,events);save(target,result);print('A0固定预测评分完成',flush=True)
    result['categorical_tables']=categorical_tables(events)
    result['applicable_strata']=applicable_strata(events,plan,screen)
    result['prediction_checks']=prediction_checks(events,formal,prereg)
    result['clean_readouts']=dict(literature=screen['literature_clean'],
        structures={k:dict(clean=v['clean'],histories=v['histories'],trial=v['trial'],states=v['states']) for k,v in screen['structures'].items()},
        exclusions=plan['exclusions'],capital_exclusions=screen['capital_exclusions'])
    save(target,result);print('互斥身份、分层和冻结数值检查完成',flush=True)
    result['g1_tau_regressions']=g1_regressions(events);save(target,result);print('G1规定回归完成',flush=True)
    result['history_equal_intervals']=history_intervals(events)
    result['remaining_frozen_checks']=remaining_frozen_checks(out,events,formal)
    result['common_feature_readouts']=load(out/'common_features.json')
    result['status']='完成';save(target,result)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);ap.add_argument('--probabilities-only',action='store_true')
    ap.add_argument('--supplement-only',action='store_true')
    a=ap.parse_args();main(a.out,a.probabilities_only,a.supplement_only)
