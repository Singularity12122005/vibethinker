"""正式续写的冻结评审及旧训练域所缺角色标签；旧标签不回写。"""
from pathlib import Path
import argparse
import hashlib
import subprocess
import time

from core import load,save,digest
from formal import STAGES,validate_materials
from screen import identity
from judging import stance_prompt,role_prompt,role_parse,label_stances
from propositions import render,parse,PROMPT
from legacy import previous,judge_dependency,load_file,PILOT
from step0 import sources,row_key


def formal_inputs(out,stage):
    materials=load(out/'factdiag6g_materials.json');plan=materials['plan']
    rows=load(out/f'formal_{stage}_generations.json')
    if len(rows)!=plan['counts'][stage]:raise RuntimeError('正式生成尚未完整')
    bank={i['item_id']:i for i in plan['items']};queues=dict(stance=[],role=[],proposition=[])
    for row in rows:
        item=bank[row['conflict_id']];c=next(c for c in item['candidates'] if c['type']==row['candidate_type'])
        key=identity(row);response=row['assistant_text']
        queues['stance'].append(dict(id=key,item=item,candidate=c['name'],original=row['original'],
            prompt=stance_prompt(item,c['name'],row['original'],response)))
        queues['role'].append(dict(id=key,structure=item['structure'],
            prompt=role_prompt(item['question_en'],c['name'],response,item['structure'])))
        if c.get('proposition'):
            scope=c.get('proposition_scope') or item.get('subject') or item['question_en']
            queues['proposition'].append(dict(id=key,response=response,
                prompt=render(c['proposition'],scope,response)))
    return queues


def old_role_inputs(pilot):
    old,_,rows3,rows4,_,bank,_,_=sources(pilot)
    records=[(3,r) for r in rows3 if r['unit'] in ('R-S','S_T','F-D') and not old.excluded(r)]
    records +=[(4,r) for r in rows4 if r['unit'] in ('R-S','S_T','F-D')]
    queue=[]
    for batch,row in records:
        m=bank[row['work_id']];question=m['R' if row['unit']=='R-S' else 'F']['question_en']
        candidate=m['d_T'] if row['unit']=='S_T' else m['F']['gold']
        queue.append(dict(id=row_key(batch,row),structure='G1',
            prompt=role_prompt(question,candidate,row['assistant_text'],'G1')))
    if len(queue)!=4180:raise RuntimeError('旧联合训练域应为4180条续写')
    return dict(role=queue)


def run(out,pilot,stage,include_training_roles=False,check_only=False):
    reg,_,_=validate_materials(out,pilot)
    if reg['frozen']['judgments']['proposition']!=PROMPT:raise RuntimeError('命题提示偏离冻结值')
    jobs=[(out/f'formal_{stage}_labels.json',formal_inputs(out,stage))]
    if include_training_roles:jobs.append((out/'joint_training_roles.json',old_role_inputs(pilot)))
    prepared=[]
    for path,queues in jobs:
        saved=load(path) if path.exists() else {k:{} for k in queues}
        for kind,queue in queues.items():
            expected={r['id']:r for r in queue}
            if len(expected)!=len(queue) or not set(saved[kind])<=set(expected):raise RuntimeError('评审输入身份不符')
            for key,value in saved[kind].items():
                if hashlib.sha256(expected[key]['prompt'].encode()).hexdigest()!=value['prompt_sha256']:
                    raise RuntimeError('已有标签对应的输入改变')
        print(path.name,{k:len(q) for k,q in queues.items()},flush=True)
        prepared.append((path,queues,saved))
    if check_only:return
    if all(len(saved[k])==len(q) for _,queues,saved in prepared for k,q in queues.items()):
        print('正式评审已完成，不重复加载',stage,flush=True);return
    occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    if occupied:raise RuntimeError('GPU已有进程，不重复加载：'+occupied)
    client=judge_dependency().LocalJudge('/output/sycophancy-phase0/judge-model',batch_size=8)
    runtime=load_file('factdiag6g_proposition_runtime',PILOT/'factdiag3/runtime.py')
    prop_client=runtime.PropositionClient(client);start=time.time()
    for path,queues,saved in prepared:
        for kind,queue in queues.items():
            pending=[r for r in queue if r['id'] not in saved[kind]]
            for off in range(0,len(pending),8):
                batch=pending[off:off+8]
                if kind=='stance':result=label_stances(client,batch)
                else:
                    raw=(prop_client if kind=='proposition' else client)([r['prompt'] for r in batch])
                    if len(raw)!=len(batch):raise RuntimeError('评审输出数量不符')
                    result=[]
                    for r,text in zip(batch,raw):
                        label=parse(text,r['response']) if kind=='proposition' else role_parse(text,r['structure'])
                        result.append(dict(raw=text,result=label,parse_failure=label is None,
                            prompt_sha256=hashlib.sha256(r['prompt'].encode()).hexdigest()))
                for r,lab in zip(batch,result):saved[kind][r['id']]=lab
                save(path,saved)
                print(f'{path.stem} {kind} {len(saved[kind])}/{len(queue)}; seconds={time.time()-start:.0f}',flush=True)
    print('正式评审结束',stage,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--pilot',type=Path,required=True);ap.add_argument('--stage',choices=STAGES,required=True)
    ap.add_argument('--include-training-roles',action='store_true');ap.add_argument('--check-only',action='store_true')
    a=ap.parse_args();run(a.out,a.pilot,a.stage,a.include_training_roles,a.check_only)
