"""S0现有第二轮和开放关系读数评审。原始文本和新标签均留运行目录。"""
from pathlib import Path
import argparse
import hashlib
import subprocess
import time

from core import load,save,digest,same_identity
from legacy import previous,judge_dependency
from screen import identity
from judging import ROLE_PROMPT,ROLE_SPECIFIC,ROLE_COMMON,stance_prompt,role_prompt,role_parse,label_stances


def collection_items(out,collection):
    original=load(out/f's0_{collection}_inputs.json')['items']
    extra={i['item_id']:i for i in load(out/f'readout_{collection}_items.json')}
    if set(extra)!={i['item_id'] for i in original}:raise RuntimeError('首答与读数题目集合不符')
    bank={}
    for item in original:
        added=extra[item['item_id']]
        for k in ('question_en','gold','work_id','answer_format'):
            if item[k]!=added[k]:raise RuntimeError('首答与读数题目内容冲突：'+k)
        bank[item['item_id']]={**item,**added}
    return bank


def second_inputs(out,collections):
    inputs=[]
    for collection in collections:
        items=collection_items(out,collection)
        for row in load(out/f's0_{collection}_t2.json'):
            item=items[row['conflict_id']]
            if row['path']=='natural_wrong':candidate=item['gold']
            else:
                main_type={'G2a':'L','G2b':'d','G2c':'D','G2d':'d'}[item['structure']]
                c=next((c for c in item.get('candidates',[]) if c['type']==main_type),None)
                if c is None:c=next(iter(item.get('candidates',[])),None)
                if c is None:raise RuntimeError('无可用条件的正确历史不应生成第二轮')
                candidate=c['name']
            original=row['first_value']
            inputs.append(dict(id=identity(row),collection=collection,item=item,candidate=candidate,original=original,
                prompt=stance_prompt(item,candidate,original,row['assistant_text'])))
    return inputs


def relation_inputs(out):
    inputs=[]
    for name in ['literature','literature_modes','adaptation','computable','version','capital']:
        config=load(out/f'readout_{name}_inputs.json')
        structure={'literature':'G1','literature_modes':'G1','adaptation':'G2c',
                   'computable':'G2d','version':'G2b','capital':'G2a'}[name]
        rows=load(out/f'readout_{name}_generations.json')
        for row in rows:
            d=config['definitions'][row['definition_key']]
            if d['kind']!='relation':continue
            # 角色读数只给生成时所问的关系问题与回答，不提供真实角色或金标。
            inputs.append(dict(id=name+'|'+row['id'],collection=name,structure=structure,
                prompt=role_prompt(row['user_text'],d['D'],row['assistant_text'],structure),
                truncated=row['truncated'],looped=row['looped']))
    return inputs


def attach_seconds(out,collections,labels):
    for collection in collections:
        items=collection_items(out,collection)
        result=[]
        for row in load(out/f's0_{collection}_t2.json'):
            j=labels[identity(row)]['result'];item=items[row['conflict_id']]
            bad=row['truncated'] or row['looped'] or j['unjudgeable']
            result.append(dict(**row,judge=j,current_value=j['final_value'],current_missing=bool(bad),
                changed_from_t1=None if bad else not same_identity(j['final_value'],row['first_value'],
                    numeric=item['answer_format']=='number')))
        save(out/f's0_{collection}_histories.json',result)


def main(out,collections,check_only=False):
    protocol=dict(stance_sha256=hashlib.sha256(previous().p3.old.JUDGE_PROMPT.encode()).hexdigest(),
        role_prompt=ROLE_PROMPT,role_specific=ROLE_SPECIFIC,role_common=ROLE_COMMON,
        rule='角色读数不向评审提供真实角色；第二轮按实际答案确定x，变答单列，不增加CE2准入要求')
    frozen=out/'s0_judge_protocol.json'
    if frozen.exists() and load(frozen)!=protocol:raise RuntimeError('已冻结评审规则改变')
    save(frozen,protocol)
    queues=dict(stance=second_inputs(out,collections),role=relation_inputs(out))
    path=out/'s0_judge_labels.json'
    saved=load(path) if path.exists() else dict(stance={},role={})
    for kind,queue in queues.items():
        bank={r['id']:r for r in queue}
        if len(bank)!=len(queue) or not set(saved[kind])<=set(bank):raise RuntimeError('评审身份重复或输入不符')
        for key,old in saved[kind].items():
            if old['prompt_sha256']!=hashlib.sha256(bank[key]['prompt'].encode()).hexdigest():
                raise RuntimeError('已有评审对应文本改变')
    print('筛查评审数量',{k:len(q) for k,q in queues.items()},flush=True)
    module=judge_dependency()
    if check_only:return
    occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    if occupied:raise RuntimeError('GPU已有进程：'+occupied)
    client=module.LocalJudge('/output/sycophancy-phase0/judge-model',batch_size=8)
    started=time.time()
    for kind,queue in queues.items():
        pending=[r for r in queue if r['id'] not in saved[kind]]
        for offset in range(0,len(pending),8):
            batch=pending[offset:offset+8]
            if kind=='stance':results=label_stances(client,batch)
            else:
                raw=client([r['prompt'] for r in batch])
                if len(raw)!=len(batch):raise RuntimeError('角色评审返回数量不符')
                results=[dict(raw=text,label=role_parse(text,r['structure']),
                    prompt_sha256=hashlib.sha256(r['prompt'].encode()).hexdigest(),
                    output_missing=bool(r['truncated'] or r['looped'])) for r,text in zip(batch,raw)]
            for r,label in zip(batch,results):saved[kind][r['id']]=label
            save(path,saved)
            print(f'S0评审 {kind}: {len(saved[kind])}/{len(queue)}; seconds={time.time()-started:.0f}',flush=True)
    attach_seconds(out,collections,saved['stance'])
    print('S0第二轮与关系评审结束',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--collections',nargs='+',default=['adaptation','version','computable','capital'])
    ap.add_argument('--check-only',action='store_true')
    a=ap.parse_args();main(a.out,a.collections,a.check_only)
