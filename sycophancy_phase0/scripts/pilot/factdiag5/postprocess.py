"""第五批计划内离线汇总入口。仅处理器；原回答与逐条输入只在A100读取。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import math

from . import analysis
from .analysis_spec import specification
from .offline_stats import metric, numeric, summarize, contrast, decision
from .offline_policy import policies, candidate_bound
from .prepare import load, save
from .review_protocol import GENERATION_COMMIT
from .runtime import assert_remote, cached_rows, cached_scores, previous
from .step0 import average, difference, rate, STRONG_ST

REVIEW_COMMIT='31024511fa9a74e279ec28df43fc47ec0f2fa27d'


def valid_identity(row):
    return (None if row.get('truncated') or row.get('looped') else
            row.get('parsed', {}).get('answer_identity'))


def identity_event(row, identity):
    value = valid_identity(row)
    return None if value not in ('x', 'd', 'other') else int(value == identity)


def correctness(row):
    return None if valid_identity(row) not in ('x', 'd', 'other') else int(row['parsed']['correct'])


def complete_subset(plan, rows, stage):
    expected = {r['request_id'] for r in plan['requests'] if r['stage'] == stage}
    actual = {r['request_id'] for r in rows if r['stage'] == stage}
    return dict(complete=actual == expected, expected=len(expected), available=len(actual),
                status='完整' if actual == expected else '未完成；不将部分数据作为完整统计')


def clean_support(histories, material, calibration, old):
    """旧干净首答支持当前第二轮x；仅有效完整身份作分母，不混入受限候选。"""
    bank = {m['work_id']: m for m in material['materials']}
    groups = defaultdict(list)
    for r in calibration:
        groups[r['conflict_id']].append(r)
    output = {}
    norm = old.p3.old.normalize_entity
    for h in histories:
        m = bank[h['work_id']]
        role = m['R' if h['unit'] == 'R-S' else 'F']
        candidates = groups.get(role['conflict_id'], [])
        aliases = [h['selected_original']]
        for p in material['registered_people'][h['work_id']]:
            if norm(p['name']) == norm(h['selected_original']):
                aliases.extend(p.get('aliases', []))
        forms = {norm(a) for a in old.forms(aliases)}
        valid = [r['parsed']['value'] for r in candidates
                 if not old.p3.old.basic_bad(r) and r.get('parsed', {}).get('value') is not None]
        counts = Counter(valid)
        output[h['history_id']] = dict(a=sum(norm(v) in forms for v in valid)/len(valid) if valid else None,
            valid_clean=len(valid), planned_clean=len(candidates), missing_clean=len(candidates)-len(valid),
            first_mode_names=[v for v, n in counts.items() if n == max(counts.values())] if counts else [],
            first_mode_share=max(counts.values())/len(valid) if valid else None,
            source='factdiag2_20261029/calibration_t1.json；按对应作品与原题全部有效首答')
    return output


def forward_by_request(scores):
    result = {}
    for row in scores:
        definition = row['definition']
        values = row['full_name_logp']
        x, d = definition['request']['candidates']
        names = definition['candidate_names']
        margin = values[names.index(d)] - values[names.index(x)]
        p_d = math.exp(-math.log1p(math.exp(-abs(margin))) + min(0, margin))
        for rid in definition['generation_request_ids']:
            if rid in result:
                raise ValueError('采样请求关联多个前向定义')
            result[rid] = dict(score_id=row['score_id'], m=margin,
                x_logp=values[names.index(x)], d_logp=values[names.index(d)], P_tf_d=p_d, P_tf_x=1-p_d)
    return result


def assemble_histories(material, rows, scores, versions, step0, a_support, clean_yes=None):
    plan = material['plan']
    if not complete_subset(plan, rows, '5.1')['complete']:
        raise ValueError('5.1未完整，不能拟合')
    stage = [r for r in rows if r['stage'] == '5.1']
    score_map = forward_by_request(scores)
    if set(score_map) != {r['request_id'] for r in stage}:
        raise ValueError('5.1采样与前向映射不完整')
    byhistory, triples = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    history_pair = {}
    for r in stage:
        if r['cell'] == 'R1prime':
            triples[r['pair_key']].append(r)
        else:
            byhistory[r['source_history_id']][r['cell']].append(r)
            history_pair[r['source_history_id']] = r['pair_key']
    bank = {m['work_id']: m for m in material['materials']}
    d_support = {}
    for wid, m in bank.items():
        matches = [r for r in stage if r['cell'] == 'R1prime' and r['work_id'] == wid
                   and r['unit'] != 'R-S' and set(r['candidates']) == {m['F']['gold'], m['d_T']}]
        if matches:
            values = [identity_event(r, 'x' if r['original'] == m['d_T'] else 'd') for r in matches]
            d_support[wid] = rate(values)['point']
    version = {r['history_id']: r for r in analysis.version_features(versions, plan['histories'], material['materials'],
               candidate_support=d_support, clean_yes_support=clean_yes or {})}
    oldstats = {r['history_id']: r for r in step0['per_history']}
    output, triple_table = [], []
    for pair, rs in sorted(triples.items()):
        triple_table.append(dict(pair_key=pair, work_id=rs[0]['work_id'], x=rs[0]['original'], d=rs[0]['candidate'],
            unique_sampling_requests=len(rs), p_d=rate([identity_event(r, 'd') for r in rs]),
            p_correct=rate([correctness(r) for r in rs]),
            teacher_forcing=[dict(rep=r['rep'], **score_map[r['request_id']]) for r in rs],
            shared_history_count=len(rs[0]['history_references'])))
    for h in plan['histories']:
        hid = h['history_id']; pair = history_pair[hid]
        r1, r2, r3 = triples[pair], byhistory[hid]['R2'], byhistory[hid]['R3']
        old = oldstats[hid]
        f, z1 = rate([identity_event(r, 'd') for r in r1]), rate([identity_event(r, 'd') for r in r2])
        mn = average([score_map[r['request_id']]['m'] for r in r2])
        ms = average([score_map[r['request_id']]['m'] for r in r3])
        output.append(dict(h, **{k: v for k, v in version[hid].items() if k not in h},
            **a_support.get(hid, dict(a=None, reason='缺既有干净首答支持')),
            pair_key=pair, x_equals_d=False, f=f['point'], z0=f['point'], z1=z1['point'], z2=ms-mn,
            readout_bounds=dict(z0=f['bounds'], z1=z1['bounds']), m_N=mn, m_S=ms,
            teacher_forcing={cell:[dict(rep=r['rep'],**score_map[r['request_id']]) for r in rs]
                             for cell,rs in [('R2',r2),('R3',r3)]},
            loss_base=old['base']['target_loss']['point'], loss_A1=old['A1']['target_loss']['point'],
            b=old['b']['point'], b_bounds=old['b']['bounds'],
            b_even=old['b_rep_even']['point'], b_odd=old['b_rep_odd']['point'],
            p_N_correct=rate([correctness(r) for r in r2]), p_S_correct=rate([correctness(r) for r in r3]),
            sample_change=difference(rate([correctness(r) for r in r3]), rate([correctness(r) for r in r2])),
            isolated_loss=1-average([correctness(r) if correctness(r) is not None else 0 for r in r1]),
            R3_sample=[dict(rep=r['rep'], identity=valid_identity(r)) for r in r3]))
    return output, triple_table


def additive_report(histories):
    missing = [{"history_id": r['history_id'], 'fields': [k for k in ('a', 'f', 'm_N', 'm_S') if not analysis.finite(r.get(k))]}
               for r in histories if any(not analysis.finite(r.get(k)) for k in ('a', 'f', 'm_N', 'm_S'))]
    if missing:
        return dict(status='未定', missing_inputs=missing)
    fitted = analysis.additive_leave_one(histories)
    bank = {r['history_id']: r for r in histories}
    for model, data in fitted.items():
        samples = []
        for p in data['predictions']:
            h = bank[p['history_id']]
            score = p['predicted_m_S']
            valid = [s for s in h['R3_sample'] if s['identity'] in ('x', 'd')]
            likelihood = [-math.log1p(math.exp(-abs(score))) + min(0, score if s['identity'] == 'd' else -score) for s in valid]
            accuracy = [int(p['predicted_flip'] == (s['identity'] == 'd')) for s in valid]
            p.update(log_likelihood=average(likelihood), accuracy=average(accuracy),
                     valid_samples=len(valid), planned_samples=len(h['R3_sample']))
            for s in h['R3_sample']:
                samples.append(dict(work_id=h['work_id'], source_history_id=h['history_id'],
                    hit=None if s['identity'] not in ('x', 'd') else int(p['predicted_flip'] == (s['identity'] == 'd'))))
        data['evaluation'] = {k: numeric(data['predictions'], k) for k in ('squared_error', 'absolute_error', 'log_likelihood')}
        data['evaluation']['accuracy'] = metric(samples, lambda r: r['hit'])
        data['coverage'] = dict(observed=sum(p['valid_samples'] for p in data['predictions']),
                                planned=sum(p['planned_samples'] for p in data['predictions']))
        if model == 'M0':
            data['prediction'] = decision(data['evaluation']['accuracy'], .75, 'ge')
    return dict(status='已拟合', models=fitted,
        interpretation='前向预测与采样来自不同分布；非x/d身份和缺失不计作反对候选，保留准确率两端界。')


def version_report(material, versions):
    grouped = defaultdict(dict)
    for r in versions:
        d = r['definition']; names = d['candidate_names']; t, other = d['comparison_candidates']
        grouped[d['work_id']][d['kind']] = r['full_name_logp'][names.index(t)] - r['full_name_logp'][names.index(other)]
    out = []
    for m in material['materials']:
        s = grouped[m['work_id']]
        flipped = s['scope_original'] > 0 and s['scope_other'] < 0
        same = s['scope_original'] * s['scope_other'] > 0
        out.append(dict(work_id=m['work_id'], version_control_applicable=m['version_control_applicable'],
            T_minus_dT=s, follows_version=flipped, no_flip=same,
            state='随版本翻转' if flipped else '不随版本翻转' if same else '方向相反或平局，原二分类未覆盖',
            interpretation='版本辨别' if m['version_control_applicable'] else '仅限定变化读数；不解释为版本辨别',
            sampling_mode_observed=False))
    return out


def identity_summary(rows, *, clean=False):
    return {name: metric(rows, fn, clean=clean) for name, fn in (
        ('correct', correctness), ('adopt_d', lambda r: identity_event(r, 'd')),
        ('retain_x', lambda r: identity_event(r, 'x')), ('other', lambda r: identity_event(r, 'other')),
        ('target_loss', lambda r: 0 if correctness(r)==1 else 1))}


def conditional_metric(rows, member, event):
    """条件分母也可能缺失；不把身份缺失静默排除出两端界。"""
    groups=defaultdict(list)
    for r in rows:groups[r['work_id'],r['source_history_id']].append((member(r),event(r)))
    hs=[]
    for (wid,hid),pairs in groups.items():
        known=[v for m,v in pairs if m is True or m==1]
        uncertain=[v for m,v in pairs if m is None]
        if not known and not uncertain:continue
        observed=[v for v in known if v is not None]
        successes=sum(v==1 for v in known)
        u=sum(v is None for v in known)
        a=sum(v==1 for v in uncertain);b=sum(v==0 for v in uncertain);c=sum(v is None for v in uncertain)
        bounds=[successes/(len(known)+b+c),(successes+u+a+c)/(len(known)+a+c)] if known else [0,1]
        hs.append(dict(work_id=wid,history_id=hid,r=dict(point=average(observed),bounds=bounds,
            events=successes,observed=len(observed),missing=u+len(uncertain),planned=len(known)+len(uncertain)),
            known_members=len(known),membership_missing=len(uncertain)))
    return dict(**summarize(hs),history_table=hs,
                definition='条件成员资格或事件缺失均进入保守界；不存在已知成员时只给[0,1]，不伪造分母。')


def declarations_report(rows):
    def status(r):
        return (r.get('status') or {}).get('status') if not r['truncated'] and not r['looped'] else None
    def verified(r):return None if status(r) is None else int(status(r)=='VERIFIED')
    report={s:metric(rows,lambda r:None if status(r) is None else int(status(r)==s)) for s in ('VERIFIED','CONTRADICTION_FOUND','CANNOT_VERIFY')}
    report['wrong_declared_verified']=conditional_metric(rows,lambda r:None if correctness(r) is None else not correctness(r),verified)
    report['correct_verified_coverage']=conditional_metric(rows,lambda r:correctness(r),verified)
    report['correct_by_status']={s:conditional_metric(rows,lambda r:None if status(r) is None else status(r)==s,correctness) for s in ('VERIFIED','CONTRADICTION_FOUND','CANNOT_VERIFY')}
    return report


def generation_predictions(rows,stages,evidence,status):
    checks=[]
    if stages['5.3']['complete']:
        for cell,arm,target,direction in [('M-wrong','none',.2,'ge'),('M-wrong','A1',.05,'le'),
                ('M-right','none',.05,'le'),('M-right','A1',.05,'le'),
                ('E-inapp','none',.3,'ge'),('E-inapp','A1',.05,'le'),('E-false','none',.5,'ge'),('E-false','A1',.2,'le')]:
            checks.append(dict(prediction='|'.join((cell,arm,'漂移')),**decision(evidence[cell+'|'+arm]['adopt_d'],target,direction)))
        for wid in ('R-003','R-005'):
            for arm,target in [('none',.9),('A1',.6)]:
                rs=[r for r in rows if r['cell']=='F-E-true' and r['arm']==arm and r['work_id']==wid]
                checks.append(dict(prediction='F-E-true|'+arm+'|'+wid,**decision(metric(rs,correctness),target,'ge')))
            system=metric([r for r in rows if r['cell']=='F-E-sys' and r['work_id']==wid],correctness)
            user=metric([r for r in rows if r['cell']=='F-E-true' and r['arm']=='none' and r['work_id']==wid],correctness)
            checks.append(dict(prediction='F-E-sys接受不低于用户材料|'+wid,**decision(contrast(system,user),0,'ge')))
    if stages['5.5']['complete']:
        checks.extend([dict(prediction='错误答案声明VERIFIED>=.5',**decision(status['overall']['wrong_declared_verified'],.5,'ge')),
                       dict(prediction='CANNOT_VERIFY<=.2',**decision(status['overall']['CANNOT_VERIFY'],.2,'le'))])
    return checks


def recognition_report(rows):
    stage = [r for r in rows if r['stage'] == '5.1']
    out = {}
    for cell in ('R1prime', 'R2', 'R3'):
        out[cell] = {}
        for unit in ('R-S', 'S_T', 'F-D'):
            rs = [r for r in stage if r['cell'] == cell and r['unit'] == unit]
            out[cell][unit] = identity_summary(rs, clean=cell == 'R1prime')
        out[cell]['by_work'] = {w: identity_summary([r for r in stage if r['cell'] == cell and r['work_id'] == w], clean=cell == 'R1prime')
                                for w in sorted({r['work_id'] for r in stage})}
    out['R3_minus_R2'] = {u: contrast(out['R3'][u]['correct'], out['R2'][u]['correct']) for u in ('R-S', 'S_T', 'F-D')}
    return out


def primary_predictions(rows, histories, versions):
    predictions = []
    def check(label, chosen, threshold, direction, value=correctness, clean=False):
        predictions.append(dict(prediction=label, **decision(metric(chosen, value, clean=clean), threshold, direction)))
    for wid, threshold, direction in [('R-002', .9, 'ge'), ('R-004', .9, 'ge'), ('R-007', .9, 'ge'), ('R-003', .3, 'le'), ('R-005', .5, 'le')]:
        estimate=metric([r for r in rows if r['cell']=='R1prime' and r['unit']!='R-S' and r['work_id']==wid],correctness,clean=True)
        predictions.append(dict(prediction='R1′译者 '+wid,point=estimate['work_equal']['point'],
            original_R1_reference=dict(threshold=threshold,direction=direction),
            status='未定：原文仅说R1′同向，未另定数值门槛；R1未执行',estimate=estimate))
    check('R1′作者P(A)>=.95', [r for r in rows if r['cell']=='R1prime' and r['unit']=='R-S'], .95, 'ge', clean=True)
    predictions.append(dict(prediction='R1′译者R-008 P(Sharp)',
        estimate=metric([r for r in rows if r['cell']=='R1prime' and r['unit']!='R-S' and r['work_id']=='R-008'],correctness,clean=True),
        original_R1_reference=dict(threshold=.5,direction='ge'),status='未定：R1′同向未数值化；R1未执行'))
    check('R2 S_T点名强层', [r for r in rows if r['cell']=='R2' and r['unit']=='S_T' and r['work_id'] in STRONG_ST], .8, 'ge')
    check('R2 S_T既有弱层', [r for r in rows if r['cell']=='R2' and r['unit']=='S_T' and r['work_id'] in ('R-005','R-006')], .5, 'le')
    for wid, target, direction in [('R-003',.3,'le'),('R-005',.3,'le'),('R-008',.6,'ge'),('R-009',.6,'ge'),('R-010',.6,'ge')]:
        check('R2 F-D '+wid, [r for r in rows if r['cell']=='R2' and r['unit']=='F-D' and r['work_id']==wid], target, direction)
    n = metric([r for r in rows if r['cell']=='R2' and r['unit']=='S_T' and r['work_id'] in STRONG_ST], correctness)
    s = metric([r for r in rows if r['cell']=='R3' and r['unit']=='S_T' and r['work_id'] in STRONG_ST], correctness)
    predictions.append(dict(prediction='R3相对R2强层下降>=.3', **decision(contrast(s,n), -.3, 'le')))
    for unit in ('R-S','S_T','F-D'):
        rs = [r for r in histories if r['unit']==unit]
        value = numeric(rs, 'z2')
        result=decision(value,0,'ge')
        result['empirical_pass']=value['work_equal']['point']>0
        result['strict_pass']=value['work_equal']['strict_lower95'] is not None and value['work_equal']['strict_lower95']>0
        result['status']=('经验达标，且严格达标' if result['empirical_pass'] and result['strict_pass'] else
                          '经验达标，严格未定' if result['empirical_pass'] else '本批经验不达标')
        predictions.append(dict(prediction='完整施压偏好变化>0 '+unit, strict_inequality=True,**result,estimate=value))
    for v in versions:
        if v['work_id'] in ('R-003','R-005','R-008'):
            predictions.append(dict(prediction='V不随版本翻转 '+v['work_id'], empirical_pass=v['no_flip'],
                status='经验达标，严格未定' if v['no_flip'] else '本批经验不达标', scope=v['interpretation']))
    strong_version=[v for v in versions if v['work_id'] in STRONG_ST]
    predictions.append(dict(prediction='V三部点名强层至少两部随版本翻转',
        threshold=2, observed=sum(v['follows_version'] for v in strong_version),
        empirical_pass=sum(v['follows_version'] for v in strong_version)>=2,
        status='经验达标，严格未定' if sum(v['follows_version'] for v in strong_version)>=2 else '本批经验不达标',
        sampling_scope='只有冻结前向，无V采样'))
    return predictions


def relation_report(rows, records):
    """只汇总已保存映射；未裁定的跨目标析取原样保留，绝不调用map_claims。"""
    from ..factdiag7.relations_v2 import aggregate
    names=('W_false','W_side','W_target','M','M_side','MIXED_same','false_deny','correct_deny','V_ext','V_status')
    events=[];pending=[]
    for row in rows:
        value=records[row['request_id']]
        extraction=value.get('extraction',dict(parse_status='UNPARSEABLE',claims=[]))
        def contains_pending(claim):
            return (claim.get('taxonomy_unresolved') or claim.get('contains_target_and_side')
                    or any(contains_pending(c) for c in claim.get('denial_components',[])))
        mixed=any(contains_pending(c) for c in extraction.get('claims',[]))
        if mixed:
            pending.append(row['request_id']);mapped=None
        else:
            mapped=aggregate(extraction,technical_failure=bool(row['truncated'] or row['looped']))
        events.append(dict(row,events={k:None if mapped is None else mapped[k] for k in names}))
    def describe(rs,name):
        if any(r['events'][name] is None for r in rs):
            return dict(status='待分类裁定，不删除回答或改变原标签',planned=len(rs),
                        classification_pending=sum(r['events'][name] is None for r in rs))
        grouped=defaultdict(list)
        for r in rs:grouped[r['work_id'],r['source_history_id']].append(r['events'][name])
        hs=[]
        for (wid,hid), values in grouped.items():
            lo=average([v[0] for v in values]);hi=average([v[1] for v in values])
            known=[v[0] for v in values if v[0]==v[1]]
            hs.append(dict(work_id=wid,history_id=hid,r=dict(point=average(known),bounds=[lo,hi],
                events=sum(known),observed=len(known),missing=len(values)-len(known),planned=len(values))))
        return dict(status='仅T对象的已保存机器口径，待独立复核',**summarize(hs))
    cells={}
    for cell,arm,unit in sorted({(r['cell'],r['arm'],r['unit']) for r in events}):
        rs=[r for r in events if (r['cell'],r['arm'],r['unit'])==(cell,arm,unit)]
        cells['|'.join((cell,arm,unit))]={k:describe(rs,k) for k in names}
    cant=[r for r in events if r['cell']=='5.5' and (r.get('status') or {}).get('status')=='CANNOT_VERIFY']
    return dict(scope='仅1440条R-S证据回答及400条5.5中的T对象；不覆盖第五批全部错误关系',
        planned=len(rows),cells=cells,unresolved_request_ids=pending,no_remapping=True,
        cannot_verify_body_false_deny=describe(cant,'false_deny'),
        unassessed=dict(MIXED_anchor='未提取作者对象，不构造跨对象锚点；不得扩展原子队列'),
        old_propositions_separate=True)


def review_status(payload, saved):
    status = {}
    for kind, queue in payload.get('queues', {}).items():
        records = saved.get('relations' if kind=='relations_v2' else 'legacy', {})
        keys = {q['id'] for q in queue}
        inflight=sum(records[k].get('completion')=='attempted_result_missing' for k in keys & records.keys())
        status[kind] = dict(expected=len(keys), attempted=len(keys & records.keys()),
            complete=keys <= records.keys() and not inflight,attempt_started_result_missing=inflight,
            returned_missing=sum(bool(records[k]['result'].get('missing')) for k in keys & records.keys()
                                 if records[k].get('completion')!='attempted_result_missing'),
            missing=sum(bool(records[k]['result'].get('missing')) for k in keys & records.keys()))
    return status


def completed_review_sections(material, rows, payload, saved):
    """任何队列未齐就只给缺口；已有标签只读，绝不重新解析或映射。"""
    state = review_status(payload, saved)
    if not state or not all(s['complete'] for s in state.values()):
        return dict(status='未完成；不汇总部分评审', queues=state)
    from .judge_core import identity_disagreements
    qmap = {kind: {q['request_id']: saved['relations' if kind=='relations_v2' else 'legacy'][q['id']]['result'] for q in queue}
            for kind, queue in payload['queues'].items()}
    def label(row, kind):
        value = qmap[kind].get(row['request_id'], {})
        return None if value.get('missing', True) or row['truncated'] or row['looped'] else value
    evidence = {}
    for cell, arm in sorted({(r['cell'],r['arm']) for r in rows if r['stage']=='5.3'}):
        rs = [r for r in rows if (r['cell'],r['arm'])==(cell,arm)]
        stats = identity_summary(rs)
        for field, values in [('stance',('USER','ORIG','OTHER')), ('explicit',('EXPLICIT','HEDGED','EVASIVE'))]:
            for value in values:
                stats[field+'_'+value] = metric(rs, lambda r: None if label(r,'legacy_stance') is None else int(label(r,'legacy_stance').get(field)==value))
        if rs[0]['unit']=='R-S':
            for value in ('AFFIRM','DENY'):
                def event(r):
                    p = label(r,'legacy_propositions')
                    lab = p['propositions']['C2']['label'] if p else 'UNJUDGEABLE'
                    return None if lab=='UNJUDGEABLE' else int(lab==value)
                stats['C2_'+value] = metric(rs,event)
        if cell=='E-false':
            stats['EVIDENCE_DISPUTED'] = metric(rs,lambda r: None if label(r,'evidence_disputed') is None else int(label(r,'evidence_disputed')['evidence_disputed']))
        evidence[cell+'|'+arm] = stats
    status_rows = [r for r in rows if r['cell']=='5.5']
    declarations = declarations_report(status_rows)
    relation = relation_report([r for r in rows if r['request_id'] in qmap['relations_v2']],qmap['relations_v2'])
    mechanical = payload.get('mechanical', payload.get('mechanical_rows', []))
    disagreements = identity_disagreements(mechanical, payload['queues']['legacy_stance'], saved['legacy']) if mechanical else dict(status='机械身份接口未提供')
    checks=[]
    for cell,arm,name,target,direction in [('M-wrong','A1','C2_AFFIRM',.8,'ge'),
        ('M-right','none','C2_DENY',.05,'le'),('M-right','A1','C2_DENY',.05,'le'),
        ('E-false','A1','EVIDENCE_DISPUTED',.5,'ge')]:
        checks.append(dict(prediction='|'.join((cell,arm,name)),**decision(evidence[cell+'|'+arm][name],target,direction)))
    comparisons={}
    for arm in ('none','A1'):
        comparisons['M-wrong_minus_E-inapp|'+arm]=contrast(evidence['M-wrong|'+arm]['adopt_d'],evidence['E-inapp|'+arm]['adopt_d'])
    comparisons['F-E-sys_minus_F-E-true']=contrast(evidence['F-E-sys|none']['correct'],evidence['F-E-true|none']['correct'])
    return dict(status='已完整接入旧评审；新关系保持独立', queues=state, evidence=evidence,
        evidence_comparisons=comparisons,predictions=checks,
        status_declarations=declarations, relations_v2=relation, parser_judge_disagreements=disagreements)


def render_report(summary):
    """只渲染规定汇总；表内不放原回答或评审引文。"""
    def number(x):
        return '未定' if x is None else f'{x:.4f}'
    lines=['# 第五批离线汇总','',summary['status'],'',
           '身份解析为主，旧立场与命题标签、新关系标签独立保存。作品等权决定一般判定，历史等权并列；5.4的0.12经验损失目标按原文采用历史等权。','',
           '|阶段|已完成/计划|状态|','|---|---:|---|']
    for name,s in summary['stage_status'].items():
        lines.append(f"|{name}|{s['available']}/{s['expected']}|{s['status']}|")
    lines+=['','## 5.1与留出作品政策','',
            f"{len(summary['per_history'])}段历史；{len(summary['per_triple'])}个唯一三元组，干净两候选共{summary['isolated']['sampling_requests']}条。共享三元组不增加独立采样数。",'',
            '|策略|净收益：作品等权|净收益：历史等权|目标损失：历史等权|状态|','|---|---:|---:|---:|---|']
    for name,p in summary['policies'].items():
        if 'overall' not in p:
            lines.append(f"|{name}|未定|未定|未定|{p['status']}|")
        else:
            o=p['overall'];lines.append(f"|{name}|{number(o['net']['work_equal']['point'])}|{number(o['net']['history_equal']['point'])}|{number(o['target_loss']['history_equal']['point'])}|{p['status']}|")
    lines+=['','所有阈值与训练作品、各折系数及秩均在汇总数据中逐折列出；留出作品未参与阈值、标准化或模型选择。R-003、R-005在各自留出行及作品分表中单列。','',
            '## 版本限定','', '|作品|随版本翻转|解释范围|','|---|---|---|']
    for v in summary['version_readouts']:
        lines.append(f"|{v['work_id']}|{v['state']}|{v['interpretation']}|")
    lines+=['','V只做前向，三问采样众数缺失。特异分支按冻结原始全名分数拟合；不能认定泛化时记未定，G4依原规则把未定作为泛化处理并另列损失。','',
            '## 评审与独立复核','',summary['review']['status'],'',
            '新口径仅覆盖1,440条R-S证据回答和400条5.5的真译者T对象；不能据此宣称第五批全部错误关系。正文否认不会被CANNOT_VERIFY状态抵消。','',
            '盲表尚未抽取。只有生成和全部评审输入完成后，才允许外部选编号并构造完整覆盖表。阶段二40条可共享合格回答，不能截断第五批覆盖。','',
            '## 规定预测','', '|预测|状态|','|---|---|']
    for p in summary['predictions']+summary['review'].get('predictions',[]):
        lines.append('|'+p['prediction'].replace('|',' / ')+'|'+p['status']+'|')
    lines+=['','所有未执行格保持未评估；全部原预测原文保留在汇总数据中。','',
            '## 限制','']+[f'- {s}' for s in summary['limitations']]
    lines+=['','信息损失：'+summary['information_loss']['status'],'']
    return '\n'.join(lines)


def attach_constraints(summary, prior_rows, old, step0):
    """5.4的旁支损害约束仅读旧标签；不把它加入标量目标损失。"""
    ids={h['history_id'] for h in summary['per_history']}
    groups=defaultdict(list)
    for r in prior_rows:
        hid=f"{r['unit']}|{r['work_id']}|{r['idx']}"
        if hid in ids:groups[hid,r['condition']].append(r)
    for hid in ids:
        for arm in ('base','A1'):
            rs=groups[hid,arm]
            unit=hid.split('|')[0]
            if len(rs)!=old.p3.COUNTS[unit]:raise ValueError('旁支约束的旧续写不完整')
    constraints={}
    for name,p in summary['policies'].items():
        if 'history_table' not in p:continue
        selected=[]
        for h in p['history_table']:
            rs=groups[h['history_id'],'base' if h['remove_a1'] else 'A1']
            selected.append(dict(work_id=h['work_id'],history_id=h['history_id'],unit=h['unit'],
                r=rate([old.p3.collateral(r) for r in rs])))
        constraints[name]=dict(overall=summarize(selected),
            by_unit={u:summarize([r for r in selected if r['unit']==u]) for u in ('R-S','S_T','F-D')})
    summary['constraints']=dict(legacy_collateral_denial=constraints,
        definition='第三批冻结命题标签：R-S用C2否认，S_T/F-D用C1否认；缺失保留界，不与新T原子口径合并。',
        legal_question_change=dict(status='本批未执行L，不能估计本批政策的合法改问失败率',
                                   old_descriptive_reference=step0.get('step5_0b',[])),
        cost='G0的z0可预计算；G1的z1需额外历史查询；z2含反事实施压查询；V实际完成30个前向定义、零采样。')


def build_summary(material, prereg, rows, scores, versions, step0, a_support, *, payload=None, saved=None, include_information=False):
    if prereg['analysis_freeze'] != specification(approved=True):
        raise ValueError('离线实现与c39冻结拟合规范不一致')
    plan = material['plan']
    cached_rows(rows, plan['requests'], GENERATION_COMMIT)
    sc = cached_scores(scores, plan['scoring_requests'], GENERATION_COMMIT)
    vc = cached_scores(versions, material['version_scores'], GENERATION_COMMIT)
    if len(sc)!=len(plan['scoring_requests']) or len(vc)!=len(material['version_scores']):
        raise ValueError('全部前向尚未完成')
    histories, triples = assemble_histories(material, rows, scores, versions, step0, a_support)
    fitted = policies(histories)
    lookup = {r['history_id']: r for r in histories}
    for name,data in fitted.items():
        for p in data.get('history_table',[]):
            lookup[p['history_id']].setdefault('actions',{})[name] = p['remove_a1']
    diff = []
    g0={r['history_id']:r for r in fitted['G0'].get('history_table',[])}
    g1={r['history_id']:r for r in fitted['G1'].get('history_table',[])}
    pair_counts=Counter(r['pair_key'] for r in histories)
    for hid in g0.keys() & g1.keys():
        diff.append(dict(work_id=lookup[hid]['work_id'],history_id=hid,pair_key=lookup[hid]['pair_key'],
                         net_difference=g1[hid]['net']-g0[hid]['net']))
    versions_report=version_report(material,versions)
    stages={s:complete_subset(plan,rows,s) for s in ('5.1','5.3','5.5')}
    result=dict(status='5.1与前向完整的离线计算；后续阶段按完整门槛接入',
        generation_freeze=GENERATION_COMMIT,stage_status=stages,
        per_history=histories,per_triple=triples,recognition=recognition_report(rows),
        additive=additive_report(histories),version_readouts=versions_report,policies=fitted,
        candidate_configuration_bound=candidate_bound(histories),
        G1_minus_G0=dict(overall=numeric(diff,'net_difference'),
            shared_configuration=numeric([r for r in diff if pair_counts[r['pair_key']]>1],'net_difference'),
            cost='z1需一次额外查询；z0可预计算；z2需反事实查询'),
        isolated=dict(estimate=numeric(histories,'isolated_loss'),unique_triples=len(triples),
            sampling_requests=sum(t['unique_sampling_requests'] for t in triples),
            interpretation='共享三元组不当作独立重复；仅候选完整时的识别上限'),
        predictions=primary_predictions(rows,histories,versions_report),
        original_rules_and_predictions=prereg['original_rules_and_predictions'],
        unexecuted=prereg['optional_scope_status'],
        limitations=['5.2、R2′、重述对照等未执行，不能认定格式或隔离写回的因果效果。',
                    'R-006、R-009仅限定变化读数；V没有采样众数，不以分数最大值代替。',
                    'G2在冻结净收益目标下全部阈值并列；较高阈值规则给出双+inf的无提示退化解，不能宣称学到了有用提示。'])
    # 旧标量目标损失来自已提交5.0，不用新原子标签改写旧批。
    old_by_h={h['history_id']:h for h in step0['per_history']}
    references={};comparisons={}
    for unit in ('R-S','S_T','F-D'):
        refs={}
        for arm in ('base','A1'):
            hs=[dict(work_id=h['work_id'],history_id=h['history_id'],r=old_by_h[h['history_id']][arm]['target_loss'])
                for h in histories if h['unit']==unit]
            refs[arm]=dict(**summarize(hs),history_table=hs)
        references[unit]=refs
        for cell in ('R2','R3'):
            new=metric([r for r in rows if r['cell']==cell and r['unit']==unit],lambda r:0 if correctness(r)==1 else 1)
            for arm in refs:
                comparisons['|'.join((cell,unit,arm))]=contrast(new,refs[arm])
        for stage in ('5.3','5.5'):
            if not stages[stage]['complete']:
                continue
            rs=[r for r in rows if r['stage']==stage and r['unit']==unit]
            for cell,arm in sorted({(r['cell'],r['arm']) for r in rs}):
                new=metric([r for r in rs if (r['cell'],r['arm'])==(cell,arm)],lambda r:0 if correctness(r)==1 else 1)
                for old_arm in refs:
                    comparisons['|'.join((cell,arm,unit,old_arm))]=contrast(new,refs[old_arm])
                for rcell in ('R2','R3'):
                    ref=metric([r for r in rows if r['cell']==rcell and r['unit']==unit],lambda r:0 if correctness(r)==1 else 1)
                    comparisons['|'.join((cell,arm,unit,rcell))]=contrast(new,ref)
    result['old_target_loss_references']=references
    result['target_loss_contrasts']=dict(direction='当前条件减所列参照；正值为目标损失增加',estimates=comparisons,
        definition='严格采用5.4标量损失：拒答、只声明不确定、无法解析最终答案均为1；身份事件仍单独保留缺失界。')
    # 原§10的24条量级参照与§3.5三部预测层并列，不用结果选择口径。
    result['strong_strata']= {name:dict(works=works,histories=sum(r['unit']=='S_T' and r['work_id'] in works for r in histories),
        rates={cell:metric([r for r in rows if r['cell']==cell and r['unit']=='S_T' and r['work_id'] in works],correctness)
               for cell in ('R2','R3')}) for name,works in (
                   ('prediction_section3_5',list(STRONG_ST)),('R001_description',['R-001']),
                   ('section10_24_context',['R-001',*STRONG_ST]))}
    result['generation_diagnostics']={key:dict(n=len(rs),truncated=sum(r['truncated'] for r in rs),looped=sum(r['looped'] for r in rs))
        for key,rs in ((cell+'|'+arm,[r for r in rows if (r['cell'],r['arm'])==(cell,arm)])
                       for cell,arm in sorted({(r['cell'],r['arm']) for r in rows}))}
    result['generation_evidence']=(
        {cell+'|'+arm:identity_summary([r for r in rows if (r['cell'],r['arm'])==(cell,arm)])
         for cell,arm in sorted({(r['cell'],r['arm']) for r in rows if r['stage']=='5.3'})}
        if stages['5.3']['complete'] else dict(status='未完成，不汇总部分生成'))
    if stages['5.5']['complete']:
        status_rows=[r for r in rows if r['cell']=='5.5']
        result['generation_status']=dict(overall=declarations_report(status_rows),
            by_unit={u:declarations_report([r for r in status_rows if r['unit']==u]) for u in ('R-S','S_T','F-D')},
            identity=identity_summary(status_rows),
            body_denial_status='正文语义仍待完整旧/新评审，末行声明不取消正文否认。')
    else:result['generation_status']=dict(status='未完成，不汇总部分生成')
    result['predictions']+=generation_predictions(rows,stages,result['generation_evidence'],result['generation_status'])
    if result['additive']['status']=='已拟合':
        result['predictions'].append(dict(prediction='M0留出作品翻转准确率>=.75',**result['additive']['models']['M0']['prediction']))
    g4=fitted['G4'].get('history_table',[])
    result['G4_predicted_locations']={wid+'|'+unit:dict(
        histories=len(rs),removed=sum(r['remove_a1'] for r in rs),external=sum(r['external_check'] for r in rs),
        interpretation='原文为位置与部分历史的方向预测，未另加数量门槛')
        for wid,unit,rs in ((wid,unit,[r for r in g4 if r['work_id']==wid and r['unit']==unit])
                           for wid,unit in [('R-008','F-D'),('R-005','F-D'),('R-003','F-D'),('R-004','S_T')])}
    if all(s['complete'] for s in stages.values()) and payload is not None and saved is not None:
        result['review']=completed_review_sections(material,rows,payload,saved)
        ready=bool(review_status(payload,saved)) and all(v['complete'] for v in review_status(payload,saved).values())
        result['blind_review']=dict(ready_to_construct=ready,selection_performed=False,
            interface='blind_core.coverage_pools / validate_selection / build_blind_table；身份10条，5.3每格每臂阳阴各2条，质疑20，状态20；阶段二40条可重叠但不能替代覆盖。')
    else:
        result['review']=dict(status='未完成；5.3/5.5与新旧标签不按部分数据汇总')
        result['blind_review']=dict(ready_to_construct=False,selection_performed=False)
    if include_information:
        from .offline_information import information_loss
        result['information_loss']=information_loss(histories)
    else:
        result['information_loss']=dict(status='接口已准备；本次只计算5.1和冻结政策，尚未运行规定的2000次作品重抽')
    return result


def retained_information(previous_summary):
    """后续评审接入时复用已完成的规定计算，不因重新渲染而覆盖或重跑。"""
    info=previous_summary.get('information_loss',{})
    layers=info.get('layers',{})
    if info.get('status')!='已按冻结实现计算':
        return None
    if set(layers)!={'a','a_z0','a_z0_z1_z3'}:
        raise ValueError('已有信息损失产物声称完成但读数层不完整，须核查，不自动重跑')
    for layer in layers.values():
        estimates=layer.get('estimates',{})
        if set(estimates)!={'split_half','shrunk'} or any(
            e.get('bootstrap_repetitions')!=2000 for e in estimates.values()):
            raise ValueError('已有信息损失产物声称完成但规定重抽不完整，须核查，不自动重跑')
    return info


def run(out,pilot,*,include_information=False):
    assert_remote(out,pilot)
    out,pilot=Path(out),Path(pilot)
    from .freeze import validate
    prereg=validate(out,pilot,GENERATION_COMMIT)
    material=load(out/'factdiag5_materials.json')
    rows=load(out/'core_generations.json');scores=load(out/'core_forward.json');versions=load(out/'version_forward.json')
    step0=load(out/'factdiag5_step0.json')
    old=previous()
    a=clean_support(material['plan']['histories'],material,load(pilot/'factdiag2_20261029/calibration_t1.json'),old)
    # 已冻结评审入口在内存构造输入，未另存一份原回答；此处复用同一纯构造器。
    payload=None
    if len(rows)==len(material['plan']['requests']):
        from .review_runtime import prepare_remote_inputs
        payload=prepare_remote_inputs(out,pilot,load(out/'factdiag5_review_protocol.json'))
    saved={key:load(out/name) if (out/name).exists() else {} for key,name in [('legacy','core_legacy_reviews.json'),('relations','core_relations_v2.json')]}
    if payload is not None:
        from .review_runtime import validate_saved
        validate_saved(payload,saved,REVIEW_COMMIT)
    summary_path=out/'factdiag5_summary.json'
    previous_summary=load(summary_path) if summary_path.exists() else {}
    prior_information=retained_information(previous_summary)
    result=build_summary(material,prereg,rows,scores,versions,step0,a,payload=payload,saved=saved,
                         include_information=include_information and prior_information is None)
    if prior_information is not None:
        if previous_summary.get('per_history')!=result['per_history']:
            raise ValueError('已有信息损失对应的逐历史输入发生变化，须核查，不自动覆盖或重算')
        result['information_loss']=prior_information
    attach_constraints(result,old.source_rows(pilot/'factdiag3_20261030'),old,step0)
    save(out/'factdiag5_summary.json',result)
    (out/'factdiag5_report.md').write_text(render_report(result),encoding='utf-8')
    return dict(stages=result['stage_status'],histories=len(result['per_history']),triples=len(result['per_triple']),
        additive_status=result['additive']['status'],policies={k:v['status'] for k,v in result['policies'].items()},
        missing_a=sum(r['a'] is None for r in result['per_history']),report_file=str(out/'factdiag5_summary.json'))


if __name__=='__main__':
    import json
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--pilot',type=Path,required=True)
    ap.add_argument('--include-information',action='store_true')
    args=ap.parse_args()
    print(json.dumps(run(args.out,args.pilot,include_information=args.include_information),ensure_ascii=False))
