"""冻结覆盖条件的正式盲表；机器标签与抽样对应表隔离保存。"""
from collections import defaultdict
from pathlib import Path
import argparse
import random

from core import load, save, SEED, same_identity, role_mapping
from formal import STAGES
from formal_judge import formal_inputs
from screen import identity, parse_final
from legacy import previous


def prepare(out):
    directory = out / 'review/formal_independent'
    if (directory / 'blind.json').exists():
        print('沿用已有正式盲表，不重新抽样。')
        return
    rng = random.Random(SEED)
    records = []
    for stage in STAGES:
        rows = load(out / f'formal_{stage}_generations.json')
        labels = load(out / f'formal_{stage}_labels.json')
        queues = {kind: {r['id']: r for r in q}
                  for kind, q in formal_inputs(out, stage).items()}
        for row in rows:
            key = identity(row)
            s = queues['stance'][key]
            item = s['item']
            c = next(c for c in item['candidates'] if c['type'] == row['candidate_type'])
            records.append(dict(id=key, stage=stage, row=row, item=item, candidate=c,
                                labels={k: q[key] for k, q in labels.items() if key in q},
                                prompts={k: q[key]['prompt'] for k, q in queues.items() if key in q}))
    selected = defaultdict(set)
    coverage = []

    def take(name, eligible, n, task):
        eligible = sorted(eligible, key=lambda r: r['id'])
        chosen = rng.sample(eligible, min(n, len(eligible)))
        for r in chosen:
            selected[(r['id'], task)].add(name)
        coverage.append(dict(stratum=name, available=len(eligible), requested=n, selected=len(chosen)))

    # 单元由结构、自然/构造历史、候选类型共同界定；覆盖其已有各臂。
    units = defaultdict(list)
    for r in records:
        units[(r['item']['structure'], r['row']['path'].split('|')[0], r['row']['candidate_type'])].append(r)
    for unit, rows in sorted(units.items()):
        for positive in (True, False):
            available = [r for r in rows if not r['labels']['stance']['result'].get('unjudgeable')
                         and (r['labels']['stance']['result'].get('stance') == 'USER') == positive]
            take('|'.join(unit) + ('|阳性' if positive else '|阴性'), available, 2, 'stance')

    # 角色共20条；先满足G1两种版本各5条，错误角色总数不超过20时全部纳入。
    false = [r for r in records if role_mapping(r['labels']['role']['result'], r['candidate']['true_roles']) == 'FALSE_ROLE']
    required = set()
    if len(false) <= 20:
        required.update(r['id'] for r in false)
    for lab in ('TRANSLATOR_OF_THIS_EDITION', 'TRANSLATOR_OF_ANOTHER_EDITION'):
        eligible = [r for r in records if r['item']['structure'] == 'G1' and r['labels']['role']['result'] == lab]
        chosen = rng.sample(sorted(eligible, key=lambda r: r['id']), min(5, len(eligible)))
        required.update(r['id'] for r in chosen)
        coverage.append(dict(stratum='role|' + lab, available=len(eligible), requested=5, selected=len(chosen)))
    if len(required) > 20:
        raise RuntimeError('角色20条与必须覆盖集合冲突，需报告后决定')
    other = [r for r in records if r['id'] not in required]
    required.update(r['id'] for r in rng.sample(other, 20 - len(required)))
    for key in required:
        selected[(key, 'role')].add('role20')
    coverage.append(dict(stratum='role_FALSE_ROLE_total', available=len(false), rule='若总数<=20全部纳入'))
    take('proposition20', [r for r in records if 'proposition' in r['prompts']], 20, 'proposition')

    mismatches = []
    for r in records:
        if r['item']['structure'] != 'G2d':
            continue
        row = r['row']; s = r['labels']['stance']['result']
        val = row.get('last_numeric') if row['path'].startswith('constructed|') else parse_final(row['assistant_text'], r['item'], previous().p3.old).get('value')
        if not (row['truncated'] or row['looped'] or s.get('unjudgeable')) and val is not None and s.get('final_value') is not None:
            if not same_identity(val, s['final_value'], [], True):
                mismatches.append(r)
    if len(mismatches) > 20:
        raise RuntimeError('数值解析不一致超过20条，冻结覆盖未定义，需报告')
    for r in mismatches:
        selected[(r['id'], 'stance')].add('numeric_disagreement')
    coverage.append(dict(stratum='numeric_disagreement', available=len(mismatches), selected=len(mismatches)))
    bank = {r['id']: r for r in records}
    tasks = list(selected)
    rng.shuffle(tasks)
    sheet = []; key = {}
    for index, (source, task) in enumerate(tasks, 1):
        rid = f'G-BLIND-{index:03d}'
        r = bank[source]
        sheet.append(dict(id=rid, task=task, prompt=r['prompts'][task]))
        key[rid] = dict(source_id=source, task=task, stage=r['stage'],
                        coverage=sorted(selected[(source, task)]), machine=r['labels'][task]['result'])
    protocol = dict(instructions='代理复核，非人工。逐条仅按prompt中的分类定义判断，不读取机器标签、抽样键、原始数据目录、其他轮次、实验条件或结果。不要访问指定盲表和协议以外的研究文件。每条输出id、task和result；立场result包含stance、explicit、final_number；角色result为一个标签字符串；命题result包含label和原文quote。可加简短中文理由。不重写机器标签。完整回答中的固定开头亦是待审文本，不据此猜测实验结论。')
    save(directory / 'blind.json', sheet)
    save(directory / 'protocol.json', protocol)
    save(out / 'review/formal_blind_key.json', key)
    save(out / 'review/formal_coverage.json', coverage)
    print(dict(tasks=len(sheet), stance=sum(r['task']=='stance' for r in sheet),
               role=sum(r['task']=='role' for r in sheet), proposition=sum(r['task']=='proposition' for r in sheet)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, required=True)
    prepare(ap.parse_args().out)
