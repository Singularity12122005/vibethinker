"""冻结§3.4的零生成附加分析：读取旧模型参数，仅改变答案边际。"""
from pathlib import Path
import sys


def evaluate(source):
    sys.path.insert(0,str(Path(__file__).parent.parent/'factdiag6g'))
    import numpy as np
    from scipy.special import logsumexp
    from frozen_comparison import joint_rows,regime_rows,predict,aggregate_scores,MODELS,STRUCTURES
    from core import load
    rows=joint_rows(source);output={}
    for regime in ['literature_to_new']+['leave_'+s for s in STRUCTURES]:
        _,tests=regime_rows(rows,regime);result={}
        for model in MODELS:
            path=source/'models_literature'/f'{model}_fit.json' if regime=='literature_to_new' else source/'models_comparison'/regime/f'{model}_fit.json'
            if not path.exists():raise RuntimeError('缺原冻结参数，不重新拟合：'+str(path))
            fitted=load(path)['fit'];result[model]={}
            for structure,test in tests.items():
                logp=logsumexp(predict(test,fitted),axis=(2,3))
                logq=logp.copy();idx=[0,2,3]
                logq[:,idx]=np.log(.99)+logp[:,idx]-logsumexp(logp[:,idx],axis=1)[:,None]
                logq[:,1]=np.log(.01)
                y=np.array([r['labels'][0] for r in test]);known=y>=0
                a=np.full(len(y),np.nan);b=a.copy()
                a[known]=logp[np.where(known)[0],y[known]];b[known]=logq[np.where(known)[0],y[known]]
                result[model][structure]={'original_answer_log_score':aggregate_scores(test,a),
                    'default_reject_answer_log_score':aggregate_scores(test,b),
                    'default_minus_original':aggregate_scores(test,b-a),
                    'unknown_answer_labels':int(sum(~known))}
        output[regime]=result
    return {'classification':'事后诊断；不重新拟合，不回改第六批评分或标签',
        'definition':'P(D)=0.01，其余身份保留各模型非D条件分布，按0.99重新归一；对数域计算，无额外截断。',
        'identity_warning':'按冻结D→X→G身份优先级评分，身份标签不是直接的正确/错误标签。',
        'results':output}
