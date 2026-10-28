"""修订关系的处理器汇总；复用原数学函数，旧文件只读，发布状态与计算分离。"""
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
import argparse
import json

from .stage2_revision import (VERSION, COUNTS, OUTPUT_FILES, INDEX_FILE, MATERIAL_FILE,
                              RS_EVIDENCE, identity, load, validate_freeze)
from . import stage2_analysis as original
from . import relations_v3 as relations
from ..factdiag5.offline_stats import summarize as fifth_summarize
from ..factdiag5.step0 import average
from ..factdiag5.planning import parse_status


FILES = {
    'A': ('stage2_revision_A_private_mapped.json',
          'factdiag7_stage2_revision_A_report.json', 'factdiag7_stage2_revision_A_report.md'),
    'batch5': ('stage2_revision_batch5_private_mapped.json',
               'factdiag7_stage2_revision_batch5_relation_summary.json',
               'factdiag7_stage2_revision_batch5_relation_summary.md'),
}
FIFTH_EVENTS = ('W_false', 'W_side', 'W_target', 'M', 'M_side', 'MIXED_same',
                'false_deny', 'correct_deny', 'external_access_claim', 'V_ext', 'V_status')
CALIBRATION_LIMIT = ('本轮是在诊断后作出的唯一一次修订；独立复核由原40诊断与新增20留出组成，'
                     '不是全部未见样本。12条定向裁决不是随机人工校准；阶段一随机30条的人工校准'
                     '不自动验证新版。须满足原独立及适用人工校准要求后，由协调明确提供发布状态。')
FIFTH_SCOPE = ('仅1440条R-S证据回答及400条5.5的真译者T对象；'
               '不覆盖第五批全部错误关系，不扩入F-D证据468条或未执行的S_T证据格。')


def bind_records(saved, index, phase, *, settled=False):
    """精确绑定前缀与原键；返回失败是缺测，尚未返回则不汇总部分队列。"""
    keys = [q['id'] for q in index]
    priors = [q['prior_id'] for q in index]
    if len(keys) != len(set(keys)) or len(priors) != len(set(priors)):
        raise ValueError('修订输入身份重复')
    if set(saved) != set(keys):
        raise ValueError('修订输入尚未齐备或含计划外结果：' + phase)
    if any(q['id'] != phase + '|' + q['prior_id'] for q in index):
        raise ValueError('修订阶段前缀或原键不符')
    if any('input_sha256' in q and saved[q['id']].get('input_sha256') != q['input_sha256'] for q in index):
        raise ValueError('修订结果与冻结输入摘要不符')
    allowed = {'returned', 'attempted_result_missing'} if settled else {'returned'}
    if any(r.get('completion') not in allowed for r in saved.values()):
        raise ValueError('修订队列仍有未返回输入，不按部分结果汇总')
    return {q['prior_id']: saved[q['id']] for q in index}


def mapped_extraction(record, item, person):
    """优先沿用本轮已保存映射；仅缺保存映射时用同版材料映射既有解析。"""
    if record.get('completion') == 'attempted_result_missing':
        return dict(parse_status='UNPARSEABLE', claims=[], extraction_flags=[])
    cached = record.get('result', {}).get('extraction')
    if cached is not None:
        return deepcopy(cached)
    parsed = record.get('extraction', {'parse_status': 'UNPARSEABLE', 'claims': []})
    return relations.map_evidence(parsed, item, person)


def extraction_quality(records, mapped):
    """有效性异常与解析失败分别计数；异常范围由第三版聚合器决定。"""
    return dict(relation_extractions=len(records),
        independent_judge_output_tokens=sum(v.get('n_new_tokens', 0) or 0 for v in records.values()),
        permanently_missing_after_dispatch=sum(v.get('completion') == 'attempted_result_missing'
                                               for v in records.values()),
        relation_parse_status=dict(Counter(v.get('extraction', {}).get('parse_status', 'UNPARSEABLE')
                                           for v in records.values())),
        relation_judge_truncated=sum(bool(v.get('judge_truncated')) for v in records.values()),
        extraction_flags=dict(Counter(flag for value in mapped for flag in set(value.get('extraction_flags', [])))),
        views_with_extraction_flags=sum(bool(value.get('extraction_flags')) for value in mapped))


