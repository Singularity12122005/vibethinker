"""只实现本批冻结的作品层无偏估计、加权描述及作品簇重抽。"""
from collections import defaultdict
import random


def work_values(rows,values):
    groups=defaultdict(list)
    for row,value in zip(rows,values):groups[row['work_id']].append((row,value))
    result={}
    for w,rs in groups.items():
        if rs[0][0]['sampling']=='stratified':
            z=defaultdict(list)
            for r,v in rs:z[r['old_stratum']].append((r,v))
            value=sum(part[0][0]['old_stratum_population']/part[0][0]['work_population']*sum(v for _,v in part)/len(part) for part in z.values())
        else:value=sum(v for _,v in rs)/len(rs)
        result[w]=(value,1/rs[0][0]['pi_work'])
    return result


def weighted_mean(records):
    return sum(v*w for v,w in records)/sum(w for _,w in records) if records else None


def estimate(rows,values):
    works=work_values(rows,values)
    return {'work_equal':weighted_mean(list(works.values())),
            'history_equal':sum(v/r['pi'] for r,v in zip(rows,values))/sum(1/r['pi'] for r in rows) if rows else None,
            'n_sample':len(rows),'n_works':len(works)}


def quantile(v,p):
    if not v:return None
    v=sorted(v);x=(len(v)-1)*p;i=int(x)
    return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(x-i)


def bootstrap(rows,lower,upper,seed=20261112,n=2000):
    low=work_values(rows,lower);up=work_values(rows,upper);keys=sorted(low);rng=random.Random(seed)
    if not keys:return {'status':'不可估计'}
    bl=[];bu=[]
    for _ in range(n):
        selected=[rng.choice(keys) for _ in keys]
        bl.append(weighted_mean([low[k] for k in selected]));bu.append(weighted_mean([up[k] for k in selected]))
    return dict(lower=estimate(rows,lower),upper=estimate(rows,upper),
        interval_lower_endpoint=[quantile(bl,.025),quantile(bl,.975)],
        interval_upper_endpoint=[quantile(bu,.025),quantile(bu,.975)],
        conservative_interval=[quantile(bl,.025),quantile(bu,.975)],
        warning='作品簇自助区间；全零不证明总体为零。' if max(upper)==0 else None)


def paired_difference(rows_a,lower_a,upper_a,rows_b,lower_b,upper_b,seed=20261112,n=2000):
    la,ua=work_values(rows_a,lower_a),work_values(rows_a,upper_a)
    lb,ub=work_values(rows_b,lower_b),work_values(rows_b,upper_b)
    keys=sorted(set(la)&set(lb));rng=random.Random(seed)
    if not keys:return {'status':'无共同作品，未估计配对差'}
    low=[la[k][0]-ub[k][0] for k in keys];up=[ua[k][0]-lb[k][0] for k in keys]
    bl=[];bu=[]
    for _ in range(n):
        ix=[rng.randrange(len(keys)) for k in keys]
        bl.append(sum(low[j] for j in ix)/len(keys));bu.append(sum(up[j] for j in ix)/len(keys))
    return dict(n_works=len(keys),works=keys,lower=sum(low)/len(keys),upper=sum(up)/len(keys),
        conservative_interval=[quantile(bl,.025),quantile(bu,.975)])
