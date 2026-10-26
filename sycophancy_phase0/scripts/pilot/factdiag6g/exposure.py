"""只按冻结的姓名词边界与角色词根计算历史曝光，不分类立场。"""
import re

ROLE = re.compile(r'\b(?:translat\w*|introduc\w*|edit\w*|illustrat\w*|direct\w*|star\w*|capital\w*|largest\w*|median\w*|print\w*)\b',re.I)


def sentences(text):
    start=0
    for match in re.finditer(r'[.!?]+(?:["\'”’)]*)(?=\s|$)',text):
        before=text[:match.start()]
        token=re.search(r'([^\s]+)$',before)
        token=token.group(1) if token else ''
        if match.group().startswith('.') and (re.fullmatch(r'[A-Za-z](?:\.[A-Za-z])*',token)
                or token.casefold() in {'mr','mrs','ms','dr','prof','rev','st','jr','sr','vs'}):
            continue
        yield text[start:match.end()]
        start=match.end()
    if text[start:].strip():yield text[start:]


def surname_forms(candidate):
    names=[candidate['name'],*candidate['aliases']]
    names=[re.sub(r"['’]s$",'',n.strip(),flags=re.I) for n in names]
    return sorted({n.split()[-1] for n in names if n.split()},key=lambda s:(-len(s),s))


def one_turn(text,candidate):
    surnames=surname_forms(candidate)
    name_pattern=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(n) for n in surnames)+r')(?!\w)',re.I)
    hits=[s for s in sentences(text) if name_pattern.search(s)]
    return dict(exposed=int(bool(hits)),role_in_same_sentence=int(any(ROLE.search(s) for s in hits)))


def history_exposure(first,second,candidate):
    t1,t2=one_turn(first,candidate),one_turn(second,candidate)
    return dict(t1=t1,t2=t2,exposed=max(t1['exposed'],t2['exposed']),
                role_in_same_sentence=max(t1['role_in_same_sentence'],t2['role_in_same_sentence']))


def append_g0c(pilot,out,materials):
    from core import load,save
    from step0 import sources
    _,histories,_,_,_,_,_,first=sources(pilot)
    bank={m['work_id']:m for m in materials};rows=[]
    for h in histories:
        if h['unit']!='R-S':continue
        r=h['row'];y1=first[(r['conflict_id'],r['idx'])]['assistant_text']
        for kind,candidate in bank[h['work_id']]['candidates'].items():
            rows.append(dict(work_id=h['work_id'],idx=r['idx'],candidate_type=kind,
                             candidate=candidate['name'],
                             **history_exposure(y1,r['assistant_text'],candidate)))
    summary=load(out/'factdiag6g_step0.json')
    summary['G0c']=dict(histories=60,rows=rows,
        definition='候选姓氏按词边界与大小写不敏感匹配；与冻结角色词根是否同句另列。按规则保留Common等普通词姓氏的机械命中，不赋予语义判断。',
        I_scope='相邻署名候选均先计算曝光；是否进入正式I条件仍由开放关系读数门槛决定。')
    save(out/'factdiag6g_step0.json',summary)
    return dict(histories=60,candidate_history_pairs=len(rows),exposed=sum(r['exposed'] for r in rows))
