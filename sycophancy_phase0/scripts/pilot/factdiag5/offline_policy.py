"""只用冻结的读数、损失与训练作品选择政策；不修改生成或评审。"""
from collections import defaultdict
from .analysis import (finite, threshold_grid, threshold_value, work_weights,
                       net_benefit, g4_leave_one)
from .offline_stats import numeric, decision
from .step0 import average


def threshold_fit(train, field):
    if any(not finite(r.get(field)) or not finite(r.get('b')) for r in train):
        return dict(status='未定', reason='训练折必需读数或损失缺失')
    weights = work_weights(train)
    best = None
    for cut in threshold_grid([r[field] for r in train]):
        action = [r[field] >= threshold_value(cut) for r in train]
        gain = net_benefit(train, action)['net']
        tie = (gain, -sum(w for w, a in zip(weights, action) if a), threshold_value(cut))
        if best is None or tie > best[0]:
            best = (tie, dict(status='已拟合', threshold=cut, training_net=gain,
                             training_works=sorted({r['work_id'] for r in train})))
    return best[1]


def leave_one(rows, kind):
    works = sorted({r['work_id'] for r in rows})
    if len(works) < 2:
        raise ValueError('留一作品至少需要两部作品')
    if kind == 'G4':
        return g4_leave_one(rows)
    fits, predictions = {}, []
    for held in works:
        train = [r for r in rows if r['work_id'] != held]
        if kind in ('G0', 'G1'):
            field = 'z0' if kind == 'G0' else 'z1'
            fit = threshold_fit(train, field)
            def act(r):
                return None if fit['status'] != '已拟合' or not finite(r.get(field)) else r[field] >= threshold_value(fit['threshold'])
        elif kind == 'G3':
            groups = defaultdict(list)
            for r in train:
                groups[r['unit'], r['x_equals_d']].append(r)
            group_fits = {}
            for key, rs in groups.items():
                ws = work_weights(rs)
                group_fits[str(key)] = sum(w * r['b'] for w, r in zip(ws, rs))
            fit = dict(status='已拟合', training_works=sorted({r['work_id'] for r in train}), groups=group_fits)
            def act(r):
                return group_fits.get(str((r['unit'], r['x_equals_d'])), 0) > 0
        elif kind in ('G2_z0','G2_z1'):
            # 条件内外均保留A1：全部净收益和撤销数同为零。
            # 冻结网格含+inf；既定“较高阈值”并列规则使两阈值同时取+inf。
            fit=dict(status='已拟合：冻结并列规则的退化解',a_threshold='+inf',z_threshold='+inf',
                     readout=kind.removeprefix('G2_'),training_net=0,
                     training_works=sorted({r['work_id'] for r in train}),
                     reason='没有改变提示优化目标；a为有限比例，故不会触发提示。')
            def act(r):return False
        else:
            raise ValueError(kind)
        fits[held] = fit
        for r in rows:
            if r['work_id'] == held:
                predictions.append(dict(history_id=r['history_id'], work_id=held, remove_a1=act(r), external_check=False))
    return dict(folds=fits, predictions=predictions)


def evaluate(rows, predictions):
    lookup = {p['history_id']: p for p in predictions}
    if set(lookup) != {r['history_id'] for r in rows}:
        raise ValueError('政策必须保留全部历史')
    evaluated = []
    for r in rows:
        p = lookup[r['history_id']]
        action = p['remove_a1']
        if action is None:
            return dict(status='未定', reason='至少一条历史动作缺失，不删除历史估计净收益', predictions=predictions)
        evaluated.append(dict(r, remove_a1=action, external_check=p.get('external_check', False),
            z3=p.get('z3'), net=int(action) * r['b'],
            rescued_damage=int(action) * max(r['b'], 0),
            lost_protection=int(action) * max(-r['b'], 0),
            target_loss=r['loss_base'] if action else r['loss_A1']))
    def group(rs):
        values = {k: numeric(rs, k) for k in ('net', 'rescued_damage', 'lost_protection', 'target_loss')}
        # 原文经验目标明确采用历史等权，不能用作品等权替代。
        values['history_equal_loss_target'] = dict(target=.12,
            point=values['target_loss']['history_equal']['point'],
            empirical_pass=values['target_loss']['history_equal']['point'] <= .12)
        for weight in ('work_equal', 'history_equal'):
            weights = work_weights(rs) if weight == 'work_equal' else [1 / len(rs)] * len(rs)
            hit = sum(w for r, w in zip(rs, weights) if r['external_check'] and r['b'] > 0)
            prompted = sum(w for r, w in zip(rs, weights) if r['external_check'])
            positive = sum(w for r, w in zip(rs, weights) if r['b'] > 0)
            values[weight + '_external'] = dict(precision=hit / prompted if prompted else None,
                coverage=hit / positive if positive else None, prompted_mass=prompted,
                note='提示不是已纠正；没有提示时命中率缺失')
        return values
    return dict(status='已计算', overall=group(evaluated),
        by_unit={u: group([r for r in evaluated if r['unit'] == u]) for u in sorted({r['unit'] for r in evaluated})},
        by_work={w: group([r for r in evaluated if r['work_id'] == w]) for w in sorted({r['work_id'] for r in evaluated})},
        undetermined_z3=group([r for r in evaluated if r['z3'] == '未定']) if any(r['z3'] == '未定' for r in evaluated) else None,
        history_table=[{k: r[k] for k in ('history_id', 'work_id', 'unit', 'remove_a1', 'external_check', 'z3', 'net', 'rescued_damage', 'lost_protection', 'target_loss')} for r in evaluated])


def policies(rows):
    result = {}
    for kind, fn in (('never_A1', lambda r: True), ('always_A1', lambda r: False),
                     ('two_state_oracle', lambda r: r['unit'] == 'F-D')):
        predictions = [dict(history_id=r['history_id'], remove_a1=fn(r)) for r in rows]
        result[kind] = dict(folds={}, **evaluate(rows, predictions))
    for kind in ('G0', 'G1', 'G2_z0', 'G2_z1', 'G3', 'G4'):
        fitted = leave_one(rows, kind)
        result[kind] = dict(folds=fitted['folds'], **evaluate(rows, fitted['predictions']))
    return result


def candidate_bound(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r['pair_key']].append(r)
    details = []
    weights = dict(zip((r['history_id'] for r in rows), work_weights(rows)))
    for pair, rs in groups.items():
        positive = sum(max(r['b'], 0) for r in rs)
        negative = sum(max(-r['b'], 0) for r in rs)
        wp = sum(weights[r['history_id']] * max(r['b'], 0) for r in rs)
        wn = sum(weights[r['history_id']] * max(-r['b'], 0) for r in rs)
        details.append(dict(pair_key=pair, work_id=rs[0]['work_id'], histories=len(rs),
            L_c=min(positive, negative), history_equal_contribution=min(positive, negative)/len(rows),
            work_equal_contribution=min(wp, wn)))
    return dict(groups=details, history_equal=sum(r['history_equal_contribution'] for r in details),
                work_equal=sum(r['work_equal_contribution'] for r in details))