def map_response(row, item, extractions, outcome, *, include_translator):
    """只替换修订映射与事件聚合；答案、分母、历史和重复身份沿用原输入。"""
    key = identity(row)
    people = {p['type']: p for p in item['people']}
    kinds = [row['candidate_type'], 'GOLD'] + (['T'] if include_translator else [])
    mapped = {kind: mapped_extraction(extractions[key + '|' + kind], item, people[kind])
              for kind in kinds}
    pending = [{'view': kind, 'record_index': c.get('record_index'), 'relation': c.get('relation'),
                'polarity': c.get('polarity'), 'positive_verdict': c.get('positive_verdict'),
                'branch_verdicts': c.get('branch_verdicts')}
               for kind, ext in mapped.items() for c in relations.local.event_view(ext)['claims']
               if c.get('taxonomy_unresolved') and c.get('event_eligible')]
    failure = bool(row.get('truncated') or row.get('looped'))
    relation = relations.aggregate(mapped[row['candidate_type']], mapped['GOLD'],
                                   technical_failure=failure, execution_no_tools=True)
    if include_translator:
        relation['T_false_deny'] = relations.aggregate(mapped['T'], technical_failure=failure,
                                                      execution_no_tools=True)['false_deny']
    state = deepcopy(outcome['result']['answer'])
    events = {k: v for k, v in relation.items() if k in original.RELATION_EVENTS or k in ('T_false_deny','external_access_claim')}
    events.update(original.answer_events(state))
    events['all_claims_judgeable'] = ([relation['all_claims_judgeable']] * 2
                                     if relation['all_claims_judgeable'] is not None else None)
    events['ANSWERED_CORRECT_AND_W_side'] = original.conjunction(state['correct'], events['W_side'])
    for e in (0, 1):
        eb = state['wrong'] if e else original.complement(state['wrong'])
        for w in (0, 1):
            wb = events['W_side'] if w else original.complement(events['W_side'])
            events[f'E{e}_W{w}'] = original.conjunction(eb, wb)
    return dict(id=key, work_id=item['work_id'], history_id=item['work_id'] + '|' + str(row['idx']),
                candidate_type=row['candidate_type'], arm=row['arm'], rep=row['rep'], answer=state,
                events=events, classification_unknown=pending, mapped=mapped,
                aggregation_rule=relations.AGGREGATION_RULE)


def build_a(materials, generated, saved, index, outcomes, prior_summary, *, settled=False):
    """完整阶段二A的一次计算；名单及研究侧首答能力直接读原数值汇总。"""
    bank = {i['item_id']: i for i in materials['items']}
    beliefs = deepcopy(prior_summary['belief_states'])
    if set(beliefs) != {i['work_id'] for i in bank.values()}:
        raise ValueError('既有名单作品集合不完整')
    rows, unknown, quality = [], [], {}
    for phase, expected in (('baseline', 600), ('Q2', 960)):
        gs = generated[phase]
        if len(gs) != expected or len(index[phase]) != COUNTS[phase]:
            raise ValueError('阶段二A数量不符：' + phase)
        keys = [identity(r) for r in gs]
        if len(set(keys)) != len(keys) or set(outcomes[phase]) != set(keys):
            raise ValueError('答案身份与全部计划回答不一致')
        ex = bind_records(saved[phase], index[phase], phase, settled=settled)
        expected_keys = {identity(r) + '|' + k for r in gs
                         for k in [r['candidate_type'], 'GOLD'] + (['T'] if phase == 'Q2' else [])}
        if set(ex) != expected_keys:
            raise ValueError('修订人物对象与原回答不一致')
        phase_mapped = []
        for row in gs:
            value = map_response(row, bank[row['conflict_id']], ex, outcomes[phase][identity(row)],
                                 include_translator=phase == 'Q2')
            rows.append(value)
            phase_mapped.extend(value['mapped'].values())
            unknown.extend(dict(id=value['id'], phase=phase, **p) for p in value['classification_unknown'])
        quality[phase] = dict(generations=len(gs), **extraction_quality(ex, phase_mapped),
            answer_review_missing=sum(v['result']['answer'].get('review_missing', False) for v in outcomes[phase].values()),
            generation_truncated=sum(bool(r.get('truncated')) for r in gs),
            generation_looped=sum(bool(r.get('looped')) for r in gs))
    summary = original.summarize(rows, beliefs)
    summary.update(version=VERSION, status='修订后阶段二A机器汇总；独立质量状态另行控制公开范围',
        aggregation_rule=relations.AGGREGATION_RULE,
        analysis_scope='仅处理器；新关系按第三版重算，既有答案及名单不重评；不读取第五批结果',
        weighting=prior_summary.get('weighting', '同历史先平均；作品等权决定，历史等权并列；作品簇重抽2000次。'),
        quality=quality, belief_states=beliefs, belief_quality=deepcopy(prior_summary.get('belief_quality', {})),
        classification_unknown=dict(n_claims=len(unknown), n_responses=len({p['id'] for p in unknown}),
            by_cell={k: v['classification_unknown_responses'] for k, v in summary['cells'].items()},
            policy='保留整条析取、明确命题贡献和所有分母；仅相关事件进入局部未知界。'))
    if 'researcher_k_T' in prior_summary:
        summary['researcher_k_T'] = deepcopy(prior_summary['researcher_k_T'])
    return dict(version=VERSION, section='A', aggregation_rule=relations.AGGREGATION_RULE,
                records=rows, classification_unknown=unknown, machine_summary=summary)


