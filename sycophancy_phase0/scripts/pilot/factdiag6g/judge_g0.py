"""仅评审现有回答；独立输出新标签，不修改旧数据，不加载主模型。"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import time

from core import OPENING_PROMPT, load, save, opening_label
from propositions import PROMPT, parse
from legacy import judge_dependency, load_file, PILOT, previous


def main(out, model_path, check_only=False):
    protocol=load(out/'g0_frozen_protocol.json')
    for value,key in [(OPENING_PROMPT,'opening_prompt_sha256'),(PROMPT,'proposition_prompt_sha256')]:
        if hashlib.sha256(value.encode()).hexdigest()!=protocol[key]:
            raise RuntimeError('评审提示与冻结哈希不一致')
    queues={key:load(out/name) for key,name in [('opening','g0_opening_inputs.json'),('proposition','g0_proposition_inputs.json')]}
    if any(len(q)!=len({r['id'] for r in q}) for q in queues.values()):
        raise RuntimeError('评审队列身份重复')
    path=out/'g0_new_labels.json'
    saved=load(path) if path.exists() else {'opening':{},'proposition':{}}
    for kind,queue in queues.items():
        expected={r['id']:r for r in queue}
        if not set(saved[kind])<=set(expected):
            raise RuntimeError('已有标签不属于冻结输入')
        for rid,item in saved[kind].items():
            if item['prompt_sha256']!=hashlib.sha256(expected[rid]['prompt'].encode()).hexdigest():
                raise RuntimeError('已有标签对应提示发生变化')
    client_module=judge_dependency()
    previous()
    runtime=load_file('factdiag6g_previous_runtime3',PILOT/'factdiag3/runtime.py')
    if check_only:
        print(json.dumps({'imports':'ok','queues':{k:len(v) for k,v in queues.items()},'model_loaded':False}))
        return
    import fcntl
    with (out.parent/'factdiag6g_gpu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
        if occupied:
            raise RuntimeError('GPU已有进程，禁止重复加载：'+occupied)
        if all(len(saved[k])==len(q) for k,q in queues.items()):
            print('G0_JUDGING_ALREADY_COMPLETE',flush=True)
            return
        client=client_module.LocalJudge(str(model_path),batch_size=8)
        prop_client=runtime.PropositionClient(client)
        started=time.time()
        for kind,queue in queues.items():
            pending=[r for r in queue if r['id'] not in saved[kind]]
            for off in range(0,len(pending),8):
                batch=pending[off:off+8]
                outputs=(client if kind=='opening' else prop_client)([r['prompt'] for r in batch])
                if len(outputs)!=len(batch):
                    raise RuntimeError('评审返回条数与请求不符')
                for r,raw in zip(batch,outputs):
                    label=opening_label(raw) if kind=='opening' else parse(raw,r['response'])
                    saved[kind][r['id']]=dict(raw=raw,result=label,parse_failure=label is None,
                                             prompt_sha256=hashlib.sha256(r['prompt'].encode()).hexdigest())
                save(path,saved)
                print(f'{kind} {len(saved[kind])}/{len(queue)} elapsed={time.time()-started:.0f}s',flush=True)
        print('G0_JUDGING_COMPLETE',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--judge-model',type=Path,default=Path('/output/sycophancy-phase0/judge-model'))
    ap.add_argument('--check-only',action='store_true')
    args=ap.parse_args()
    main(args.out,args.judge_model,args.check_only)
