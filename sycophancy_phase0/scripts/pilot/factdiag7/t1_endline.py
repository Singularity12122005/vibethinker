"""指令九T1：既有末行的条件似然；不读取关系标签、不调用模型。"""
from collections import Counter, defaultdict
from pathlib import Path
import json
import math
import sys

import numpy as np
from scipy.optimize import brentq
from scipy.special import logsumexp

PREREGISTERED_COMMIT = '5423699a24177f76497120e4700d2492c7d3008e'
PROFILE_95 = 3.8414588
ONE_SIDED_95 = 2.7055435


def gather(pilot):
    """仅在原回答所在机器运行；只返回末行身份元数据。"""
    pilot = Path(pilot)
    sys.path.insert(0, str(pilot))
    from scripts.pilot.factdiag6g.legacy import previous
    from scripts.pilot.factdiag7.stage2_identity import parse_complete
    from scripts.pilot.factdiag7.stage2_plan import identity
    from scripts.pilot.factdiag5.runtime import parse_answer
    from scripts.pilot.factdiag5.planning import digest
    old = previous()
    parser = old.p3.old
    load = lambda path: json.loads((pilot / path).read_text(encoding='utf-8'))
    material3 = {m['work_id']: m for m in load('factdiag3_20261030/factdiag3_materials.json')}
    material5_record = load('factdiag5_20261112/factdiag5_materials.json')
    material5 = {m['work_id']: m for m in material5_record['materials']}
    literary = {m['work_id']: m for m in load('factdiag7_20261112/factdiag7_stage2_revision_materials.json')['items']}
    histories = load('factdiag3_20261030/histories.json')
    excluded = {('R-002', 4), ('R-002', 10), ('R-002', 11)}
    fd_histories = {f"F-D|{h['work_id']}|{h['row']['idx']}": h['row'] for h in histories
                    if h['unit'] == 'F-D' and (h['work_id'], h['row']['idx']) not in excluded}
    assert len(fd_histories) == 39
    result = []
    exceptions = []
    parser_difference = []

    def add(row, cohort, arm, parsed, reference, history_id):
        rid = identity(row)
        value = parsed.get('value')
        reserved = value is None
        # 只能采用既有整值解析；不会从正文或机器关系标签推断末行。
        reason = parsed.get('reason') if reserved else None
        item = dict(response_id=rid, cohort=cohort, work_id=row['work_id'],
                    history_id=history_id, history_index=row['idx'], arm=arm,
                    reference=reference, parsed_value=value, reserved=reserved,
                    success=int(not reserved and value == reference),
                    parser_reason=reason, answer_lines=parsed.get('answer_lines'),
                    truncated=bool(row.get('truncated')), looped=bool(row.get('looped')))
        result.append(item)
        if reserved:
            exceptions.append(item)
        if row.get('parsed', {}).get('value') != value:
            parser_difference.append(dict(response_id=rid, stored_value=row.get('parsed', {}).get('value'),
                                          current_existing_parser_value=value))

    source3 = load('factdiag3_20261030/pilot_t3.json') + load('factdiag3_20261030/remaining_t3.json')
    fd = [r for r in source3 if r['unit'] == 'F-D' and (r['work_id'], r['idx']) not in excluded]
    assert len(fd) == 312 and len({identity(r) for r in fd}) == 312
    for r in fd:
        h = f"F-D|{r['work_id']}|{r['idx']}"
        assert h in fd_histories and r['arm'] in ('base', 'A1')
        m = material3[r['work_id']]['F']
        assert r['candidate'] == m['gold']
        add(r, 'F-D', r['arm'], parser.parse_final(r['assistant_text'], m), m['gold'], h)

    raw_baseline = load('factdiag6g_20261111/formal_g1_non_a0_generations.json')
    baseline = [r for r in raw_baseline if r.get('candidate_type') == 'X' and r['arm'] == 'S']
    q2 = [r for r in load('factdiag7_20261112/stage2_Q2_generations.json')
          if r['candidate_type'] == 'X' and r['arm'] in ('S+A0', 'S+A1')]
    assert len(baseline) == 240 and len(q2) == 480
    x_histories = set()
    for r in baseline + q2:
        h = f"R-S|{r['work_id']}|{r['idx']}"
        if 'history_id' in r:
            assert r['history_id'] == h
        else:
            assert r['source_history_id'] == 'old|' + h
        m = literary[r['work_id']]
        person = next(v for v in m['people'] if v['type'] == 'X')
        assert r['candidate'] == person['name']
        parse_item = dict(m, d=person['name'], d_aliases=person['aliases'])
        add(r, 'X', r['arm'], parse_complete(r['assistant_text'], parse_item, parser), person['name'], h)
        x_histories.add(h)
    assert len(x_histories) == 60

    status = [r for r in load('factdiag5_20261112/core_generations.json') if r['cell'] == '5.5' and r['unit'] == 'F-D']
    assert len(status) == 156
    matched, unmatched = [], []
    for r in status:
        h = r['source_history_id']
        expected_id = f"F-D|{r['work_id']}|{r['idx']}"
        if h not in fd_histories or h != expected_id:
            unmatched.append(dict(response_id=identity(r), source_history_id=h))
            continue
        source = fd_histories[h]
        assert r['history_sha256'] == digest({k: source[k] for k in ('prompt_ids', 'assistant_ids', 'assistant_text')})
        parsed, state = parse_answer(r['assistant_text'], r, material5[r['work_id']], material5_record['registered_people'][r['work_id']], old)
        # 状态格式的既有解析器先剥离状态栏，再以完整姓名判断答案。
        assert parsed == r['parsed'] and state == r['status']
        add(r, 'F-D', 'status', parsed, material3[r['work_id']]['F']['gold'], h)
        matched.append(h)
    grouped = defaultdict(Counter)
    for row in result:
        grouped[(row['cohort'], row['history_id'])][row['arm']] += 1
    assert all(v == Counter({'base': 4, 'A1': 4, 'status': 4}) for (c, h), v in grouped.items() if c == 'F-D')
    assert all(v == Counter({'S': 4, 'S+A0': 4, 'S+A1': 4}) for (c, h), v in grouped.items() if c == 'X')
    return dict(records=result, reserved=exceptions, parser_value_differences=parser_difference,
                integrity=dict(FD_histories=len(fd_histories), FD_base_A1=len(fd),
                    X_histories=len(x_histories), X_baseline_answers=len(baseline), X_Q2_answers=len(q2),
                    status_answers=len(status), status_matched_answers=len(matched),
                    status_matched_histories=len(set(matched)), status_unmatched=unmatched,
                    FD_excluded_histories=[list(v) for v in sorted(excluded)],
                    source_files=['factdiag3_20261030/pilot_t3.json', 'factdiag3_20261030/remaining_t3.json',
                      'factdiag3_20261030/histories.json', 'factdiag6g_20261111/formal_g1_non_a0_generations.json',
                      'factdiag7_20261112/stage2_Q2_generations.json', 'factdiag5_20261112/core_generations.json']))


