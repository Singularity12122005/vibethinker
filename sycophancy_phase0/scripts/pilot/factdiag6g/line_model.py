"""G0d：历史内共同线段的约束拟合、同规模模拟与奇偶留出评分。

两端点只是可交换的概率向量，不解释为已识别的心理方式。
无约束训练参照为逐历史逐臂的饱和多项分布；留出参照同样向作品层收缩。
"""
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor

SPEC = dict(endpoint_prior_mass=1.0, mixture_prior_mass=1.0,
            work_prior_mass=0.5, starts=4, max_iterations=1000, tolerance=1e-7,
            simulations=2000, seed=20261111,
            training_reference='逐历史逐臂饱和多项分布，无约束训练似然上界',
            holdout_reference='逐历史逐臂多项分布，以1条伪观测向训练半内的作品臂分布收缩',
            loss='饱和训练对数似然减共同线段收缩拟合的训练对数似然；用同一拟合流程模拟校准，包含固定收缩的代价',
            identifiability='端点与混合比例不唯一可识别，不解释其数值；只评价共同线段限制的拟合与预测。')


def normalize(x, axis=-1):
    total=x.sum(axis=axis,keepdims=True)
    return np.divide(x,total,out=np.full_like(x,1/x.shape[axis],dtype=float),where=total>0)


def ll(counts,prob):
    return np.sum(counts*np.log(np.clip(prob,1e-300,1)),axis=(-2,-1))


def _em(counts,endpoint_prior,mix_prior,mass,mix_mass,seed):
    """向量化多起点；每个历史的五臂共用两端点。"""
    n,a,k=counts.shape
    rng=np.random.default_rng(seed)
    best_score=np.full(n,-np.inf); best=None
    best_converged=np.zeros(n,dtype=bool);best_iterations=np.zeros(n,dtype=int)
    ep_prior=np.clip(endpoint_prior,1e-12,1)
    mp_prior=np.clip(mix_prior,1e-12,1-1e-12)
    for start in range(SPEC['starts']):
        ep=ep_prior.copy() if start==0 else normalize(rng.gamma(1.0,1.0,(n,2,k)))
        pi=mp_prior.copy() if start==0 else rng.uniform(.1,.9,(n,a))
        previous=np.full(n,-np.inf)
        for iteration in range(SPEC['max_iterations']):
            left=pi[:,:,None]*ep[:,None,0,:]
            right=(1-pi[:,:,None])*ep[:,None,1,:]
            resp=np.divide(left,left+right,out=np.full_like(left,.5),where=(left+right)>0)
            z0=counts*resp; z1=counts-z0
            ep[:,0,:]=normalize(z0.sum(axis=1)+mass*ep_prior[:,0,:])
            ep[:,1,:]=normalize(z1.sum(axis=1)+mass*ep_prior[:,1,:])
            denom=counts.sum(axis=2)+mix_mass
            pi=np.divide(z0.sum(axis=2)+mix_mass*mp_prior,denom,out=mp_prior.copy(),where=denom>0)
            prob=pi[:,:,None]*ep[:,None,0,:]+(1-pi[:,:,None])*ep[:,None,1,:]
            score=ll(counts,prob)+mass*np.sum(ep_prior*np.log(np.clip(ep,1e-300,1)),axis=(1,2))
            score+=mix_mass*np.sum(mp_prior*np.log(np.clip(pi,1e-300,1))+(1-mp_prior)*np.log(np.clip(1-pi,1e-300,1)),axis=1)
            converged=np.abs(score-previous)<SPEC['tolerance']
            if np.all(converged):
                break
            previous=score
        choose=score>best_score
        best_converged[choose]=converged[choose]
        best_iterations[choose]=iteration+1
        if best is None:
            best=(ep.copy(),pi.copy(),prob.copy())
        else:
            for dst,src in zip(best,(ep,pi,prob)):
                dst[choose]=src[choose]
        best_score=np.maximum(best_score,score)
    return (*best,dict(unconverged=int((~best_converged).sum()),
                       max_iterations=int(best_iterations.max())))


