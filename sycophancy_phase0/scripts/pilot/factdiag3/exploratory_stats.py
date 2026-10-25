"""第三批探索性补充的只读统计；主报告提交后才用于真实数据。"""
from collections import defaultdict
from itertools import product
import numpy as np

import protocol as p


def avg(values):
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


def cov(x, y):
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < 2:
        return None
    a, b = np.asarray(pairs, float).T
    return float(np.dot(a-a.mean(), b-b.mean())/(len(a)-1))


def ci(values):
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None
    a = np.asarray(values, float)
    rng = np.random.default_rng(p.SEED)
    means = a[rng.integers(len(a), size=(2000, len(a)))].mean(axis=1)
    return np.quantile(means, [.025, .975]).tolist()


def rate(values):
    n, m = len(values), sum(v is None for v in values)
    x = sum(v == 1 for v in values)
    return dict(events=x, observed=n-m, missing=m, planned=n,
                point=x/(n-m) if n > m else None,
                bounds=[x/n, (x+m)/n] if n else None)


def delta(base, a1):
    return dict(point=None if base['point'] is None or a1['point'] is None else base['point']-a1['point'],
                bounds=[base['bounds'][0]-a1['bounds'][1], base['bounds'][1]-a1['bounds'][0]])


def endpoints(bounds):
    return np.asarray(list(product(*[[lo] if lo == hi else [lo, hi] for lo, hi in bounds])), float)


def cov_bounds(xbounds, ybounds):
    """协方差对每一坐标分别为线性：枚举一侧，另一侧直接取不利端点。"""
    n = len(xbounds)
    if n < 2:
        return None
    xs = endpoints(xbounds)
    coef = (xs-xs.mean(axis=1, keepdims=True))/(n-1)
    yl, yh = np.asarray(ybounds).T
    low = np.where(coef >= 0, coef*yl, coef*yh).sum(axis=1)
    high = np.where(coef >= 0, coef*yh, coef*yl).sum(axis=1)
    return [float(low.min()), float(high.max())]


def risk_gain_bounds(bo, ao, be, ae):
    """保持风险与收益共享的计数，不能把相关输入当独立区间。

    目标为 Cov(bo,be) - [Cov(bo,ae)+Cov(ao,be)]/2。
    枚举奇数半两条件端点，偶数半端点按线性系数选择。
    """
    n = len(bo)
    if n < 2:
        return None
    v = endpoints(bo+ao)
    b, a = v[:, :n], v[:, n:]
    bc, ac = b-b.mean(axis=1, keepdims=True), a-a.mean(axis=1, keepdims=True)
    coeffs = np.concatenate(((bc-.5*ac)/(n-1), -.5*bc/(n-1)), axis=1)
    lo, hi = np.asarray(be+ae).T
    lower = np.where(coeffs >= 0, coeffs*lo, coeffs*hi).sum(axis=1)
    upper = np.where(coeffs >= 0, coeffs*hi, coeffs*lo).sum(axis=1)
    return [float(lower.min()), float(upper.max())]


def build_histories(rows, materials, unit):
    bank = {m['work_id']:m for m in materials}
    groups = defaultdict(lambda:defaultdict(list))
    for row in rows:
        if row['unit'] != unit:
            continue
        value = p.outcome(row, bank[row['work_id']])
        if unit == 'F-D' and value is not None:
            value = 1-value
        groups[row['work_id'], row['idx']][row['condition']].append((row['rep'], value))
    histories = []
    for (wid, idx), conditions in sorted(groups.items()):
        item = dict(work_id=wid, idx=idx, unit=unit)
        for condition in ('base', 'A1'):
            pairs = conditions[condition]
            if len(pairs) != p.COUNTS[unit] or len({rep for rep,_ in pairs}) != len(pairs):
                raise RuntimeError('探索性分析的实际条数或续写编号与主分析不符')
            item[condition] = dict(full=rate([v for _,v in pairs]),
                odd=rate([v for rep,v in pairs if rep%2]), even=rate([v for rep,v in pairs if not rep%2]))
        item['gain'] = {part:delta(item['base'][part], item['A1'][part]) for part in ('full','odd','even')}
        histories.append(item)
    return histories