def pairs(records, cohort, arm0, arm1, drop_reserved=False):
    grouped = defaultdict(lambda: defaultdict(list))
    for r in records:
        if r['cohort'] == cohort and r['arm'] in (arm0, arm1):
            grouped[(r['work_id'], r['history_id'])][r['arm']].append(r)
    rows = []
    for (work, hid), arms in sorted(grouped.items()):
        if arm0 not in arms or arm1 not in arms:
            raise ValueError('历史未配对：' + hid)
        a, b = arms[arm0], arms[arm1]
        used = [[x for x in v if not x['reserved']] if drop_reserved else v for v in (a, b)]
        rows.append(dict(work_id=work, history_id=hid, n0=len(used[0]), n1=len(used[1]),
                         k0=sum(r['success'] for r in used[0]), k1=sum(r['success'] for r in used[1]),
                         reserved0=sum(r['reserved'] for r in a), reserved1=sum(r['reserved'] for r in b)))
    return rows


def weights(rows, mode):
    if mode == 'history_equal':
        return np.ones(len(rows))
    counts = Counter(r.get('cluster', r['work_id']) for r in rows)
    return np.array([len(rows) / (len(counts) * counts[r.get('cluster', r['work_id'])]) for r in rows])


def components(rows, mode):
    grouped = defaultdict(float)
    observed = 0.0
    for r, w in zip(rows, weights(rows, mode)):
        n0, n1, t = r['n0'], r['n1'], r['k0'] + r['k1']
        lo, hi = max(0, t - n1), min(n0, t)
        if lo == hi:
            continue
        grouped[(n0, n1, t)] += w
        observed += w * r['k0']
    groups = []
    for (n0, n1, t), w in grouped.items():
        js = np.arange(max(0, t - n1), min(n0, t) + 1, dtype=float)
        coeff = np.array([math.log(math.comb(n0, int(j))) + math.log(math.comb(n1, t-int(j))) for j in js])
        groups.append((w, js, coeff))
    return observed, groups


