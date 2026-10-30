"""指令十的秩相关、描述性分辨力与Firth替代；无模型生成入口。"""
from collections import Counter, defaultdict
import math
import numpy as np
from scipy.optimize import minimize, brentq
from scipy.special import expit
from .t1_endline import empirical_interval, weights


def weighted_rank(v, w):
    v=np.asarray(v);w=np.asarray(w);out=np.zeros(len(v));before=0.0
    for value in sorted(set(v)):
        mask=v==value;mass=w[mask].sum();out[mask]=before+mass/2;before+=mass
    return out


def rank_correlation(rows, field, mode):
    rr=[r for r in rows if r[field] is not None and r['y'] is not None]
    if len(rr)<2:return None
    w=weights(rr,mode);x=weighted_rank([r[field] for r in rr],w);y=weighted_rank([r['y'] for r in rr],w)
    x=x-np.average(x,weights=w);y=y-np.average(y,weights=w)
    d=math.sqrt(float(np.dot(w,x*x)*np.dot(w,y*y)))
    return float(np.dot(w,x*y)/d) if d>1e-14 else None


def mean_group(rows, value, mode):
    rr=[r for r in rows if r['r1']==value and r['y'] is not None]
    if not rr:return None
    return float(np.average([r['y'] for r in rr],weights=weights(rr,mode)))


def group_difference(rows, mode):
    a,b=mean_group(rows,1,mode),mean_group(rows,0,mode)
    return a-b if a is not None and b is not None else None


def boot_summary(values):
    return dict(requested=len(values),defined=sum(v is not None for v in values),
                undefined=sum(v is None for v in values),
                positive_infinite=sum(v==math.inf for v in values),
                negative_infinite=sum(v==-math.inf for v in values),interval95=empirical_interval(values),
                interval_conditioning='在可定义重抽上取经验分位；未定义次数单列，不能冒称所有重抽均给出有效估计。')


def prediction_decision(point, ci):
    if point is None or ci is None:return '读数或结局无变异/可用配对不足，预测力不可识别；不能记为相关0。'
    if ci[0]>0:return '按登记规则，该读数在该单元有预测力。'
    if ci[0]<=0<=ci[1] and point<0.2:return '按登记规则，无可测预测力。'
    return '未达到登记的有预测力或无可测预测力条件。'


def analyze_readings(rows,repetitions=2000):
    works=sorted({r['work_id'] for r in rows});by={w:[r for r in rows if r['work_id']==w] for w in works}
    perwork=[]
    for w,rr in by.items():
        perwork.append(dict(work_id=w,histories=len(rr),r1_counts=dict(Counter(str(r['r1']) for r in rr)),
            r1_mean=float(np.mean([r['r1'] for r in rr if r['r1'] is not None])),
            r2_values=sorted({r['r2'] for r in rr if r['r2'] is not None}),
            r2=float(np.mean([r['r2'] for r in rr if r['r2'] is not None])),y=float(np.mean([r['y'] for r in rr]))))
    result=dict(histories=len(rows),works=len(works),per_work=perwork,readings=rows,modes={},
        r2_constant_within_every_work=all(len(r['r2_values'])==1 for r in perwork),
        r3_status='不计算：没有允许使用的既有确定性正文识别项；不能读取关系提取作替代。')
    rng=np.random.default_rng()
    for mode in ('work_equal','history_equal'):
        estimates={field:rank_correlation(rows,field,mode) for field in ('r1','r2')}
        delta=group_difference(rows,mode)
        values={field:[] for field in ('r1','r2','group_difference','work_level_r2')}
        wr=[dict(work_id=r['work_id'],r2=r['r2'],y=r['y']) for r in perwork]
        wp=rank_correlation(wr,'r2','history_equal')
        if all(v is None for v in estimates.values()) and delta is None and wp is None:
            for k in values:values[k]=[None]*repetitions
        else:
            for _ in range(repetitions):
                chosen=rng.choice(works,len(works),replace=True)
                sample=[dict(r,cluster=str(i)) for i,w in enumerate(chosen) for r in by[w]]
                for field in ('r1','r2'):values[field].append(rank_correlation(sample,field,mode))
                values['group_difference'].append(group_difference(sample,mode))
                means=[dict(wr[works.index(w)],cluster=str(i)) for i,w in enumerate(chosen)]
                values['work_level_r2'].append(rank_correlation(means,'r2','history_equal'))
        answer={field:dict(estimate=estimates[field],bootstrap=boot_summary(values[field]),
            decision=prediction_decision(estimates[field],empirical_interval(values[field]))) for field in ('r1','r2')}
        answer['r1_groups']=dict(group1_n=sum(r['r1']==1 for r in rows),group0_n=sum(r['r1']==0 for r in rows),
            group1_mean=mean_group(rows,1,mode),group0_mean=mean_group(rows,0,mode),difference=delta,
            bootstrap=boot_summary(values['group_difference']),
            note='1组减0组；组间作品组成可能不同，不是同作品内因果效应。')
        answer['work_level_r2']=dict(estimate=wp,works=len(works),bootstrap=boot_summary(values['work_level_r2']))
        result['modes'][mode]=answer
    return result


