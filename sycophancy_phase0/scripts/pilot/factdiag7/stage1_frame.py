"""第七批阶段一：只读正式产物，构造抽样框与概率样本；不调用模型。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import random
import sys

SEED = 20261112
STAGES = ('g1_non_a0', 'g1_a0', 'adaptation', 'version', 'computable', 'capital')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def rng_for(name):
    return random.Random(int.from_bytes(hashlib.sha256(f'{SEED}|{name}'.encode()).digest()[:8], 'big'))


def identity(r):
    return '|'.join(str(r[k]) for k in ('conflict_id','idx','path','arm','rep','t','phase'))


def role_mapping(label, roles):
    if label is None or label == 'CONFLICTING':
        return 'UNKNOWN'
    if label in ('TRANSLATOR_EDITION_UNSPECIFIED','DIRECTOR_VERSION_UNSPECIFIED'):
        return 'TRUE_ROLE_COARSE'
    if label in ('NONE_STATED','DENIED_ANY_ROLE','UNMENTIONED','OTHER'):
        return label
    return 'TRUE_ROLE' if label in roles else 'FALSE_ROLE'


def build_frame(source):
    bank = {i['item_id']: i for i in load(source/'factdiag6g_materials.json')['plan']['items']}
    frame = []
    for stage in STAGES:
        rows = load(source/f'formal_{stage}_generations.json')
        labels = load(source/f'formal_{stage}_labels.json')
        for row in rows:
            key = identity(row)
            item = bank[row['conflict_id']]
            c = next(c for c in item['candidates'] if c['type'] == row['candidate_type'])
            mapped = role_mapping(labels['role'][key]['result'], c['true_roles'])
            frame.append(dict(id=key, stage=stage, structure=item['structure'],
                work_id=row['work_id'], item_id=item['item_id'], history_id=row['source_history_id'],
                candidate_type=c['type'], arm=row['arm'], path=row['path'].split('|')[0],
                old_role=labels['role'][key]['result'], old_stratum='FALSE_ROLE' if mapped=='FALSE_ROLE' else 'OTHER',
                truncated=bool(row['truncated']), looped=bool(row['looped'])))
    if len(frame)!=5976 or len({r['id'] for r in frame})!=len(frame):
        raise RuntimeError('正式抽样框数量或身份与第六批不一致')
    return sorted(frame, key=lambda r:r['id'])


def cell_name(structure, candidate, arm, path=None):
    return '|'.join([structure,candidate,arm]+([path] if path else []))


def sample_cell(frame, structure, candidate, arm, total, expected_works, mode, path=None):
    cell = cell_name(structure,candidate,arm,path)
    rows = [r for r in frame if r['structure']==structure and r['candidate_type']==candidate
            and r['arm']==arm and (path is None or r['path']==path)]
    works = defaultdict(list)
    for r in rows: works[r['work_id']].append(r)
    keys = sorted(works)
    if len(keys)!=expected_works:
        raise RuntimeError(f'{cell}作品数：实际{len(keys)}，规范{expected_works}')
    rng = rng_for(cell)
    allocation = {}
    if mode=='subset':
        chosen = sorted(rng.sample(keys,total))
        allocation = {w:1 for w in chosen}
        work_probability = total/len(keys)
        extra = []
    else:
        base, rem = divmod(total,len(keys))
        extra = sorted(rng.sample(keys,rem)) if rem else []
        allocation = {w:base+int(w in extra) for w in keys}
        work_probability = 1.0
    selected = []
    for wid,n in allocation.items():
        population = sorted(works[wid],key=lambda r:r['id'])
        if not 1<=n<=3 or n>len(population):
            raise RuntimeError(f'{cell}/{wid}配额不可用')
        strata={z:[r for r in population if r['old_stratum']==z] for z in ('FALSE_ROLE','OTHER')}
        chosen = []
        stratified = n>=2 and all(strata.values())
        if stratified:
            quotas={'FALSE_ROLE':1,'OTHER':1}
            if n==3:
                # 第三条在剩余总体中等概率决定所属层；冻结最终配额及其条件概率。
                remainder=[r for z,rs in strata.items() for r in rs[1:]]
                quotas[rng.choice(remainder)['old_stratum']]+=1
            for z,rs in strata.items():
                chosen.extend((r,quotas[z]/len(rs)) for r in rng.sample(rs,quotas[z]))
        else:
            chosen=[(r,n/len(population)) for r in rng.sample(population,n)]
        for row,pi in chosen:
            selected.append(dict(**row,cell=cell,work_population=len(population),
                work_quota=n,old_stratum_population=len(strata[row['old_stratum']]),
                sampling='stratified' if stratified else 'simple_random',
                pi_within_work=pi,pi_work=work_probability,pi=pi*work_probability))
    return selected,dict(cell=cell,population=len(rows),population_works=len(keys),sample_size=len(selected),
        allocation=allocation,extra_quota_works=extra,extra_quota_probability=(len(extra)/len(keys)),
        work_inclusion_probability=work_probability,
        probability_note='所有作品先入样的格，追加配额不是第二次作品入样；pi_work=1。条件于独立随机配额，按层内概率估计。')


def select(frame):
    specs=[]
    for a in ('C','S','S+A1'):specs.append(('G2c','N',a,50,24,'all',None))
    for c,a,n in [('X','S',20),('X','C',10),('d_T','S',20),('d_T','C',10),('T','S',15),('T','C',10),('F_w','S',15)]:
        specs.append(('G1',c,a,n,10,'all',None))
    specs.append(('G2a','L','S',20,16,'all',None))
    for a in ('S','S+A1'):specs.append(('G2d','d',a,10,96,'subset','constructed'))
    # 导演条件只有23部有正式续写；候选与原答案重合的条件在G中已排除。
    for c in ('D','A'):specs.append(('G2c',c,'S',5,23 if c=='D' else 24,'subset',None))
    sample=[]; cells=[]
    for spec in specs:
        selected,cell=sample_cell(frame,*spec);sample.extend(selected);cells.append(cell)
    if len(sample)!=300 or len({r['id'] for r in sample})!=300:
        raise RuntimeError('300条配额或身份去重失败')
    sample.sort(key=lambda r:r['id'])
    blind=rng_for('independent60').sample([r['id'] for r in sample],60)
    human=rng_for('human_calibration30').sample([r['id'] for r in sample],30)
    return dict(seed=SEED,cells=cells,selected=sample,independent60=blind,human_calibration30=human,
        human_adjudication='评审与独立复核后按协议优先级抽取，不预填标签。')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if (args.out/'factdiag7_sampling.json').exists():
        raise RuntimeError('已有抽样文件，先沿用检查，不重新抽样')
    frame=build_frame(args.source);sample=select(frame)
    save(args.out/'factdiag7_frame.json',frame);save(args.out/'factdiag7_sampling.json',sample)
    print(json.dumps({'frame':len(frame),'sample':len(sample['selected']),'cells':sample['cells']},ensure_ascii=False))


if __name__=='__main__':main()