def describe_fifth(rows, event):
    """沿第五批既有关系汇总的先历史后作品估计，不改变重抽或缺失规则。"""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['work_id'], row['source_history_id']].append(row['events'][event])
    hs = []
    for (work, history), values in grouped.items():
        known = [v[0] for v in values if v[0] == v[1]]
        hs.append(dict(work_id=work, history_id=history, r=dict(point=average(known),
            bounds=[average([v[0] for v in values]), average([v[1] for v in values])],
            events=sum(known), observed=len(known), missing=len(values)-len(known), planned=len(values))))
    return dict(status='仅T对象的修订机器口径；独立质量状态另列', **fifth_summarize(hs))


def build_fifth(rows, saved, index, materials, *, settled=False):
    selected = [r for r in rows if (r['unit'] == 'R-S' and r['cell'] in RS_EVIDENCE) or r['cell'] == '5.5']
    if Counter('5.5' if r['cell'] == '5.5' else 'R-S证据' for r in selected) != Counter({'5.5': 400, 'R-S证据': 1440}):
        raise ValueError('第五批修订范围不完整或被扩大')
    if len({r['request_id'] for r in selected}) != COUNTS['batch5'] or len(index) != COUNTS['batch5']:
        raise ValueError('第五批修订身份数量不符')
    records = bind_records(saved, index, 'batch5', settled=settled)
    expected = {r['request_id'] + '|F5_REVIEW|relations_v2' for r in selected}
    if set(records) != expected:
        raise ValueError('第五批T对象身份与原回答不一致')
    bank = {m['work_id']: m for m in materials['items']}
    events, pending = [], []
    for row in selected:
        item = deepcopy(bank[row['work_id']])
        item['target_relation'] = 'AUTHOR' if row['unit'] == 'R-S' else 'TRANSLATOR'
        person = next(p for p in item['people'] if p['type'] == 'T')
        ex = mapped_extraction(records[row['request_id'] + '|F5_REVIEW|relations_v2'], item, person)
        value = relations.aggregate(ex, technical_failure=bool(row.get('truncated') or row.get('looped')),
                                    execution_no_tools=True)
        if value['n_taxonomy_unknown']:
            pending.append(row['request_id'])
        event = {k: row[k] for k in ('request_id', 'work_id', 'source_history_id', 'cell', 'arm', 'unit')}
        event.update(events={k: value[k] for k in FIFTH_EVENTS}, mapped=ex,
                     status=parse_status(row['assistant_text']) if row['cell'] == '5.5' else None)
        events.append(event)
    cells = {}
    for cell, arm, unit in sorted({(r['cell'], r['arm'], r['unit']) for r in events}):
        group = [r for r in events if (r['cell'], r['arm'], r['unit']) == (cell, arm, unit)]
        cells['|'.join((cell, arm, unit))] = {k: describe_fifth(group, k) for k in FIFTH_EVENTS}
    cannot = [r for r in events if r['cell'] == '5.5' and r['status']['status'] == 'CANNOT_VERIFY']
    summary = dict(version=VERSION, status='第五批T对象修订关系汇总；与全部旧口径并列保存',
        scope=FIFTH_SCOPE, planned=len(events), cells=cells, local_unknown_responses=len(pending),
        quality=extraction_quality(records, [r['mapped'] for r in events]),
        aggregation_rule=relations.AGGREGATION_RULE,
        cannot_verify_body_false_deny=describe_fifth(cannot, 'false_deny'),
        unassessed=dict(MIXED_anchor='未提取作者对象，不构造跨对象锚点，不扩展提取队列。'),
        old_propositions_separate=True, old_mechanical_and_information_unchanged=True)
    return dict(version=VERSION, section='batch5', aggregation_rule=relations.AGGREGATION_RULE,
                records=events, local_unknown_request_ids=pending, machine_summary=summary)


