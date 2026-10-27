"""独立代理盲审与机器标签并列；不回改标签、不将分层样本泛化为总体。"""
from pathlib import Path
from collections import Counter, defaultdict
import argparse
from core import load, save


def summarize(out):
    directory=out/'review/formal_independent'
    sheet=load(directory/'blind.json');key=load(out/'review/formal_blind_key.json')
    annotations=load(directory/'annotations.json')
    if isinstance(annotations,dict):
        annotations=annotations.get('annotations',annotations.get('rows'))
    if not isinstance(annotations,list):raise RuntimeError('独立评审返回格式未定义')
    if len(annotations)!=len({r['id'] for r in annotations}):raise RuntimeError('独立评审身份重复')
    if {r['id'] for r in sheet}!={r['id'] for r in annotations}:raise RuntimeError('独立评审任务未完整或多出')
    data=defaultdict(list);decisions=[]
    for r in annotations:
        expected=key[r['id']]
        if r['task']!=expected['task']:raise RuntimeError('盲审任务类型改变')
        machine=expected['machine'];independent=r['result'];task=r['task']
        if task=='stance':
            for field in ('stance','explicit'):
                data[field].append((machine.get(field),independent.get(field)))
            labels={field:dict(machine=machine.get(field),independent=independent.get(field)) for field in ('stance','explicit')}
        elif task=='role':
            data['role'].append((machine,independent));labels=dict(machine=machine,independent=independent)
        elif task=='proposition':
            m=(machine or {}).get('label');i=independent.get('label')
            data['proposition'].append((m,i));labels=dict(machine=m,independent=i)
        else:raise RuntimeError('未知盲审任务')
        decisions.append(dict(blind_id=r['id'],source_id=expected['source_id'],task=task,labels=labels))
    tables={}
    for name,pairs in data.items():
        all_labels=sorted({str(v) for p in pairs for v in p})
        counts=Counter((str(m),str(i)) for m,i in pairs)
        metrics=[]
        for label in all_labels:
            positive=sum(str(m)==label for m,i in pairs)
            correct=sum(str(m)==label and str(i)==label for m,i in pairs)
            negative=sum(str(m)!=label for m,i in pairs)
            discoveries=sum(str(m)!=label and str(i)==label for m,i in pairs)
            metrics.append(dict(label=label,machine_positive=positive,confirmed_positive=correct,
                precision=correct/positive if positive else None,machine_negative=negative,
                discoveries=discoveries,negative_discovery_rate=discoveries/negative if negative else None,
                support='尚无法验证该类别' if positive<5 else '仅本次分层样本'))
        tables[name]=dict(n=len(pairs),agreement=sum(m==i for m,i in pairs),
            confusion=[dict(machine=m,independent=i,n=n) for (m,i),n in sorted(counts.items())],per_label=metrics)
    result=dict(review='独立代理复核，非人工',tasks=len(annotations),tables=tables,decisions=decisions,
        coverage=load(out/'review/formal_coverage.json'),
        limitation='按冻结条件分层抽样；精确率和机器阴性发现率只描述该盲审样本，不是总体漏检率。原机器标签保持不变。原文引文与独立判读理由留在运行目录。')
    save(out/'formal_blind_validation.json',result)
    print({k:dict(n=v['n'],agreement=v['agreement']) for k,v in tables.items()})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path)
    summarize(ap.parse_args().out)