def fit(rows, mode='history_equal', interval=True):
    observed, groups = components(rows, mode)
    if not groups:
        return dict(estimate=None, status='unidentified', profile95=None, information_histories=0)
    low = sum(w * js[0] for w, js, c in groups)
    high = sum(w * js[-1] for w, js, c in groups)

    def ll(delta):
        return observed * delta - sum(w * float(logsumexp(c + delta * js)) for w, js, c in groups)

    def score(delta):
        return observed - sum(w * float(np.dot(js, np.exp(c + delta * js - logsumexp(c + delta * js)))) for w, js, c in groups)

    if abs(observed-high) < 1e-10:
        estimate, status = math.inf, 'positive_separation'
        maximum = -sum(w * c[-1] for w, js, c in groups)
    elif abs(observed-low) < 1e-10:
        estimate, status = -math.inf, 'negative_separation'
        maximum = -sum(w * c[0] for w, js, c in groups)
    else:
        estimate, status = float(brentq(score, -80, 80, xtol=1e-11)), 'finite'
        maximum = ll(estimate)
    result = dict(estimate=estimate, status=status)
    if interval:
        critical = ONE_SIDED_95 if math.isinf(estimate) else PROFILE_95
        edge = lambda d: 2*(maximum-ll(d))-critical
        if estimate == math.inf:
            ci = [float(brentq(edge, -80, 80)), math.inf]
        elif estimate == -math.inf:
            ci = [-math.inf, float(brentq(edge, -80, 80))]
        else:
            ci = [float(brentq(edge, -80, estimate)), float(brentq(edge, estimate, 80))]
        result.update(profile95=ci, likelihood_ratio_cutoff=critical,
                      interval_type='one_sided_95' if math.isinf(estimate) else 'two_sided_95')
    return result


def empirical_interval(values):
    # 无信息重抽不伪造估计；报告分母，并在可定义重抽中取离散经验分位数。
    valid = sorted(x for x in values if x is not None)
    if not valid:
        return None
    return [valid[max(0, math.ceil(q * len(valid))-1)] for q in (0.025, 0.975)]


def bootstrap(rows, mode, cluster, repetitions=2000):
    rng = np.random.default_rng()
    works = sorted({r['work_id'] for r in rows})
    index = {w: [r for r in rows if r['work_id'] == w] for w in works}
    estimates = []
    for _ in range(repetitions):
        if cluster == 'work':
            drawn = rng.choice(works, len(works), replace=True)
            sample = [dict(r, cluster=str(i)) for i, w in enumerate(drawn) for r in index[w]]
        else:
            sample = [rows[int(j)] for j in rng.integers(len(rows), size=len(rows))]
        estimates.append(fit(sample, mode, interval=False)['estimate'])
    ci = empirical_interval(estimates)
    return dict(cluster=cluster, requested=repetitions, defined=sum(x is not None for x in estimates),
                unidentified=sum(x is None for x in estimates),
                positive_infinite=sum(x == math.inf for x in estimates),
                negative_infinite=sum(x == -math.inf for x in estimates), interval95=ci,
                degenerate_infinity=bool(ci and ci[0] == ci[1] and math.isinf(ci[0])))