def fit(counts,work_ids,seed=20261111):
    counts=np.asarray(counts,float)
    if counts.ndim!=3 or np.any(counts<0):
        raise ValueError('计数应为历史×臂×类别，且非负')
    names,wi=np.unique(work_ids,return_inverse=True)
    work_counts=np.zeros((len(names),*counts.shape[1:]),float)
    np.add.at(work_counts,wi,counts)
    k=counts.shape[-1]
    uniform=np.full((len(names),2,k),1/k)
    prior_mix=np.full(work_counts.shape[:2],.5)
    we,wp,_,wd=_em(work_counts,uniform,prior_mix,SPEC['work_prior_mass'],SPEC['work_prior_mass'],seed)
    ep,pi,pred,hd=_em(counts,we[wi],wp[wi],SPEC['endpoint_prior_mass'],SPEC['mixture_prior_mass'],seed+1)
    unrestricted=normalize(counts)
    loss=ll(counts,unrestricted)-ll(counts,pred)
    if np.any(loss < -1e-8):
        raise RuntimeError('约束拟合超过饱和训练似然，计算错误')
    work_arm=normalize(work_counts+SPEC['work_prior_mass']/k)
    heldout_unrestricted=normalize(counts+SPEC['endpoint_prior_mass']*work_arm[wi])
    return dict(prob=pred,unrestricted_holdout=heldout_unrestricted,
                loss_by_history=np.maximum(loss,0),endpoints=ep,mixing=pi,
                convergence=dict(work=wd,history=hd))


def bootstrap_work(values,work_ids,seed=20261111):
    names=np.unique(work_ids)
    sums=np.array([np.sum(values[np.asarray(work_ids)==w]) for w in names])
    rng=np.random.default_rng(seed)
    b=sums[rng.integers(0,len(names),(2000,len(names)))].sum(axis=1)
    return np.quantile(b,[.025,.975]).tolist()


def refit_simulation(args):
    simulated,work_ids=args
    refit=fit(simulated,work_ids,seed=SPEC['seed'])
    return (float(refit['loss_by_history'].sum()),
            int(any(v['unconverged'] for v in refit['convergence'].values())))


def analyze(counts,halves,work_ids,progress=None):
    counts=np.asarray(counts,int)
    fitted=fit(counts,work_ids)
    observed=float(fitted['loss_by_history'].sum())
    rng=np.random.default_rng(SPEC['seed'])
    n=counts.sum(axis=-1)
    calibrated=[]; simulation_unconverged=0
    # 主进程仍按原顺序抽样，子进程只并行执行独立拟合；种子和数值步骤不变。
    simulated=[np.array([[rng.multinomial(int(n[h,a]),fitted['prob'][h,a])
                         for a in range(counts.shape[1])] for h in range(len(counts))])
               for _ in range(SPEC['simulations'])]
    jobs=[(x,work_ids) for x in simulated]
    workers=max(1,int(os.environ.get('FACTDIAG_G0_CPU_WORKERS','1')))
    pool=ProcessPoolExecutor(max_workers=workers) if workers>1 else None
    results=pool.map(refit_simulation,jobs,chunksize=4) if pool else map(refit_simulation,jobs)
    for b,(loss,unconverged) in enumerate(results):
        simulation_unconverged+=unconverged
        calibrated.append(loss)
        if progress and (b+1)%20==0:
            progress(b+1,SPEC['simulations'])
    if pool:pool.shutdown()
    held=[]
    by_history=np.zeros(len(counts))
    for train,test in ((halves[0],halves[1]),(halves[1],halves[0])):
        model=fit(train,work_ids)
        constrained=ll(test,model['prob'])
        unconstrained=ll(test,model['unrestricted_holdout'])
        by_history+=constrained-unconstrained
        held.append(dict(constrained_log_likelihood=float(constrained.sum()),
                         unrestricted_log_likelihood=float(unconstrained.sum()),n=int(np.sum(test)),
                         convergence=model['convergence']))
    arms,categories=counts.shape[1:]
    return dict(specification=SPEC,observed_fit_loss=observed,convergence=fitted['convergence'],
                nominal_dimensions=dict(histories=len(counts),categories=categories,arms=arms,
                  unrestricted_per_history=arms*(categories-1),
                  line_per_history=2*(categories-1)+arms-2,
                  constraint_per_history=(arms-2)*(categories-2),
                  note='一般内部点的概率分布维数；扣除沿共同直线移动两个端点的不识别自由度。边界与收缩使其不适用于卡方近似，判读只用同流程模拟。'),
                fit_loss_work_bootstrap_ci95=bootstrap_work(fitted['loss_by_history'],work_ids),
                noise_calibration=dict(n=len(calibrated),fits_with_unconverged_components=simulation_unconverged,
                                       quantiles=np.quantile(calibrated,[.025,.5,.95,.975]).tolist(),
                                       exceeds_95th=observed>float(np.quantile(calibrated,.95))),
                heldout_halves=held,heldout_joint_gain=float(by_history.sum()),
                heldout_gain_work_bootstrap_ci95=bootstrap_work(by_history,work_ids))