def heterogeneity(histories):
    groups = defaultdict(list)
    for h in histories:
        groups[h['work_id']].append(h)
    works = []
    for wid, hs in sorted(groups.items()):
        if len(hs) < 2:
            works.append(dict(work_id=wid, histories=len(hs), eligible=False))
            continue
        valid = [h for h in hs if all(h[c][s]['point'] is not None for c in ('base','A1') for s in ('odd','even'))]
        variance = cov([h['gain']['odd']['point'] for h in valid], [h['gain']['even']['point'] for h in valid])
        c1 = cov([h['base']['odd']['point'] for h in valid], [h['gain']['even']['point'] for h in valid])
        c2 = cov([h['base']['even']['point'] for h in valid], [h['gain']['odd']['point'] for h in valid])
        vbound = cov_bounds([h['gain']['odd']['bounds'] for h in hs], [h['gain']['even']['bounds'] for h in hs])
        cbound = risk_gain_bounds(*[[h[c][s]['bounds'] for h in hs] for c,s in [('base','odd'),('A1','odd'),('base','even'),('A1','even')]])
        works.append(dict(work_id=wid, histories=len(hs), point_histories=len(valid), eligible=True,
                          V_delta=variance, V_delta_bounds=vbound,
                          risk_gain_covariance=avg([c1,c2]), risk_gain_bounds=cbound))
    eligible = [w for w in works if w['eligible']]
    result = dict(works=works, planned_works=len(groups), eligible_works=len(eligible),
                  missing_continuations=sum(h[c]['full']['missing'] for h in histories for c in ('base','A1')))
    for name, bound in [('V_delta','V_delta_bounds'),('risk_gain_covariance','risk_gain_bounds')]:
        values = [w[name] for w in eligible]
        result[name] = dict(point=avg(values), ci95=ci(values), point_works=sum(v is not None for v in values),
            bounds=[avg([w[bound][j] for w in eligible]) for j in (0,1)])
    return result


def completed_rates(summary):
    return [(summary['events']+k)/summary['planned'] for k in range(summary['missing']+1)]


def assignment_history(h):
    bo,ao,be,ae = [h[c][s] for c,s in [('base','odd'),('A1','odd'),('base','even'),('A1','even')]]
    points = [x['point'] for x in (bo,ao,be,ae)]
    valid = all(x is not None for x in points)
    if valid:
        b,a,c,d = points
        select_odd,select_even = int(b>a),int(c>d)
        cross = .5*((d if select_odd else c)+(a if select_even else b))
        application = .5*(select_odd+select_even)
        never,always = h['base']['full']['point'],h['A1']['full']['point']
        plugin = min(never,always)
        plugin_application = int(never>always)
    else:
        cross=application=never=always=plugin=plugin_application=None
    losses, applications = [],[]
    for b,a,c,d in product(*(completed_rates(x) for x in (bo,ao,be,ae))):
        first,second = b>a,c>d
        losses.append(.5*((d if first else c)+(a if second else b)))
        applications.append(.5*(first+second))
    nb,ab = h['base']['full']['bounds'],h['A1']['full']['bounds']
    return dict(work_id=h['work_id'],idx=h['idx'],unit=h['unit'],point_eligible=valid,
        never=dict(point=never,bounds=nb),always=dict(point=always,bounds=ab),
        crossfit=dict(point=cross,bounds=[min(losses),max(losses)]),
        plugin=dict(point=plugin,bounds=[min(nb[0],ab[0]),min(nb[1],ab[1])]),
        crossfit_application=dict(point=application,bounds=[min(applications),max(applications)]),
        plugin_application=dict(point=plugin_application,bounds=[int(nb[0]>ab[1]),int(nb[1]>ab[0])]))


def assignment_table(histories):
    rows = [assignment_history(h) for h in histories]
    result = dict(histories=len(rows),point_histories=sum(r['point_eligible'] for r in rows),
                  missing_continuations=sum(h[c]['full']['missing'] for h in histories for c in ('base','A1')),
                  weighting='历史等权；各比较使用四个半样本均有观测的共同历史。缺失界覆盖全部计划历史。')
    for key in ('never','always','crossfit','plugin','crossfit_application','plugin_application'):
        result[key] = dict(point=avg([r[key]['point'] for r in rows]),
                           bounds=[avg([r[key]['bounds'][j] for r in rows]) for j in (0,1)])
    return result
