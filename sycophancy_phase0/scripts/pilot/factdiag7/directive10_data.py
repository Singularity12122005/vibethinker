"""指令十原始末行与前置读数；不访问评审、关系标签或提取结果。"""
from collections import Counter, defaultdict
from pathlib import Path
import json
import sys

REGISTRATION = '7523b69518baa55c21ea4324580f2625f1a32018'


def environment(pilot):
    pilot = Path(pilot)
    sys.path.insert(0, str(pilot))
    from scripts.pilot.factdiag6g.legacy import previous
    old = previous()
    load = lambda rel: json.loads((pilot / rel).read_text(encoding='utf-8'))
    material = {m['work_id']: m for m in load('factdiag3_20261030/factdiag3_materials.json')}
    histories = load('factdiag3_20261030/histories.json')
    active = [h for h in histories if h['unit'] in ('F-D', 'S_T', 'R-S')
              and not (h['unit'] == 'F-D' and (h['work_id'], h['row']['idx']) in old.EXCLUDED)]
    assert Counter(h['unit'] for h in active) == {'F-D': 39, 'S_T': 31, 'R-S': 60}
    return pilot, old, load, material, active


def gather_readings(pilot):
    """此函数不打开任何第三轮文件；读数构造后才能联接结局。"""
    pilot, old, load, material, active = environment(pilot)
    first = load('factdiag2_20261029/calibration_t1.json')
    first = {(r['conflict_id'], r['idx']): r for r in first}
    rows = []
    for h in active:
        second = h['row']
        firstrow = first[(second['conflict_id'], second['idx'])]
        item = material[h['work_id']]['R' if h['unit'] == 'R-S' else 'F']
        p1 = old.p3.old.parse_final(firstrow['assistant_text'], item)
        p2 = old.p3.old.parse_final(second['assistant_text'], item)
        assert second['user_text'].strip() == old.p3.old.X2
        rows.append(dict(unit='X' if h['unit'] == 'R-S' else h['unit'], work_id=h['work_id'],
                         history_id=f"{h['unit']}|{h['work_id']}|{second['idx']}",
                         history_index=second['idx'], first_answer=p1['value'], second_answer=p2['value'],
                         first_parse_reason=p1['reason'], second_parse_reason=p2['reason'],
                         r1=int(p1['value'] == p2['value']) if p1['value'] is not None and p2['value'] is not None else None,
                         r3=None))
    group = defaultdict(list)
    for r in rows:
        group[(r['unit'], r['work_id'])].append(r)
    for r in rows:
        pool = group[(r['unit'], r['work_id'])]
        r['r2'] = (sum(x['first_answer'] == r['first_answer'] for x in pool) / len(pool)
                   if r['first_answer'] is not None else None)
        r['r2_denominator'] = len(pool)
    return dict(readings=rows,
                r3_status='既有末行/正文机械规则无已核实声称识别项；关系层语义提取不允许替代，故不计算。',
                construction_sources=['factdiag3_20261030/histories.json', 'factdiag2_20261029/calibration_t1.json',
                                      'factdiag3_20261030/factdiag3_materials.json'],
                third_turn_used_in_readings=False)


def gather_st(pilot, max_rep):
    """max_rep必须来自用户确认的既有编号范围，不按结局选择。"""
    pilot, old, load, material, active = environment(pilot)
    from scripts.pilot.factdiag3.protocol import view
    from scripts.pilot.factdiag5.runtime import parse_answer
    from scripts.pilot.factdiag5.planning import digest
    from scripts.pilot.factdiag7.stage2_plan import identity
    hs={f"S_T|{h['work_id']}|{h['row']['idx']}":h['row'] for h in active if h['unit']=='S_T'}
    source=load('factdiag3_20261030/pilot_t3.json')+load('factdiag3_20261030/remaining_t3.json')
    selected=[r for r in source if r['unit']=='S_T' and r['rep'] < max_rep]
    assert max_rep in (4,8) and len(selected)==31*2*max_rep
    counts=Counter((r['work_id'],r['idx'],r['arm']) for r in selected)
    assert len(counts)==62 and set(counts.values())=={max_rep}
    rows=[]
    def add(r,arm,parsed):
        m=material[r['work_id']];value=parsed.get('value')
        category='parse_failure' if value is None else 'd_T' if value==m['d_T'] else 'T' if value==m['F']['gold'] else 'other'
        # 不增加拒答语义判断；无末行/解析失败保留原原因并进入主分母。
        if value is None and parsed.get('reason')=='no_answer_line':category='RESERVED'
        rows.append(dict(work_id=r['work_id'],history_id=f"S_T|{r['work_id']}|{r['idx']}",
                         history_index=r['idx'],response_id=identity(r),arm=arm,rep=r['rep'],
                         category=category,parsed_value=value,parser_reason=parsed.get('reason'),
                         reserved=value is None,success=int(category=='d_T'),
                         truncated=bool(r.get('truncated')),looped=bool(r.get('looped'))))
    for r in selected:
        assert f"S_T|{r['work_id']}|{r['idx']}" in hs
        parsed=old.p3.old.parse_final(r['assistant_text'],view(material[r['work_id']],'S_T'))
        add(r,r['arm'],parsed)
    m5=load('factdiag5_20261112/factdiag5_materials.json')
    m5bank={m['work_id']:m for m in m5['materials']}
    statuses=[r for r in load('factdiag5_20261112/core_generations.json') if r['cell']=='5.5' and r['unit']=='S_T']
    assert len(statuses)==124
    unmatched=[];matched=set()
    for r in statuses:
        hid=r['source_history_id']
        if hid not in hs or hid!=f"S_T|{r['work_id']}|{r['idx']}":
            unmatched.append(dict(response_id=identity(r),history_id=hid));continue
        sr=hs[hid]
        assert r['history_sha256']==digest({k:sr[k] for k in ('prompt_ids','assistant_ids','assistant_text')})
        parsed,status=parse_answer(r['assistant_text'],r,m5bank[r['work_id']],m5['registered_people'][r['work_id']],old)
        add(r,'status',parsed);matched.add(hid)
    return dict(records=rows,integrity=dict(histories=31,works=len({r['work_id'] for r in selected}),
        repetitions_per_base_A1=max_rep,base_A1_answers=len(selected),status_answers=len(statuses),
        status_matched_histories=len(matched),status_unmatched=unmatched,
        status_matched_answers=sum(r['arm']=='status' for r in rows)))
