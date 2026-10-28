"""按新冻结协议提取既有600条与新Q2回答；原阶段一标签保持不变。"""
from pathlib import Path
import argparse
import hashlib
import re
import subprocess
import time

from stage2_plan import load,save,identity,baseline_records,legacy
from stage2_freeze import validate


def inputs(out,source,phase):
    protocol=load(out/'factdiag7_stage2_relation_protocol.json')
    plan=load(out/'factdiag7_stage2_materials.json');bank={i['item_id']:i for i in plan['items']}
    if phase=='baseline':
        rows=baseline_records(source)
    else:
        rows=load(out/'stage2_Q2_generations.json')
        if len(rows)!=960:raise RuntimeError('Q2生成未完整')
    result=[]
    for row in rows:
        item=bank[row['conflict_id']]
        prefix=row.get('forced_prefix','')
        response=row['assistant_text']
        if prefix and not response.startswith(prefix):raise RuntimeError('助手固定前缀边界不符')
        suffix=response[len(prefix):]
        kinds=[row['candidate_type'],'GOLD']+(['T'] if phase=='Q2' else [])
        for kind in kinds:
            person=next(p for p in item['people'] if p['type']==kind)
            values=dict(QUESTION=item['question_en'],CANDIDATE=person['name'],ALIASES='; '.join(person['aliases']),
                        PREFIX=prefix,RESPONSE=suffix)
            prompt=re.sub(r'\{(QUESTION|CANDIDATE|ALIASES|PREFIX|RESPONSE)\}',lambda m:values[m[1]],protocol['prompt'])
            result.append(dict(id=identity(row)+'|'+kind,kind=kind,prompt=prompt,response=suffix,
                               item=item,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()))
    n=1200 if phase=='baseline' else 2880
    if len(result)!=n or len({q['id'] for q in result})!=n:raise RuntimeError('原子提取队列不符')
    return protocol,result


def run(out,source,phase,commit,check_only=False):
    validate(out,'factdiag7_stage2_baseline_prereg.json' if phase=='baseline' else 'factdiag7_stage2_prereg.json')
    if not re.fullmatch('[0-9a-f]{40}',commit):raise RuntimeError('缺已提交推送的冻结提交号')
    protocol,queue=inputs(out,source,phase);path=out/f'stage2_{phase}_extractions.json'
    saved=load(path) if path.exists() else {};bank={q['id']:q for q in queue}
    if not set(saved)<=set(bank):raise RuntimeError('已有提取身份不同')
    for key,r in saved.items():
        if r['prompt_sha256']!=bank[key]['prompt_sha256']:raise RuntimeError('已评输入不同')
    pending=[q for q in queue if q['id'] not in saved]
    print('阶段二原子提取',phase,len(saved),'/',len(queue),flush=True)
    if check_only or not pending:return
    occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    if occupied:raise RuntimeError('GPU有其他任务，不重复加载：'+occupied)
    legacy()
    from legacy import judge_dependency
    from relations_v2 import parse
    settings=protocol['judge_runtime']
    client=judge_dependency().LocalJudge(settings['model_path'],batch_size=settings['batch'])
    start=time.time()
    for off in range(0,len(pending),settings['batch']):
        batch=pending[off:off+settings['batch']]
        texts=[client.tok.apply_chat_template([{'role':'user','content':q['prompt']}],tokenize=False,add_generation_prompt=True) for q in batch]
        encoded=client.tok(texts,return_tensors='pt',padding=True).to(client.model.device)
        with client.torch.no_grad():
            generated=client.model.generate(**encoded,do_sample=False,max_new_tokens=settings['max_new_tokens'],
                pad_token_id=client.tok.pad_token_id,temperature=None,top_p=None,top_k=None)
        sampled=generated[:,encoded.input_ids.shape[1]:];decoded=client.tok.batch_decode(sampled,skip_special_tokens=True)
        if len(decoded)!=len(batch):raise RuntimeError('评审返回数不符')
        for q,raw,ids in zip(batch,decoded,sampled):
            seq=ids.tolist();truncated=len(seq)>=settings['max_new_tokens'] and client.tok.eos_token_id not in seq
            ext={'parse_status':'UNPARSEABLE','claims':[]} if truncated else parse(raw,q['response'],q['item'])
            saved[q['id']]=dict(raw=raw,extraction=ext,prompt_sha256=q['prompt_sha256'],judge_truncated=truncated,freeze_commit=commit)
        save(path,saved)
        print(f'阶段二 {phase} 原子提取 {len(saved)}/{len(queue)}；耗时{time.time()-start:.0f}秒',flush=True)
    print('阶段二 '+phase+' 原子提取完成',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--phase',choices=['baseline','Q2'],required=True);ap.add_argument('--freeze-commit',required=True)
    ap.add_argument('--check-only',action='store_true');a=ap.parse_args();run(a.out,a.source,a.phase,a.freeze_commit,a.check_only)
