"""完整正式数据的冻结结局表；不重新评审，不使用筛查续写估计效应。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import numpy as np

from core import load, save, rate, difference, avg, SEED, ideal_event, exact_role_event
from formal import STAGES
from formal_judge import formal_inputs
from screen import identity
from joint_data import outcomes


def cluster_interval(projects, field, *, extreme=False):
    groups = defaultdict(list)
    for p in projects:
        if p[field] is not None:
            groups[p['cluster_id']].append(p[field])
    if len(groups) < 2:
        return None
    if extreme and (all(v == 0 for vs in groups.values() for v in vs) or
                    all(v == 1 for vs in groups.values() for v in vs)):
        return None
    total = np.array([sum(v) for v in groups.values()])
    size = np.array([len(v) for v in groups.values()])
    indices = np.random.default_rng(SEED).integers(0, len(groups), (2000, len(groups)))
    samples = total[indices].sum(1) / size[indices].sum(1)
    return np.quantile(samples, [.025, .975]).tolist()


def aggregate(history_values, counts=None):
    by_project = defaultdict(list)
    for h in history_values:
        by_project[(h['work_id'], h['cluster_id'])].append(h)
    projects = []
    for (w, c), hs in sorted(by_project.items()):
        projects.append(dict(work_id=w, cluster_id=c, histories=len(hs),
            point=avg([h['value']['point'] for h in hs]),
            lower=avg([h['value']['bounds'][0] for h in hs]),
            upper=avg([h['value']['bounds'][1] for h in hs])))
    estimates = dict(point=avg([p['point'] for p in projects]),
        bounds=[avg([p[f] for p in projects]) for f in ('lower', 'upper')],
        ci95=cluster_interval(projects, 'point', extreme=True),
        lower_bound_ci95=cluster_interval(projects, 'lower', extreme=True),
        upper_bound_ci95=cluster_interval(projects, 'upper', extreme=True))
    return dict(project_equal=estimates, history_equal=dict(
        point=avg([h['value']['point'] for h in history_values]),
        bounds=[avg([h['value']['bounds'][j] for h in history_values]) for j in (0, 1)]),
        projects=len(projects), clusters=len({p['cluster_id'] for p in projects}),
        histories=len(history_values), counts=counts, per_project=projects)


def measure(rows, event):
    groups = defaultdict(list)
    for r in rows:
        if r[event] != 'NOT_APPLICABLE':
            groups[(r['work_id'], r['cluster_id'], r['history_id'])].append(r[event])
    h = [dict(work_id=w, cluster_id=c, history_id=hid, value=rate(v)) for (w, c, hid), v in groups.items()]
    return aggregate(h, rate([r[event] for r in rows if r[event] != 'NOT_APPLICABLE']))


def paired(rows, left, right, event):
    grouped = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r['arm'] in (left, right) and r[event] != 'NOT_APPLICABLE':
            grouped[(r['work_id'], r['cluster_id'], r['history_id'], r['candidate_type'])][r['arm']].append(r[event])
    h = []; excluded = 0
    for (w, c, hid, candidate), arms in grouped.items():
        if set(arms) != {left, right}:
            excluded += 1
            continue
        h.append(dict(work_id=w, cluster_id=c, history_id=hid, candidate_type=candidate,
                      value=difference(rate(arms[left]), rate(arms[right]))))
    result = aggregate(h)
    result.update(left=left, right=right, unmatched_history_candidates=excluded)
    return result


EVENTS = ('adopt', 'correct', 'keep', 'role_true', 'role_false', 'role_denied', 'proposition_deny', 'ideal')


def collect(out):
    plan = load(out / 'factdiag6g_materials.json')['plan']
    bank = {i['item_id']: i for i in plan['items']}
    features = {r['history_id']+'|'+r['candidate_type']: r['values'] for r in load(out/'common_features.json')['rows']}
    data = []; completion = []; mismatches = []
    for stage in STAGES:
        rows = load(out / f'formal_{stage}_generations.json')
        labels = load(out / f'formal_{stage}_labels.json')
        queues = formal_inputs(out, stage)
        for kind, queue in queues.items():
            if set(labels[kind]) != {r['id'] for r in queue}:
                raise RuntimeError('评审尚未齐备：'+stage+' '+kind)
        completion.append(dict(stage=stage, generated=len(rows), expected=plan['counts'][stage],
            labels={k: len(v) for k, v in labels.items()}, tokens=sum(r['n_new_tokens'] for r in rows),
            truncated=sum(r['truncated'] for r in rows), looped=sum(r['looped'] for r in rows)))
        for row in rows:
            item = bank[row['conflict_id']]; key = identity(row)
            c = next(c for c in item['candidates'] if c['type'] == row['candidate_type'])
            s = labels['stance'][key]['result']; role = labels['role'][key]['result']
            prop = (labels['proposition'][key]['result'] or {}).get('label') if c.get('proposition') else 'N/A'
            val = outcomes(row, item, c, row['original'], role, prop, numeric_main=row['path'].startswith('constructed|'))
            f = features[row['source_history_id']+'|'+c['type']]
            bad = bool(row['truncated'] or row['looped'])
            role_value = val['role']; prop_value = val['proposition']; ident = val['identity']
            d = dict(id=key, stage=stage, structure=item['structure'], item_id=item['item_id'],
                work_id=item['work_id'], cluster_id=item.get('pair_id', item['work_id']),
                history_id=row['source_history_id'], path=row['path'].split('|')[0],
                candidate_type=c['type'], arm=row['arm'], rep=row['rep'],
                feature_values=f, labels=val['labels'], final_identity=ident['category'],
                correct=ident['correct'], adopt=ident['adopt'], keep=ident['keep'],
                role=role_value, role_raw=role, proposition=prop_value,
                role_true=None if bad else exact_role_event(role_value),
                role_false=None if bad or role_value in (None, 'UNKNOWN', 'TRUE_ROLE_COARSE', 'OTHER') else int(role_value=='FALSE_ROLE'),
                role_denied=None if bad or role_value in (None, 'UNKNOWN', 'TRUE_ROLE_COARSE', 'OTHER') else int(role_value=='DENIED'),
                proposition_deny='NOT_APPLICABLE' if prop=='N/A' else (None if bad or prop in (None, 'UNJUDGEABLE') else int(prop=='DENY')),
                ideal='NOT_APPLICABLE' if not c.get('proposition') else ideal_event(ident['correct'], prop_value),
                stance=None if bad or s.get('unjudgeable') else s.get('stance'),
                explicit=None if bad or s.get('unjudgeable') else s.get('explicit'),
                truncated=bool(row['truncated']), looped=bool(row['looped']), n_new_tokens=row['n_new_tokens'])
            if d['adopt'] is not None and d['stance'] is not None and d['adopt'] != int(d['stance']=='USER'):
                mismatches.append(dict(id=key, structure=d['structure'], identity=d['final_identity'], stance=d['stance']))
            data.append(d)
    return data, completion, mismatches


def summarize(out):
    data, completion, mismatches = collect(out)
    tables = []; contrasts = []; history_table = []
    for scope in ('all', 'unexposed'):
        selected = [r for r in data if scope=='all' or (r['structure']=='G1' and not r['feature_values']['exposed'])]
        units = defaultdict(list)
        for r in selected:
            units[(r['structure'], r['path'], r['candidate_type'])].append(r)
        for unit, rows in sorted(units.items()):
            label = dict(scope=scope, structure=unit[0], path=unit[1], candidate_type=unit[2])
            for arm in sorted({r['arm'] for r in rows}):
                block = [r for r in rows if r['arm']==arm]
                tables.append(dict(**label, arm=arm, metrics={e: measure(block, e) for e in EVENTS},
                    identity_counts=dict(Counter(r['final_identity'] for r in block)),
                    role_counts=dict(Counter(str(r['role']) for r in block)),
                    proposition_counts=dict(Counter(str(r['proposition']) for r in block)),
                    role_among_adopters=measure([r for r in block if r['adopt']==1], 'role_true'),
                    quality=dict(planned=len(block), truncated=sum(r['truncated'] for r in block), looped=sum(r['looped'] for r in block))))
            arms={r['arm'] for r in rows}
            for right in ('C', 'S+A1', 'S+A0'):
                if 'S' in arms and right in arms:
                    contrasts.append(dict(**label, right=right, metrics={e: paired(rows, 'S', right, e) for e in EVENTS}))
    groups=defaultdict(list)
    for r in data:
        groups[(r['structure'],r['work_id'],r['history_id'],r['candidate_type'],r['arm'])].append(r)
    for (structure,w,h,c,a), rows in sorted(groups.items()):
        history_table.append(dict(structure=structure,work_id=w,history_id=h,candidate_type=c,arm=a,
            counts={e:rate([r[e] for r in rows if r[e]!='NOT_APPLICABLE']) for e in EVENTS}))
    computational=[]
    items={i['item_id']:i for i in load(out/'factdiag6g_materials.json')['plan']['items']}
    constructed=[r for r in data if r['structure']=='G2d' and r['path']=='constructed']
    strata={'c_at_least_0.9':[r for r in constructed if r['feature_values']['c']>=.9]}
    for r in constructed:
        item=items[r['item_id']]
        level=str(item.get('family','unknown'))+'_'+str(item.get('level','unknown'))
        strata.setdefault('difficulty_'+level,[]).append(r)
    for name, rows in strata.items():
        computational.append(dict(stratum=name, arms={a:measure([r for r in rows if r['arm']==a],'correct') for a in ('S','S+A1')},
            difference_S_minus_A1=paired(rows,'S','S+A1','correct'),
            clean_c=avg(list({r['item_id']:r['feature_values']['c'] for r in rows}.values()))))
    result=dict(completion=completion,tables=tables,contrasts=contrasts,per_history=history_table,
                computational=computational,identity_stance_disagreements=mismatches,
                intervals='按项目重抽2000次，电影版本按配对抽簇后方向等权；全零/全一及单簇不报告退化置信区间。缺失仍报告两端界。')
    save(out/'formal_events.json',data)
    save(out/'formal_results.json',result)
    print('正式汇总',len(data),'条；',len(tables),'个条件表；身份/立场不一致',len(mismatches))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    summarize(ap.parse_args().out)
