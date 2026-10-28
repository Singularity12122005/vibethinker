"""本批主模型词元合计；评审输出与复用的旧续写不进入新生成预算。"""
from pathlib import Path
import json


def used_tokens(pilot):
    pilot=Path(pilot)
    files=list((pilot/'factdiag7_20261112').glob('stage2_*_generations.json'))
    fifth=pilot/'factdiag5_20261112/core_generations.json'
    if fifth.exists():files.append(fifth)
    counts={}
    for path in files:
        rows=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows,list):raise RuntimeError('主模型生成文件须为列表：'+str(path))
        counts[str(path.relative_to(pilot))]=sum(int(r['n_new_tokens']) for r in rows)
    return {'total':sum(counts.values()),'files':counts}


def check_next_batch(pilot,n,max_new_tokens=1024):
    report=used_tokens(pilot)
    if report['total']+n*max_new_tokens>1500000:
        raise RuntimeError('下一批可能越过150万主模型新词元，暂停请用户决定；不删格。当前='+str(report['total']))
    if report['total']>=1200000:print('主模型新词元120万预警：'+str(report['total']),flush=True)
    return report