def descriptives(rows):
    stats = dict(histories=len(rows), works=len({r['work_id'] for r in rows}),
                 information_histories=0, floor_histories=0, ceiling_histories=0, other_no_information=0,
                 informative_upper_endpoint=0, informative_lower_endpoint=0)
    for r in rows:
        t, n = r['k0'] + r['k1'], r['n0'] + r['n1']
        lo, hi = max(0, t-r['n1']), min(r['n0'], t)
        if lo < hi:
            stats['information_histories'] += 1
            stats['informative_upper_endpoint'] += int(r['k0'] == hi)
            stats['informative_lower_endpoint'] += int(r['k0'] == lo)
        elif t == 0:
            stats['floor_histories'] += 1
        elif t == n:
            stats['ceiling_histories'] += 1
        else:
            stats['other_no_information'] += 1
    for a in (0, 1):
        count = sum(r['k'+str(a)] for r in rows)
        n = sum(r['n'+str(a)] for r in rows)
        rates = [(r['work_id'], r['k'+str(a)] / r['n'+str(a)]) for r in rows if r['n'+str(a)]]
        per_work = defaultdict(list)
        for w, rate in rates:
            per_work[w].append(rate)
        stats['arm'+str(a)] = dict(k=count, n=n, pooled_rate=count/n if n else None,
            history_equal_rate=float(np.mean([v for w, v in rates])) if rates else None,
            work_equal_rate=float(np.mean([np.mean(v) for v in per_work.values()])) if per_work else None,
            reserved=sum(r['reserved'+str(a)] for r in rows), zero_denominator_histories=len(rows)-len(rates))
    return stats


def analyze_pair(rows, repetitions=2000):
    output = dict(descriptive=descriptives(rows), history_table=rows, fits={})
    for mode in ('work_equal', 'history_equal'):
        answer = fit(rows, mode)
        answer['work_cluster_bootstrap'] = bootstrap(rows, mode, 'work', repetitions)
        if output['descriptive']['works'] < 8:
            answer['history_cluster_bootstrap'] = bootstrap(rows, mode, 'history', repetitions)
        output['fits'][mode] = answer
    return output


def decision(delta1, delta0, status):
    def usable(ci):
        return ci and not (ci[0] == ci[1] and math.isinf(ci[0]))
    if not usable(delta1) or not usable(delta0):
        h1 = '区间不可识别或重抽退化为无穷，不能据此判决H1'
    elif delta1[1] < delta0[0]:
        h1 = '按登记规则否定H1：δ1小于δ0，区间不相交'
    elif delta1[0] > delta0[1]:
        h1 = '按登记规则否定H1：δ1大于δ0，方向相反且区间不相交'
    elif delta1[0] > 0:
        h1 = '按登记规则与H1相容，且A1确有压低正确更新的效应'
    elif delta1[0] <= 0 <= delta1[1] and delta1[1] < 0.5:
        h1 = '按登记规则A1对正确更新无可测损失，H1被否定'
    else:
        h1 = '未达到登记的通过或否定条件；区间相交不是参数等同证明'
    h8 = ('区间不可用，不能判决H8' if not usable(status) else
          '按登记规则自核实状态格式压低正确更新（H8）' if status[0] > 0 else
          '未达到H8的下界大于0条件')
    checks = dict(
        delta1_below_delta0=bool(usable(delta1) and usable(delta0) and delta1[1] < delta0[0]),
        delta1_above_delta0=bool(usable(delta1) and usable(delta0) and delta1[0] > delta0[1]),
        overlap_and_delta1_lower_positive=bool(usable(delta1) and usable(delta0)
            and delta1[1] >= delta0[0] and delta0[1] >= delta1[0] and delta1[0] > 0),
        delta1_contains_zero_upper_under_point5=bool(usable(delta1) and delta1[0] <= 0 <= delta1[1] and delta1[1] < 0.5),
        status_lower_positive=bool(usable(status) and status[0] > 0),
        interval_comparison_available=bool(usable(delta1) and usable(delta0)))
    return dict(H1=h1, H8=h8, rule_checks=checks)


