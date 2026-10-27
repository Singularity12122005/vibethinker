"""冻结跨结构预测、特征增量与规定统计。只读既有产物，纯中央处理器。"""
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import argparse
import random
import time
import numpy as np
from scipy.special import logsumexp, log_softmax

from core import load, save, SEED, digest, INTERVENTION_FIELDS
from fit_prediction import design_fit, design_apply, feature_columns, observation_weights, PENALTIES
from joint_model import JointModel, observed_mask

MODELS = ('A', 'A_prime', 'B')
STRUCTURES = ('literature', 'G2c', 'G2b', 'G2d', 'G2a')
GROUPS = ['s', 'delta_pol', 'delta_gold', 'f_assoc', 'r_adj_diag', 'r_adj_online',
          'exposed', 'role_in_same_sentence', 'k', 'z_scope', 'c', 'same_subject',
          'relation_change', 'qualifier_change', 'medium_change', 'creator_type_role', 'computable']


def predict(rows,fitted):
    """在对数域计算同一联合链；极端外推不下溢、不截断、不平滑。"""
    X,gate=design_apply(rows,fitted['design'])
    m=JointModel(X.shape[1],gate.shape[1] if gate is not None else 0)
    theta=np.array(fitted['fit']['theta']);chains=[];p=X.shape[1]
    for z in range(m.components):
        w1,w2,w3=m.chain.unpack(theta[z*m.chain.n:(z+1)*m.chain.n])
        l1=log_softmax(X@w1,axis=-1)
        l2=log_softmax((X@w2[:p])[:,None,:]+w2[p:][None,:,:],axis=-1)
        l3=log_softmax((X@w3[:p])[:,None,None,:]+w3[p:p+4][None,:,None,:]+w3[p+4:][None,None,:,:],axis=-1)
        chains.append(l1[:,:,None,None]+l2[:,:,:,None]+l3)
    if m.components==1:return chains[0]
    eta=gate@theta[2*m.chain.n:]
    return np.logaddexp(chains[0]-np.logaddexp(0,-eta)[:,None,None,None],
                        chains[1]-np.logaddexp(0,eta)[:,None,None,None])


def log_scores(distribution,labels):
    y=np.array(labels,dtype=int);mask=observed_mask(y).astype(bool)
    joint=logsumexp(np.where(mask,distribution,-np.inf),axis=(1,2,3))
    joint[np.all(y<0,axis=1)]=np.nan
    result=dict(joint=joint)
    for axis in range(3):
        marginal=logsumexp(distribution,axis=tuple(i for i in (1,2,3) if i!=axis+1))
        known=y[:,axis]>=0;v=np.full(len(y),np.nan)
        v[known]=marginal[np.where(known)[0],y[known,axis]]
        result['y'+str(axis+1)]=v
    return result


def score(rows,distribution):
    values=log_scores(distribution,[r['labels'] for r in rows])['joint']
    return float(observation_weights(rows)@np.nan_to_num(values,nan=0.))


def joint_rows(out):
    old = load(out/'joint_observations.json')['rows']
    rows = [r for r in old if r['structure']=='literature']
    if len(rows)!=6160 or any(r['arm']=='A0' for r in rows):
        raise RuntimeError('原文献域训练观测不符冻结输入')
    for e in load(out/'formal_events.json'):
        if e['structure']=='G1':
            continue
        rows.append(dict(id=e['id'], structure=e['structure'], project_id=e['work_id'],
            cluster_id=e['cluster_id'], history_id=e['history_id'], candidate_type=e['candidate_type'],
            arm={'S':'base','S+A1':'A1','C':'C'}[e['arm']], phase=e['stage'],
            feature_values=e['feature_values'], labels=e['labels']))
    if len(rows)!=len({r['id'] for r in rows}):
        raise RuntimeError('联合数据重复')
    return rows