def safe_logit(p):
    return -math.inf if p==0 else math.inf if p==1 else math.log(p/(1-p))


def discrimination(fd,st,repetitions=2000):
    """重复同作品的两单元一起抽；无穷值保留，未定义单列。"""
    by=[]
    for rows in (fd,st):
        d=defaultdict(list)
        for r in rows:d[r['work_id']].append(r)
        by.append(d)
    union=sorted(set(by[0])|set(by[1]));overlap=sorted(set(by[0])&set(by[1]))
    def rate(bank,chosen,arm,mode):
        grouped=[bank[w] for w in chosen if w in bank]
        if not grouped:return None
        rr=[sum(r['k'+str(arm)]/r['n'+str(arm)] for r in group)/len(group) for group in grouped]
        return float(np.average(rr,weights=[1 if mode=='work_equal' else len(group) for group in grouped]))
    def statistic(chosen,arm,mode):
        h,f=rate(by[0],chosen,arm,mode),rate(by[1],chosen,arm,mode)
        if h is None or f is None:return None
        d=safe_logit(h)-safe_logit(f)
        return None if math.isnan(d) else d
    result={};rng=np.random.default_rng()
    for label,ws in [('all_works',union),('overlap_works',overlap)]:
        output=dict(work_ids=ws,FD_works=sum(w in by[0] for w in ws),ST_works=sum(w in by[1] for w in ws),modes={})
        for mode in ('work_equal','history_equal'):
            sims=[[],[]]
            for _ in range(repetitions):
                chosen=rng.choice(ws,len(ws),replace=True)
                for arm in (0,1):sims[arm].append(statistic(chosen,arm,mode))
            output['modes'][mode]={('base' if arm==0 else 'A1'):dict(estimate=statistic(ws,arm,mode),
                hit_rate=rate(by[0],ws,arm,mode),false_alarm_rate=rate(by[1],ws,arm,mode),
                bootstrap=boot_summary(sims[arm])) for arm in (0,1)}
        result[label]=output
    return result


def firth_design(rows,mode):
    n_hist=len(rows);X=np.zeros((n_hist*2,n_hist+1));k=[];n=[]
    for i,(r,w) in enumerate(zip(rows,weights(rows,mode))):
        X[2*i:2*i+2,i]=1;X[2*i+1,-1]=1
        k.extend([w*r['k0'],w*r['k1']]);n.extend([w*r['n0'],w*r['n1']])
    return X,np.asarray(k),np.asarray(n)


def firth_objective(beta,X,k,n):
    eta=X@beta;p=expit(eta);w=n*p*(1-p)
    info=X.T@(w[:,None]*X)
    sign,ld=np.linalg.slogdet(info)
    if sign<=0 or not np.isfinite(ld):return 1e100,np.zeros(len(beta))
    ll=np.dot(k,eta)-np.dot(n,np.logaddexp(0,eta))+.5*ld
    leverage=w*np.einsum('ij,ji->i',X,np.linalg.solve(info,X.T))
    gradient=X.T@(k-n*p+leverage*(.5-p))
    return -float(ll),-gradient


def fit_firth(rows,mode='history_equal',interval=True):
    X,k,n=firth_design(rows,mode);h=len(rows)
    initial=np.r_[np.log((k.reshape(-1,2).sum(1)+.5)/(n.reshape(-1,2).sum(1)-k.reshape(-1,2).sum(1)+.5)),0.0]
    opt=minimize(firth_objective,initial,args=(X,k,n),jac=True,method='BFGS',options={'gtol':1e-8,'maxiter':2000})
    error=float(np.max(np.abs(firth_objective(opt.x,X,k,n)[1])))
    if not np.isfinite(opt.fun) or error>1e-5:raise RuntimeError('Firth优化未收敛：'+str(opt.message)+' score='+str(error))
    gamma=float(opt.x[-1]);answer=dict(delta=-gamma,gamma=gamma,converged=True,max_penalized_score=error,
        observations=len(n),histories=h,works=len({r['work_id'] for r in rows}),weighting=mode,
        method='历史固定截距、A1共同系数及Firth信息行列式惩罚；非后验。')
    if interval:
        def prof(g):
            def fn(a):
                v,gr=firth_objective(np.r_[a,g],X,k,n);return v,gr[:-1]
            r=minimize(fn,opt.x[:-1],jac=True,method='BFGS',options={'gtol':1e-8,'maxiter':2000})
            err=np.max(np.abs(fn(r.x)[1]))
            if err>1e-5:raise RuntimeError('Firth剖面优化未收敛：'+str(err))
            return 2*(r.fun-opt.fun)-3.8414588
        bounds=[]
        for direction in (-1,1):
            step=1.0
            while prof(gamma+direction*step)<0:
                step*=2
                if step>64:raise RuntimeError('Firth剖面界未找到')
            a,b=sorted([gamma,gamma+direction*step]);bounds.append(float(brentq(prof,a,b,xtol=1e-7)))
        answer['penalized_profile95']=[-bounds[1],-bounds[0]]
    return answer
