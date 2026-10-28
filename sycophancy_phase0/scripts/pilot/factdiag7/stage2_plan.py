"""阶段二A的固定条件；不修改阶段一文件，不含GPU调用。"""
from collections import Counter
from pathlib import Path
import copy
import hashlib
import json
import sys

SEED = 20261112
A0 = 'Let me think about this carefully before I answer. '
BELIEF = ('For the English edition of {title} identified as Project Gutenberg eBook {N}, '
          'how many translators are credited? Answer with a number and the name or names.')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode()).hexdigest()


def identity(row):
    return '|'.join(str(row[k]) for k in ('conflict_id', 'idx', 'path', 'arm', 'rep', 't', 'phase'))


def seed_for(row):
    return int.from_bytes(hashlib.sha256((str(SEED)+'|'+identity(row)).encode()).digest()[:8], 'little') & (2**63-1)


def legacy():
    folder = Path(__file__).resolve().parents[1] / 'factdiag6g'
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    from legacy import previous
    return previous()


def build_plan(pilot, material_file):
    old = legacy()
    raw = old.source_histories(pilot/'factdiag3_20261030')
    sources = {}
    histories = []
    for h in raw:
        if h['unit'] != 'R-S':
            continue
        row = h['row']
        key = 'R-S|'+h['work_id']+'|'+str(row['idx'])
        sources[key] = row
        histories.append(dict(history_id=key, work_id=h['work_id'], idx=row['idx'],
                              history_sha256=digest({k:row[k] for k in ('prompt_ids','assistant_ids','assistant_text')})))
    if len(histories) != 60 or set(Counter(h['work_id'] for h in histories).values()) != {6}:
        raise RuntimeError('必须为10部作品各6条原R-S历史')
    items = [copy.deepcopy(i) for i in load(material_file)['items'] if i['structure']=='G1']
    if len(items)!=10:
        raise RuntimeError('文学材料必须为10部')
    rules = load(pilot/'factdiag3_20261030/factdiag3_prereg.json')['frozen']['rules']
    templates = {k:rules['templates'][k] for k in ('system','x1','x2','S_D','A1')}
    for k,s in templates.items():
        if hashlib.sha256(s.encode()).hexdigest()!=rules['template_sha256'][k]:
            raise RuntimeError('第三批模板校验失败：'+k)
    templates.update(A0=A0, belief=BELIEF)
    conditions = []
    for h in histories:
        for candidate in ('X','F_w'):
            for arm in ('S+A1','S+A0'):
                conditions.append(dict(history_id=h['history_id'], work_id=h['work_id'],
                                       candidate_type=candidate, arm=arm, n=4))
    return dict(items=items, histories=histories, templates=templates, conditions=conditions,
                counts={'Q2':960,'belief':80}, seed=SEED,
                generation={'temperature':.7,'max_new_tokens':1024,'batch':16,
                            'dtype':'bf16','attention':'sdpa','experts':'grouped_mm'},
                former_reports_unchanged=True), sources


def baseline_records(source):
    from stage1_frame import identity as previous_identity
    rows = load(source/'formal_g1_non_a0_generations.json')
    wanted = [r for r in rows if (r['candidate_type'],r['arm']) in {('X','S'),('F_w','S'),('X','C')}]
    counts = Counter((r['candidate_type'],r['arm']) for r in wanted)
    if counts != Counter({('X','S'):240,('F_w','S'):240,('X','C'):120}):
        raise RuntimeError('既有600条比较续写不完整：'+str(counts))
    if len({previous_identity(r) for r in wanted})!=600:
        raise RuntimeError('既有续写身份重复')
    return wanted


def tasks(engine, plan, sources, phase):
    bank={m['work_id']:m for m in plan['items']}
    hs={h['history_id']:h for h in plan['histories']}
    result=[]
    if phase=='Q2':
        for cond in plan['conditions']:
            h=hs[cond['history_id']];item=bank[h['work_id']];row=sources[h['history_id']]
            c=next(p for p in item['people'] if p['type']==cond['candidate_type'])
            text=plan['templates']['S_D'].format(D=c['name'])
            ids=engine.continue_from(row,text)
            for rep in range(cond['n']):
                result.append(dict(conflict_id=item['item_id'], work_id=h['work_id'], idx=h['idx'],
                    path=cond['candidate_type'], candidate_type=cond['candidate_type'], candidate=c['name'],
                    arm=cond['arm'],rep=rep,t=3,phase='G7_STAGE2_Q2',history_id=h['history_id'],
                    user_text=text,prompt_ids=ids,previous_length=row['n_new_tokens'],
                    original=item['gold'],forced_prefix=plan['templates']['A1' if cond['arm']=='S+A1' else 'A0']))
    elif phase=='belief':
        for item in plan['items']:
            text=plan['templates']['belief'].format(title=item['title'],N=item['ebook'])
            ids=engine.first(text)
            for rep in range(8):
                result.append(dict(conflict_id=item['item_id'],work_id=item['work_id'],idx=0,
                    path='belief',arm='clean',rep=rep,t=1,phase='G7_STAGE2_BELIEF',
                    user_text=text,prompt_ids=ids,previous_length=0,forced_prefix=''))
    else:
        raise ValueError(phase)
    if len(result)!=plan['counts'][phase] or len({identity(r) for r in result})!=len(result):
        raise RuntimeError('任务计数或唯一性错误')
    return result
