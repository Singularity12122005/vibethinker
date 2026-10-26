"""v3.3 已批准的纯读取修复；从保存输出重解析，原文件不改，不调用模型。"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
from core import load,save
from propositions import parse,PROMPT


def main(out):
    source=load(out/'g0_new_labels.json');repaired=deepcopy(source)
    protocol=load(out/'g0_frozen_protocol.json')
    if protocol['proposition_prompt_sha256']!=hashlib.sha256(PROMPT.encode()).hexdigest():
        raise RuntimeError('提示词改变，停止读取修复')
    queue={r['id']:r for r in load(out/'g0_proposition_inputs.json')}
    if set(queue)!=set(source['proposition']):raise RuntimeError('补标输入与保存输出不一一对应')
    changed=[];before=Counter();after=Counter();recovered=0
    for rid,item in source['proposition'].items():
        response=queue[rid]['response']
        original=parse(item['raw'],response,unwrap=False)
        if original!=item['result']:raise RuntimeError('旧解析结果与冻结读取器不一致：'+rid)
        result=parse(item['raw'],response)
        if original is not None and result!=original:raise RuntimeError('原已成功解析的标签发生变化')
        repaired['proposition'][rid].update(result=result,parse_failure=result is None)
        before[original['label'] if original else 'PARSE_FAIL']+=1
        after[result['label'] if result else 'PARSE_FAIL']+=1
        if result!=original:
            recovered+=int(original is None and result is not None)
            changed.append(dict(id=rid,before=original,after=result))
    record=dict(approval_commit='905207c',n=len(queue),recovered=recovered,
                before=dict(before),after=dict(after),changed=changed,
                rule='只剥离完整包裹单个JSON对象的外层代码块；无新增评审；提示、标签和引文检查不变；原始解析文件保留。')
    target=out/'g0_new_labels_reparsed.json'
    if target.exists() and load(target)!=repaired:raise RuntimeError('已有修复结果发生变化')
    save(target,repaired)
    summary=load(out/'factdiag6g_step0.json');summary['proposition_reader_repair']=record
    save(out/'factdiag6g_step0.json',summary)
    print({k:v for k,v in record.items() if k!='changed'})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    main(ap.parse_args().out)
