"""把已核对材料变为读数输入。这里只准备输入，不读取正式续写。"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse

from core import load,save,same_identity
from legacy import previous


def literature(out,pilot):
    draft=load(out/'g1_candidates_draft.json')['materials']
    bank={m['work_id']:m for m in draft}
    items=[]
    for material in draft:
        m=material['legacy_material'];n=m['ebook']
        candidates=[]
        for kind,c in material['candidates'].items():
            c=dict(c,type=kind)
            if kind=='T':c['true_role_phrase']=f'the English translator credited in Project Gutenberg eBook {n}, an edition of'
            elif kind=='d_T':c['true_role_phrase']=f'the translator of an English edition other than Project Gutenberg eBook {n} of'
            elif kind=='I':
                role=c['true_roles'][0]
                relation={'ILLUSTRATOR':'the illustrator','EDITOR_OR_INTRODUCER':'the writer of the introduction'}[role]
                c['true_role_phrase']=f'{relation} credited in Project Gutenberg eBook {n}, an edition of'
            candidates.append(c)
        items.append(dict(item_id=m['work_id']+'-R',work_id=m['work_id'],structure='G1',
            subject=m['title'],question_en=m['R']['question_en'],gold=m['R']['gold'],
            gold_aliases=m['R']['gold_aliases'],answer_format='entity',candidates=candidates,
            policy_pairs=[dict(x=m['R']['gold'],d=c['name'],reference=c['type']) for c in candidates],
            note='关系读数的主体是作品标题；精确版本知识由诊断问句显式区分。'))
    old=previous()
    histories=old.source_histories(pilot/'factdiag3_20261030')
    group=defaultdict(list)
    for h in histories:
        if h['unit'] in ('S_T','F-D') and not old.excluded(h):group[h['work_id']].append(h)
    excluded=[];mode_status=[]
    for wid,hh in sorted(group.items()):
        m=bank[wid]['legacy_material'];f=m['F'];pairs=[];wrong=[]
        for h in hh:
            raw=h['row']['judge']['final_value']
            parsed=old.p3.old.parse_value(raw,f)['value']
            if parsed is None:raise RuntimeError('已有历史当前答案不可解析：'+wid)
            x=raw
            for name,aliases in [(f['gold'],f['gold_aliases']),(m['d_T'],m['d_T_aliases'])]:
                if same_identity(parsed,name,aliases):x=name;break
            d=m['d_T'] if h['unit']=='S_T' else f['gold']
            aliases=m['d_T_aliases'] if h['unit']=='S_T' else f['gold_aliases']
            if same_identity(x,d,aliases):
                excluded.append(dict(work_id=wid,idx=h['row']['idx'],unit=h['unit'],reason='d等于第2轮实际答案'))
                continue
            pairs.append(dict(x=x,d=d,reference=f"{h['unit']}|{wid}|{h['row']['idx']}"))
            if h['unit']=='F-D':wrong.append(x)
        # 校正与保护的当前问题同为译者题，使用这一题的k，不使用作者题或旧L。
        candidate=dict(type='d_T',**bank[wid]['candidates']['d_T'])
        candidate['true_role_phrase']=f"the translator of an English edition other than Project Gutenberg eBook {m['ebook']} of"
        items.append(dict(item_id=wid+'-F',work_id=wid,structure='G1',subject=m['title'],
            question_en=f['question_en'],gold=f['gold'],gold_aliases=f['gold_aliases'],answer_format='entity',
            candidates=[candidate],policy_pairs=pairs))
        counts=Counter(wrong)
        if counts:
            top=max(counts.values());modes=sorted(x for x,n in counts.items() if n==top)
            mode_status.append(dict(work_id=wid,counts=dict(counts),modes=modes,
                                    status='并列众数，待用户决定' if len(modes)>1 else '唯一众数'))
    return items,dict(policy_excluded=excluded,mode_status=mode_status)


def adaptation():
    from adaptation_materials import build
    items=build()
    for item in items:
        for c in item['candidates']:
            if c['type']=='D':c['true_role_phrase']='the director of a film adaptation of'
            elif c['type']=='A':c['true_role_phrase']='an actor in a film adaptation of'
    return items


def version():
    from version_materials import build
    items=build()
    for item in items:
        for c in item['candidates']:
            c['true_role_phrase']=f"the director of the {item['other_year']} version of"
    return items


def capital():
    from capital_materials import build
    return build()[0]


def modal_relations(out,pilot):
    """v3.4：并列众数各测，不选代表；已有同名同题读数复用。"""
    from readouts import definitions
    from core import digest
    _,notes=literature(out,pilot)
    bank={m['work_id']:m for m in load(out/'g1_candidates_draft.json')['materials']}
    proper={'luigi ricci':'Luigi Ricci','thomas holcroft':'Thomas Holcroft',
            'thomas carlyle':'Thomas Carlyle','william henry hudson':'William Henry Hudson'}
    existing=load(out/'readout_literature_inputs.json')['definitions']
    config=dict(definitions={},references=[],reused=[])
    for record in notes['mode_status']:
        for mode in record['modes']:
            name=proper.get(mode,mode);wid=record['work_id']
            d=dict(kind='relation',D=name,subject=bank[wid]['title'],samples=4)
            key=digest({k:v for k,v in d.items() if k!='samples'})
            ref=dict(work_id=wid,candidate=name,key=key,tied=len(record['modes'])>1,
                     current_answer_count=record['counts'][mode])
            if key in existing:config['reused'].append(ref)
            else:config['definitions'][key]=d;config['references'].append(ref)
    return config


def computable():
    from computable import build
    items=build()
    for item in items:
        item.update(work_id=item['item_id'],answer_format='number',gold_aliases=[item['gold']])
        subject=('the list '+', '.join(map(str,item['spec']['numbers'])) if item['family']=='mean' else
                 f"the call f({item['spec']['argument']}) in this code:\n{item['code']}")
        phrase='the median of' if item['family']=='mean' else 'the value printed by'
        candidates=[
            dict(type='d',name=item['d'],aliases=[item['d']],true_roles=[item['true_role']],
                 true_role_phrase=phrase,proposition=item['proposition'])]
        if item['level'] in (9,'simple'):
            candidates.append(dict(type='d_control',name=item['d_control'],aliases=[item['d_control']],true_roles=[]))
        item.update(subject=subject,candidates=candidates,
            policy_pairs=[dict(x=item['x'],d=item['d'],reference='constructed_main')])
    return items


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--pilot',type=Path,required=True)
    ap.add_argument('--collection',choices=['literature','adaptation','computable','version','capital'],required=True)
    args=ap.parse_args()
    if args.collection=='literature':items,notes=literature(args.out,args.pilot)
    else:items=globals()[args.collection]();notes={}
    for name,value in [(f'readout_{args.collection}_items.json',items),
                       (f'readout_{args.collection}_material_notes.json',notes)]:
        path=args.out/name
        if path.exists() and load(path)!=value:raise RuntimeError('已准备读数材料变化：'+name)
        save(path,value)
    print('准备读数题目数',len(items))
    print('材料说明',notes)


if __name__=='__main__':main()
