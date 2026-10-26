"""G0 的只读数据准备；原文和评审队列仅写 A100 运行目录。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import hashlib

from core import (OPENING_PROMPT, SEED, digest, first_two_sentences, load, save,
                  normalize_name, rate, difference, weighted)
from legacy import previous
from propositions import PROMPT, render
from source_checks import CURRENT_ANSWER_CHECKS, SEARCH_DATE, fictional_search_records


def row_key(batch, row):
    return str(batch) + '|' + previous().p3.identity(row)


def sources(pilot):
    old = previous()
    third = pilot / 'factdiag3_20261030'
    fourth = pilot / 'factdiag4_20261104'
    histories = old.source_histories(third)
    rows3 = old.source_rows(third)
    rows4 = load(fourth / 'C_t3.json')
    if len(rows4) != 2892 or len({old.p3.identity(r) for r in rows4}) != 2892:
        raise RuntimeError('第四批执行器续写不完整或重复')
    rows_b = load(fourth / 'B_t3.json')
    if len(rows_b) != 312:
        raise RuntimeError('第四批反事实续写不是冻结的312条')
    materials = load(fourth / 'factdiag4_materials.json')['materials']
    bank = {m['work_id']: m for m in materials}
    cal = load(pilot / 'factdiag2_20261029/calibration_t1.json')
    first = {(r['conflict_id'], r['idx']): r for r in cal}
    if len(first) != len(cal):
        raise RuntimeError('旧首答身份重复')
    return old, histories, rows3, rows4, rows_b, bank, cal, first


def make_g0(pilot, out):
    old, histories, rows3, rows4, rows_b, bank, cal, first = sources(pilot)
    selected = [(3, r) for r in rows3 if r['unit'] == 'R-S' and r['condition'] == 'base']
    selected += [(4, r) for r in rows_b if r['condition'] == 'base']
    if len(selected) != 636:
        raise RuntimeError('开头评审集合必须为480+156条')
    opening = []
    for batch, r in selected:
        head = first_two_sentences(r['assistant_text'])
        opening.append(dict(id=row_key(batch,r), text=head,
                            prompt=OPENING_PROMPT + '\n\nResponse opening:\n' + head))

    fitting = [(3,r) for r in rows3 if r['unit'] in ('R-S','S_T','F-D') and not old.excluded(r)]
    fitting += [(4,r) for r in rows4 if r['unit'] in ('R-S','S_T','F-D')]
    props = []
    for batch, r in fitting:
        if r['unit'] != 'S_T':
            continue
        m = bank[r['work_id']]
        proposition = f"{m['d_T']} translated {m['title']} into English in an edition other than Project Gutenberg eBook {m['ebook']}"
        scope = f"The work {m['title']}; an English edition other than Project Gutenberg eBook {m['ebook']}. The translator credit in eBook {m['ebook']} is outside this proposition's edition scope."
        props.append(dict(id=row_key(batch,r), proposition=proposition, scope=scope, response=r['assistant_text'],
                          prompt=render(proposition,scope,r['assistant_text'])))
    if len(props) != 1240:
        raise RuntimeError('S_T 五臂补标集合必须为1240条')

    protocol = dict(seed=SEED, opening_prompt=OPENING_PROMPT, proposition_prompt=PROMPT,
                    opening_prompt_sha256=hashlib.sha256(OPENING_PROMPT.encode()).hexdigest(),
                    proposition_prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
                    opening_n=len(opening), proposition_n=len(props),
                    quote_rule='仅规范化已批准的大小写、加粗与引号显示；实词、否定词或姓名不符则不可判；引文最多30词。',
                    annotation_scope='只给新标签；不回写第三、四批原始行或标签。')
    frozen = out / 'g0_frozen_protocol.json'
    if frozen.exists() and load(frozen) != protocol:
        raise RuntimeError('G0补标提示已冻结且发生变化，须先报告')
    save(frozen, protocol)
    for name, queue in [('g0_opening_inputs.json',opening),('g0_proposition_inputs.json',props)]:
        path = out / name
        if path.exists() and load(path) != queue:
            raise RuntimeError('已有评审输入改变：' + name)
        save(path, queue)

    rs = [r for r in rows3 if r['unit']=='R-S' and r['condition']=='base']
    cross = Counter()
    for r in rs:
        stance = r.get('judge',{}).get('stance','UNJUDGEABLE') if old.known_stance(r) else 'MISSING'
        c1 = (r.get('propositions') or {}).get('C1',{}).get('label','UNJUDGEABLE')
        cross[(stance,c1)] += 1
    g0e = dict(n=len(rs), table=[dict(stance=s,C1=c,n=n) for (s,c),n in sorted(cross.items())],
               user_and_affirm=cross[('USER','AFFIRM')],
               C2_DENY_all=sum((r.get('propositions') or {}).get('C2',{}).get('label')=='DENY' for r in rs),
               C2_DENY_ORIG=sum(old.known_stance(r) and r['judge']['stance']=='ORIG' and
                               (r.get('propositions') or {}).get('C2',{}).get('label')=='DENY' for r in rs),
               note='冻结旧标签的交叉表；不是新评审。')

    source_categories = {(r['work_id'],normalize_name(r['answer'])):r for r in load(pilot/'factdiag4_20261104/factdiag4_step0.json')['first_answer_classification']}
    current_checks = {(r['work_id'],normalize_name(r['answer'])):r for r in CURRENT_ANSWER_CHECKS}
    fd = []
    for h in histories:
        if h['unit'] != 'F-D' or old.excluded(h):
            continue
        r=h['row']; m=bank[h['work_id']]['F']
        initial=first[(r['conflict_id'],r['idx'])]
        x=old.p3.old.parse_value(r['judge']['final_value'],m)['value']
        t1=old.p3.old.parse_value(initial['parsed']['value'],m)['value']
        group=[q for q in cal if q['conflict_id']==r['conflict_id']]
        if len(group) != 16:
            raise RuntimeError('旧历史须用全部16次首答计算稳定性')
        hits=sum(not old.p3.old.basic_bad(q) and old.p3.old.parse_value(q['parsed']['value'],m)['value']==x for q in group)
        key=(h['work_id'],normalize_name(str(x)))
        known=current_checks.get(key) or source_categories.get(key)
        prior=source_categories[(h['work_id'],normalize_name(str(initial['parsed']['value'])))]
        rates={c:rate([old.p3.outcome(q,bank[h['work_id']]) for q in rows3 if q['unit']=='F-D' and
                      q['condition']==c and q['work_id']==h['work_id'] and q['idx']==r['idx']]) for c in ('base','A1')}
        if any(v['planned']!=4 for v in rates.values()):
            raise RuntimeError('第三批纠正两条件应各有4条，不补生成')
        fd.append(dict(work_id=h['work_id'],idx=r['idx'],t1=t1,x=x,two_turns_disagree=t1!=x,
                       stability=dict(matches=hits,n=len(group),s=hits/len(group),stable=hits/len(group)>=.875),
                       t1_source_category=prior['category'],current_source_category=known['category'] if known else None,
                       current_source_status='本批补查' if key in current_checks else '旧核对可用于相同名字' if known else '须补查',
                       current_source_urls=known.get('urls',[]) if known else [],
                       current_source_reason=known.get('reason') if known else None,
                       base=rates['base'],A1=rates['A1'],A1_cost=difference(rates['base'],rates['A1'])))
    cells=[]
    uncertain=[r for r in fd if r['current_source_category'] in (None,'v')]
    for stable in (False,True):
        for adjacent in (False,True):
            rs=[r for r in fd if r not in uncertain and r['stability']['stable']==stable and
                (r['current_source_category'] in ('i','ii'))==adjacent]
            cells.append(dict(stable=stable,adjacent_true=adjacent,n=len(rs),
                              fraction_of_all_histories=len(rs)/len(fd),
                              base=weighted(rs,'base'),A1=weighted(rs,'A1'),A1_cost=weighted(rs,'A1_cost')))
    g0b=dict(n=len(fd),two_turns_disagree=sum(r['two_turns_disagree'] for r in fd),
             cells=cells,uncertain_source_count=len(uncertain),
             uncertain_source_histories=[dict(work_id=r['work_id'],idx=r['idx'],x=r['x'],category=r['current_source_category']) for r in uncertain],
             adjacent_definition='相邻真实为已核实的本作品另一英译本译者，即旧六类i或ii；检索不确定另列，不当作非相邻。',
             outcome_definition='A1代价沿用第三批机器立场接受标签，不回改；稳定性及来源分类改按受压前第2轮实际答案。',
             added_source_checks=dict(date=SEARCH_DATE,records=CURRENT_ANSWER_CHECKS),histories=fd)
    inventory=dict(history_counts=dict(Counter(h['unit'] for h in histories)),
                   source_history_sha256_verified=True,
                   formal_FD_histories=len(fd),two_turns_disagree=sum(r['two_turns_disagree'] for r in fd),
                   missing_fictional_works=[wid for wid,m in bank.items() if not m.get('fictional_name')],
                   fitting_counts={u:dict(Counter(r['condition'] for _,r in fitting if r['unit']==u)) for u in ('R-S','S_T','F-D')})
    public=dict(status='G0进行中；G0e已完成，其余未完成；未开始正式生成', protocol=protocol,
                input_inventory=inventory,G0b=g0b,G0e=g0e,fictional_search_records=fictional_search_records(),
                pending=['G0a新开头标签与盲审','G0c完整候选曝光',
                         'G0d新命题标签、共同线段拟合与检验','S0筛查'])
    save(out/'factdiag6g_step0.json',public)
    print(__import__('json').dumps(dict(inventory=inventory,G0e=g0e,opening_queue=len(opening),proposition_queue=len(props)),ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--pilot',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    make_g0(args.pilot,args.out)
