"""A100分时执行第三批：补第二轮、复用历史、第三轮、两种评审。"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import time
import protocol as p


class Main(p.previous_runtime.Main):
    def generate(self,tasks):
        from sycophancy_phase0.inference.engine import GenRequest
        from sycophancy_phase0.constants import IM_END, ENDOFTEXT
        prefixes=[self.tok.encode(p.A1,add_special_tokens=False) if r.get('condition')=='A1' else [] for r in tasks]
        requests=[GenRequest(ids=r['prompt_ids']+prefix,seed=p.seed_for(r),max_new_tokens=1024,temperature=.7) for r,prefix in zip(tasks,prefixes)]
        outputs=self.engine.generate(requests)
        if len(outputs)!=len(tasks):raise RuntimeError('推理返回条数不符')
        rows=[]
        for task,result,prefix in zip(tasks,outputs,prefixes):
            n=next((j+1 for j,x in enumerate(result.ids) if x in (IM_END,ENDOFTEXT)),len(result.ids))
            normalized=self.builder.normalize(result.ids,result.finish_reason)
            ids=prefix+normalized.ids
            text=self.tok.decode(ids,skip_special_tokens=True)
            if prefix and not text.startswith(p.A1):raise RuntimeError('A1未成为实际助手开头')
            rows.append(dict(**task,assistant_ids=ids,assistant_text=text,n_new_tokens=n,forced_prefix_tokens=len(prefix),
                             truncated=normalized.truncated,looped=p.old.looped(ids[:len(prefix)+n]),
                             parsed=p.old.parse_final(text,self.bank[task['conflict_id']])))
        return rows


def run_tasks(main,tasks,path):
    expected={p.identity(r):r for r in tasks}
    cached={p.identity(r):r for r in p.load(path,[])}
    if len(expected)!=len(tasks) or not set(cached)<=set(expected):raise RuntimeError('任务身份或已有数据不符')
    for key,row in cached.items():
        for field in ('prompt_ids','user_text','condition'):
            if row.get(field)!=expected[key].get(field):raise RuntimeError('已存任务内容不符')
    pending=sorted((r for key,r in expected.items() if key not in cached),key=lambda r:(r['work_id'],r['previous_length'],p.identity(r)))
    start=time.time()
    for off in range(0,len(pending),main.batch):
        for row in main.generate(pending[off:off+main.batch]):cached[p.identity(row)]=row
        p.save(path,[cached[key] for key in expected if key in cached])
        print(f'{path.name} {len(cached)}/{len(tasks)} 耗时{time.time()-start:.0f}秒',flush=True)
    if not tasks:p.save(path,[])
    return [cached[key] for key in expected]


def check(args,phase2=False):
    reg=p.load(args.out/'factdiag3_prereg.json')
    materials=p.load(args.out/'factdiag3_materials.json')
    if not reg or len(args.prereg_commit or '')!=40:raise RuntimeError('必须提供已推送预注册的真实提交号')
    if p.digest(reg['frozen'])!=reg['frozen_sha256'] or p.digest(materials)!=reg['frozen']['materials_sha256']:raise RuntimeError('冻结数据发生变化')
    from specification import fixed_rules
    if fixed_rules()!=reg['frozen']['rules']:raise RuntimeError('实现的规则与冻结不符')
    for name,sha in reg['frozen']['code_sha256'].items():
        if hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('冻结代码发生变化：'+name)
    for name,sha in reg['frozen']['source_sha256'].items():
        if hashlib.sha256((args.previous/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('前批原始文件发生变化：'+name)
    if phase2 and not reg.get('phase2'):raise RuntimeError('尚未完成第二阶段预注册')
    return reg,{m['work_id']:m for m in materials}


def sources(args):
    first=p.load(args.previous/'calibration_t1.json')
    second=p.load(args.previous/'pilot_t2.json')+p.load(args.previous/'remaining_t2.json')
    return first,second


def select_seconds(first,second,materials):
    existing={(r['conflict_id'],r['idx']):r for r in second}
    selected=[]
    for wid,m in sorted(materials.items()):
        for unit,item,limit,correct in [('F-D',m['F'],8,False),('S_T',m['F'],6,True)]:
            candidates=sorted((r for r in first if r['conflict_id']==item['conflict_id'] and p.old.valid_first(r)
                               and (r['parsed']['value']==item['gold'])==correct),key=lambda r:r['idx'])[:limit]
            for row in candidates:selected.append((wid,unit,row,existing.get((row['conflict_id'],row['idx']))))
    return selected


def add_seconds(args):
    reg,materials=check(args)
    first,second=sources(args)
    chosen=select_seconds(first,second,materials)
    bank={m['F']['conflict_id']:m['F'] for m in materials.values()}
    new=[x for x in chosen if x[3] is None]
    if not new:p.save(args.out/'additional_t2.json',[]);return
    main=Main(args.main_model,bank,args.batch)
    tasks=[]
    for wid,unit,row,_ in new:
        item=materials[wid]['F']
        tasks.append(dict(work_id=wid,unit=unit,conflict_id=row['conflict_id'],idx=row['idx'],path='correct' if unit=='S_T' else 'natural_wrong',
            arm='shared',rep=0,t=2,phase='factdiag3_history',user_text=p.old.X2,prompt_ids=main.continue_from(row,p.old.X2),
            previous_length=row['n_new_tokens'],original=item['gold'] if unit=='S_T' else row['parsed']['value'],
            original_raw=None if unit=='S_T' else p.old.raw_final_value(row['assistant_text']),candidate=item['d'] if unit=='S_T' else item['gold']))
    run_tasks(main,tasks,args.out/'additional_t2.json')


def freeze_histories(args):
    reg,materials=check(args)
    if reg.get('phase2'):raise RuntimeError('第二阶段已冻结，禁止覆盖')
    first,second=sources(args)
    additional=p.load(args.out/'additional_t2.json',[])
    added={(r['conflict_id'],r['idx']):r for r in additional}
    histories=[];counts={}
    for wid,m in sorted(materials.items()):
        rows=sorted((r for r in second if r['conflict_id']==wid and p.old.clean_second(r,m['R'])),key=lambda r:r['idx'])
        if len(rows)!=6:raise RuntimeError('R历史不是预定6条：'+wid)
        for row in rows:
            for unit in ('R-S','L'):histories.append(dict(work_id=wid,unit=unit,row=row,source='batch2'))
    checks={r['id']:r for r in p.load(args.checks)}
    if set(checks)!=set(materials):raise RuntimeError('候选独立核对不完整')
    for wid,unit,firstrow,existing in select_seconds(first,second,materials):
        row=existing or added.get((firstrow['conflict_id'],firstrow['idx']))
        if row is None or 'judge' not in row:raise RuntimeError('第二轮未完成真实评审')
        item=materials[wid]['F']
        status=p.second_status(row,item) if unit=='F-D' else ('eligible' if p.old.clean_second(row,item) else 'not_clean')
        accepted=status=='still_wrong' if unit=='F-D' else status=='eligible' and checks[wid]['answer']=='no'
        counts.setdefault(wid,[]).append(dict(unit=unit,idx=row['idx'],status=status,accepted=accepted))
        if accepted:histories.append(dict(work_id=wid,unit=unit,row=row,source='batch2' if existing else 'factdiag3'))
    public=[dict(work_id=h['work_id'],unit=h['unit'],idx=h['row']['idx'],source=h['source'],
                 history_sha256=p.digest({'prompt_ids':h['row']['prompt_ids'],'assistant_ids':h['row']['assistant_ids'],'assistant_text':h['row']['assistant_text']})) for h in histories]
    reg['phase2']=dict(candidate_checks=list(checks.values()),history_list=public,history_selection=counts)
    p.save(args.out/'histories.json',histories)
    p.save(args.out/'factdiag3_prereg.json',reg)
    print(json.dumps({u:sum(h['unit']==u for h in histories) for u in p.COUNTS},ensure_ascii=False))


def branch_tasks(main,histories,materials):
    tasks=[]
    for h in histories:
        wid,unit,row=h['work_id'],h['unit'],h['row'];m=materials[wid]
        text=p.user_message(m,unit);ids=main.continue_from(row,text)
        item=p.view(m,unit)
        candidate=m['F']['gold'] if unit in ('F-D','L') else item['d']
        for condition in ('base','A1'):
            for rep in range(p.COUNTS[unit]):
                tasks.append(dict(work_id=wid,unit=unit,condition=condition,conflict_id=wid+'_'+unit,idx=row['idx'],
                    path=unit,arm=condition,rep=rep,t=3,phase='factdiag3',user_text=text,prompt_ids=list(ids),
                    previous_length=row['n_new_tokens'],original=row['original'],original_raw=row.get('original_raw'),candidate=candidate,
                    shared_second_prompt_ids=row['prompt_ids'],shared_second_assistant_ids=row['assistant_ids']))
    return tasks


def branches(args):
    reg,materials=check(args,True)
    histories=p.load(args.out/'histories.json')
    for h,expected in zip(histories,reg['phase2']['history_list']):
        actual=p.digest({k:h['row'][k] for k in ('prompt_ids','assistant_ids','assistant_text')})
        if actual!=expected['history_sha256'] or (h['work_id'],h['unit'],h['row']['idx'])!=(expected['work_id'],expected['unit'],expected['idx']):raise RuntimeError('历史与预注册不符')
    if len(histories)!=len(reg['phase2']['history_list']):raise RuntimeError('历史数量不符')
    pilot=set(sorted(materials)[:3]);selected=pilot if args.cohort=='pilot' else set(materials)-pilot
    if args.cohort=='remaining' and p.load(args.out/'budget.json',{}).get('over_budget',True):raise RuntimeError('先行预算未放行')
    bank={wid+'_'+unit:p.view(m,unit) for wid,m in materials.items() for unit in p.COUNTS}
    main=Main(args.main_model,bank,args.batch)
    tasks=branch_tasks(main,[h for h in histories if h['work_id'] in selected],materials)
    run_tasks(main,tasks,args.out/f'{args.cohort}_t3.json')


class PropositionClient:
    """复用已加载评审模型；命题与引文输出使用512词元，立场仍64。"""
    def __init__(self,client): self.client=client
    def __call__(self,prompts):
        c=self.client
        rendered=[c.tok.apply_chat_template([{'role':'user','content':x}],tokenize=False,add_generation_prompt=True) for x in prompts]
        batch=c.tok(rendered,return_tensors='pt',padding=True).to(c.model.device)
        with c.torch.no_grad():
            gen=c.model.generate(**batch,do_sample=False,max_new_tokens=512,pad_token_id=c.tok.pad_token_id,temperature=None,top_p=None,top_k=None)
        return c.tok.batch_decode(gen[:,batch.input_ids.shape[1]:],skip_special_tokens=True)


def judge(args):
    _,materials=check(args,args.stage!='judge2')
    path=args.out/('additional_t2.json' if args.stage=='judge2' else f'{args.cohort}_t3.json')
    rows=p.load(path)
    if rows is None:raise RuntimeError('尚无生成文件')
    from rescore import LocalJudge
    client=None;start=time.time()
    bank={m['F']['conflict_id']:m['F'] for m in materials.values()} if args.stage=='judge2' else {wid+'_'+unit:p.view(m,unit) for wid,m in materials.items() for unit in p.COUNTS}
    pending=[r for r in rows if r.get('unit')!='L' and 'judge' not in r]
    if pending:client=LocalJudge(args.judge_model,batch_size=8)
    for off in range(0,len(pending),8):
        p.previous_runtime.label_batch(client,pending[off:off+8],bank);p.save(path,rows)
        print(f'立场评审 {min(off+8,len(pending))}/{len(pending)} {time.time()-start:.0f}秒',flush=True)
    if args.stage=='judge2':return
    pending=[r for r in rows if 'propositions' not in r]
    if pending and client is None:client=LocalJudge(args.judge_model,batch_size=8)
    props=PropositionClient(client)
    for off in range(0,len(pending),8):
        batch=pending[off:off+8];prompts=[p.propositions(materials[r['work_id']],r) for r in batch]
        raw=props(prompts)
        for r,text in zip(batch,raw):
            value=p.parse_propositions(text,r['assistant_text'])
            r['propositions']=value;r['propositions_raw']=text
        retry=[j for j,r in enumerate(batch) if r['propositions'] is None]
        if retry:
            for j,text in zip(retry,props([prompts[j]+p.old.RETRY_SUFFIX for j in retry])):
                batch[j]['propositions']=p.parse_propositions(text,batch[j]['assistant_text']);batch[j]['propositions_raw']=text
        p.save(path,rows)
        print(f'命题评审 {min(off+8,len(pending))}/{len(pending)} {time.time()-start:.0f}秒',flush=True)


def budget(args):
    _,materials=check(args,True)
    histories=p.load(args.out/'histories.json');rows=p.load(args.out/'pilot_t3.json')
    expected=sum(p.COUNTS[h['unit']]*2 for h in histories if h['work_id'] in sorted(materials)[:3])
    if len(rows)!=expected:raise RuntimeError('先行生成不完整')
    total=sum(r['n_new_tokens'] for r in p.load(args.out/'additional_t2.json',[]));detail={}
    for unit in p.COUNTS:
        for condition in ('base','A1'):
            sample=[r['n_new_tokens'] for r in rows if r['unit']==unit and r['condition']==condition]
            mean=sum(sample)/len(sample) if sample else 1024
            n=sum(h['unit']==unit for h in histories)*p.COUNTS[unit]
            total+=n*mean;detail[unit+'_'+condition]=dict(pilot_n=len(sample),mean_new_tokens=mean,planned_n=n)
    result=dict(projected_new_tokens=total,limit=1500000,over_budget=total>1500000,detail=detail,
                scope='新增第二轮与全部第三轮新采样词元；不计旧历史、输入或固定A1前缀；评审词元另列。')
    p.save(args.out/'budget.json',result);print(json.dumps(result,ensure_ascii=False))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('stage',choices=['second','judge2','histories','branches','judge3','budget'])
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--previous',type=Path,required=True)
    ap.add_argument('--checks',type=Path);ap.add_argument('--prereg-commit',required=True)
    ap.add_argument('--main-model',default='/output/sycophancy-phase0/model')
    ap.add_argument('--judge-model',default='/output/sycophancy-phase0/judge-model')
    ap.add_argument('--batch',type=int,default=16);ap.add_argument('--cohort',choices=['pilot','remaining'],default='pilot')
    args=ap.parse_args()
    start=time.time()
    {'second':add_seconds,'judge2':judge,'histories':freeze_histories,'branches':branches,'judge3':judge,'budget':budget}[args.stage](args)
    execution=p.load(args.out/'execution.json',[])
    execution.append(dict(stage=args.stage,cohort=args.cohort,started_unix=start,seconds=time.time()-start))
    p.save(args.out/'execution.json',execution)

if __name__=='__main__':main()