def collapse_design(X, labels, weights, gate=None):
    """完全相同的设计、未知模式和标签只合并权重，目标函数与梯度恒等。"""
    labels=np.asarray(labels, dtype=int)
    matrix=np.column_stack([X, labels] if gate is None else [X, gate, labels])
    unique, first, inv=np.unique(matrix, axis=0, return_index=True, return_inverse=True)
    del unique
    summed=np.bincount(inv, weights=weights, minlength=len(first))
    return X[first], labels[first], summed, None if gate is None else gate[first]


def fit_compact(rows, model, penalty, omit=None):
    if any(r['arm']=='A0' for r in rows):
        raise RuntimeError('A0禁止进入拟合')
    design=design_fit(rows,model,omit)
    X,gate=design_apply(rows,design)
    X,y,w,gate=collapse_design(X,[r['labels'] for r in rows],observation_weights(rows),gate)
    fitted=JointModel(X.shape[1],gate.shape[1] if gate is not None else 0).fit(X,y,w,penalty,gate)
    fitted['original_observations']=len(rows)
    fitted['equivalent_compressed_observations']=len(X)
    return dict(design=design,fit=fitted)


def choose_cached(rows,model,target):
    groups=sorted({r['cluster_id'] for r in rows})
    random.Random(SEED).shuffle(groups)
    if len(groups)<5:
        raise RuntimeError('训练项目不足五折')
    folds={g:i%5 for i,g in enumerate(groups)}
    results=[]
    for penalty in PENALTIES:
        vals=[]; convergence=[]
        for fold in range(5):
            train=[r for r in rows if folds[r['cluster_id']]!=fold]
            test=[r for r in rows if folds[r['cluster_id']]==fold]
            path=target/f'cv_{model}_{penalty}_{fold}.json'
            signature=digest(dict(train=[r['id'] for r in train],test=[r['id'] for r in test],model=model,penalty=penalty))
            if path.exists():
                cached=load(path)
                if cached['signature']!=signature:
                    raise RuntimeError('验证缓存输入不一致')
                cached['score']=score(test,predict(test,cached['fitted']))
                save(path,cached)
            else:
                fitted=fit_compact(train,model,penalty)
                cached=dict(signature=signature,fitted=fitted,score=score(test,predict(test,fitted)))
                save(path,cached)
            vals.append(cached['score']);convergence.append(cached['fitted']['fit']['converged'])
        results.append(dict(penalty=penalty,scores=vals,mean=float(np.mean(vals)),converged=convergence))
        print('冻结五折完成',target.name,model,penalty,flush=True)
    best=max(results,key=lambda r:(r['mean'],r['penalty']))
    return dict(chosen=best['penalty'],results=results,folds=folds)


def aggregate_scores(rows, values):
    values=np.asarray(values,dtype=float)
    if np.any(np.isinf(values)):
        raise FloatingPointError('有效评分出现无穷值；不得当缺失删除')
    groups=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
    for r,v in zip(rows,values):
        if np.isfinite(v):
            groups[(r['project_id'],r['cluster_id'])][r['history_id']][(r['candidate_type'],r['arm'])].append(float(v))
    projects=[]
    for (p,c),histories in sorted(groups.items()):
        hs=[float(np.mean([np.mean(vs) for vs in conditions.values()])) for conditions in histories.values()]
        projects.append(dict(project_id=p,cluster_id=c,score=float(np.mean(hs)),history_sum=sum(hs),histories=len(hs)))
    if not projects:
        return dict(project_equal=None,history_equal=None,observations=0,projects=0,histories=0,clusters=0,per_project=[])
    clusters=defaultdict(list)
    for p in projects:
        clusters[p['cluster_id']].append(p)
    arr=np.array([[sum(p['score'] for p in ps),len(ps),sum(p['history_sum'] for p in ps),sum(p['histories'] for p in ps)] for ps in clusters.values()])
    ind=np.random.default_rng(SEED).integers(0,len(arr),(2000,len(arr)))
    b=arr[ind].sum(1)
    def est(num,den):
        return dict(point=float(arr[:,num].sum()/arr[:,den].sum()),
            ci95=np.quantile(b[:,num]/b[:,den],[.025,.975]).tolist())
    return dict(project_equal=est(0,1),history_equal=est(2,3),observations=int(np.isfinite(values).sum()),
        projects=len(projects),histories=sum(p['histories'] for p in projects),clusters=len(clusters),per_project=projects)


