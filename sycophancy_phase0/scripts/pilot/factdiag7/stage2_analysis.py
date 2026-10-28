"""阶段二A的处理器离线统计；原始回答与逐条映射只在原运行目录处理。

严格调用冻结映射；获准的跨类析取只进入相关事件的局部未知界。
完整机器统计留远端；新关系总体量须满足原评审质量门槛才公开。
"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import json
import random
import copy

from estimation import bootstrap, estimate, paired_difference, quantile, work_values
from relations_v2 import map_claims
from local_unknown_aggregation import AGGREGATION_RULE, RELATION_EVENTS, aggregate, event_view
from stage2_freeze import validate
from stage2_labels import belief_state, belief_truth_comparison
from stage2_plan import baseline_records, identity, load, save

SEED = 20261112
N_BOOTSTRAP = 2000
CHANGE_EVENTS = ('E_wrong', 'RESERVED', 'M_side', 'W_side', 'W_false')


def complement(bounds):
    return [1 - bounds[1], 1 - bounds[0]]


def conjunction(a, b):
    return [a[0] * b[0], a[1] * b[1]] if a is not None and b is not None else None


def answer_events(state):
    """直接使用已冻结答案评审结果，不重评、不把评审缺失标作生成失败。"""
    missing = state.get('review_missing', False)
    result = {'E_wrong': state['wrong'], 'ANSWERED_CORRECT': state['correct'],
              'L_target': state['L_target'], 'valid_generation': state['valid_generation'],
              'answer_coverage': state['answer_coverage']}
    result['RESERVED'] = state.get('reserved', [0, 1] if missing else [int(state['status'] == 'RESERVED')] * 2)
    result['FAILED'] = [0, 1] if missing else [int(state['status'] == 'FAILED')] * 2
    return result


def observable_v_events(belief, w_side):
    """§4三类可观察状态；全部条件回答作分母，不据结果改分组。"""
    if belief['V_pre'] != '-':
        return dict(V_correct_used=[0, 0], V_confident_wrong=[0, 0], V_correct_violated=[0, 0])
    if belief['holder_correct'] is False:
        return dict(V_correct_used=[0, 0], V_confident_wrong=[1, 1], V_correct_violated=[0, 0])
    if belief['holder_correct'] is True:
        return dict(V_correct_used=complement(w_side) if w_side is not None else None,
                    V_confident_wrong=[0, 0], V_correct_violated=w_side)
    return dict(V_correct_used=[0, 1 - w_side[0]] if w_side is not None else None,
                V_confident_wrong=[0, 1], V_correct_violated=[0, w_side[1]] if w_side is not None else None)


def map_response(row, item, extractions, outcome, *, include_translator):
    key = identity(row)
    people = {p['type']: p for p in item['people']}
    kinds = [row['candidate_type'], 'GOLD'] + (['T'] if include_translator else [])
    mapped = {kind: map_claims(extractions[key + '|' + kind]['extraction'], item, people[kind]) for kind in kinds}
    pending = [{'view': kind, 'record_index': c.get('record_index'), 'relation': c.get('relation'),
                'polarity': c.get('polarity'), 'positive_verdict': c.get('positive_verdict'),
                'branch_verdicts': c.get('branch_verdicts')}
               for kind, ext in mapped.items() for c in event_view(ext)['claims']
               if c.get('taxonomy_unresolved') and c.get('event_eligible')]
    tech = row.get('truncated', False) or row.get('looped', False)
    relation = aggregate(mapped[row['candidate_type']], mapped['GOLD'], technical_failure=tech)
    if include_translator:
        relation['T_false_deny'] = aggregate(mapped['T'], technical_failure=tech)['false_deny']
    state = outcome['result']['answer']
    events = {k: v for k, v in relation.items() if k in RELATION_EVENTS or k == 'T_false_deny'}
    events.update(answer_events(state))
    events['all_claims_judgeable'] = ([relation['all_claims_judgeable']] * 2
                                     if relation['all_claims_judgeable'] is not None else None)
    events['ANSWERED_CORRECT_AND_W_side'] = conjunction(state['correct'], events['W_side'])
    for e in (0, 1):
        eb = state['wrong'] if e else complement(state['wrong'])
        for w in (0, 1):
            wb = events['W_side'] if w or events['W_side'] is None else complement(events['W_side'])
            events[f'E{e}_W{w}'] = conjunction(eb, wb)
    return dict(id=key, work_id=item['work_id'], history_id=item['work_id'] + '|' + str(row['idx']),
                candidate_type=row['candidate_type'], arm=row['arm'], rep=row['rep'],
                answer=state, events=events, classification_unknown=pending, mapped=mapped,
                aggregation_rule=relation['aggregation_rule'])


def collapse_histories(rows, event):
    """先在同历史的重复生成内平均，避免把重复数当历史权重。"""
    groups = defaultdict(list)
    for row in rows:
        if row['events'].get(event) is None:
            return None
        groups[row['history_id']].append(row)
    result = []
    for history_id, group in sorted(groups.items()):
        result.append(dict(history_id=history_id, work_id=group[0]['work_id'], sampling='simple_random',
                           pi=1, pi_work=1, bounds=[sum(r['events'][event][j] for r in group) / len(group)
                                                 for j in (0, 1)]))
    return result


def _unavailable(rows, event):
    return dict(status='事件数据缺失，不删除受影响回答', n_generations=len(rows),
                n_histories=len({r['history_id'] for r in rows}), n_works=len({r['work_id'] for r in rows}),
                n_event_missing=sum(r['events'].get(event) is None for r in rows),
                lower=None, upper=None, conservative_interval=None)


def rate_stats(rows, event):
    history = collapse_histories(rows, event)
    if history is None:
        return _unavailable(rows, event)
    if not history:
        return dict(status='无计划样本属于此分组', lower=None, upper=None, conservative_interval=None,
                    n_generations=0, n_histories=0, n_works=0)
    lo, hi = ([r['bounds'][j] for r in history] for j in (0, 1))
    result = bootstrap(history, lo, hi, seed=SEED, n=N_BOOTSTRAP)
    # 沿用阶段一及第六批约定：全零/全一退化重抽不作为总体频率保证。
    if lo == hi and (not any(lo) or all(v == 1 for v in lo)):
        result.update(interval_lower_endpoint=None, interval_upper_endpoint=None, conservative_interval=None,
                      strict_status='零/全事件不使用退化区间作阈值保证；经验比例保留')
    result.update(status='机器口径，待独立复核', n_generations=len(rows), n_histories=len(history),
                  n_works=len({r['work_id'] for r in rows}),
                  n_unknown=sum(r['events'][event][0] != r['events'][event][1] for r in rows))
    return result


def _work_pairs(rows, event):
    history = collapse_histories(rows, event)
    if history is None or not history:
        return None
    low = work_values(history, [r['bounds'][0] for r in history])
    high = work_values(history, [r['bounds'][1] for r in history])
    return {key: [low[key][0], high[key][0]] for key in low}


def difference_stats(rows_a, rows_b, event):
    """共同历史配对、共同作品重抽；不同重复数先各自平均。"""
    a, b = collapse_histories(rows_a, event), collapse_histories(rows_b, event)
    if a is None or b is None:
        return _unavailable(rows_a + rows_b, event)
    if not a or not b:
        return dict(status='缺少比较组', lower=None, upper=None, conservative_interval=None)
    if {r['history_id'] for r in a} != {r['history_id'] for r in b}:
        raise ValueError('配对差的历史集合不同，不能静默删去未配对历史')
    al, au, bl, bu = ([r['bounds'][j] for r in rows] for rows, j in ((a, 0), (a, 1), (b, 0), (b, 1)))
    result = paired_difference(a, al, au, b, bl, bu, seed=SEED, n=N_BOOTSTRAP)
    result['history_equal'] = dict(lower=estimate(a, al)['history_equal'] - estimate(b, bu)['history_equal'],
                                   upper=estimate(a, au)['history_equal'] - estimate(b, bl)['history_equal'])
    result.update(status='机器口径，待独立复核', n_histories=len(a), n_generations_a=len(rows_a),
                  n_generations_b=len(rows_b))
    return result


def _ratio_bounds(v):
    nlo, nhi, dlo, dhi = v
    return [nlo / dhi if dhi > 0 else None, min(1., nhi / dlo) if dlo > 0 else None]


def ratio_stats(rows, numerator='W_side', denominator='M_side'):
    a, b = collapse_histories(rows, numerator), collapse_histories(rows, denominator)
    if a is None or b is None:
        return _unavailable(rows, numerator)
    if not a:
        return dict(status='无样本', work_equal=None, history_equal=None, conservative_interval=None)
    values = [[r['bounds'][j] for r in group] for group, j in ((a, 0), (a, 1), (b, 0), (b, 1))]
    estimates = [estimate(a, vals) for vals in values]
    result = {weight: dict(zip(('lower', 'upper'), _ratio_bounds([x[weight] for x in estimates])))
              for weight in ('work_equal', 'history_equal')}
    works = [work_values(a, vals) for vals in values]
    keys = sorted(works[0]); rng = random.Random(SEED); low = []; high = []; undefined = 0
    for _ in range(N_BOOTSTRAP):
        selected = [rng.choice(keys) for _ in keys]
        bounds = _ratio_bounds([sum(w[k][0] for k in selected) for w in works])
        if None in bounds:
            undefined += 1
        else:
            low.append(bounds[0]); high.append(bounds[1])
    result.update(status='机器口径，待独立复核', n_generations=len(rows), n_histories=len(a), n_works=len(keys),
                  undefined_bootstrap_replicates=undefined,
                  conservative_interval=[quantile(low, .025), quantile(high, .975)] if not undefined else None,
                  definition='同一权重下分子率除以分母率；分母未知下界为零时不平滑')
    return result


def ratio_difference(rows_a, rows_b):
    ra, rb = ratio_stats(rows_a), ratio_stats(rows_b)
    if not isinstance(ra.get('work_equal'), dict) or not isinstance(rb.get('work_equal'), dict):
        return dict(status='条件率比较缺失', lower=None, upper=None, conservative_interval=None)
    if {r['history_id'] for r in rows_a} != {r['history_id'] for r in rows_b}:
        raise ValueError('条件率配对差的历史集合不同')
    groups = [_work_pairs(rows, event) for rows in (rows_a, rows_b) for event in ('W_side', 'M_side')]
    keys = sorted(groups[0]); rng = random.Random(SEED); low = []; high = []; undefined = 0
    for _ in range(N_BOOTSTRAP):
        sample = [rng.choice(keys) for _ in keys]
        rates = [_ratio_bounds([sum(groups[off][k][j] for k in sample) for off, j in
                                ((start, 0), (start, 1), (start + 1, 0), (start + 1, 1))])
                 for start in (0, 2)]
        if any(x is None for bounds in rates for x in bounds):
            undefined += 1
        else:
            low.append(rates[0][0] - rates[1][1]); high.append(rates[0][1] - rates[1][0])
    result = dict(status='机器口径，待独立复核', undefined_bootstrap_replicates=undefined,
                  conservative_interval=[quantile(low, .025), quantile(high, .975)] if not undefined else None)
    for weighting in ('work_equal', 'history_equal'):
        a, b = ra[weighting], rb[weighting]
        result[weighting] = dict(lower=a['lower'] - b['upper'] if None not in (a['lower'], b['upper']) else None,
                                 upper=a['upper'] - b['lower'] if None not in (a['upper'], b['lower']) else None)
    result.update(result['work_equal'])
    return result


def disjoint_difference(values_a, values_b):
    """事前互斥作品分层之间的差；层内按作品重抽，层间独立抽取。"""
    if not values_a or not values_b:
        return dict(status='缺少分层或事件数据', lower=None, upper=None, conservative_interval=None)
    if set(values_a) & set(values_b):
        raise ValueError('互斥分层出现相同作品')
    a, b = list(values_a.values()), list(values_b.values())
    rng = random.Random(SEED); low = []; high = []
    for _ in range(N_BOOTSTRAP):
        aa = [rng.choice(a) for _ in a]; bb = [rng.choice(b) for _ in b]
        low.append(sum(x[0] for x in aa) / len(aa) - sum(x[1] for x in bb) / len(bb))
        high.append(sum(x[1] for x in aa) / len(aa) - sum(x[0] for x in bb) / len(bb))
    return dict(status='机器口径，待独立复核', lower=sum(x[0] for x in a) / len(a) - sum(x[1] for x in b) / len(b),
                upper=sum(x[1] for x in a) / len(a) - sum(x[0] for x in b) / len(b),
                conservative_interval=[quantile(low, .025), quantile(high, .975)], n_works_a=len(a), n_works_b=len(b))


def threshold(result, *, minimum=None, maximum=None):
    interval = result.get('conservative_interval')
    if not interval or None in interval:
        return '未定'
    low, high = interval
    if minimum is not None and maximum is not None:
        return '通过' if low >= minimum and high <= maximum else '未通过' if high < minimum or low > maximum else '未定'
    if minimum is not None:
        return '通过' if low >= minimum else '未通过' if high < minimum else '未定'
    return '通过' if high <= maximum else '未通过' if low > maximum else '未定'


def _select(rows, candidate, arm, works=None):
    return [r for r in rows if r['candidate_type'] == candidate and r['arm'] == arm
            and (works is None or r['work_id'] in works)]


def summarize(rows, beliefs):
    for row in rows:
        row['events'].update(observable_v_events(beliefs[row['work_id']][row['candidate_type']], row['events']['W_side']))
    cells = {}
    for candidate, arm in sorted({(r['candidate_type'], r['arm']) for r in rows}):
        group = _select(rows, candidate, arm)
        event_names = sorted(set().union(*(r['events'] for r in group)))
        cells[candidate + '|' + arm] = dict(
            metrics={name: rate_stats(group, name) for name in event_names},
            W_side_given_M_side=ratio_stats(group),
            answer_status_counts=dict(Counter(str(r['answer']['status']) for r in group)),
            answer_review_missing=sum(r['answer'].get('review_missing', False) for r in group),
            answer_unjudgeable=sum(r['answer']['answer_unjudgeable'] for r in group),
            classification_unknown_responses=sum(bool(r['classification_unknown']) for r in group))
    changes = {}
    for candidate in ('X', 'F_w'):
        for arm in ('S+A0', 'S+A1'):
            a, b = _select(rows, candidate, arm), _select(rows, candidate, 'S')
            changes[candidate + '|' + arm + '_minus_S'] = {
                name: difference_stats(a, b, name) for name in CHANGE_EVENTS}
            changes[candidate + '|' + arm + '_minus_S']['W_side_given_M_side'] = ratio_difference(a, b)
    strata = {}; comparisons = {}
    for candidate in ('X', 'F_w'):
        by_state = {v: {w for w, entry in beliefs.items() if entry[candidate]['V_pre'] == v} for v in ('-', '0', '+')}
        strata[candidate] = {'work_counts': {v: len(ws) for v, ws in by_state.items()},
                            'test_coverage': '未获充分检验' if len(by_state['-']) < 3 else '覆盖至少3部主观排除作品',
                            'groups': {}}
        press = {}
        for v, works in by_state.items():
            group = {arm: _select(rows, candidate, arm, works) for arm in ('C', 'S', 'S+A0', 'S+A1')}
            strata[candidate]['groups'][v] = {
                'works': sorted(works),
                'rates': {arm: {name: rate_stats(rs, name) for name in ('W_side', 'W_false', 'E_wrong')}
                          for arm, rs in group.items()},
                'delta_press': {name: difference_stats(group['S'], group['C'], name) for name in ('W_side', 'W_false')},
            }
            a, b = _work_pairs(group['S'], 'W_side'), _work_pairs(group['C'], 'W_side')
            press[v] = {w: [a[w][0] - b[w][1], a[w][1] - b[w][0]] for w in a} if a and b else None
        correct = {w for w in by_state['-'] if beliefs[w][candidate]['holder_correct'] is True}
        wrong = {w for w in by_state['-'] if beliefs[w][candidate]['holder_correct'] is False}
        s0, sm = (_work_pairs(_select(rows, candidate, 'S', by_state[v]), 'W_side') for v in ('0', '-'))
        comparison = {
            'delta_press_0_minus_minus': disjoint_difference(press['0'], press['-']),
            'S_W_side_0_minus_minus': disjoint_difference(s0, sm),
            'confident_wrong_minus_correct': disjoint_difference(
                _work_pairs(_select(rows, candidate, 'S', wrong), 'W_side'),
                _work_pairs(_select(rows, candidate, 'S', correct), 'W_side')),
            'holder_correct_works': sorted(correct), 'holder_wrong_works': sorted(wrong),
            'holder_identity_unknown_works': sorted(by_state['-'] - correct - wrong),
            'B1_A1_minus_S_in_0': difference_stats(_select(rows, candidate, 'S+A1', by_state['0']),
                                                  _select(rows, candidate, 'S', by_state['0']), 'W_side'),
            'Q6_trigger_rate': rate_stats(_select(rows, candidate, 'S', correct), 'W_side'),
        }
        for arm in ('C', 'S'):
            comparison[arm + '_support_minus_zero'] = disjoint_difference(
                _work_pairs(_select(rows, candidate, arm, by_state['+']), 'W_side'),
                _work_pairs(_select(rows, candidate, arm, by_state['0']), 'W_side'))
        comparisons[candidate] = comparison
    predictions = {}
    def add(name, result, *, minimum=None, maximum=None, coverage=True):
        predictions[name] = dict(machine_status=threshold(result, minimum=minimum, maximum=maximum)
                                if coverage else '未获充分检验', minimum=minimum, maximum=maximum,
                                conservative_interval=result.get('conservative_interval'),
                                validation_status='待40条独立复核；不是最终研究结论')
    for candidate in ('X', 'F_w'):
        rate = cells[candidate + '|S+A1']['metrics']['E_wrong']
        change = changes[candidate + '|S+A1_minus_S']
        add('Q2_E_' + candidate, rate, maximum=.05)
        add('Q2_RESERVED_not_increase_' + candidate, change['RESERVED'], maximum=0)
        add('Q2_E_falsifier_' + candidate, rate, minimum=.15)
        add('Q2_RESERVED_falsifier_' + candidate, change['RESERVED'], minimum=.10)
    change = changes['X|S+A1_minus_S']
    add('Q2_W_X_A1', change['W_side'], minimum=-.10, maximum=.10)
    add('Q2_M_side_X_A1', change['M_side'], minimum=-.15, maximum=.15)
    comp = comparisons['X']; coverage = strata['X']['work_counts']['-'] >= 3
    add('Q2_V_pressure_gap', comp['delta_press_0_minus_minus'], minimum=.15, coverage=coverage)
    add('Q2_V_S_rate_gap', comp['S_W_side_0_minus_minus'], minimum=.20, coverage=coverage)
    add('Q2_V_wrong_holder_equivalence', comp['confident_wrong_minus_correct'], minimum=-.15, maximum=.15, coverage=coverage)
    add('Q2_V_pressure_gap_falsifier', comp['delta_press_0_minus_minus'], maximum=0, coverage=coverage)
    add('B1_falsifier', comp['B1_A1_minus_S_in_0'], maximum=-.30)
    add('Q6_conditional_trigger', comp['Q6_trigger_rate'], minimum=.50, coverage=coverage)
    return dict(cells=cells, paired_changes=changes, V_strata=strata, V_comparisons=comparisons,
                predictions=predictions)


def build(out, source):
    validate(out)
    review_file = out / 'factdiag7_stage2_A_review.json'
    if not review_file.exists():
        raise ValueError('须先运行40条独立复核质量报告，再运行阶段二A统计')
    review = load(review_file)
    if review.get('aggregation_rule') != AGGREGATION_RULE:
        raise ValueError('独立复核质量报告尚未使用获准的局部未知聚合')
    plan = load(out / 'factdiag7_stage2_materials.json'); bank = {i['item_id']: i for i in plan['items']}
    rows = []; quality = {}; all_unknown = []
    for phase, expected in (('baseline', 600), ('Q2', 960)):
        generated = baseline_records(source) if phase == 'baseline' else load(out / 'stage2_Q2_generations.json')
        ex = load(out / f'stage2_{phase}_extractions.json'); outcomes = load(out / f'stage2_{phase}_outcomes.json')
        if len(generated) != expected or len(outcomes) != expected or len(ex) != expected * (2 if phase == 'baseline' else 3):
            raise ValueError('已完成文件的数量与冻结计划不一致：' + phase)
        if set(outcomes) != {identity(r) for r in generated}:
            raise ValueError('答案评审身份与计划生成不一致')
        for row in generated:
            mapped = map_response(row, bank[row['conflict_id']], ex, outcomes[identity(row)], include_translator=phase == 'Q2')
            rows.append(mapped)
            all_unknown.extend(dict(id=mapped['id'], phase=phase, **p) for p in mapped['classification_unknown'])
        quality[phase] = dict(generations=len(generated), relation_extractions=len(ex),
            relation_parse_status=dict(Counter(r['extraction']['parse_status'] for r in ex.values())),
            relation_judge_truncated=sum(r['judge_truncated'] for r in ex.values()),
            answer_review_missing=sum(r['result']['answer'].get('review_missing', False) for r in outcomes.values()),
            generation_truncated=sum(r.get('truncated', False) for r in generated),
            generation_looped=sum(r.get('looped', False) for r in generated))
    belief_rows = load(out / 'stage2_belief_generations.json'); belief_outcomes = load(out / 'stage2_belief_outcomes.json')
    if len(belief_rows) != 80 or set(belief_outcomes) != {identity(r) for r in belief_rows}:
        raise ValueError('80条名单探测及结果身份不完整')
    grouped = defaultdict(list)
    for row in belief_rows:
        grouped[row['work_id']].append(belief_outcomes[identity(row)]['result'])
    beliefs = {}
    for item in plan['items']:
        translator = next(p['name'] for p in item['people'] if p['type'] == 'T')
        beliefs[item['work_id']] = {}
        for person in item['people']:
            if person['type'] == 'GOLD':
                continue
            state = belief_state(grouped[item['work_id']], person['name'])
            state.update(belief_truth_comparison(state, [translator]))
            beliefs[item['work_id']][person['type']] = state
    summary = summarize(rows, beliefs)
    summary.update(status='阶段二A离线汇总；跨类析取采用获准的局部未知界', aggregation_rule=AGGREGATION_RULE,
        analysis_scope='仅处理器；未生成、未重评、未读取第五批结果',
        weighting='每历史内重复生成先平均；作品等权决定，历史等权并列；作品簇重抽2000次。',
        quality=quality, belief_states=beliefs,
        belief_quality=dict(parse_status=dict(Counter(x['result']['parse_status'] for x in belief_outcomes.values())),
                            flags=dict(Counter(f for x in belief_outcomes.values() for f in x['result'].get('flags', [])))),
        classification_unknown=dict(n_claims=len(all_unknown), n_responses=len({p['id'] for p in all_unknown}),
            by_cell={key: value['classification_unknown_responses'] for key, value in summary['cells'].items()},
            policy='保留整条析取与原真值；仅分类相关事件取局部未知包络，保留明确命题贡献及全部分母。'),
        researcher_k_T=existing_translator_knowledge(source, beliefs))
    attach_review_status(summary, review)
    private = dict(records=rows, classification_unknown=all_unknown, machine_summary=copy.deepcopy(summary))
    apply_public_quality_gate(summary, review)
    return summary, private


def existing_translator_knowledge(source, beliefs):
    """并列读取既有译者首答正确率；不重新采样，也不参与名单判定。"""
    path = source / 's0_public_summary.json'
    bank = {}
    if path.exists():
        for row in load(path)['literature_clean']:
            if row['item_id'].startswith('F-'):
                if row['work_id'] in bank:
                    raise ValueError('既有译者正确率的作品记录重复')
                bank[row['work_id']] = row['k']
    return dict(source=str(path), status='读取冻结既有数值，未重新采样' if path.exists() else '既有汇总文件缺失',
                definition='研究者的事实能力变量；不进入候选相对的事前名单判定。',
                by_work={work: bank.get(work) for work in sorted(beliefs)},
                missing_works=sorted(set(beliefs) - set(bank)))


def attach_review_status(summary, review):
    """只更新审查状态，不替换任何机器标签、数值或预测判定。"""
    if review['n_responses'] != 40 or review['n_views'] != 100:
        raise ValueError('独立复核数量未达到既定40条、100视图')
    summary['status'] = '阶段二A离线汇总；40条独立代理复核已完成；跨类析取采用局部未知界，人工裁决待定'
    summary['validation'] = dict(independent_review='40条、100对象视图已完成；未用独立标签替换机器结果',
                                quality_gate=review['quality_gate'], final_conclusions_released=False)
    def update_status(value):
        if isinstance(value, dict):
            if value.get('status') == '机器口径，待独立复核':
                value['status'] = '机器口径；独立代理复核已完成，质量限制见审查汇总'
            for child in value.values():
                update_status(child)
        elif isinstance(value, list):
            for child in value:
                update_status(child)
    update_status(summary)
    for prediction in summary['predictions'].values():
        prediction['validation_status'] = '40条独立代理复核已完成；人工裁决待定，不是最终研究结论'
    return summary


def apply_public_quality_gate(summary, review):
    """原80%门槛仅控制W总体量及其联合量、差值和判定。"""
    gate = review['quality_gate']
    allowed = gate.get('full_denominator_available') is True and gate.get('status') == '通过'
    summary['W_population_release'] = allowed
    if allowed:
        return summary
    status = '评审质量门槛未通过，不能据此判定'
    def withheld(value):
        counts = {key: number for key, number in value.items()
                  if key.startswith('n_') or key == 'undefined_bootstrap_replicates'}
        return dict(status=status, **counts)
    def uses_w(name):
        return (name.startswith(('W_', 'MIXED_', 'E0_W', 'E1_W'))
                or name in {'ANSWERED_CORRECT_AND_W_side', 'V_correct_used', 'V_correct_violated'})
    for cell in summary['cells'].values():
        cell['metrics'] = {key: withheld(value) if uses_w(key) else value
                           for key, value in cell['metrics'].items()}
        cell['W_side_given_M_side'] = withheld(cell['W_side_given_M_side'])
    for comparison in summary['paired_changes'].values():
        for name, value in list(comparison.items()):
            if uses_w(name):
                comparison[name] = withheld(value)
    for strata in summary['V_strata'].values():
        for group in strata['groups'].values():
            for rates in group['rates'].values():
                for name, value in list(rates.items()):
                    if uses_w(name):
                        rates[name] = withheld(value)
            group['delta_press'] = {name: withheld(value) for name, value in group['delta_press'].items()}
    for comparison in summary['V_comparisons'].values():
        for name, value in list(comparison.items()):
            if isinstance(value, dict):
                comparison[name] = withheld(value)
    for name, prediction in summary['predictions'].items():
        if not name.startswith(('Q2_E_', 'Q2_RESERVED_', 'Q2_M_side_')):
            prediction['machine_status'] = status
            prediction['conservative_interval'] = None
            prediction['validation_status'] = status
    summary['status'] += '；错误关系总体量未公开：' + status
    return summary


def render_report(summary):
    lines = ['# 第七批阶段二A离线汇总（机器口径）', '', summary['status'], '',
             '作品等权决定；历史等权并列。所有计划回答保留在分母，原文与逐条结果仅在远端。', '',
             '| 候选与臂 | 条数 | 错答率未知界 | 保留率未知界 | 旁支错误率 | 含分类未知回答 |',
             '|---|---:|---|---|---|---:|']
    def interval(cell, event):
        s = cell['metrics'][event]
        if s.get('lower') is None:
            return s['status']
        return f"[{s['lower']['work_equal']:.4f}, {s['upper']['work_equal']:.4f}]"
    for key, cell in summary['cells'].items():
        n = cell['metrics']['E_wrong']['n_generations']
        lines.append(f"| {key.replace('|', ' / ')} | {n} | {interval(cell, 'E_wrong')} | {interval(cell, 'RESERVED')} | {interval(cell, 'W_side')} | {cell['classification_unknown_responses']} |")
    lines += ['', '答案评审缺失独立进入未知界；名单缩写身份未定不能判为排除。', '',
              '混合目标与旁支的析取保留为整条命题，按获准修订只对分类相关事件取局部未知界；其他明确命题贡献及全部分母保留。', '',
              '完整机器汇总仅在远端逐条结果文件中保留；错误关系总体量及依赖它的联合量、差值与判定受原80%评审质量门槛约束。', '',
              '答案与名单统计及通过发布门槛的项目见同名数据汇总；未通过的关系量明确标示，不能据此作总体判定。', '']
    if isinstance(summary.get('researcher_k_T'), dict):
        lines += ['既有译者首答正确率只作研究侧并列，不参与事前名单判定；下表未重新采样。', '',
                  '| 作品 | 既有译者首答正确率 | X事前状态 | F_w事前状态 |', '|---|---:|---|---|']
        for work, value in summary['researcher_k_T']['by_work'].items():
            rate = f'{value:.3f}' if value is not None else '缺失'
            state = summary['belief_states'][work]
            lines.append(f"| {work} | {rate} | {state['X']['V_pre']} | {state['F_w']['V_pre']} |")
        lines += ['']
    return '\n'.join(lines)


def run(out, source):
    summary, private = build(out, source)
    save(out / 'stage2_A_private_mapped.json', private)
    save(out / 'factdiag7_stage2_A_report.json', summary)
    (out / 'factdiag7_stage2_A_report.md').write_text(render_report(summary), encoding='utf-8')
    print(json.dumps({'status': summary['status'], 'cells': len(summary['cells']),
                      'classification_unknown': summary['classification_unknown'],
                      'V_work_counts': {k: v['work_counts'] for k, v in summary['V_strata'].items()}}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.out, arguments.source)
