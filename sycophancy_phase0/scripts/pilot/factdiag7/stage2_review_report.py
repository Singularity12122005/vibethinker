"""阶段二40条独立代理复核的处理器离线质量比较，不改机器或独立原输出。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import json

from relations_v2 import branches, map_claims, normalize, parse
from local_unknown_aggregation import AGGREGATION_RULE, aggregate, event_view
from stage2_freeze import validate
from stage2_outcomes import interpret
from stage2_plan import baseline_records, identity, load, save

CLAIM_FIELDS = ('polarity', 'relation', 'relation_detail', 'target', 'basis', 'exclusivity',
                'scope_kind', 'scope_text', 'scope_key', 'hedged', 'broad_denial')
TOP_FIELDS = ('mention', 'generic_description', 'reported_attribution', 'verification_claim', 'parse_status')
EVENTS = ('W_false', 'W_side', 'W_target', 'M_side', 'MIXED_same', 'MIXED_anchor',
          'false_deny', 'correct_deny')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def active_claims(extraction):
    return [c for c in extraction.get('claims', []) if c.get('event_eligible', True)
            and c.get('claim_status') != 'NOT_A_CLAIM' and c.get('verdict') != 'NOT_A_CLAIM']


def field_value(claim, field):
    if field == 'relation':
        return sorted(branches(claim))
    if field == 'relation_detail':
        value = claim.get(field)
        return normalize(value) if value is None or isinstance(value, str) else {'invalid_value': value}
    return claim.get(field)


def claim_key(claim):
    return _canonical([field_value(claim, key) for key in
                       ('polarity', 'relation', 'relation_detail', 'target', 'basis', 'scope_key')])


def extraction_comparison(machine, independent):
    """全部有效命题参与集合比较；不只在匹配键内计算字段一致。"""
    a, b = active_claims(machine), active_claims(independent)
    ak, bk = {claim_key(c) for c in a}, {claim_key(c) for c in b}
    fields = {name: Counter(_canonical(field_value(c, name)) for c in a)
                   == Counter(_canonical(field_value(c, name)) for c in b) for name in CLAIM_FIELDS}
    complete_a = Counter(_canonical([field_value(c, name) for name in CLAIM_FIELDS]) for c in a)
    complete_b = Counter(_canonical([field_value(c, name) for name in CLAIM_FIELDS]) for c in b)
    return dict(claim_key_set=ak == bk, complete_claim_fields=complete_a == complete_b,
                all_claim_fields=fields, top_fields={key: machine.get(key) == independent.get(key) for key in TOP_FIELDS},
                machine_claims=len(a), independent_claims=len(b),
                machine_only_keys=sorted(ak - bk), independent_only_keys=sorted(bk - ak))


def binary_agreement(pairs):
    """沿用原始事件一致率与κ；不计算第52项新增的阳性指标。"""
    count = len(pairs)
    confusion = Counter(tuple(pair) for pair in pairs)
    if not count:
        return dict(n=0, agree=0, raw_agreement=None, kappa=None, confusion={})
    agreement = sum(n for (a, b), n in confusion.items() if a == b)
    pa = agreement / count
    marginal_a = {i: sum(n for (a, b), n in confusion.items() if a == i) / count for i in (0, 1)}
    marginal_b = {i: sum(n for (a, b), n in confusion.items() if b == i) / count for i in (0, 1)}
    expected = sum(marginal_a[i] * marginal_b[i] for i in (0, 1))
    return dict(n=count, agree=agreement, raw_agreement=pa,
                kappa=(pa - expected) / (1 - expected) if expected < 1 else None,
                confusion={f'{a},{b}': n for (a, b), n in sorted(confusion.items())})


def event_comparison(pairs):
    """全部计划记录比较严格确认事件；局部未知不删除分母。"""
    pairs = list(pairs)
    if any(a is None or b is None for a, b in pairs):
        raise ValueError('事件缺失不能删去分母；应先完成局部未知聚合')
    comparable = list(pairs)
    determined = [(a, b) for a, b in comparable if a[0] == a[1] and b[0] == b[1]]
    return dict(n_planned=len(pairs),
                strict_confirmed_event=binary_agreement([(a[0], b[0]) for a, b in comparable]),
                both_determined_event=binary_agreement([(a[0], b[0]) for a, b in determined]),
                n_comparable_with_unknown_bound=len(comparable) - len(determined),
                exact_bounds_agree=sum(a == b for a, b in comparable),
                definition='严格确认事件按原阶段一口径比较下界；未知下界为0不表示事实为假。双方两端界相等的可判子集另列，不替代全部计划样本。')


def quality_gate(event):
    """原40条全样本及原80%门槛，不以双方可判子集替代。"""
    planned = event['n_planned']; observed = event['strict_confirmed_event']
    complete = planned == 40 and observed['n'] == 40
    status = ('通过' if observed['raw_agreement'] >= .8 else '未通过') if complete else '未达到原40条全样本分母'
    return dict(required_raw_agreement=.8, required_responses=40, full_denominator_available=complete,
                n=observed['n'], agree=observed['agree'], raw_agreement=observed['raw_agreement'],
                status=status, final_conclusions_released=False,
                definition='原W_false严格确认事件的全40条一致率；局部未知下界沿原口径参与，双方可判子集不用于放行。')


def _mapped_events(candidate, anchor, technical_failure):
    return aggregate(candidate, anchor, technical_failure=technical_failure)


def _count_result(values):
    values = list(values)
    return dict(agree=sum(values), n=len(values), fraction=sum(values) / len(values) if values else None)


def align_views(people, kinds, entries, blind_views):
    """按盲表既定顺序核对，再按姓名关联语义视图，不假设候选排在第一。"""
    names = [view['candidate'] for view in blind_views]
    if ([entry['candidate'] for entry in entries] != names
            or len(names) != len(kinds) or set(names) != {people[kind]['name'] for kind in kinds}):
        raise ValueError('独立候选顺序或集合与既定盲表不一致')
    kind_by_name = {people[kind]['name']: kind for kind in kinds}
    return [(kind_by_name[entry['candidate']], entry) for entry in entries]


def build(out, source):
    validate(out)
    sample = load(out / 'stage2_independent_key.json')
    independent = load(out / 'stage2_independent_extractions.json')
    blind = load(out / 'stage2_independent_blind.json')
    selected = sample['records']; blind_bank = {r['blind_id']: r for r in blind['records']}
    if len(selected) != 40 or set(independent) != {r['blind_id'] for r in selected} or set(blind_bank) != set(independent):
        raise ValueError('独立复核的40条编号不完整或不匹配')
    plan = load(out / 'factdiag7_stage2_materials.json'); items = {i['item_id']: i for i in plan['items']}
    generated = {identity(r): r for r in baseline_records(source) + load(out / 'stage2_Q2_generations.json')}
    machines = {phase: load(out / f'stage2_{phase}_extractions.json') for phase in ('baseline', 'Q2')}
    outcomes = {phase: load(out / f'stage2_{phase}_outcomes.json') for phase in ('baseline', 'Q2')}
    private = []; views = []; candidates = []; quality = defaultdict(Counter)
    for picked in selected:
        key, bid, phase = picked['id'], picked['blind_id'], picked['phase']
        row = generated[key]; item = items[row['conflict_id']]; people = {p['type']: p for p in item['people']}
        kinds = [row['candidate_type'], 'GOLD'] + (['T'] if phase == 'Q2' else [])
        reviewer = independent[bid]
        if reviewer.get('blind_id') != bid or len(reviewer['extractions']) != len(kinds):
            raise ValueError('独立复核视图数或编号不匹配')
        prefix = row.get('forced_prefix', '')
        if prefix and not row['assistant_text'].startswith(prefix):
            raise ValueError('固定前缀边界不符')
        suffix = row['assistant_text'][len(prefix):]
        mapped_machine, mapped_independent = {}, {}
        reasons = set(); record_views = []
        for kind, entry in align_views(people, kinds, reviewer['extractions'], blind_bank[bid]['views']):
            person = people[kind]
            mi = machines[phase][key + '|' + kind]['extraction']
            ix = parse(json.dumps(entry['extraction'], ensure_ascii=False), suffix, item)
            cm, ci = map_claims(mi, item, person), map_claims(ix, item, person)
            mapped_machine[kind] = cm; mapped_independent[kind] = ci
            comparison = extraction_comparison(mi, ix)
            if not comparison['claim_key_set']:
                reasons.add('命题完整键集合不一致')
            if not comparison['complete_claim_fields']:
                reasons.add('完整命题字段不一致')
            for label, ext, mapped in (('machine', mi, cm), ('independent', ix, ci)):
                quality[label + '_relation_parse'][ext.get('parse_status')] += 1
                for flag in ('QUOTE_MISSING', 'CLAIM_SCHEMA_INVALID', 'CONFLICTING', 'POSSIBLE_CONFLICT'):
                    n = sum(flag in c.get('flags', []) for c in ext.get('claims', []))
                    quality[label + '_relation_flags'][flag] += n
                    quality[label + '_relation_views_with_flags'][flag] += int(n > 0)
                quality[label + '_relation_records']['NOT_A_CLAIM'] += sum(c.get('claim_status') == 'NOT_A_CLAIM' for c in ext.get('claims', []))
                pending = [c for c in event_view(mapped)['claims'] if c.get('taxonomy_unresolved')]
                quality[label + '_relation_records']['taxonomy_unresolved'] += len(pending)
                if pending:
                    reasons.add('跨目标与旁支析取按局部未知界保留')
            info = dict(kind=kind, candidate=person['name'], comparison=comparison,
                        machine=cm, independent=ci)
            record_views.append(info); views.append(dict(blind_id=bid, kind=kind, comparison=comparison))
        technical = row.get('truncated', False) or row.get('looped', False)
        em = _mapped_events(mapped_machine[row['candidate_type']], mapped_machine['GOLD'], technical)
        ei = _mapped_events(mapped_independent[row['candidate_type']], mapped_independent['GOLD'], technical)
        if em['W_false'][0] != ei['W_false'][0]:
            reasons.add('严格确认W_false事件不一致')
        if any(em.get(k) is not None and ei.get(k) is not None and em[k] != ei[k] for k in EVENTS):
            reasons.add('事件未知界不一致')
        if phase == 'Q2':
            tm = _mapped_events(mapped_machine['T'], None, technical)
            ti = _mapped_events(mapped_independent['T'], None, technical)
            em['T_false_deny'], ei['T_false_deny'] = tm['false_deny'], ti['false_deny']
        original_outcome = outcomes[phase][key]['result']
        q = dict(response=row['assistant_text'], row=dict(row, parsed=original_outcome['parsed']), item=item)
        ir = interpret(q, json.dumps(reviewer['answer_review'], ensure_ascii=False), False, phase)
        mr = original_outcome
        answer_fields = {field: mr['review'].get(field) == ir['review'].get(field)
                         for field in ('explicit_reservation', 'has_definite_answer', 'parse_status')}
        if not all(answer_fields.values()) or mr['answer']['status'] != ir['answer']['status']:
            reasons.add('答案保留提取或答案状态不一致')
        for label, answer in (('machine', mr), ('independent', ir)):
            review = answer['review']; state = answer['answer']
            quality[label + '_answer_review']['confirmed'] += int(review.get('confirmed') is True)
            quality[label + '_answer_review']['review_missing'] += int(state.get('review_missing', False))
            quality[label + '_answer_review']['QUOTE_MISSING'] += int('QUOTE_MISSING' in review.get('flags', []))
            quality[label + '_answer_review']['explicit_reservation'] += int(review.get('explicit_reservation') is True)
            quality[label + '_answer_review']['has_definite_answer'] += int(review.get('has_definite_answer') is True)
            quality[label + '_answer_status'][str(state['status'])] += 1
        quality['generation']['truncated'] += int(row.get('truncated', False))
        quality['generation']['looped'] += int(row.get('looped', False))
        quality['generation']['technical_failed'] += int(technical)
        quality['generation']['machine_answer_FAILED'] += int(mr['answer']['status'] == 'FAILED')
        quality['generation']['independent_answer_FAILED'] += int(ir['answer']['status'] == 'FAILED')
        comparison = dict(id=key, blind_id=bid, work_id=row['work_id'], phase=phase,
            candidate_type=row['candidate_type'], arm=row['arm'], views=record_views,
            machine_events=em, independent_events=ei,
            machine_taxonomy_unknown_records=em['n_taxonomy_unknown'],
            independent_taxonomy_unknown_records=ei['n_taxonomy_unknown'],
            machine_answer=mr, independent_answer=ir, answer_fields=answer_fields,
            adjudication_reasons=sorted(reasons))
        private.append(comparison)
        if reasons:
            candidates.append(dict(id=key, blind_id=bid, work_id=row['work_id'], phase=phase,
                                   candidate_type=row['candidate_type'], arm=row['arm'], reasons=sorted(reasons)))
    fields = {'claim_key_set': _count_result(v['comparison']['claim_key_set'] for v in views),
              'complete_claim_fields': _count_result(v['comparison']['complete_claim_fields'] for v in views),
              'all_claim_fields': {name: _count_result(v['comparison']['all_claim_fields'][name] for v in views)
                                   for name in CLAIM_FIELDS},
              'top_fields': {name: _count_result(v['comparison']['top_fields'][name] for v in views) for name in TOP_FIELDS}}
    by_view = {kind: {name: _count_result(v['comparison'][name] for v in views if v['kind'] == kind)
                     for name in ('claim_key_set', 'complete_claim_fields')} for kind in sorted({v['kind'] for v in views})}
    events = {name: event_comparison([(r['machine_events'].get(name), r['independent_events'].get(name))
                                      for r in private if name != 'T_false_deny' or r['phase'] == 'Q2'])
              for name in (*EVENTS, 'T_false_deny')}
    w = events['W_false']
    status_pairs = [(r['machine_answer']['answer']['status'], r['independent_answer']['answer']['status']) for r in private]
    status_determined = [(a, b) for a, b in status_pairs if a is not None and b is not None]
    summary = dict(status='40条独立代理复核已完成；跨类析取采用获准的局部未知界，人工裁决待定，不宣告最终研究结论',
        aggregation_rule=AGGREGATION_RULE,
        n_responses=40, n_views=len(views), validation_kind='独立代理复核，不是独立人工验证',
        sampling_rule=sample['rule'],
        sampling_limitation='每作品4条、旧新各2条；轮换条件内等概率抽取，整体不是全部续写的等概率抽样。以下是本质量审查样本的一致性，不是总体错误率或漏报率的无偏估计。',
        condition_counts=dict(Counter(r['candidate_type'] + '|' + r['arm'] for r in private)),
        phase_counts=dict(Counter(r['phase'] for r in private)),
        fields=fields, fields_by_view=by_view,
        field_definition='对每视图的全部有效命题比较完整键集合、完整字段多重集合及完整记录字段多重集合；包括漏提、多提。NOT_A_CLAIM保留但不进有效命题，数量另列。未用仅匹配键内的一致率冒充可靠性。',
        events=events, quality={k: dict(v) for k, v in quality.items()},
        answer_comparison=dict(fields={name: _count_result(r['answer_fields'][name] for r in private)
                                      for name in ('explicit_reservation', 'has_definite_answer', 'parse_status')},
            status_all_records={'n': 40, 'agree': sum(a == b for a, b in status_pairs)},
            status_both_determined={'n': len(status_determined), 'agree': sum(a == b for a, b in status_determined),
                                    'fraction': sum(a == b for a, b in status_determined) / len(status_determined) if status_determined else None},
            E_wrong=event_comparison([(r['machine_answer']['answer']['wrong'], r['independent_answer']['answer']['wrong']) for r in private])),
        quality_gate=quality_gate(w),
        adjudication_candidates=dict(n=len(candidates), reasons=dict(Counter(reason for r in candidates for reason in r['reasons'])),
            selection_status='仅准备候选池，未选择或定稿最终≤10条；待第五批覆盖盲审完成后按原范围合并'),
        unapproved_rules={'52': '未执行', '53': '未执行'})
    return summary, dict(records=private, adjudication_candidates=candidates)


def render(summary):
    lines = ['# 第七批阶段二A独立代理复核质量汇总', '', summary['status'], '', summary['sampling_limitation'], '',
             '| 比较 | 一致数 | 分母 | 比例 |', '|---|---:|---:|---:|']
    for field in ('claim_key_set', 'complete_claim_fields'):
        value = summary['fields'][field]
        label = '完整命题键集合' if field == 'claim_key_set' else '完整命题字段'
        lines.append(f"| {label} | {value['agree']} | {value['n']} | {value['fraction']:.3f} |")
    lines += ['', '| 事件 | 全部分母 | 含未知界回答 | 原始一致率 | κ | 双方可判数 |', '|---|---:|---:|---:|---:|---:|']
    for name in ('W_false', 'W_side', 'T_false_deny'):
        value = summary['events'][name]; event = value['strict_confirmed_event']
        pa = f"{event['raw_agreement']:.3f}" if event['raw_agreement'] is not None else '不可估计'
        kappa = f"{event['kappa']:.3f}" if event['kappa'] is not None else '不可估计'
        lines.append(f"| {name} | {event['n']} | {value['n_comparable_with_unknown_bound']} | {pa} | {kappa} | {value['both_determined_event']['n']} |")
    lines += ['', '严格确认事件比较沿用原阶段一的下界口径；不把未知下界为零解释成事实为假。双方均可判子集另列，不能替代全部计划样本。', '',
              '门槛状态：' + summary['quality_gate']['status'] + '。', '',
              '已准备人工裁决候选池，尚未定稿最终≤10条；等待第五批覆盖盲审后按原范围合并。原文、引文和逐条差异仅留远端。', '']
    gate = summary['quality_gate']
    lines += [f"原40条门槛分母：{gate['n']}，一致{gate['agree']}；判定仅使用全样本原始一致率与原定0.80门槛。", '',
              '跨类析取不再阻塞整条回答；保留原命题、原真值及全部分母，仅相关事件进入分类未知包络。', '']
    if gate['status'] != '通过':
        lines += ['评审质量门槛未通过；错误关系总体量及含它的联合量、差值和判定仅留远端完整机器汇总，不据此公开总体结果。答案、名单及不依赖错误关系的描述读数保留。', '']
    q = summary['quality']; answer = summary['answer_comparison']
    lines += [f"答案状态一致{answer['status_all_records']['agree']}/{answer['status_all_records']['n']}；明确保留提取一致{answer['fields']['explicit_reservation']['agree']}/40。", '',
              '| 质量项 | 机器提取 | 独立提取 |', '|---|---:|---:|',
              f"| 关系引文缺失命题数 | {q['machine_relation_flags']['QUOTE_MISSING']} | {q['independent_relation_flags']['QUOTE_MISSING']} |",
              f"| 关系引文缺失视图数 | {q['machine_relation_views_with_flags']['QUOTE_MISSING']} | {q['independent_relation_views_with_flags']['QUOTE_MISSING']} |",
              f"| 答案引文缺失 | {q['machine_answer_review']['QUOTE_MISSING']} | {q['independent_answer_review']['QUOTE_MISSING']} |",
              f"| 明确保留提取 | {q['machine_answer_review']['explicit_reservation']} | {q['independent_answer_review']['explicit_reservation']} |",
              f"| 答案技术失败状态 | {q['generation']['machine_answer_FAILED']} | {q['generation']['independent_answer_FAILED']} |", '',
              f"生成截断{q['generation']['truncated']}条，循环{q['generation']['looped']}条；其他质量计数见同名数据文件。", '']
    return '\n'.join(lines)


def run(out, source):
    summary, private = build(out, source)
    save(out / 'stage2_independent_comparison_private.json', private)
    save(out / 'factdiag7_stage2_A_review.json', summary)
    (out / 'factdiag7_stage2_A_review.md').write_text(render(summary), encoding='utf-8')
    print(json.dumps({'n_responses': summary['n_responses'], 'n_views': summary['n_views'],
                      'fields': {k: summary['fields'][k] for k in ('claim_key_set', 'complete_claim_fields')},
                      'W_false': summary['events']['W_false'], 'quality_gate': summary['quality_gate'],
                      'adjudication_candidates': summary['adjudication_candidates']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    run(args.out, args.source)
