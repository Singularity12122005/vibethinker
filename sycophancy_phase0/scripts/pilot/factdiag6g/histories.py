"""筛查后的自然历史与试运行；不把试运行续写用于正式效应。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import random
import time

from core import SEED, load, save, same_identity, normalize_name
from exposure import one_turn
from screen import identity, make_main
from readouts import token_total


def valid(row):
    return not (row['truncated'] or row['looped'] or row['parsed']['kind']=='missing')


def stable_key(value,item):
    if same_identity(value,item['gold'],item['gold_aliases'],item['answer_format']=='number'):
        return item['gold']
    for c in item.get('candidates',[]):
        if same_identity(value,c['name'],c.get('aliases',[]),item['answer_format']=='number'):
            return c['name']
    return normalize_name(value) if item['answer_format']=='entity' else value


def select_first(config,rows):
    """条数仅按预设结构；按首答选历史，不另加第二轮正确性门槛。"""
    group=defaultdict(list)
    for row in rows:group[row['conflict_id']].append(row)
    selected=[];notes=[]
    for item in config['items']:
        rs=sorted(group[item['item_id']],key=lambda r:r['idx'])
        if len(rs)!=8 or {r['idx'] for r in rs}!=set(range(8)):
            raise RuntimeError('干净首答不完整，不补采：'+item['item_id'])
        good=[r for r in rs if valid(r) and r['parsed']['kind']=='gold']
        wrong=[r for r in rs if valid(r) and r['parsed']['kind']!='gold']
        counts=Counter(stable_key(r['parsed']['value'],item) for r in rs if valid(r))
        structure=item['structure'];chosen=[]
        if structure=='G2c':
            director=next(c for c in item['candidates'] if c['type']=='D')
            for exposed in (True,False):
                subgroup=[r for r in good if bool(one_turn(r['assistant_text'],director)['exposed'])==exposed]
                if subgroup:chosen.append(subgroup[0])
            chosen+=(r for r in good if r not in chosen)
            chosen=chosen[:2]
        elif structure=='G2d':
            chosen=good[:1] if item['level'] in (9,'simple') else []
        else:chosen=good[:1] if item.get('candidates') else []
        selected.extend(dict(item_id=item['item_id'],idx=r['idx'],path='correct',first=r) for r in chosen)
        if structure in ('G2a','G2b','G2d'):
            stable_wrong=[r for r in wrong if counts[stable_key(r['parsed']['value'],item)]/8>=.875]
            if structure=='G2b':
                c=item['candidates'][0]
                stable_wrong=[r for r in stable_wrong if same_identity(r['parsed']['value'],c['name'],c['aliases'])]
            if stable_wrong:
                selected.append(dict(item_id=item['item_id'],idx=stable_wrong[0]['idx'],path='natural_wrong',first=stable_wrong[0]))
        notes.append(dict(item_id=item['item_id'],correct=len(good),valid_wrong=len(wrong),
            missing=8-len(good)-len(wrong),answer_counts=dict(counts),
            selected_correct=[r['idx'] for r in chosen]))
    return selected,notes


def second_tasks(main,config,selected):
    tasks=[]
    for s in selected:
        first=s['first'];x2=config['templates']['x2']
        tasks.append(dict(conflict_id=s['item_id'],work_id=first['work_id'],idx=s['idx'],
            path=s['path'],arm='shared',rep=0,t=2,phase='G6_S0_HISTORY',
            user_text=x2,prompt_ids=main.continue_from(first,x2),previous_length=first['n_new_tokens'],
            first_value=first['parsed']['value'],first_identity=identity(first)))
    return tasks


def run_rows(main,tasks,path,out):
    expected={identity(r):r for r in tasks}
    rows=load(path) if path.exists() else []
    cached={identity(r):r for r in rows}
    if len(expected)!=len(tasks) or len(cached)!=len(rows) or not set(cached)<=set(expected):
        raise RuntimeError('自然历史或试运行缓存不符')
    for key,row in cached.items():
        if any(row[k]!=expected[key][k] for k in ('prompt_ids','user_text')):
            raise RuntimeError('已有历史词元改变')
    pending=sorted((r for r in tasks if identity(r) not in cached),
                   key=lambda r:(r['conflict_id'],r['previous_length'],identity(r)))
    started=time.time()
    for off in range(0,len(pending),16):
        for row in main.generate(pending[off:off+16]):cached[identity(row)]=row
        result=[cached[identity(r)] for r in tasks if identity(r) in cached]
        save(path,result)
        total=token_total(out)
        print(f'{path.stem}: {len(result)}/{len(tasks)}; 累计词元={total}; seconds={time.time()-started:.1f}',flush=True)
        if total>=1_200_000:print('120万词元预警',flush=True)
        if total>=1_500_000:raise RuntimeError('150万词元，暂停请示')
    result=[cached[identity(r)] for r in tasks]
    save(path,result)
    if result and sum(r['looped'] for r in result)/len(result)>.05:
        raise RuntimeError('循环诊断超过5%')
    return result


def trial_selection(items,histories):
    """用户批准：只从有主相邻候选和有效自然历史的项目抽10项。"""
    bank={i['item_id']:i for i in items};group=defaultdict(list);excluded=[]
    for h in histories:
        item=bank[h['conflict_id']]
        kind={'G2a':'L','G2b':'d','G2c':'D','G2d':'d'}[item['structure']]
        candidate=next((c for c in item.get('candidates',[]) if c['type']==kind),None)
        if h['path']!='correct' or candidate is None:continue
        if 'current_value' not in h:raise RuntimeError('尚未确定第2轮实际答案')
        if h.get('current_missing') or h['truncated'] or h['looped']:continue
        if same_identity(h['current_value'],candidate['name'],candidate.get('aliases',[]),item['answer_format']=='number'):
            excluded.append(dict(item_id=h['conflict_id'],idx=h['idx'],reason='d=x'))
            continue
        group[h['conflict_id']].append((h,candidate))
    ids=sorted(group);random.Random(SEED).shuffle(ids)
    return [sorted(group[k],key=lambda x:x[0]['idx'])[0] for k in ids[:10]],excluded


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--collections',nargs='+',required=True)
    ap.add_argument('--prepare-only',action='store_true')
    args=ap.parse_args()
    configs=[load(args.out/f's0_{c}_inputs.json') for c in args.collections]
    all_selected=[]
    for config in configs:
        selected,notes=select_first(config,load(args.out/f"s0_{config['collection']}_clean.json"))
        metadata=dict(selected=[{k:v for k,v in s.items() if k!='first'} for s in selected],notes=notes)
        path=args.out/f"s0_{config['collection']}_history_selection.json"
        if path.exists() and load(path)!=metadata:raise RuntimeError('既有历史选择改变')
        save(path,metadata);all_selected.append(selected)
        print('第二轮历史',config['collection'],len(selected),flush=True)
    if args.prepare_only:return
    engine=make_main('/output/sycophancy-phase0/model',[i for c in configs for i in c['items']])
    for config,selected in zip(configs,all_selected):
        run_rows(engine,second_tasks(engine,config,selected),args.out/f"s0_{config['collection']}_t2.json",args.out)


if __name__=='__main__':main()
