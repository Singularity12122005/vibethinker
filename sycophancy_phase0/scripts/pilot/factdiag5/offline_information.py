"""第五批冻结的分半信息损失估计；连续特征只在训练作品标准化。"""
from collections import Counter, defaultdict
import numpy as np

from .analysis import finite, fit_g4, specificity, g4_action, threshold_value, work_weights
from .offline_policy import threshold_fit


LAYERS = {'a': ('a',), 'a_z0': ('a', 'z0'), 'a_z0_z1_z3': ('a', 'z0', 'z1')}
RULES = {'a': {'never_A1','always_A1'},
         'a_z0': {'never_A1','always_A1','G0','G2_z0'},
         'a_z0_z1_z3': {'never_A1','always_A1','G0','G1','G2_z0','G2_z1','G4'}}


def _fit(train, test, continuous, target, multiplicities, categorical=False):
    counts = Counter(r['work_id'] for r in train)
    weight = np.asarray([multiplicities[r['work_id']] / counts[r['work_id']] for r in train], float)
    weight /= weight.sum()
    x = np.asarray([[r[k] for k in continuous] for r in train], float)
    y = np.asarray([r[target] for r in train], float)
    mean = (x * weight[:, None]).sum(axis=0)
    scale = np.sqrt(((x - mean)**2 * weight[:, None]).sum(axis=0))
    scale[scale == 0] = 1
    def design(rs):
        a = np.asarray([[r[k] for k in continuous] for r in rs], float)
        cols = [np.ones((len(rs), 1)), (a - mean) / scale]
        if categorical:
            cols.append(np.asarray([[int(r.get('z3', '未定') == state) for state in ('未定', '泛化', '特异')] for r in rs], float))
        return np.column_stack(cols)
    root = np.sqrt(weight)
    coef, _, rank, _ = np.linalg.lstsq(design(train) * root[:, None], y * root, rcond=None)
    values = design(test) @ coef
    return values, dict(coefficients=coef.tolist(), rank=int(rank), mean=mean.tolist(), scale=scale.tolist(),
                        training_works=sorted(counts), training_multiplicities=dict(multiplicities))


def crossfit(rows, layer, *, shrink=False, multiplicities=None):
    works = sorted({r['work_id'] for r in rows})
    mult = Counter(works) if multiplicities is None else Counter(multiplicities)
    selected = [dict(r) for r in rows if mult[r['work_id']] > 0]
    if len({r['work_id'] for r in selected}) < 2:
        return None
    if shrink:
        means = {}
        for w in works:
            rs = [r for r in selected if r['work_id'] == w]
            if rs:
                means[w] = {k: sum(r[k] for r in rs)/len(rs) for k in ('b_even', 'b_odd')}
        for r in selected:
            for k in ('b_even', 'b_odd'):
                r[k] = .5*r[k] + .5*means[r['work_id']][k]
    predictions, folds = [], {}
    for held in sorted({r['work_id'] for r in selected}):
        train = [r for r in selected if r['work_id'] != held]
        test = [r for r in selected if r['work_id'] == held]
        train_mult = {w: n for w, n in mult.items() if w != held and n}
        expanded = [dict(r, work_id=r['work_id'] + '#' + str(j))
                    for r in train for j in range(train_mult[r['work_id']])]
        action_names=set().union(*(set(r.get('actions',{})) for r in test)) & RULES[layer]
        policy_fits={}
        for name,field in [('G0','z0'),('G1','z1')]:
            if name in action_names:policy_fits[name]=threshold_fit(expanded,field)
        if 'G3' in action_names:
            groups=defaultdict(list)
            for r in expanded:groups[r['unit'],r['x_equals_d']].append(r)
            policy_fits['G3']={str(k):sum(w*r['b'] for w,r in zip(work_weights(rs),rs)) for k,rs in groups.items()}
        z3_fit = None
        if layer == 'a_z0_z1_z3' or 'G4' in action_names:
            # 此处不能复用其他留出折的z3：它可能间接看过当前留出作品损失。
            z3_fit = fit_g4(expanded)
            train = [dict(r, z3=specificity(r, z3_fit['specificity_threshold'])) for r in train]
            test = [dict(r, z3=specificity(r, z3_fit['specificity_threshold'])) for r in test]
        even, fit_even = _fit(train, test, LAYERS[layer], 'b_even', train_mult, layer == 'a_z0_z1_z3')
        odd, fit_odd = _fit(train, test, LAYERS[layer], 'b_odd', train_mult, layer == 'a_z0_z1_z3')
        folds[held] = dict(sign_half=fit_even, evaluation_half=fit_odd, specificity_fit=z3_fit,policy_fits=policy_fits)
        for r, m_even, m_odd in zip(test, even, odd):
            # 一起算的奇数续写即零起算rep偶数：前者估计符号，后者评价幅度。
            abs_b = float(np.sign(r['b_even']) * r['b_odd'])
            abs_m = float(np.sign(m_even) * m_odd)
            actions={}
            for name in action_names:
                if name=='never_A1':actions[name]=True
                elif name=='always_A1':actions[name]=False
                elif name in ('G2_z0','G2_z1'):actions[name]=False
                elif name=='two_state_oracle':actions[name]=r['unit']=='F-D'
                elif name in ('G0','G1'):
                    field='z0' if name=='G0' else 'z1'
                    actions[name]=r[field]>=threshold_value(policy_fits[name]['threshold'])
                elif name=='G3':actions[name]=policy_fits[name].get(str((r['unit'],r['x_equals_d'])),0)>0
                elif name=='G4':actions[name]=g4_action(r,z3_fit['specificity_threshold'],z3_fit['z0_threshold'])['remove_a1']
            losses = {name: float((.5*(np.sign(m_even) + 1) - int(action)) * m_odd)
                      for name, action in actions.items()}
            predictions.append(dict(history_id=r['history_id'], work_id=held,
                abs_b=abs_b, abs_conditional_mean=abs_m, R_info=.5*(abs_b-abs_m),
                rule_losses=losses, conditional_sign=float(m_even), conditional_evaluation=float(m_odd)))
    counts = Counter(r['work_id'] for r in predictions)
    result = dict(folds=folds, predictions=predictions)
    for weight in ('work_equal', 'history_equal'):
        ws = [mult[r['work_id']] / counts[r['work_id']] if weight == 'work_equal' else mult[r['work_id']] for r in predictions]
        def avg(values):
            return float(np.dot(values, ws)/sum(ws))
        result[weight] = {k: avg([r[k] for r in predictions]) for k in ('abs_b', 'abs_conditional_mean', 'R_info')}
        names = sorted(set.intersection(*(set(r['rule_losses']) for r in predictions)))
        result[weight]['rule_losses'] = {k: avg([r['rule_losses'][k] for r in predictions]) for k in names}
    return result