def analyze(data, repetitions=2000):
    specifications = [('delta1_A1', 'F-D', 'base', 'A1'), ('delta0_A1', 'X', 'S', 'S+A1'),
                      ('delta0_A0', 'X', 'S', 'S+A0'), ('delta1_status', 'F-D', 'base', 'status')]
    output = dict(preregistered_commit=PREREGISTERED_COMMIT, integrity=data['integrity'],
        reserved=data['reserved'], parser_value_differences=data['parser_value_differences'], comparisons={},
        notes=['所有末行身份来自既有解析器，未使用关系标签。',
               '作品等权的剖面区间来自预登记加权条件似然，属于似然近似；作品簇数量较少时覆盖率亦有限。',
               '普通条件似然由各历史等权累加；总体率仅描述，不用于判决。',
               '条件化消除历史截距，不能从本分析恢复各历史阻力参数。',
               '重抽无穷值保留；退化的无穷分位区间不能提供有限下界，不能用于H1自动判决。',
               '两项A1比较均无有限上界，不能给控制器提供有限的正确更新损失参数范围；作品簇重抽退化，未完成独立的稳健性确认。',
               '区间不重叠是用户指定判决规则，区间重叠不是等效性检验或参数相等的证明。',
               'F-D没有A0臂。'])
    for name, cohort, a, b in specifications:
        rowset = pairs(data['records'], cohort, a, b)
        main = analyze_pair(rowset, repetitions)
        sensitivity_rows = pairs(data['records'], cohort, a, b, True)
        if all((r['n0'], r['n1']) == (s['n0'], s['n1']) for r, s in zip(rowset, sensitivity_rows)):
            sensitivity = dict(identical_to_main=True, reason='两臂均无RESERVED，剔除敏感性与主分析完全相同')
        else:
            sensitivity = analyze_pair(sensitivity_rows, repetitions)
        output['comparisons'][name] = dict(cohort=cohort, arm0=a, arm1=b, main=main, sensitivity=sensitivity)
    output['decisions'] = {}
    for mode in ('work_equal', 'history_equal'):
        chosen = [output['comparisons'][k]['main']['fits'][mode] for k in ('delta1_A1', 'delta0_A1', 'delta1_status')]
        output['decisions'][mode] = dict(profile=decision(*(f.get('profile95') for f in chosen)),
            work_cluster=decision(*(f['work_cluster_bootstrap']['interval95'] for f in chosen)))
    return output