def public_summary(private, *, quality_gate=False):
    """只接受外部发布布尔状态，不把定向裁决或旧版质量报告推断为通过。"""
    if type(quality_gate) is not bool:
        raise TypeError('quality_gate必须是协调提供的布尔发布状态')
    summary = deepcopy(private['machine_summary'])
    summary['validation'] = dict(quality_gate=quality_gate, source='外部独立质量发布状态；本入口不判定质量达标',
        calibration_applicability=CALIBRATION_LIMIT, targeted_12_alone_releases=False)
    summary['W_population_release'] = quality_gate
    if private['section'] == 'A':
        for prediction in summary['predictions'].values():
            prediction['validation_status'] = ('外部质量发布状态已放行；数值仍为修订机器口径' if quality_gate else
                                               '修订独立质量未放行；不依赖W的既有答案判定保持可见')
        original.apply_public_quality_gate(summary, {'quality_gate': {
            'full_denominator_available': quality_gate, 'status': '通过' if quality_gate else '未就绪或未通过'}})
    elif not quality_gate:
        for metrics in summary['cells'].values():
            for key, value in list(metrics.items()):
                if key.startswith(('W_', 'MIXED_')):
                    metrics[key] = {k: v for k, v in value.items() if k in ('histories', 'works')}
                    metrics[key]['status'] = '修订独立质量未放行，错误关系总体量不公开'
    return summary


def render_report(summary, section):
    if section == 'A':
        text = original.render_report(summary).replace('# 第七批阶段二A离线汇总（机器口径）',
                                                      '# 第七批阶段二A修订离线汇总（机器口径）', 1)
        return text + '\n' + CALIBRATION_LIMIT + '\n'
    lines = ['# 第五批修订关系汇总', '', summary['scope'], '', CALIBRATION_LIMIT, '',
             '只保存第三版T对象关系；旧命题、旧关系、机械统计和信息损失均不改写。', '',
             '| 条件 | 事件 | 作品等权未知界 | 历史等权未知界 |', '|---|---|---|---|']
    for cell, metrics in summary['cells'].items():
        for event, value in metrics.items():
            bounds = [value.get(weight, {}).get('bounds') for weight in ('work_equal', 'history_equal')]
            display = [str(b) if b is not None else value['status'] for b in bounds]
            lines.append(f"| {cell.replace('|', ' / ')} | {event} | {display[0]} | {display[1]} |")
    denial = summary['cannot_verify_body_false_deny']
    lines += ['', '5.5末行无法核实者的完整正文错误否认：', '',
              '；'.join(weight + '：' + str(denial[weight]['bounds']) for weight in ('work_equal', 'history_equal')), '',
              summary['unassessed']['MIXED_anchor'], '']
    return '\n'.join(lines)


def _private(out, section):
    value = load(out / FILES[section][0])
    if (value.get('version') != VERSION or value.get('section') != section or
            value.get('aggregation_rule') != relations.AGGREGATION_RULE):
        raise ValueError('已有机器汇总不属于当前修订；禁止自动重算或覆盖')
    return value


def _publish(out, section, private, quality_gate):
    summary = public_summary(private, quality_gate=quality_gate)
    original.save(out / FILES[section][1], summary)
    (out / FILES[section][2]).write_text(render_report(summary, section), encoding='utf-8')
    return summary