def information_loss(rows):
    required = ('a', 'z0', 'z1', 'b_even', 'b_odd')
    missing = [{"history_id": r['history_id'], 'fields': [k for k in required if not finite(r.get(k))]}
               for r in rows if any(not finite(r.get(k)) for k in required)]
    if missing:
        return dict(status='未能可靠识别', missing_inputs=missing, reason='缺少分半或读数，未以零补齐或删除历史')
    works = sorted({r['work_id'] for r in rows})
    draws = np.random.default_rng(20261112).integers(0, len(works), (2000, len(works)))
    output = {}
    for layer in LAYERS:
        versions = {}
        for shrink in (False, True):
            point = crossfit(rows, layer, shrink=shrink)
            boot = []
            for indices in draws:
                fitted = crossfit(rows, layer, shrink=shrink,
                    multiplicities=Counter(works[i] for i in indices))
                if fitted is not None:
                    boot.append({w: fitted[w] for w in ('work_equal', 'history_equal')})
            if point is None:
                versions['shrunk' if shrink else 'split_half'] = dict(status='未能可靠识别')
                continue
            interval = {}
            for weight in ('work_equal', 'history_equal'):
                interval[weight] = {k: np.quantile([b[weight][k] for b in boot], [.025, .975]).tolist()
                                    for k in ('abs_b', 'abs_conditional_mean', 'R_info')}
                interval[weight]['rule_losses'] = {k: np.quantile([b[weight]['rule_losses'][k] for b in boot], [.025, .975]).tolist()
                                                   for k in point[weight]['rule_losses']}
            versions['shrunk' if shrink else 'split_half'] = dict(**point, ci95=interval,
                bootstrap_repetitions=2000, usable_bootstrap=len(boot),
                excluded_bootstrap_reason='只剩一个不同作品的重抽不能留一，未重抽替补' if len(boot) < 2000 else None)
        a, b = versions['split_half'], versions['shrunk']
        states = {}
        for weight in ('work_equal', 'history_equal'):
            if 'ci95' not in a or 'ci95' not in b:
                states[weight] = dict(status='未能可靠识别', bounds=None)
                continue
            intervals = [a['ci95'][weight]['R_info'], b['ci95'][weight]['R_info']]
            same_sign = a[weight]['R_info'] * b[weight]['R_info'] > 0
            excludes_zero = all(lo > 0 or hi < 0 for lo, hi in intervals)
            states[weight] = dict(status='两套估计方向一致且区间不含零' if same_sign and excludes_zero else '未能可靠识别',
                bounds=[min(x[0] for x in intervals), max(x[1] for x in intervals)])
        output[layer] = dict(estimates=versions, interpretation=states)
    return dict(status='已按冻结实现计算', layers=output,
                excluded_rule_losses='G3与两态预言机使用单元角色，不是原文三层X的函数；净收益照常报告，此处不扩X。',
                note='负的分半估计不截成零；留出估计不能强制满足总体信息损失单调性。方向一致不代表幅度等价，不新增一致性容忍阈值。')
