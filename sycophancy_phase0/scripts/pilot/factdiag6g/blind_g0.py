"""只从冻结输入抽取独立盲表；不读机器评审标签。"""
from pathlib import Path
import argparse
import random

from core import load,save,SEED,OPENING_PROMPT
from propositions import PROMPT


def prepare(out):
    rng=random.Random(SEED)
    opening=load(out/'g0_opening_inputs.json')
    props=load(out/'g0_proposition_inputs.json')
    selected=[('opening',r) for r in rng.sample(opening,20)]+[('proposition',r) for r in rng.sample(props,20)]
    rng.shuffle(selected)
    sheet=[];key={}
    for i,(kind,r) in enumerate(selected):
        rid=f'G0-BLIND-{i+1:03d}'
        row=dict(id=rid,task=kind)
        if kind=='opening':
            row['response_opening']=r['text']
        else:
            row.update(proposition=r['proposition'],scope=r['scope'],response=r['response'])
        sheet.append(row)
        key[rid]=dict(task=kind,source_id=r['id'])
    directory=out/'review/g0_independent'
    files={directory/'blind.json':sheet,
           directory/'protocol.json':dict(opening=OPENING_PROMPT,proposition=PROMPT,
               instructions='代理复核，非人工。仅依据盲表文本独立判断；不读取机器标签、其他轮次、结果或其他目录。逐条输出id、label、理由；命题另附原文引文。不回改机器标签。'),
           out/'review/g0_blind_key.json':key}
    for path,content in files.items():
        if path.exists() and load(path)!=content:
            raise RuntimeError('已有盲表或抽样发生变化，停止')
        save(path,content)
    print('盲表已建立：开头20条、命题20条；未读取任何机器标签。')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    prepare(ap.parse_args().out)