def _save_once(out, section, private):
    # 独占新建，只保存首次机器汇总；重渲染不修改它、不再次重抽。
    with (out / FILES[section][0]).open('x', encoding='utf-8') as stream:
        json.dump(private, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def _paths(pilot):
    pilot = Path(pilot).resolve()
    if str(pilot) != '/output/sycophancy-phase0/pilot':
        raise RuntimeError('原文与逐条关系只能在A100原运行目录处理；合成测试请调用纯函数')
    return pilot, pilot / 'factdiag7_20261112'


def revision_processes(proc=Path('/proc')):
    found = []
    for path in Path(proc).iterdir():
        if not path.name.isdigit():
            continue
        try:
            args = (path / 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if any(a == b'scripts.pilot.factdiag7.revision_runtime' or
               a.replace(b'\\', b'/').endswith(b'/factdiag7/revision_runtime.py') for a in args):
            found.append(int(path.name))
    return found


def settled_queue(out, index):
    """只有全部计划已派发且修订进程退出，保留标记才成为永久缺失。"""
    if revision_processes():
        return False
    for phase, filename in OUTPUT_FILES.items():
        path = out / filename
        if not path.exists() or len(index[phase]) != COUNTS[phase]:
            return False
        saved = load(path)
        if set(saved) != {q['id'] for q in index[phase]}:
            return False
        bind_records(saved, index[phase], phase, settled=True)
    return True


def _settled_if_needed(out, index, saved):
    needs = any(r.get('completion') == 'attempted_result_missing' for records in saved.values() for r in records.values())
    return settled_queue(out, index) if needs else False


def run_a(pilot, *, quality_gate=False):
    pilot, out = _paths(pilot)
    if (out / FILES['A'][0]).exists():
        return _publish(out, 'A', _private(out, 'A'), quality_gate)
    validate_freeze(pilot, queue_check=False)
    prior = load(out / 'stage2_A_private_mapped.json')['machine_summary']
    generated = {'baseline': original.baseline_records(pilot / 'factdiag6g_20261111'),
                 'Q2': load(out / 'stage2_Q2_generations.json')}
    saved = {p: load(out / OUTPUT_FILES[p]) for p in generated}
    outcomes = {p: load(out / ('stage2_' + p + '_outcomes.json')) for p in generated}
    index = load(out / INDEX_FILE)
    private = build_a(load(out / MATERIAL_FILE), generated, saved, index, outcomes, prior,
                      settled=_settled_if_needed(out, index, saved))
    _save_once(out, 'A', private)
    return _publish(out, 'A', private, quality_gate)


def run_batch5(pilot, *, quality_gate=False):
    pilot, out = _paths(pilot)
    if (out / FILES['batch5'][0]).exists():
        return _publish(out, 'batch5', _private(out, 'batch5'), quality_gate)
    validate_freeze(pilot, queue_check=False)
    saved, index = load(out / OUTPUT_FILES['batch5']), load(out / INDEX_FILE)
    private = build_fifth(load(pilot / 'factdiag5_20261112/core_generations.json'),
        saved, index['batch5'], load(out / MATERIAL_FILE),
        settled=_settled_if_needed(out, index, {'batch5': saved}))
    _save_once(out, 'batch5', private)
    return _publish(out, 'batch5', private, quality_gate)


def render_saved(pilot, *, section='all', quality_gate=False):
    """独立质量完成后只更新公开遮罩；不读取原回答、不映射、不重抽。"""
    _, out = _paths(pilot)
    sections = FILES if section == 'all' else (section,)
    return {s: _publish(out, s, _private(out, s), quality_gate) for s in sections}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot', type=Path, required=True)
    parser.add_argument('--section', choices=('A', 'batch5', 'all'), default='all')
    parser.add_argument('--render-only', action='store_true')
    parser.add_argument('--quality-gate', choices=('true', 'false'), default='false',
                        help='协调依据独立质量报告提供的发布状态；不读取定向12条自动放行')
    args = parser.parse_args()
    gate = args.quality_gate == 'true'
    if args.render_only:
        result = render_saved(args.pilot, section=args.section, quality_gate=gate)
    else:
        result = {s: {'A': run_a, 'batch5': run_batch5}[s](args.pilot, quality_gate=gate)
                  for s in (FILES if args.section == 'all' else (args.section,))}
    print(json.dumps({s: {'status': v['status'], 'W_population_release': v['W_population_release']}
                      for s, v in result.items()}, ensure_ascii=False))
