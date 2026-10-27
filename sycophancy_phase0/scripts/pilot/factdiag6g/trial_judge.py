"""只评审S0试运行的立场；不写入正式效应数据。"""
from pathlib import Path
import argparse
import hashlib
import subprocess
import time
from core import load,save
from legacy import judge_dependency
from screen import identity
from screen_judge import collection_items
from judging import stance_prompt,label_stances


def main(out,collections):
    inputs=[]
    for collection in collections:
        bank=collection_items(out,collection)
        for row in load(out/f's0_{collection}_trial.json'):
            item=bank[row['conflict_id']]
            inputs.append(dict(id=identity(row),item=item,candidate=row['candidate'],original=row['original'],
                prompt=stance_prompt(item,row['candidate'],row['original'],row['assistant_text'])))
    expected={r['id']:r for r in inputs}
    path=out/'s0_trial_labels.json';saved=load(path) if path.exists() else {}
    if len(expected)!=len(inputs) or not set(saved)<=set(expected):raise RuntimeError('试运行评审身份不符')
    for key,value in saved.items():
        if value['prompt_sha256']!=hashlib.sha256(expected[key]['prompt'].encode()).hexdigest():
            raise RuntimeError('试运行评审提示改变')
    pending=[r for r in inputs if r['id'] not in saved]
    if pending:
        module=judge_dependency()
        occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
        if occupied:raise RuntimeError('GPU已有进程，不重复加载：'+occupied)
        client=module.LocalJudge('/output/sycophancy-phase0/judge-model',batch_size=8)
        start=time.time()
        for off in range(0,len(pending),8):
            batch=pending[off:off+8]
            for r,result in zip(batch,label_stances(client,batch)):saved[r['id']]=result
            save(path,saved)
            print(f'S0试运行评审 {len(saved)}/{len(inputs)}; seconds={time.time()-start:.0f}',flush=True)
    print('S0试运行评审结束',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--collections',nargs='+',default=['adaptation','version','computable','capital'])
    a=ap.parse_args();main(a.out,a.collections)