def score_arrays(rows,distribution):
    result=log_scores(distribution,[r['labels'] for r in rows])
    labels=np.array([r['labels'] for r in rows])
    for name,known in [('complete_three',np.all(labels>=0,axis=1)),
                       ('complete_three_applicable',np.all(labels>=0,axis=1)&(labels[:,2]!=3))]:
        result[name]=np.where(known,result['joint'],np.nan)
    return result


def evaluate(rows,distribution):
    return {k:aggregate_scores(rows,v) for k,v in score_arrays(rows,distribution).items()}


def difference_scores(rows,left,right):
    a=score_arrays(rows,left);b=score_arrays(rows,right)
    return {k:aggregate_scores(rows,a[k]-b[k]) for k in a}


def parameter_summary(fitted, validation=None):
    d=fitted['design'];f=fitted['fit']
    features=['intercept']+[d['names'][j] for j in d['kept']]+[d['names'][j]+'_missing' for j in d['missing_kept']]
    arms=[INTERVENTION_FIELDS[j] for j in d['arm_kept']]
    base=features if d['model']=='B' else features+arms
    gate=['intercept']+[d['names'][j] for j in d['kept'] if d['names'][j] in {'s','delta_pol','exposed','role_in_same_sentence'}]
    gate +=[d['names'][j]+'_missing' for j in d['missing_kept'] if d['names'][j] in {'s','delta_pol','exposed','role_in_same_sentence'}]+arms
    m=JointModel(len(base),len(gate) if d['model']=='B' else 0)
    theta=np.array(f['theta']);parts=[]
    for z in range(m.components):
        matrices=m.chain.unpack(theta[z*m.chain.n:(z+1)*m.chain.n])
        parts.append(dict(heads=[dict(features=names,coefficients=w.tolist()) for names,w in zip(
            [base,base+['y1_'+str(i) for i in range(4)],base+['y1_'+str(i) for i in range(4)]+['y2_'+str(i) for i in range(5)]],matrices)]))
    return dict(validation=validation,fit={k:v for k,v in f.items() if k!='theta'},design=d,components=parts,
        gate=dict(features=gate,coefficients=theta[2*m.chain.n:].tolist()) if d['model']=='B' else None,
        interpretation='标准化设计的惩罚系数；训练恒定列固定零。重合列和混合分量标签不得单独作机制解释。')


def regime_rows(rows,regime):
    if regime=='literature_to_new':
        return [r for r in rows if r['structure']=='literature'],{s:[r for r in rows if r['structure']==s] for s in STRUCTURES[1:]}
    held=regime.removeprefix('leave_')
    return [r for r in rows if r['structure']!=held],{held:[r for r in rows if r['structure']==held]}


