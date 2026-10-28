"""第五批离线统计：先历史后作品；缺失界与作品整簇重抽分开保存。"""
from collections import defaultdict
import numpy as np

from .step0 import average, difference, rate


def summarize(histories, *, seed=20261112, repetitions=2000):
    """每项含work_id与r；不把缺失或零事件补成阴性。"""
    groups = defaultdict(list)
    for h in histories:
        groups[h['work_id']].append(h['r'])
    works = sorted(groups)
    result = dict(histories=len(histories), works=len(works),
                  missing_history_points=sum(h['r']['point'] is None for h in histories))
    if not works:
        for weight in ('work_equal', 'history_equal'):
            result[weight] = dict(point=None, bounds=None, ci95=None,
                conservative_ci95=None, strict_lower95=None, strict_upper95=None, strict_available=False)
        return result
    counts = [len(groups[w]) for w in works]
    table = [[average([r['point'] for r in groups[w]]),
              average([r['bounds'][0] for r in groups[w]]),
              average([r['bounds'][1] for r in groups[w]])] for w in works]
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(works), (repetitions, len(works)))
    total_events = sum(h['r'].get('events', 3) for h in histories)
    for weight in ('work_equal', 'history_equal'):
        weights = np.ones(len(works)) if weight == 'work_equal' else np.asarray(counts, float)
        a = np.asarray([[np.nan if x is None else x for x in row] for row in table], float)
        def weighted(matrix, ws):
            valid = np.isfinite(matrix)
            den = (valid * ws[..., None]).sum(axis=-2)
            return np.divide(np.nansum(matrix * ws[..., None], axis=-2), den,
                             out=np.full_like(den, np.nan, dtype=float), where=den != 0)
        point = weighted(a, weights)
        boot = weighted(a[draw], weights[draw])
        quantiles = []
        for j in range(3):
            good = boot[:, j][np.isfinite(boot[:, j])]
            quantiles.append(np.quantile(good, [.025, .05, .95, .975]).tolist() if len(good) else None)
        q, lo, hi = quantiles
        strict = bool(q and len(works) >= 2 and total_events > 2 and
                      np.nanmax(boot[:, 0]) - np.nanmin(boot[:, 0]) >= 1e-12)
        result[weight] = dict(point=None if not np.isfinite(point[0]) else float(point[0]),
            bounds=[float(x) if np.isfinite(x) else None for x in point[1:]], ci95=[q[0], q[3]] if q else None,
            conservative_ci95=[lo[1], hi[2]] if lo and hi else None,
            strict_lower95=lo[1] if strict else None, strict_upper95=hi[2] if strict else None,
            strict_available=strict)
    result['counts'] = {k: sum(h['r'].get(k, 0) for h in histories)
                        for k in ('events', 'observed', 'missing', 'planned')}
    return result


def metric(rows, value, *, clean=False):
    groups = defaultdict(list)
    for r in rows:
        key = (r['work_id'], r['pair_key'] if clean else r['source_history_id'])
        groups[key].append(value(r))
    hs = [dict(work_id=w, history_id=h, r=rate(v)) for (w, h), v in sorted(groups.items())]
    return dict(**summarize(hs), history_table=hs)


def numeric(rows, key):
    return summarize([dict(work_id=r['work_id'], r=dict(point=r[key], bounds=[r[key], r[key]]))
                      for r in rows])


def contrast(left, right):
    a = {h['history_id']: h for h in left['history_table']}
    b = {h['history_id']: h for h in right['history_table']}
    if set(a) != set(b):
        raise ValueError('差值必须按同一历史完整配对')
    rows = [dict(work_id=a[k]['work_id'], history_id=k,
                 r=dict(difference(a[k]['r'], b[k]['r']),
                        events=a[k]['r'].get('events',3)+b[k]['r'].get('events',3))) for k in a]
    return dict(**summarize(rows), history_table=rows)


def decision(estimate, target, direction):
    """逐字沿用第四批的四态判定，作品等权决定判定。"""
    value = estimate['work_equal']
    point = value['point']
    empirical = point is not None and (point <= target if direction == 'le' else point >= target)
    bound = value['strict_upper95' if direction == 'le' else 'strict_lower95']
    strict = bound is not None and (bound <= target if direction == 'le' else bound >= target)
    status = ('未评估' if point is None else '经验达标，且严格达标' if empirical and strict else
              '经验达标，严格未定' if empirical else '本批经验不达标')
    return dict(target=target, direction=direction, point=point, empirical_pass=empirical,
                strict_pass=strict, strict_bound=bound, status=status)
