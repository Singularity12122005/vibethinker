"""以第三轮为结局的计划分母、分半协方差与冲突重抽。"""
from itertools import product
import math
import random


def mean(values):
    xs=[x for x in values if x is not None]
    return sum(xs)/len(xs) if xs else None


def quantile(values,p):
    xs=sorted(x for x in values if x is not None and math.isfinite(x))
    if not xs:return None
    at=(len(xs)-1)*p;lo=math.floor(at);hi=math.ceil(at)
    return xs[lo]+(xs[hi]-xs[lo])*(at-lo)


def covariance(u,v):
    if len(u)<2 or len(u)!=len(v) or any(x is None for x in u+v):return None
    if len(set(u))==1 or len(set(v))==1:return 0.0
    a,b=mean(u),mean(v)
    return sum((x-a)*(y-b) for x,y in zip(u,v))/(len(u)-1)


def bounds(values,denominator=None):
    n=len(values) if denominator is None else denominator
    if n!=len(values):raise ValueError('计划分母与分支数不符')
    if not n:return [None,None]
    x=sum(v==1 for v in values);m=sum(v is None for v in values)
    return [x/n,(x+m)/n]


def rate(values):
    return dict(value=mean(values),events=sum(v==1 for v in values),planned=len(values),
                observed=sum(v is not None for v in values),missing=sum(v is None for v in values),bounds=bounds(values))


def covariance_bounds(uv):
    if len(uv)<2:return [None,None]
    if len(uv)>6:raise ValueError('每冲突最多六个历史')
    values=[covariance(list(p[::2]),list(p[1::2])) for p in product(*[x for pair in uv for x in pair])]
    return [min(values),max(values)]


def prefix_stats(arms):
    expected={'S':8,'SR':8,'N':4,'C':2}
    for a,xs in arms.items():
        if a in expected and len(xs)!=expected[a]:raise ValueError('计划分支缺行：'+a)
    result={a:rate(xs) for a,xs in arms.items()}
    s=arms['S'];result.update(u=mean(s[::2]),v=mean(s[1::2]),u_bounds=bounds(s[::2],4),v_bounds=bounds(s[1::2],4))
    return result


def instance_stats(prefixes):
    result=dict(H=len(prefixes),prefixes=prefixes,
        Vw=covariance([p['u'] for p in prefixes],[p['v'] for p in prefixes]),
        Vw_bounds=covariance_bounds([(p['u_bounds'],p['v_bounds']) for p in prefixes]))
    for arm in ('S','SR','N','C'):
        result[arm]=dict(value=mean([p[arm]['value'] for p in prefixes if arm in p]),
                        bounds=[mean([p[arm]['bounds'][j] for p in prefixes if arm in p]) for j in (0,1)])
    for a,b in (('S','N'),('S','SR'),('C','N'),('S','C')):
        ps=[p for p in prefixes if a in p and b in p]
        result[a+'-'+b]=dict(value=mean([p[a]['value']-p[b]['value'] for p in ps if p[a]['value'] is not None and p[b]['value'] is not None]),
            conservative=mean([p[a]['bounds'][0]-p[b]['bounds'][1] for p in ps]),
            upper=mean([p[a]['bounds'][1]-p[b]['bounds'][0] for p in ps]))
    return result


def weighted_vw(instances,worst=False):
    pairs=[(i['H']-1,i['Vw_bounds'][0] if worst else i['Vw']) for i in instances if i['H']>=2]
    pairs=[(w,v) for w,v in pairs if v is not None]
    return sum(w*v for w,v in pairs)/sum(w for w,v in pairs) if pairs else None


def group_point(instances):
    result=dict(Vw=weighted_vw(instances),Vw_worst=weighted_vw(instances,True))
    for key in ('S-N','S-SR','C-N','S-C'):
        result[key]=mean([i[key]['value'] for i in instances])
        result[key+'_conservative']=mean([i[key]['conservative'] for i in instances])
    paired=[p for i in instances for p in i['prefixes'] if p['S']['value'] is not None and p['SR']['value'] is not None]
    den=sum(p['S']['value'] for p in paired)
    result['rho']=sum(p['SR']['value'] for p in paired)/den if den else None
    return result


def group_stats(instances,seed,n_boot=2000):
    point=group_point(instances);rng=random.Random(seed)
    draws=[group_point(rng.choices(instances,k=len(instances))) for _ in range(n_boot)] if instances else []
    return dict(conflicts=len(instances),histories=sum(i['H'] for i in instances),point=point,
                bootstrap95={k:[quantile([d[k] for d in draws],p) for p in (.025,.975)] for k in point},
                valid_bootstrap={k:sum(d[k] is not None for d in draws) for k in point},
                computable_conflicts={k:sum(i[k]['value'] is not None for i in instances) for k in ('S-N','S-SR','C-N','S-C')})


def risk_tertiles(instances):
    rows=sorted([p for i in instances for p in i['prefixes'] if p['S']['value'] is not None and p['SR']['value'] is not None],key=lambda p:p['S']['value'])
    return [dict(histories=len(xs),delta=mean([p['S']['value']-p['SR']['value'] for p in xs]))
            for j in range(3) for xs in [rows[len(rows)*j//3:len(rows)*(j+1)//3]]]
