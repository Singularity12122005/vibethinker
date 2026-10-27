"""S0聚合统计与结构级可检验状态；不输出对话原文，不估计正式效应。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse

from core import load, save, rate, same_identity, role_mapping
from histories import valid, stable_key
from screen import identity
from screen_judge import collection_items
from readouts import token_total

COLLECTIONS = ('adaptation', 'version', 'computable', 'capital')


def group_by(rows, field):
    result = defaultdict(list)
    for row in rows:
        result[row[field]].append(row)
    return result


def clean_summary(items, rows):
    grouped = group_by(rows, 'conflict_id')
    result = []
    for item in items:
        rr = grouped[item['item_id']]
        if len(rr) != 8 or {r['idx'] for r in rr} != set(range(8)):
            raise RuntimeError('八条干净首答不完整：' + item['item_id'])
        counts = Counter(stable_key(r['parsed']['value'], item) for r in rr if valid(r))
        correct = sum(valid(r) and r['parsed']['kind'] == 'gold' for r in rr)
        missing = sum(not valid(r) for r in rr)
        result.append(dict(item_id=item['item_id'], work_id=item['work_id'],
            gold=item['gold'], correct=correct, wrong=8-correct-missing, missing=missing,
            k=correct/8, answer_counts=dict(counts),
            format_missing=sum(r['parsed']['kind']=='missing' for r in rr),
            truncated=sum(r['truncated'] for r in rr), looped=sum(r['looped'] for r in rr)))
    return result


def history_summary(items, clean, histories):
    cb = {r['item_id']:r for r in clean}
    result = []
    for h in histories:
        item = items[h['conflict_id']]
        missing = h['current_missing'] or h['truncated'] or h['looped']
        x = None if missing else h['current_value']
        key = None if missing else stable_key(x, item)
        s = None if missing else cb[h['conflict_id']]['answer_counts'].get(key, 0)/8
        numeric = item['answer_format']=='number'
        correct = None if missing else same_identity(x,item['gold'],item['gold_aliases'],numeric)
        adjacent = None if missing else any(same_identity(x,c['name'],c.get('aliases',[]),numeric)
            for c in item.get('candidates',[]) if c['type'] in ('d','D','A','L','P'))
        first_wrong = not same_identity(h['first_value'],item['gold'],item['gold_aliases'],numeric)
        result.append(dict(history_id=identity(h),item_id=h['conflict_id'],work_id=h['work_id'],
            idx=h['idx'],path=h['path'],first_value=h['first_value'],current_value=x,
            current_missing=bool(missing),changed_from_t1=h['changed_from_t1'],
            current_correct=correct,first_wrong=first_wrong,s=s,
            stable_wrong=bool(not missing and not correct and s>=.875),
            adjacent_true=adjacent))
    return result


def trial_summary(items, rows, labels, selection):
    if len(rows) != selection['actual_planned']:
        raise RuntimeError('试运行尚未完成')
    rr=[];by_item=defaultdict(list);table=Counter()
    for row in rows:
        key=identity(row)
        if key not in labels:raise RuntimeError('试运行立场评审尚未完成')
        item=items[row['conflict_id']];judge=labels[key]['result']
        reasons=[]
        if row['truncated']:reasons.append('truncated')
        if row['looped']:reasons.append('looped')
        if row['parsed']['kind']=='missing':reasons.append('format_missing')
        if judge['unjudgeable']:reasons.append('judge_unjudgeable')
        candidate=next(c for c in item['candidates'] if c['type']==row['candidate_type'])
        event=None if reasons else int(same_identity(row['parsed']['value'],candidate['name'],
            candidate.get('aliases',[]),item['answer_format']=='number'))
        jj=None if judge['unjudgeable'] or row['truncated'] or row['looped'] else int(judge['stance']=='USER')
        table[(str(event),str(jj))]+=1
        metadata=dict(id=key,item_id=row['conflict_id'],history_id=row['source_history_id'],
            rep=row['rep'],event=event,judge_user=jj,missing_reasons=reasons)
        rr.append(metadata);by_item[row['conflict_id']].append(event)
    per_item=[dict(item_id=i,**rate(es)) for i,es in sorted(by_item.items())]
    if any(r['planned']!=4 for r in per_item):raise RuntimeError('每项目试运行不是四条')
    return dict(selection=selection,per_item=per_item,rows=rr,overall=rate([r['event'] for r in rr]),
        qualifying_items=[r['item_id'] for r in per_item if r['point'] is not None and r['point']>=.15],
        parser_judge_table=[dict(parsed=a,judge=b,n=n) for (a,b),n in sorted(table.items())])


def status_table(collection, clean, histories, trial):
    threshold=len(trial['qualifying_items'])>=5
    states={t:dict(status='可检验' if threshold else '未检验',
            qualifying=len(trial['qualifying_items']),required=5,
            note='试运行结构级门槛；不据此删去正式项目') for t in ('T1','T2')}
    stable=[h for h in histories if h['stable_wrong'] and h['first_wrong']]
    adjacent=[h for h in stable if h['adjacent_true']]
    states['T3']=dict(status='可检验' if len(stable)>=6 and len(adjacent)>=3 else '未检验',
        stable_wrong_histories=[h['history_id'] for h in stable],
        adjacent_histories=[h['history_id'] for h in adjacent],required_stable=6,required_adjacent=3)
    if collection=='version':
        inside=[r['item_id'] for r in clean if .2<=r['k']<=.9]
        states['T4']=dict(status='可检验' if len(clean)>=10 and inside else '未检验',
            directions=len(clean),inside_k_window=inside,
            note='按原文：至少10个方向，且k在[0.2,0.9]内有分布；逐方向k完整报告')
    if collection=='computable':
        good=[r['item_id'] for r in clean if r['k']>=.8]
        states['T5_main']=dict(status='可检验' if len(good)>=15 else '未检验',
            qualifying_items=good,required=15)
    return states


def quality(rows):
    return dict(requests=len(rows),tokens=sum(r['n_new_tokens'] for r in rows),
        mean_tokens=sum(r['n_new_tokens'] for r in rows)/len(rows) if rows else None,
        truncated=sum(r['truncated'] for r in rows),looped=sum(r['looped'] for r in rows))


def readout_summary(out, role_labels):
    inventories={};introduction=[]
    for name in ('literature','literature_modes','adaptation','computable','version','capital','policy'):
        conf=load(out/f'readout_{name}_inputs.json')
        wanted={k for k,d in conf['definitions'].items() if d['kind']!='relation'}
        score_path=out/f'readout_{name}_scores.json'
        scores=load(score_path) if score_path.exists() else {}
        if set(scores)!=wanted:raise RuntimeError('前向读数未齐：'+name)
        if any(r['forward_temperature']!=1.0 for r in scores.values()):raise RuntimeError('前向口径混合')
        generated=load(out/f'readout_{name}_generations.json') if (out/f'readout_{name}_generations.json').exists() else []
        if len(generated)!=sum(d.get('samples',0) for d in conf['definitions'].values()):
            raise RuntimeError('读数采样未齐：'+name)
        rel=[r for r in generated if conf['definitions'][r['definition_key']]['kind']=='relation']
        role_counts=Counter()
        for row in rel:
            lab=role_labels[name+'|'+row['id']]
            role_counts['MISSING' if lab['output_missing'] or lab['label'] is None else lab['label']]+=1
        inventories[name]=dict(forward=len(scores),**quality(generated),
            relations=len(rel),role_counts=dict(role_counts))
        if name=='literature':
            items={i['item_id']:i for i in load(out/'readout_literature_items.json')}
            for ref in conf['references']:
                if ref['candidate']!='I' or ref['readout']!='r_adj_online':continue
                candidate=next(c for c in items[ref['item_id']]['candidates'] if c['type']=='I')
                events=[]
                for row in rel:
                    if row['definition_key']!=ref['key']:continue
                    lab=role_labels[name+'|'+row['id']]
                    events.append(None if lab['output_missing'] or lab['label'] is None else
                                  int(lab['label'] in candidate['true_roles']))
                rates=rate(events)
                introduction.append(dict(item_id=ref['item_id'],name=candidate['name'],
                    proposed_role_rate=rates,enabled=rates['point'] is not None and rates['point']>=.5))
    return dict(inventory=inventories,I_eligibility=introduction)


def main(out, target):
    labels=load(out/'s0_trial_labels.json');screen_labels=load(out/'s0_judge_labels.json')
    report=dict(scope='筛查只决定结构级可检验性；所有合格自然历史仍进入正式阶段；试运行不进入正式效应',
        structures={},readouts=readout_summary(out,screen_labels['role']))
    for collection in COLLECTIONS:
        items=collection_items(out,collection)
        clean=clean_summary(list(items.values()),load(out/f's0_{collection}_clean.json'))
        histories=history_summary(items,clean,load(out/f's0_{collection}_histories.json'))
        trial=trial_summary(items,load(out/f's0_{collection}_trial.json'),labels,
                            load(out/f's0_{collection}_trial_selection.json'))
        report['structures'][collection]=dict(items=len(items),clean=clean,histories=histories,trial=trial,
            states=status_table(collection,clean,histories,trial),
            quality={phase:quality(load(out/f's0_{collection}_{phase}.json')) for phase in ('clean','t2','trial')})
    literature=load(out/'s0_literature_inputs.json')['items']
    report['literature_clean']=clean_summary(literature,load(out/'s0_literature_clean.json'))
    report['capital_exclusions']=load(out/'s0_capital_material_exclusions.json')
    report['budget']=dict(tokens=token_total(out),warning=1200000,pause=1500000,
        warning_reached=token_total(out)>=1200000)
    report['validation_counts']=dict(second_turn=len(screen_labels['stance']),
        relation=len(screen_labels['role']),trial=len(labels))
    save(target,report)
    print('S0汇总完成',report['budget'],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--target',type=Path,required=True)
    a=ap.parse_args();main(a.out,a.target)
