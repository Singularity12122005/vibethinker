"""固定64道留出题各两条真实首答，六卡按题分工；不判分、不输出正文。"""
import argparse
from collections import Counter
import json
import os
import time
import program_semantic_transfer_v133 as original


def main(worker):
    import fcntl
    import torch
    from transformers import AutoTokenizer
    import g1_runtime_main as legacy
    directory=original.HOLDOUT/('worker-'+str(worker));directory.mkdir(parents=True,exist_ok=True)
    fd=os.open(directory,os.O_RDONLY);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert (original.OUT/'development_complete_for_holdout.json').exists()
    source=original.RUNS/'internal8_program_checks_v129'
    scored=json.loads((source/'holdout_scores.json').read_text())
    materials=json.loads((source/'holdout_materials.json').read_text())
    assert scored['complete'] and len(scored['rows'])==len(materials)==64
    assert {r['id'] for r in materials}=={r['id'] for r in scored['rows']}
    all_prompts=original.first_prompts(materials)
    prompts={item:messages for i,(item,messages) in enumerate(all_prompts.items()) if i%6==worker}
    keys={f'{item}-{i}' for item in prompts for i in range(2)}
    path=directory/'first_answers.json';status_path=directory/'status.json'
    rows=json.loads(path.read_text()) if path.exists() else {}
    assert set(rows)<=keys
    status=json.loads(status_path.read_text()) if status_path.exists() else {'calls':{},'complete':False}
    previous=Counter(status['calls']);torch.set_num_threads(2)
    tokenizer=AutoTokenizer.from_pretrained(original.MODEL,local_files_only=True);engine=original.Engine()
    def save():
        status.update({'finished':sum(r['finished'] for r in rows.values()),'total':len(keys),
                       'calls':dict(previous+Counter(engine.counter)),
                       'limit_hits':sum(r.get('incomplete_reason')=='length_limit' for r in rows.values())})
        original.write(status_path,status)
    try:
        with torch.inference_mode():
            for item,messages in prompts.items():
                if all(rows.get(f'{item}-{i}',{}).get('finished') for i in range(2)):continue
                rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
                assert rendered.endswith('<|im_start|>assistant\n') and '<think>' not in rendered
                ids=tokenizer.encode(rendered,add_special_tokens=False)
                initial=engine.call(ids,None,'holdout_first_prefill')
                for repeat in range(2):
                    key=f'{item}-{repeat}'
                    if rows.get(key,{}).get('finished'):continue
                    seed=legacy.derive_seed('internal8_program_holdout_v133',item,'first','native',repeat,1)
                    def persist(answer):
                        rows[key]={'prompt_ids':ids,**answer};original.write(path,rows);save()
                    original.generate_one(engine,tokenizer,ids,initial,seed,'N',None,None,rows.get(key),persist)
                    print(json.dumps({'finished':status['finished'],'total':len(keys)}),flush=True)
                del initial
        assert set(rows)==keys and all(r['finished'] for r in rows.values());status['complete']=True
    finally:
        save();os.close(fd)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=int,required=True)
    worker=parser.parse_args().worker;assert worker in range(6);main(worker)
