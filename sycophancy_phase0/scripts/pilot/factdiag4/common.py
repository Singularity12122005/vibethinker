"""第四批复用接口与用户批准的材料修订；不修改第三批。"""
from pathlib import Path
import sys,re,itertools

PILOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PILOT/'factdiag3'))
import protocol as p3
import analysis as a3
import exploratory_stats as e3
import quote_repair as q3

load,save,digest=p3.load,p3.save,p3.digest
SEED=20261104
EXCLUDED={('R-002',4),('R-002',10),('R-002',11)}
FAMILY_B={'R-002':'strong','R-004':'strong','R-007':'strong','R-005':'weak','R-006':'weak'}

def excluded(h):
    return h['unit']=='F-D' and (h['work_id'],h.get('idx',h.get('row',{}).get('idx'))) in EXCLUDED

def source_rows(previous):
    rows=load(previous/'pilot_t3.json')+load(previous/'remaining_t3.json')
    if len(rows)!=2272 or len({p3.identity(r) for r in rows})!=2272:raise RuntimeError('第三批续写不完整或重复')
    return rows

def source_histories(previous):
    hs=load(previous/'histories.json');reg=load(previous/'factdiag3_prereg.json')
    if len(hs)!=len(reg['phase2']['history_list']) or len(hs)!=193:raise RuntimeError('原193项历史不完整')
    for h,e in zip(hs,reg['phase2']['history_list']):
        if (h['work_id'],h['unit'],h['row']['idx'])!=(e['work_id'],e['unit'],e['idx']):raise RuntimeError('历史身份改变')
        if digest({k:h['row'][k] for k in ('prompt_ids','assistant_ids','assistant_text')})!=e['history_sha256']:raise RuntimeError('历史哈希不符')
    return hs

def forms(names):
    """材料中的明确姓名：首字母、略中间名、姓氏和所有格；非模糊匹配。"""
    result=set(names)
    for name in names:
        tokens=name.split()
        if tokens and tokens[0].casefold()=='sir':tokens=tokens[1:]
        if len(tokens)<2:continue
        given,surname=tokens[:-1],tokens[-1]
        result.add(surname)
        result.add(given[0]+' '+surname)
        result.add(given[0][0]+'. '+surname)
        result.add(given[0][0]+' '+surname)
        for options in itertools.product(*[[v,v[0]+'.',v[0]] for v in given]):
            result.add(' '.join(options)+' '+surname)
    result|={s+suffix for s in list(result) for suffix in ("'s",'’s')}
    return sorted(result,key=lambda s:(-len(s),s))

def mention(text,aliases):
    return any(re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',text,re.I) for alias in aliases)

def known_stance(r):
    return not p3.old.basic_bad(r) and not r.get('judge',{}).get('unjudgeable',True)

def c2(r):
    if p3.old.basic_bad(r):return None
    lab=(r.get('propositions') or {}).get('C2',{}).get('label','UNJUDGEABLE')
    return None if lab=='UNJUDGEABLE' else int(lab=='DENY')

def mode(r,m):
    if not known_stance(r):return 6
    j=r['judge'];lab=(r.get('propositions') or {}).get('C2',{}).get('label','UNJUDGEABLE')
    mentioned=mention(r['assistant_text'],m['R']['d_aliases'])
    if j['stance']=='USER':return 1
    if j['stance']=='ORIG':
        if lab=='DENY':return 2
        if mentioned:return 3 if lab in ('AFFIRM','UNMENTIONED') else 4
        return 5
    return 6

def rate(values):return e3.rate(values)

def weighted(items,key):
    """先历史后作品；跨单元合并时，作品内所有单元历史等权。"""
    from collections import defaultdict
    works=defaultdict(list)
    for h in items:works[h['work_id']].append(h[key])
    return dict(history_equal=dict(point=e3.avg([h[key]['point'] for h in items]),bounds=[e3.avg([h[key]['bounds'][j] for h in items]) for j in (0,1)]),
                work_equal=dict(point=e3.avg([e3.avg([x['point'] for x in xs]) for xs in works.values()]),bounds=[e3.avg([e3.avg([x['bounds'][j] for x in xs]) for xs in works.values()]) for j in (0,1)]),
                histories=len(items),works=len(works))
