"""S0结构级试运行与第二轮实际答案的策略读数；不估计正式效应。"""
from pathlib import Path
import argparse
from core import load,save,digest,same_identity
from screen import identity,make_main
from screen_judge import collection_items
from histories import trial_selection,run_rows
from readouts import pair,run
from legacy import previous
from judging import aliases_for


def policy_readouts(out,collections):
    definitions={};references=[];reused=[];excluded=[]
    existing={}
    for path in out.glob('readout_*_inputs.json'):
        if path.name=='readout_policy_inputs.json':continue
        for key,value in load(path)['definitions'].items():
            if key in existing and existing[key]['definition']!=value:
                # 不同集合可能只在采样数上不同，纯前向定义须相同。
                left={k:v for k,v in existing[key]['definition'].items() if k!='samples'}
                right={k:v for k,v in value.items() if k!='samples'}
                if left!=right:raise RuntimeError('已有读数键冲突')
            existing[key]=dict(collection=path.name[len('readout_'):-len('_inputs.json')],definition=value)
    for collection in collections:
        bank=collection_items(out,collection)
        for h in load(out/f's0_{collection}_histories.json'):
            if h['current_missing']:continue
            item=bank[h['conflict_id']];x=h['current_value'];numeric=item['answer_format']=='number'
            candidates=item['candidates'] if h['path']=='correct' else [dict(type='correction',name=item['gold'],aliases=item['gold_aliases'])]
            for c in candidates:
                ref=dict(history_id=identity(h),item_id=item['item_id'],work_id=item['work_id'],
                         candidate_type=c['type'],candidate=c['name'],current_answer=x)
                if same_identity(x,c['name'],c.get('aliases',[]),numeric):
                    excluded.append(dict(ref,reason='d=x'));continue
                d=pair(item['question_en'],x,c['name'])
                key=digest({k:v for k,v in d.items() if k!='samples'})
                ref=dict(ref,key=key)
                if key in existing:reused.append(dict(ref,collection=existing[key]['collection']))
                else:definitions[key]=d;references.append(ref)
    return dict(definitions=definitions,references=references,reused=reused,excluded=excluded)


def prepare(out,collections):
    selections={}
    for collection in collections:
        items=list(collection_items(out,collection).values())
        chosen,excluded=trial_selection(items,load(out/f's0_{collection}_histories.json'))
        meta=dict(collection=collection,selected=[dict(history_id=identity(h),item_id=h['conflict_id'],
                 idx=h['idx'],candidate=c['name'],candidate_type=c['type']) for h,c in chosen],
                 excluded=excluded,planned=40,actual_planned=len(chosen)*4,
                 note='每项一条自然历史、四条试运行；不足十项不替补国家或另造历史')
        path=out/f's0_{collection}_trial_selection.json'
        if path.exists() and load(path)!=meta:raise RuntimeError('既有试运行抽样改变')
        save(path,meta);selections[collection]=chosen
    return selections,policy_readouts(out,collections)


def tasks(main,chosen):
    result=[]
    for h,c in chosen:
        text=previous().p3.old.S3.format(D=c['name'])
        ids=main.continue_from(h,text)
        for rep in range(4):
            result.append(dict(conflict_id=h['conflict_id'],work_id=h['work_id'],idx=h['idx'],
                path=h['path'],arm='S',rep=rep,t=3,phase='G6_S0_TRIAL',
                user_text=text,prompt_ids=ids,previous_length=h['n_new_tokens'],
                original=h['current_value'],candidate=c['name'],candidate_type=c['type'],
                source_history_id=identity(h)))
    return result


def main(out,collections,prepare_only=False):
    selections,policy=prepare(out,collections)
    print('试运行排定',{k:len(v)*4 for k,v in selections.items()},flush=True)
    print('策略读数补齐',len(policy['definitions']),'复用',len(policy['reused']),flush=True)
    if prepare_only:return
    items=[i for c in collections for i in collection_items(out,c).values()]
    engine=make_main('/output/sycophancy-phase0/model',items);engine.forward_temperature=1.0
    run(engine,policy,out,'policy',stage='score')
    for collection,chosen in selections.items():
        run_rows(engine,tasks(engine,chosen),out/f's0_{collection}_trial.json',out)
    print('S0结构试运行生成结束',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--collections',nargs='+',default=['adaptation','version','computable','capital'])
    ap.add_argument('--prepare-only',action='store_true')
    a=ap.parse_args();main(a.out,a.collections,a.prepare_only)
