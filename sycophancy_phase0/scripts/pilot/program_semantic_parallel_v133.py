"""仅改变已批准768条的执行分工；每组是一段历史的一次重复、三臂齐全。"""
import argparse
import copy
import json
import os
from collections import Counter
from pathlib import Path
import time

import program_semantic_transfer_v133 as original


def verify_device(engine,x,bases,ids,cache,start,tag):
    import numpy as np
    native=engine.call(ids,copy.deepcopy(cache),'parallel_identity_'+tag+'_native')
    reference=original.logp(native.logits[0,-1])
    result={}
    for name,arm,zero in [('native_repeat','N',False),('zero_block','O',True),('zero_remove','L',True)]:
        with original.scope(engine,x,bases,arm,start,zero):
            alternative=engine.call(ids,copy.deepcopy(cache),'parallel_identity_'+tag+'_'+name)
        delta=(original.logp(alternative.logits[0,-1])-reference).abs()
        maximum=float(delta.max())
        result[name]={'max_abs_logp':maximum,'p99_abs_logp':0.0 if maximum==0 else float(np.quantile(delta.cpu().numpy(),.99))}
        del alternative,delta
    result['tolerance_nat']=max(1e-4,3*result['native_repeat']['max_abs_logp'])
    result['pass']=all(result[k]['max_abs_logp']<=result['tolerance_nat'] for k in ('zero_block','zero_remove'))
    if not result['pass']:
        original.write(original.OUT/'identity_failure.json',{'worker_shape':tag,'results':result})
        raise RuntimeError('新设备零编辑超差，禁止发放生成任务')
    return result,native


def work(worker):
    import fcntl
    import torch
    from transformers import AutoTokenizer
    import g1_runtime_main as legacy
    if (original.OUT/'identity_failure.json').exists():
        raise RuntimeError('存在尚未处理的零编辑失败，禁止生成')
    directory=original.OUT/('worker-'+worker)
    directory.mkdir(exist_ok=True)
    fd=os.open(directory,os.O_RDONLY)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    queue_path=directory/'queue.json';answer_path=directory/'answers.json';status_path=directory/'status.json'
    rows=json.loads(answer_path.read_text()) if answer_path.exists() else {}
    status=json.loads(status_path.read_text()) if status_path.exists() else {'calls':{},'phase':'loading'}
    old_calls=Counter(status['calls'])
    torch.set_num_threads(2)
    tokenizer=AutoTokenizer.from_pretrained(original.MODEL,local_files_only=True)
    cases,bases=original.inputs(tokenizer)
    by_source={r['source_key']:(r,x) for r,x,_ in cases}
    assert set(rows)<={f'{s}__{a}__{i}' for s in by_source for a in original.ARMS for i in range(4)}
    engine=original.Engine()
    def save():
        status.update({'worker':worker,'finished':sum(r['finished'] for r in rows.values()),
                       'keys':{k:{'finished':v['finished'],'tokens':v['tokens'],
                                  'limit_hit':v.get('incomplete_reason')=='length_limit'} for k,v in rows.items()},
                       'calls':dict(old_calls+Counter(engine.counter))})
        original.write(status_path,status)
    try:
        with torch.inference_mode():
            # 新实例的环境/设备尚未参与既有验收，先做同形状零编辑核查。
            row,x,_=cases[0];prefix=engine.prefix(x);header=x['ids'][x['bounds'][2]:]
            first,native=verify_device(engine,x,bases,header,prefix,x['bounds'][2],'header')
            second,one=verify_device(engine,x,bases,[2610],native.past_key_values,len(x['ids']),'single')
            status['identity']={'header':first,'single':second}
            del prefix,native,one
            status['phase']='waiting';status['queue_locking']=True;save()
            while True:
                with (directory/'queue.lock').open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    queue=json.loads(queue_path.read_text()) if queue_path.exists() else {'tasks':[],'closed':False}
                    assert len(queue['tasks'])==len({(t['source_key'],t['repeat']) for t in queue['tasks']})
                    task=next((t for t in queue['tasks'] if not all(rows.get(f"{t['source_key']}__{a}__{t['repeat']}",{}).get('finished') for a in original.ARMS)),None)
                    if task is not None:
                        status.update({'phase':'generating','task':task});save()
                if task is None:
                    if queue['closed']:
                        status['phase']='complete';save();break
                    status['phase']='waiting';save();time.sleep(5);continue
                source=task['source_key'];repeat=task['repeat'];assert source in by_source and repeat in range(4)
                row,x=by_source[source]
                prefix=engine.prefix(x);header=x['ids'][x['bounds'][2]:]
                seed=legacy.derive_seed(original.STAGE,source,'continuation','shared',repeat,1)
                for arm in original.ARMS:
                    key=f'{source}__{arm}__{repeat}'
                    if rows.get(key,{}).get('finished'):continue
                    with original.scope(engine,x,bases,arm,x['bounds'][2]):
                        initial=engine.call(header,copy.deepcopy(prefix),'generate_header_'+arm)
                    def persist(answer):
                        rows[key]={**{k:row[k] for k in ('source_key','item','family','side','condition','entry_effect','entry_group')},
                                   'arm':arm,'repeat':repeat,**answer}
                        original.write(answer_path,rows);save()
                    original.generate_one(engine,tokenizer,x['ids'],initial,seed,arm,x,bases,rows.get(key),persist)
                    del initial
                del prefix
                status['phase']='waiting';save()
    except BaseException as error:
        status['phase']='failed';status['error']=repr(error);save();raise
    finally:
        os.close(fd)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',required=True)
    worker=parser.parse_args().worker
    assert worker in ('0','1','2','3','4','5','6','7')
    work(worker)
