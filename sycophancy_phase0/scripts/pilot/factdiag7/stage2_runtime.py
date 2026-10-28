"""阶段二A第三轮与隔离探测；只在对应预注册已提交后运行。"""
from pathlib import Path
import argparse
import hashlib
import re
import subprocess
import time

from stage2_plan import load,save,digest,legacy,identity,seed_for,tasks
from stage2_freeze import validate
from stage2_budget import check_next_batch
from stage2_identity import parse_complete


def generate(out,pilot,phase,commit):
    if not re.fullmatch('[0-9a-f]{40}',commit):
        raise RuntimeError('缺已提交推送的阶段二冻结提交')
    validate(out)
    plan=load(out/'factdiag7_stage2_materials.json')
    old=legacy();sources={}
    for h in old.source_histories(pilot/'factdiag3_20261030'):
        if h['unit']=='R-S':sources['R-S|'+h['work_id']+'|'+str(h['row']['idx'])]=h['row']
    for h in plan['histories']:
        row=sources[h['history_id']]
        if digest({k:row[k] for k in ('prompt_ids','assistant_ids','assistant_text')})!=h['history_sha256']:
            raise RuntimeError('原历史变化')
    occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    if occupied:raise RuntimeError('GPU有现有进程，不加载第二进程：'+occupied)
    p=old.p3
    class Main(p.previous_runtime.Main):
        def generate(self,requests):
            from sycophancy_phase0.inference.engine import GenRequest
            from sycophancy_phase0.constants import IM_END,ENDOFTEXT
            prefixes=[self.tok.encode(r['forced_prefix'],add_special_tokens=False) for r in requests]
            outputs=self.engine.generate([GenRequest(ids=r['prompt_ids']+prefix,seed=seed_for(r),
                temperature=.7,max_new_tokens=1024) for r,prefix in zip(requests,prefixes)])
            if len(outputs)!=len(requests):raise RuntimeError('生成返回条数错误')
            result=[]
            for r,a,prefix in zip(requests,outputs,prefixes):
                n=next((j+1 for j,t in enumerate(a.ids) if t in (IM_END,ENDOFTEXT)),len(a.ids))
                normalized=self.builder.normalize(a.ids,a.finish_reason)
                ids=prefix+normalized.ids;text=self.tok.decode(ids,skip_special_tokens=True)
                if prefix and not text.startswith(r['forced_prefix']):raise RuntimeError('固定前缀未进入助手回复')
                item=dict(self.bank[r['conflict_id']])
                if r['path']!='belief':
                    person=next(c for c in item['people'] if c['type']==r['candidate_type'])
                    item.update(d=person['name'],d_aliases=person['aliases'])
                # 隔离探测按人数及封闭名单后续评审，不硬套作者题答案解析。
                parsed=None if r['path']=='belief' else parse_complete(text,item,p.old)
                result.append(dict(**r,assistant_ids=ids,assistant_text=text,n_new_tokens=n,
                    forced_prefix_tokens=len(prefix),truncated=normalized.truncated,
                    looped=p.old.looped(ids[:len(prefix)+n]),parsed=parsed,freeze_commit=commit))
            return result
    parsebank={}
    for item in plan['items']:
        # 保留原答案解析器的别名匹配接口，仅补本单元实际候选。
        aliases=[a for c in item['people'] if c['type'] in ('X','F_w') for a in c['aliases']]
        parsebank[item['item_id']]=dict(question_en=item['question_en'],gold=item['gold'],
            gold_aliases=item['gold_aliases'],d='__candidate__',d_aliases=aliases,answer_format='entity',people=item['people'])
    engine=Main('/output/sycophancy-phase0/model',parsebank,batch=16)
    queue=tasks(engine,plan,sources,phase);path=out/f'stage2_{phase}_generations.json'
    rows=load(path) if path.exists() else [];cached={identity(r):r for r in rows};expected={identity(r):r for r in queue}
    if len(cached)!=len(rows) or not set(cached)<=set(expected):raise RuntimeError('已有续写身份不符')
    for key,r in cached.items():
        if any(r[k]!=expected[key][k] for k in ('prompt_ids','user_text','forced_prefix')):
            raise RuntimeError('已有输入不同，不能复用')
    pending=sorted((r for key,r in expected.items() if key not in cached),key=lambda r:(r['work_id'],r['previous_length'],identity(r)))
    start=time.time()
    for offset in range(0,len(pending),16):
        check_next_batch(pilot,len(pending[offset:offset+16]))
        for r in engine.generate(pending[offset:offset+16]):cached[identity(r)]=r
        save(path,[cached[key] for key in expected if key in cached])
        if sum(r['looped'] for r in cached.values())/len(cached)>.05:
            raise RuntimeError('固定循环诊断超过5%，停止')
        print(f'{phase} {len(cached)}/{len(queue)}；耗时{time.time()-start:.0f}秒',flush=True)
    print(phase+'生成完成',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--pilot',type=Path,required=True)
    ap.add_argument('--phase',choices=['Q2','belief'],required=True);ap.add_argument('--freeze-commit',required=True)
    a=ap.parse_args();generate(a.out,a.pilot,a.phase,a.freeze_commit)
