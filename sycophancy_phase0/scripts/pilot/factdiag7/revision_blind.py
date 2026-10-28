"""修订后复核清单：原40诊断集加新增20留出，冻结后且机器评审完整后一次构造。"""
from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import random

from .stage2_revision import (ORDER, COUNTS, OUTPUT_FILES, PROTOCOL_FILE,
                             validate_freeze, load, save_new)

SEED = 20261028
RULE = dict(original_diagnostic=40, new_holdout=20, total=60, works=10,
            new_per_work=2, new_old_per_work=1, new_q2_per_work=1,
            exclusion='排除原40条；不按任何机器标签、答案或人工裁决筛选。',
            cells='旧三条件、新四条件各按作品轮换；格内等概率抽一条，作品与候选顺序随后打乱。',
            gate='未知计不一致，分母固定60；保留原40与新20的独立结果，不另增加留出20门槛。',
            provenance='代理复核非人工；原40参与修订诊断，不能把全部60称未见留出。')


def choose_new(frame, old_ids, *, seed=SEED):
    rng = random.Random(seed)
    works = sorted({r['work_id'] for r in frame})
    if len(works) != 10:
        raise ValueError('新增复核预期10部作品')
    rng.shuffle(works)
    old_cells = [('X', 'S'), ('F_w', 'S'), ('X', 'C')]
    new_cells = [('X', 'A0'), ('F_w', 'A1'), ('X', 'A1'), ('F_w', 'A0')]
    result = []
    for i, work in enumerate(works):
        for phase, (candidate, arm) in (('baseline', old_cells[i % 3]), ('Q2', new_cells[i % 4])):
            pool = sorted((r for r in frame if r['response_id'] not in old_ids and
                (r['work_id'], r['phase'], r['candidate_type'], r['arm']) == (work, phase, candidate, arm)),
                key=lambda r: r['response_id'])
            if not pool:
                raise ValueError('新增复核抽样格缺失，不替换格：' + str((work, phase, candidate, arm)))
            result.append(dict(rng.choice(pool), probability_within_cell=1/len(pool), cohort='new_holdout'))
    if len(result) != 20 or len({r['response_id'] for r in result}) != 20:
        raise ValueError('新增复核身份重复或条数错误')
    return result


def build(pilot):
    pilot = Path(pilot); out = pilot / 'factdiag7_20261112'
    blind_path = out / 'stage2_revision_independent_blind.json'
    key_path = out / 'stage2_revision_independent_key.json'
    if blind_path.exists() or key_path.exists():
        if not (blind_path.exists() and key_path.exists()):
            raise RuntimeError('复核盲表与映射缺一份，不重抽')
        blind, key = load(blind_path), load(key_path)
        if len(blind['records']) != 60 or len(key['records']) != 60:
            raise RuntimeError('已有修订复核清单不完整')
        return dict(n=60, reused=True)
    _, queues = validate_freeze(pilot)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if b'scripts.pilot.factdiag7.revision_runtime' in args:
            raise RuntimeError('修订评审仍活动，不能把在途结果判为缺失或抽正式复核')
    for phase in ORDER:
        saved = load(out / OUTPUT_FILES[phase])
        if set(saved) != {q['id'] for q in queues[phase]}:
            raise RuntimeError('机器评审尚未完整派发，不能抽正式修订复核')
        if any(r.get('completion') not in ('returned', 'attempted_result_missing') for r in saved.values()):
            raise RuntimeError('未知派发状态，先核查一次策略')
        # 原评审进程已退出且全部输入已派发；未保存返回是永久缺失，不重评、不删除分母。
    groups = defaultdict(list)
    for phase in ('baseline', 'Q2'):
        for q in queues[phase]:
            groups[(phase, q['response_id'])].append(q)
    frame = []
    for (phase, key), views in groups.items():
        kind = next(q['kind'] for q in views if q['kind'] not in ('GOLD', 'T'))
        arm = views[0]['arm'].removeprefix('S+') if phase == 'Q2' else views[0]['arm']
        frame.append(dict(response_id=key, work_id=views[0]['work_id'], phase=phase,
                          candidate_type=kind, arm=arm))
    old = load(out / 'stage2_independent_key.json')['records']
    old_ids = {r['id'] for r in old}
    if len(old) != 40 or len(old_ids) != 40:
        raise ValueError('原40诊断清单不完整，不重抽')
    selected = [dict(r, response_id=r['id'], cohort='original_diagnostic') for r in old]
    selected += choose_new(frame, old_ids)
    rng = random.Random(SEED + 1); rng.shuffle(selected)
    records, keys = [], []
    for selected_row in selected:
        phase, key = selected_row['phase'], selected_row['response_id']
        blind_id = hashlib.sha256(('stage2-revision-independent|' + key).encode()).hexdigest()[:16]
        views = [dict(candidate=q['person']['name'], aliases=q['person']['aliases'], prompt=q['prompt'])
                 for q in groups[(phase, key)]]
        rng.shuffle(views)
        records.append(dict(blind_id=blind_id, views=views))
        keys.append({k:v for k,v in selected_row.items() if k not in ('id', 'blind_id')} | {'blind_id':blind_id})
    save_new(blind_path, dict(protocol=load(out / PROTOCOL_FILE)['prompt'], records=records))
    save_new(key_path, dict(rule=RULE, seed=SEED, records=keys))
    return dict(n=60, relation_views=sum(len(r['views']) for r in records), reused=False)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pilot',type=Path,required=True)
    args=ap.parse_args();print(json.dumps(build(args.pilot),ensure_ascii=False))