def run_model(out_string,regime,model):
    out=Path(out_string);start=time.monotonic();rows=joint_rows(out)
    train,tests=regime_rows(rows,regime)
    target=out/'models_comparison'/regime;target.mkdir(parents=True,exist_ok=True)
    if regime=='literature_to_new':
        saved=load(out/'models_literature'/f'{model}_fit.json')
        fitted=saved['fit'];validation=saved['validation']
    else:
        path=target/f'{model}_fit.json'
        if path.exists():
            saved=load(path);fitted=saved['fit'];validation=saved['validation']
        else:
            validation=choose_cached(train,model,target)
            fitted=fit_compact(train,model,validation['chosen'])
            save(path,dict(fit=fitted,validation=validation))
    full={s:predict(test,fitted) for s,test in tests.items()}
    result=dict(model=model,training_observations=len(train),training_projects=len({r['project_id'] for r in train}),
        parameters=parameter_summary(fitted,validation),scores={s:evaluate(t,full[s]) for s,t in tests.items()},increments={})
    save(target/f'{model}_summary.json',result)
    learned={fitted['design']['names'][j] for j in fitted['design']['kept']+fitted['design']['missing_kept']}
    for group in GROUPS:
        removed=set(feature_columns(model))-set(feature_columns(model,{group}))
        if not removed:
            result['increments'][group]=dict(status='不适用',reason='该模型的冻结特征集合不含此组')
        elif not removed.intersection(learned):
            result['increments'][group]=dict(status='不可估',reason='训练域该组恒定或全缺失，完整模型已固定零，不重复拟合',removed=sorted(removed))
        else:
            path=target/f'{model}_without_{group}.json'
            if path.exists():
                reduced=load(path)
            else:
                reduced=fit_compact(train,model,validation['chosen'],{group});save(path,reduced)
            result['increments'][group]=dict(status='完成',penalty=validation['chosen'],removed=sorted(removed),
                convergence={k:v for k,v in reduced['fit'].items() if k!='theta'},
                full_minus_removed={s:difference_scores(t,full[s],predict(t,reduced)) for s,t in tests.items()})
        save(target/f'{model}_summary.json',result)
    print('冻结模型及增量完成',regime,model,round(time.monotonic()-start,1),'秒',flush=True)
    return regime,model


def collect_comparison(out,result):
    rows=joint_rows(out)
    for regime in ['literature_to_new']+['leave_'+s for s in STRUCTURES]:
        _,tests=regime_rows(rows,regime)
        target=out/'models_comparison'/regime
        entry=result.setdefault('regimes',{}).setdefault(regime,dict(models={},differences={}))
        for model in MODELS:
            path=target/f'{model}_summary.json'
            if path.exists():entry['models'][model]=load(path)
        distributions={}
        for model in ('A_prime','B'):
            path=out/'models_literature'/f'{model}_fit.json' if regime=='literature_to_new' else target/f'{model}_fit.json'
            if path.exists():
                fitted=load(path)['fit'];distributions[model]={s:predict(t,fitted) for s,t in tests.items()}
        if len(distributions)==2:
            entry['differences']={s:difference_scores(t,distributions['B'][s],distributions['A_prime'][s]) for s,t in tests.items()}
    dif=result['regimes']['literature_to_new']['differences']
    passed=[s for s,d in dif.items() if d['joint']['project_equal']['ci95'][0]>0]
    result['frozen_decision']=dict(status='通过' if len(passed)>=2 else '未通过',passing_structures=passed,
        required=2,comparison='文献域固定模型B减A_prime的项目等权联合评分；95%重抽区间下界大于零',
        interpretation='只判定冻结机器标签的联合预测；独立盲审显示角色及命题标签可靠性受限，不能等同三个事实维度已可靠确认。')
    save(out/'frozen_comparison.json',result)


def initial_scores(out):
    rows=joint_rows(out);train,tests=regime_rows(rows,'literature_to_new')
    target=out/'models_comparison'/'literature_to_new';target.mkdir(parents=True,exist_ok=True)
    for model in MODELS:
        saved=load(out/'models_literature'/f'{model}_fit.json');fitted=saved['fit']
        path=target/f'{model}_summary.json'
        prior=load(path) if path.exists() else {}
        save(path,dict(model=model,training_observations=len(train),training_projects=len({r['project_id'] for r in train}),
            parameters=parameter_summary(fitted,saved['validation']),
            scores={s:evaluate(t,predict(t,fitted)) for s,t in tests.items()},increments=prior.get('increments',{})))
    result=dict(status='进行中',rules=dict(A0='完全排除拟合、调参及特征选择',bootstrap=2000,
        labels='冻结原机器标签；保留未知，按未知维度边际化',weighting='先续写平均、再条件平均、再历史平均、再项目平均；历史等权并列；电影配对重抽'))
    collect_comparison(out,result)
    return result


