"""阶段一仅提取已有续写的原子命题，不含主模型生成入口。"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time
from stage1_frame import load,save,identity,STAGES
from relations import parse


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(out):
    reg=load(out/'factdiag7_prereg.json')
    for name,value in reg['frozen_files'].items():
        if sha(out/name)!=value:raise RuntimeError('冻结文件变化：'+name)
    for name,value in reg['code_sha256'].items():
        if sha(Path(__file__).parent/name)!=value:raise RuntimeError('冻结代码变化：'+name)
    if not reg.get('freeze_parent_commit'):raise RuntimeError('缺冻结父提交')
    return reg


def collect(out,source):
    sampling=load(out/'factdiag7_sampling.json');materials=load(out/'factdiag7_relation_materials.json')
    bank={i['item_id']:i for i in materials['items']};wanted={r['id'] for r in sampling['selected']}
    records={}
    for stage in STAGES:
        for row in load(source/f'formal_{stage}_generations.json'):
            k=identity(row)
            if k in wanted:records[k]=row
    if set(records)!=wanted:raise RuntimeError('300条原始续写不完整')
    return sampling,bank,records


def inputs(out,source):
    protocol=load(out/'factdiag7_relation_protocol.json')
    sample,bank,records=collect(out,source);queue=[];public=[]
    for selected in sample['selected']:
        row=records[selected['id']];item=bank[selected['item_id']]
        text=row['assistant_text'];prefix=''
        if row['arm']=='S+A1':prefix=protocol['fixed_prefixes']['A1']
        elif row['arm']=='S+A0':prefix=protocol['fixed_prefixes']['A0']
        if prefix and not text.startswith(prefix):raise RuntimeError('固定前缀边界不符')
        suffix=text[len(prefix):]
        blind_id=hashlib.sha256(('blind7|'+selected['id']).encode()).hexdigest()[:16]
        views=[]
        for kind in (selected['candidate_type'],'GOLD'):
            person=next(c for c in item['people'] if c['type']==kind)
            values={'QUESTION':item['question_en'],'CANDIDATE':person['name'],'ALIASES':'; '.join(person['aliases']),
                    'PREFIX':prefix,'RESPONSE':suffix}
            prompt=protocol['prompt']
            # 替换一次固定占位符，正文出现花括号不会被再次解释。
            import re
            prompt=re.sub(r'\{(QUESTION|CANDIDATE|ALIASES|PREFIX|RESPONSE)\}',lambda m:values[m.group(1)],prompt)
            key=selected['id']+'|'+kind
            queue.append(dict(id=key,sample_id=selected['id'],kind=kind,blind_id=blind_id,
                prompt=prompt,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),response=suffix,item=item))
            views.append(dict(candidate=person['name'],aliases=person['aliases'],prompt=prompt))
        public.append(dict(blind_id=blind_id,views=views))
    if len(queue)!=600:raise RuntimeError('必须恰好600次提取')
    return sample,queue,public


def prepare(out,source):
    reg=validate(out);sample,queue,public=inputs(out,source)
    mapping={q['blind_id']:q['sample_id'] for q in queue}
    blindset=set(sample['independent60']);humanset=set(sample['human_calibration30'])
    # 人工文件还需材料及后续机器标签；此处仅创建独立代理盲表，始终留A100。
    blind=[r for r in public if mapping[r['blind_id']] in blindset]
    path=out/'stage1_independent_blind.json'
    content={'protocol':load(out/'factdiag7_relation_protocol.json')['prompt'],'records':blind,
             'instructions':'只按原文提取两名对象各自的原子命题；不查事实，不推断作者与候选身份，不访问其他运行文件。'}
    if path.exists() and load(path)!=content:raise RuntimeError('盲表已存在，不重新抽样或覆盖')
    if not path.exists():save(path,content)
    save(out/'stage1_private_blind_mapping.json',mapping)
    save(out/'stage1_judge_input_manifest.json',[{'id':q['id'],'prompt_sha256':q['prompt_sha256']} for q in queue])
    print(json.dumps({'sample':300,'extractions':len(queue),'independent_responses':len(blind),'human_calibration':len(humanset)},ensure_ascii=False))


def judge(out,source,freeze_commit):
    validate(out)
    if len(freeze_commit)!=40:raise RuntimeError('必须传入已提交推送的冻结提交号')
    _,queue,_=inputs(out,source);path=out/'stage1_machine_extractions.json'
    saved=load(path) if path.exists() else {}
    bank={r['id']:r for r in queue}
    if not set(saved)<=set(bank):raise RuntimeError('已有提取身份不符')
    for key,row in saved.items():
        if row['prompt_sha256']!=bank[key]['prompt_sha256']:raise RuntimeError('已有输入变化')
    pending=[q for q in queue if q['id'] not in saved]
    if not pending:print('600次评审已经完成，不重复');return
    occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    if occupied:raise RuntimeError('GPU被占用，不加载第二个进程：'+occupied)
    sys.path.insert(0,str(Path(__file__).parent.parent/'factdiag6g'))
    from legacy import judge_dependency
    client=judge_dependency().LocalJudge('/output/sycophancy-phase0/judge-model',batch_size=8)
    settings=load(out/'factdiag7_relation_protocol.json')['judge_runtime']
    start=time.time()
    for off in range(0,len(pending),settings['batch']):
        batch=pending[off:off+settings['batch']]
        texts=[client.tok.apply_chat_template([{'role':'user','content':r['prompt']}],tokenize=False,add_generation_prompt=True) for r in batch]
        encoded=client.tok(texts,return_tensors='pt',padding=True).to(client.model.device)
        with client.torch.no_grad():
            generated=client.model.generate(**encoded,do_sample=False,max_new_tokens=settings['max_new_tokens'],
                pad_token_id=client.tok.pad_token_id,temperature=None,top_p=None,top_k=None)
        sampled=generated[:,encoded.input_ids.shape[1]:]
        decoded=client.tok.batch_decode(sampled,skip_special_tokens=True)
        for q,raw,ids in zip(batch,decoded,sampled):
            seq=ids.tolist();eos=client.tok.eos_token_id
            terminated=eos in seq
            trunc=(len(seq)>=settings['max_new_tokens'] and not terminated)
            extraction=parse(raw,q['response'],q['item']) if not trunc else {'parse_status':'UNPARSEABLE','claims':[]}
            saved[q['id']]=dict(raw=raw,extraction=extraction,prompt_sha256=q['prompt_sha256'],
                judge_truncated=trunc,freeze_commit=freeze_commit)
        save(path,saved)
        print(f'原子命题提取 {len(saved)}/600；耗时{time.time()-start:.0f}秒',flush=True)
    print('阶段一机器评审完成',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','judge']);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--freeze-commit')
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out,a.source)
    else:judge(a.out,a.source,a.freeze_commit)
