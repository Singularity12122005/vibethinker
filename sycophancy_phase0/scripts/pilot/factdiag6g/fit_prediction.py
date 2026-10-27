"""按冻结共同变量拟合预测；A0仅构造预测输入，绝不读取其续写。"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
import random
import numpy as np
from core import load,save,SEED,INTERVENTIONS,INTERVENTION_FIELDS,digest
from features import FEATURE_NAMES
from joint_model import JointModel,log_scores
from specification import MODEL_PROTOCOL

TAU={'same_subject','relation_change','qualifier_change','medium_change','creator_type_role','computable'}
GATE={'s','delta_pol','exposed','role_in_same_sentence'}
PENALTIES=(.001,.01,.1)


def observation_weights(rows):
    valid=[i for i,r in enumerate(rows) if any(v>=0 for v in r['labels'])]
    groups=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
    for i in valid:
        r=rows[i];groups[r['project_id']][r['history_id']][(r['candidate_type'],r['arm'])].append(i)
    if not groups:raise RuntimeError('没有可评分的观测，不能拟合')
    weights=np.zeros(len(rows))
    for histories in groups.values():
        for conditions in histories.values():
            for indices in conditions.values():
                weights[indices]=1/(len(groups)*len(histories)*len(conditions)*len(indices))
    return weights


def feature_columns(model,omit=None):
    keys=list(FEATURE_NAMES)
    if model=='A':keys=[k for k in keys if k not in TAU and k!='r_adj_diag' and not k.startswith('online_')]
    if omit:
        keys=[k for k in keys if not (k in omit or ('r_adj_online' in omit and k.startswith('online_')))]
    return keys


def design_fit(rows,model,omit=None):
    names=feature_columns(model,omit);raw=np.array([[r['feature_values'][k] for k in names] for r in rows],dtype=float)
    means=[];scales=[];kept=[];missing_kept=[];unestimated=[]
    for j,name in enumerate(names):
        known=np.isfinite(raw[:,j]);values=raw[known,j]
        mean=float(np.mean(values)) if len(values) else 0.;scale=float(np.std(values)) if len(values) else 0.
        means.append(mean);scales.append(scale if scale>1e-12 else 1.)
        if scale>1e-12:kept.append(j)
        else:unestimated.append(name)
        if 0<sum(known)<len(known):missing_kept.append(j)
    arms=np.array([INTERVENTIONS[r['arm']] for r in rows],dtype=float)
    arm_kept=[j for j in range(arms.shape[1]) if np.std(arms[:,j])>1e-12]
    return dict(model=model,names=names,means=means,scales=scales,kept=kept,
        missing_kept=missing_kept,arm_kept=arm_kept,unestimated=unestimated)


def design_apply(rows,design):
    raw=np.array([[r['feature_values'][k] for k in design['names']] for r in rows],dtype=float)
    missing=~np.isfinite(raw);means=np.array(design['means']);scales=np.array(design['scales'])
    transformed=(np.where(missing,means,raw)-means)/scales
    continuous=transformed[:,design['kept']];indicators=missing[:,design['missing_kept']].astype(float)
    arms=np.array([INTERVENTIONS[r['arm']] for r in rows],dtype=float)[:,design['arm_kept']]
    base=np.column_stack([np.ones(len(rows)),continuous,indicators])
    if design['model']=='B':
        used=[j for j in design['kept'] if design['names'][j] in GATE]
        miss=[j for j in design['missing_kept'] if design['names'][j] in GATE]
        gate=np.column_stack([np.ones(len(rows)),transformed[:,used],missing[:,miss],arms])
        return base,gate
    return np.column_stack([base,arms]),None


def fit_one(rows,model,penalty,omit=None):
    if any(r['arm']=='A0' for r in rows):raise RuntimeError('A0不得进入拟合、调参或特征选择')
    design=design_fit(rows,model,omit);X,gate=design_apply(rows,design)
    model_object=JointModel(X.shape[1],gate.shape[1] if gate is not None else 0)
    fit=model_object.fit(X,[r['labels'] for r in rows],observation_weights(rows),penalty,gate)
    return dict(design=design,fit=fit)


def predict(rows,fitted):
    X,gate=design_apply(rows,fitted['design'])
    m=JointModel(X.shape[1],gate.shape[1] if gate is not None else 0)
    return m.distribution(np.array(fitted['fit']['theta']),X,gate)


def score(rows,distribution):
    scores=log_scores(distribution,[r['labels'] for r in rows]);weights=observation_weights(rows)
    return float(np.dot(weights,np.nan_to_num(scores['joint'],nan=0.)))


def choose_penalty(rows,model,out):
    groups=sorted({r['cluster_id'] for r in rows});random.Random(SEED).shuffle(groups)
    if len(groups)<5:raise RuntimeError('训练项目不足五折，不自行改变验证划分')
    folds={g:i%5 for i,g in enumerate(groups)};results=[]
    for penalty in PENALTIES:
        scores=[];convergence=[]
        for fold in range(5):
            train=[r for r in rows if folds[r['cluster_id']]!=fold]
            test=[r for r in rows if folds[r['cluster_id']]==fold]
            cache=out/f'cv_{model}_{penalty}_{fold}.json'
            signature=digest(dict(train=[r['id'] for r in train],test=[r['id'] for r in test],model=model,penalty=penalty))
            if cache.exists():
                saved=load(cache)
                if saved['signature']!=signature:raise RuntimeError('旧交叉验证缓存不匹配')
                fitted=saved['fitted'];heldout=saved['score']
            else:
                fitted=fit_one(train,model,penalty);heldout=score(test,predict(test,fitted))
                save(cache,dict(signature=signature,fitted=fitted,score=heldout))
            scores.append(heldout);convergence.append(fitted['fit']['converged'])
            print('训练域验证',model,penalty,fold,heldout,'converged',convergence[-1],flush=True)
        results.append(dict(penalty=penalty,scores=scores,mean=float(np.mean(scores)),converged=convergence))
    best=max(results,key=lambda r:(r['mean'],r['penalty']))
    return dict(chosen=best['penalty'],results=results,folds=folds)


def a0_inputs(out):
    materials=load(out/'factdiag6g_materials.json')['plan']
    features={r['history_id']+'|'+r['candidate_type']:r for r in load(out/'common_features.json')['rows']}
    rows=[]
    for c in materials['conditions']:
        if c['stage']!='g1_a0':continue
        feature=features[c['history_id']+'|'+c['candidate_type']]
        rows.append(dict(history_id=c['history_id'],project_id=c['work_id'],arm='A0',
            feature_values=feature['values'],candidate_type=c['candidate_type'],planned=c['n']))
    if len(rows)!=60 or sum(r['planned'] for r in rows)!=240:raise RuntimeError('A0预测输入应为60历史、240续写')
    return rows


def main(out):
    reg=load(out/'factdiag6g_prereg.json')
    if reg['frozen']['model_protocol']!=MODEL_PROTOCOL:raise RuntimeError('估计规则改变')
    data=load(out/'joint_observations.json');rows=data['rows']
    if data['stages']!=['g1_non_a0'] or any(r['structure']!='literature' or r['arm']=='A0' for r in rows):
        raise RuntimeError('A0预测只能用旧文献域与本批G1非A0')
    target=out/'models_literature';target.mkdir(exist_ok=True)
    test=a0_inputs(out);result={}
    for model in ('A','A_prime','B'):
        cv=choose_penalty(rows,model,target)
        fitted=fit_one(rows,model,cv['chosen'])
        probabilities=predict(test,fitted)
        values=[dict(history_id=r['history_id'],project_id=r['project_id'],
            target_error_probability=float(p[1].sum()),joint_probability=p.tolist()) for r,p in zip(test,probabilities)]
        result[model]=dict(validation=cv,fit=fitted,predictions=values,
            predicted_target_error=float(np.mean([r['target_error_probability'] for r in values])))
        save(target/f'{model}_fit.json',result[model]);print('文献域拟合完成',model,flush=True)
    prediction=dict(status='拟合完成，待单独提交推送后生成A0',models=result,
        training_observations=len(rows),training_features_sha256=digest(load(out/'common_features.json')),
        rule='A0输入只含受压前变量；预测完整联合分布，目标错误为y1=D的边际概率。',
        frozen_prereg_sha256=reg['frozen_sha256'])
    save(out/'a0_prediction_candidate.json',prediction)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    main(ap.parse_args().out)