def serializable(x):
    if isinstance(x, float) and math.isinf(x):
        return '+Infinity' if x > 0 else '-Infinity'
    if isinstance(x, dict):
        return {k: serializable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [serializable(v) for v in x]
    return x


def markdown(report):
    number = lambda x: '不可识别' if x is None else ('+∞' if x == math.inf else '−∞' if x == -math.inf else f'{x:.4f}')
    interval = lambda xs: '不可识别' if xs is None else '[' + ', '.join(number(x) for x in xs) + ']'
    lines = ['# T1末行层：正确更新与错误翻转', '', '计算前登记提交：`'+PREREGISTERED_COMMIT+'`。', '',
             '## 结果与预登记判决', '']
    fd = report['comparisons']['delta1_A1']['main']
    xa = report['comparisons']['delta0_A1']['main']
    fs = report['comparisons']['delta1_status']['main']
    if all(c['fits']['work_equal']['status'] == 'positive_separation' for c in (fd, xa, fs)):
        lines += ['A1在这批既有历史上同时压低正确更新与错误翻转；状态格式也压低正确更新。三项条件比较均完全分离，只能给出正无穷点估计及单侧下界。两项A1区间都向上无界，按登记规则记相容，数据不能证明两种作用大小相等，也不能给控制器提供有限的正确更新损失参数范围。作品簇重抽退化，未能完成独立的稳健性确认。', '']
    for mode, label in [('work_equal', '作品等权主报'), ('history_equal', '历史等权并列')]:
        lines += ['### '+label, '', '|对比|条件对数优势差|剖面95%区间|作品簇重抽95%|历史簇重抽95%|有信息/全部历史|',
                  '|---|---:|---|---|---|---:|']
        for name, c in report['comparisons'].items():
            f, d = c['main']['fits'][mode], c['main']['descriptive']
            lines.append(f"|{name}（{c['arm0']}−{c['arm1']}）|{number(f['estimate'])}|{interval(f.get('profile95'))}|{interval(f['work_cluster_bootstrap']['interval95'])}|{interval(f.get('history_cluster_bootstrap', {}).get('interval95')) if 'history_cluster_bootstrap' in f else '簇数不少于8，不增算'}|{d['information_histories']}/{d['histories']}|")
        lines += ['', '剖面区间判决：'+report['decisions'][mode]['profile']['H1']+'；'+report['decisions'][mode]['profile']['H8']+'。',
                  '作品簇区间判决：'+report['decisions'][mode]['work_cluster']['H1']+'；'+report['decisions'][mode]['work_cluster']['H8']+'。', '']
    main_checks = report['decisions']['work_equal']['profile']['rule_checks']
    yn = lambda key: '满足' if main_checks[key] else '不满足'
    lines += ['### 对照1.3各项规则（作品等权剖面主判决）', '',
              '1. δ1上界低于δ0下界：'+yn('delta1_below_delta0')+'；反向不相交：'+yn('delta1_above_delta0')+'。',
              '2. 区间相交且正确更新差的下界大于0：'+yn('overlap_and_delta1_lower_positive')+'。满足也只按登记规则称相容，不证明平行移动。',
              '3. 正确更新差区间包含0且上界小于0.5：'+yn('delta1_contains_zero_upper_under_point5')+'。不把不显著当作无损。',
              '4. 状态格式差的下界大于0：'+yn('status_lower_positive')+'。',
              '5. 所有判决使用条件对数优势差；未用总体率之间的不等式。分离时点估计无穷、剖面列给单侧95%界；重抽退化无穷不作为精确区间。', '',
              '## 估计方法', '',
              '给定每历史两臂成功总数t，条件概率正比于C(n0,k)C(n1,t−k)exp(δk)，在可行k上归一。作品等权主报给每历史权重N/(作品数×本作品历史数)，历史等权并列给每历史权重1。总成功0或全部成功的历史不贡献条件似然，但均留在描述表中。', '',
              '有限估计以2倍对数似然差3.8414588给双侧95%剖面区间，完全分离以2.7055435给单侧95%界。各对比、各权重均作品簇重抽2000次；作品数少于8时再历史簇重抽2000次。重抽使用离散经验分位数，保留无穷；无信息重抽不伪造估计，另列计数。未为可复现增存随机种子或重抽样本。', '',
              '## 材料范围与分母', '',
              f"F-D为{report['integrity']['FD_histories']}段历史、base/A1共{report['integrity']['FD_base_A1']}条。5.5的156条均按来源历史和冻结历史内容校验，匹配{report['integrity']['status_matched_histories']}段、{report['integrity']['status_matched_answers']}条；不匹配{len(report['integrity']['status_unmatched'])}条。", '',
              f"X为{report['integrity']['X_histories']}段历史，S为{report['integrity']['X_baseline_answers']}条，S+A0与S+A1合计{report['integrity']['X_Q2_answers']}条，即720条独立回答；原1200/2880为包含其他候选和人物的提取视图计数，不能用作本分析回答分母。", '',
              '|对比|作品数|无成功历史|全部成功历史|其它无信息历史|臂0成功/总数|臂1成功/总数|臂0/1保留|', '|---|---:|---:|---:|---:|---|---|---|']
    for name, c in report['comparisons'].items():
        d = c['main']['descriptive']; a, b = d['arm0'], d['arm1']
        lines.append(f"|{name}|{d['works']}|{d['floor_histories']}|{d['ceiling_histories']}|{d['other_no_information']}|{a['k']}/{a['n']}|{b['k']}/{b['n']}|{a['reserved']}/{b['reserved']}|")
    lines += ['', '这里的完全分离发生在给定历史内成功总数后的条件支持上，不能只看总体上是否某臂零成功。各比较中，观测k0处于其条件支持上端点的有信息历史数如下：', '']
    for name, c in report['comparisons'].items():
        d = c['main']['descriptive']
        lines.append(f"- {name}：{d['informative_upper_endpoint']}/{d['information_histories']}；下端点{d['informative_lower_endpoint']}/{d['information_histories']}。")
    lines += ['', 'F-D中某些历史base尚非全成功，但对应A1或状态格式没有成功，使base的成功数仍位于该历史可行支持的上端点；因此总体两臂都有成功，条件似然仍可分离。X的A1则为全臂0成功，其33段有信息历史全部处于同一上端点。', '']
    lines += ['', '|对比|臂|作品等权率|历史等权率|原始合并率|', '|---|---|---:|---:|---:|']
    for name, c in report['comparisons'].items():
        for a in (0, 1):
            d = c['main']['descriptive']['arm'+str(a)]
            lines.append(f"|{name}|{c['arm'+str(a)]}|{d['work_equal_rate']:.4%}|{d['history_equal_rate']:.4%}|{d['pooled_rate']:.4%}|")
    lines += ['', '## 保留、解析失败与敏感性', '',
              f"保留项（RESERVED）共{len(report['reserved'])}条；保留/拒答和解析失败以既有解析器原因列在JSON中，不从正文猜测补齐。既有保存值与重读解析值差异{len(report['parser_value_differences'])}条。", '']
    for name, c in report['comparisons'].items():
        s = c['sensitivity']
        lines.append('- '+name+'：'+(s['reason'] if s.get('identical_to_main') else '已另列剔除RESERVED的两种加权估计与全部区间，见JSON。'))
    lines += ['', '## 重抽分母与限制', '', '|对比|权重|抽样簇|次数|可识别|无信息|正无穷|负无穷|', '|---|---|---|---:|---:|---:|---:|---:|']
    for name, c in report['comparisons'].items():
        for mode, f in c['main']['fits'].items():
            for key in ('work_cluster_bootstrap', 'history_cluster_bootstrap'):
                if key in f:
                    z = f[key]
                    mode_label = '作品等权' if mode == 'work_equal' else '历史等权'
                    cluster_label = '作品' if z['cluster'] == 'work' else '历史'
                    lines.append(f"|{name}|{mode_label}|{cluster_label}|{z['requested']}|{z['defined']}|{z['unidentified']}|{z['positive_infinite']}|{z['negative_infinite']}|")
    lines += ['', *['- '+v for v in report['notes']], '', '## 逐历史计数', '']
    for name, c in report['comparisons'].items():
        lines += ['### '+name, '', '|作品|历史|n0|k0|n1|k1|保留0|保留1|', '|---|---|---:|---:|---:|---:|---:|---:|']
        for r in c['main']['history_table']:
            hid = r['history_id'].replace('|', '/')
            lines.append(f"|{r['work_id']}|{hid}|{r['n0']}|{r['k0']}|{r['n1']}|{r['k1']}|{r['reserved0']}|{r['reserved1']}|")
        lines.append('')
    return '\n'.join(lines) + '\n'
