"""有限前缀库的描述量、冲突重抽与固定分母缺失界。"""
from itertools import product
import math
import random
import statistics


def mean(values):
    xs = [x for x in values if x is not None]
    return sum(xs)/len(xs) if xs else None


def quantile(values, p):
    xs = sorted(x for x in values if x is not None and math.isfinite(x))
    if not xs:
        return None
    at = (len(xs)-1)*p
    lo, hi = math.floor(at), math.ceil(at)
    return xs[lo] + (xs[hi]-xs[lo])*(at-lo)


def covariance(u,v):
    if len(u)<2 or len(u)!=len(v) or any(x is None for x in u+v):
        return None
    a,b = mean(u),mean(v)
    return sum((x-a)*(y-b) for x,y in zip(u,v))/(len(u)-1)


def bounds(values, denominator=None):
    n = len(values) if denominator is None else denominator
    if n == 0:
        return [None,None]
    if len(values) != n:
        raise ValueError("缺失界的固定分母与分支数不符")
    x = sum(v == 1 for v in values)
    m = sum(v is None for v in values)
    return [x/n,(x+m)/n]


def covariance_bounds(uv_bounds):
    """协方差对每个u/v坐标都是仿射的，最值在矩形端点。"""
    if len(uv_bounds)<2:
        return [None,None]
    if len(uv_bounds)>4:
        raise ValueError("本批每冲突最多四个干净前缀")
    ranges = [interval for pair in uv_bounds for interval in pair]
    values = []
    for point in product(*ranges):
        values.append(covariance(list(point[::2]),list(point[1::2])))
    return [min(values),max(values)]


def prefix_stats(arms):
    s = arms["S"]
    if len(s)!=8 or len(arms["N"])!=4 or len(arms["C"])!=4:
        raise ValueError("前缀分支数应为S8/N4/C4，缺失保留占位")
    result = {arm: dict(rhat=mean(values),bounds=bounds(values),n=len(values),
                       missing=sum(v is None for v in values)) for arm,values in arms.items()}
    result.update(u=mean(s[::2]),v=mean(s[1::2]),u_bounds=bounds(s[::2],4),v_bounds=bounds(s[1::2],4))
    return result


def instance_stats(prefixes):
    h = len(prefixes)
    uv = [(p["u_bounds"],p["v_bounds"]) for p in prefixes]
    result = dict(H=h, u=mean([p["u"] for p in prefixes]),v=mean([p["v"] for p in prefixes]),
        Vw=covariance([p["u"] for p in prefixes],[p["v"] for p in prefixes]),
        Vw_bounds=covariance_bounds(uv),prefixes=prefixes)
    for arm in ("S","N","C"):
        result[arm] = dict(rhat=mean([p[arm]["rhat"] for p in prefixes]),
                          bounds=[mean([p[arm]["bounds"][j] for p in prefixes]) for j in (0,1)])
    for a,b in (("S","N"),("C","N"),("S","C")):
        ds = [p[a]["rhat"]-p[b]["rhat"] for p in prefixes
              if p[a]["rhat"] is not None and p[b]["rhat"] is not None]
        result[a+"-"+b] = dict(value=mean(ds),bounds=[
            mean([p[a]["bounds"][0]-p[b]["bounds"][1] for p in prefixes]),
            mean([p[a]["bounds"][1]-p[b]["bounds"][0] for p in prefixes])])
    return result


def weighted_vw(instances, key="Vw", endpoint=None):
    pairs=[]
    for i in instances:
        value=i[key] if endpoint is None else i[key][endpoint]
        if i["H"]>=2 and value is not None:
            pairs.append((i["H"]-1,value))
    return sum(w*x for w,x in pairs)/sum(w for w,_ in pairs) if pairs else None


def group_point(instances):
    vw=weighted_vw(instances)
    usable=[i for i in instances if i["u"] is not None and i["v"] is not None]
    vb=covariance([i["u"] for i in usable],[i["v"] for i in usable])
    ratio=vw/(vw+vb) if vw is not None and vb is not None and vw+vb != 0 else None
    result=dict(Vw=vw,Vb=vb,descriptive_ratio=ratio,
                Vw_worst=weighted_vw(instances,"Vw_bounds",0))
    for a in ("S-N","C-N","S-C"):
        result[a]=mean([i[a]["value"] for i in instances])
        result[a+"_lower"]=mean([i[a]["bounds"][0] for i in instances])
        result[a+"_upper"]=mean([i[a]["bounds"][1] for i in instances])
    for a in ("S","N","C"):
        result["r"+a]=mean([i[a]["rhat"] for i in instances])
    return result


def group_stats(instances, seed, n_boot=2000):
    point=group_point(instances)
    rng=random.Random(seed)
    draws=[group_point(rng.choices(instances,k=len(instances))) for _ in range(n_boot)] if instances else []
    intervals={key:[quantile([d[key] for d in draws],.025),quantile([d[key] for d in draws],.975)]
               for key in point if not key.endswith(("_lower","_upper"))}
    result=dict(instances=len(instances),point=point,bootstrap95=intervals,
        missing_bounds={a:[point[a+"_lower"],point[a+"_upper"]] for a in ("S-N","C-N","S-C")},
        computable_instances=dict(Vw=sum(i["H"]>=2 and i["Vw"] is not None for i in instances),
            Vw_worst=sum(i["H"]>=2 for i in instances),Vb=sum(i["u"] is not None and i["v"] is not None for i in instances),
            **{a:sum(i[a]["value"] is not None for i in instances) for a in ("S-N","C-N","S-C")}),
        computable_prefixes=dict(total=sum(i["H"] for i in instances),
            paired_halves=sum(p["u"] is not None and p["v"] is not None for i in instances for p in i["prefixes"])))
    result["criterion_satisfied"]=bool(intervals["Vw_worst"][0] is not None and intervals["Vw_worst"][0]>0 and
                        intervals["S-N"][0] is not None and intervals["S-N"][0]>0)
    return result


def logit(p):
    return math.log(p/(1-p)) if p is not None and 0<p<1 else None


def logit_tertiles(prefixes):
    valid=sorted((p for p in prefixes if p["N"]["rhat"] is not None), key=lambda p:p["N"]["rhat"])
    result=[]
    for j in range(3):
        chunk=valid[len(valid)*j//3:len(valid)*(j+1)//3]
        values=[]
        for p in chunk:
            a,b=logit(p["S"]["rhat"]),logit(p["N"]["rhat"])
            values.append(a-b if a is not None and b is not None else None)
        result.append(dict(prefixes=len(chunk),not_computable=sum(v is None for v in values),
                           mean_logit_difference=mean(values)))
    return result