def main(out,workers,initial_only):
    result=initial_scores(out)
    if initial_only:return
    tasks=[(str(out),regime,model) for regime in ['literature_to_new']+['leave_'+s for s in STRUCTURES] for model in MODELS]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(run_model,*args) for args in tasks]
        for future in as_completed(futures):
            regime,model=future.result()
            collect_comparison(out,result)
            print('已汇入',regime,model,flush=True)
    result['status']='模型比较完成'
    collect_comparison(out,result)
    finalize(out)


def finalize(out):
    result=load(out/'frozen_comparison.json')
    rows=joint_rows(out);completed=0;convergence=[]
    for regime in ['literature_to_new']+['leave_'+s for s in STRUCTURES]:
        if regime not in result['regimes']:raise RuntimeError('训练方案尚未完成')
        entry=result['regimes'][regime]
        for model in MODELS:
            if model not in entry['models'] or len(entry['models'][model]['increments'])!=len(GROUPS):
                raise RuntimeError('完整模型或规定特征增量尚未齐备')
            completed+=1;summary=entry['models'][model]
            convergence.append(dict(regime=regime,model=model,chosen_penalty=summary['parameters']['fit']['penalty'],
                final_converged=summary['parameters']['fit']['converged'],
                final_iterations=summary['parameters']['fit']['iterations'],
                cv_not_converged=sum(not v for trial in summary['parameters']['validation']['results'] for v in trial['converged']),
                removed_not_converged=[k for k,v in summary['increments'].items() if v['status']=='完成' and not v['convergence']['converged']]))
        _,tests=regime_rows(rows,regime)
        for structure,test in tests.items():
            expected=sum(any(y>=0 for y in r['labels']) for r in test)
            for model in MODELS:
                if entry['models'][model]['scores'][structure]['joint']['observations']!=expected:
                    raise RuntimeError('联合评分分母不等于全部至少一维已知的正式样本')
    diagnostic=[]
    test=[r for r in rows if r['structure']=='G2b']
    for model in ('A_prime','B'):
        d=result['regimes']['literature_to_new']['models'][model]['parameters']['design']
        j=d['names'].index('f_assoc');v=np.array([r['feature_values']['f_assoc'] for r in test],float)
        diagnostic.append(dict(model=model,feature='f_assoc',training_mean=d['means'][j],training_sd=d['scales'][j],
            film_input_range=[float(v.min()),float(v.max())],maximum_absolute_standardized_value=float(np.max(abs((v-d['means'][j])/d['scales'][j])))))
    result['implementation_notes']=dict(compression='完全相同的设计、标签及未知模式合并权重；测试验证目标、梯度、项目权重恒等。',
        log_domain='对数域联合链和混合评分修复直接概率下溢；正常范围新旧一致，极端输入仍为有限对数概率；没有截断、平滑或删除有效样本。',
        film_extreme_diagnostic=diagnostic,
        film_interpretation='冻结共同表将文献教师强制P(yes)与电影无年份8次采样频率置于同一f_assoc列；文献近恒定训练尺度用于电影0至1频率，造成分布外极端输入。保留原参数和原分数，不解释为同量纲知识读数上的巨大科学效应；相对优势不等于绝对校准或内部机制得到确认。')
    result['completion']=dict(regime_model_tasks=completed,expected=18,feature_groups_per_task=len(GROUPS),
        A0_excluded=True,convergence=convergence)
    result['status']='全部规定模型比较与特征增量完成'
    save(out/'frozen_comparison.json',result)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--workers',type=int,default=12);ap.add_argument('--initial-only',action='store_true')
    ap.add_argument('--finalize-only',action='store_true')
    a=ap.parse_args()
    if a.finalize_only:finalize(a.out)
    else:main(a.out,a.workers,a.initial_only)
