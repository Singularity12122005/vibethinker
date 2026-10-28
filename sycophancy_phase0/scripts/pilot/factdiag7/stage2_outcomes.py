"""四分答案与隔离名单的语义评审；与关系提取分别保存，不改旧标签。"""
from pathlib import Path
import argparse,hashlib,re,subprocess,time
from stage2_plan import load,save,identity,baseline_records,legacy
from stage2_freeze import validate
from stage2_labels import answer_prompt,belief_inputs,parse_answer_review,parse_belief,answer_state
from stage2_identity import parse_complete


def inputs(out,source,phase):
    protocol=load(out/'factdiag7_stage2_label_protocol.json')
    if phase=='belief':
        rows=load(out/'stage2_belief_generations.json')
        return protocol,belief_inputs(rows)
    plan=load(out/'factdiag7_stage2_materials.json');bank={r['item_id']:r for r in plan['items']}
    rows=baseline_records(source) if phase=='baseline' else load(out/'stage2_Q2_generations.json')
    if len(rows)!=(600 if phase=='baseline' else 960):raise RuntimeError('答案评审的生成输入未完整')
    parser=legacy().p3.old;result=[]
    for row in rows:
        item=dict(bank[row['conflict_id']]);person=next(p for p in item['people'] if p['type']==row['candidate_type'])
        item.update(d=person['name'],d_aliases=person['aliases'])
        parsed=parse_complete(row['assistant_text'],item,parser)
        prompt=answer_prompt(item['question_en'],row['assistant_text'])
        result.append(dict(id=identity(row),work_id=item['work_id'],prompt=prompt,response=row['assistant_text'],
            item=item,row=dict(row,parsed=parsed),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()))
    if len({q['id'] for q in result})!=len(result):raise RuntimeError('答案评审身份重复')
    return protocol,result


def interpret(q,raw,judge_truncated,phase):
    if phase=='belief':
        return parse_belief(raw,q['response'],truncated=q['truncated'],looped=q['looped'],judge_truncated=judge_truncated)
    review=({'parse_status':'UNPARSEABLE','flags':['REVIEW_TRUNCATED']} if judge_truncated
            else parse_answer_review(raw,q['response']))
    try:
        state=answer_state(q['row'],q['item'],review)
    except ValueError:
        if review.get('parse_status')=='OK' and review.get('confirmed') is True:
            raise
        # 缺少语义评审意味着无法分清保留和确定作答，不冒充模型技术失败。
        state=dict(status=None,answer_status=None,answer_unjudgeable=True,review_missing=True,
                   correct=[0,1],wrong=[0,1],reserved=[0,1],L_target=[0,1],
                   valid_generation=[0,1],answer_coverage=[0,1],reason='答案语义评审不可判')
    return {'review':review,'answer':state,'parsed':q['row']['parsed']}


def run(out,source,phase,commit,check_only=False):
    validate(out)
    if not re.fullmatch('[0-9a-f]{40}',commit):raise RuntimeError('缺已提交的完整生成与标签协议')
    protocol,queue=inputs(out,source,phase)
    path=out/f'stage2_{phase}_outcomes.json';saved=load(path) if path.exists() else {}
    bank={q['id']:q for q in queue}
    if not set(saved)<=set(bank):raise RuntimeError('已有答案评审身份不同')
    for k,r in saved.items():
        if r['prompt_sha256']!=bank[k]['prompt_sha256']:raise RuntimeError('已有评审提示改变')
    pending=[q for q in queue if q['id'] not in saved]
    print('答案/名单评审',phase,len(saved),'/',len(queue),flush=True)
    if check_only or not pending:return
    occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    if occupied:raise RuntimeError('显卡已有进程：'+occupied)
    legacy();from legacy import judge_dependency
    settings=protocol['judge_runtime'];client=judge_dependency().LocalJudge(settings['model_path'],batch_size=settings['batch'])
    start=time.time()
    for off in range(0,len(pending),settings['batch']):
        batch=pending[off:off+settings['batch']]
        texts=[client.tok.apply_chat_template([{'role':'user','content':q['prompt']}],tokenize=False,add_generation_prompt=True) for q in batch]
        encoded=client.tok(texts,return_tensors='pt',padding=True).to(client.model.device)
        with client.torch.no_grad():
            generated=client.model.generate(**encoded,do_sample=False,max_new_tokens=settings['max_new_tokens'],
                pad_token_id=client.tok.pad_token_id,temperature=None,top_p=None,top_k=None)
        sampled=generated[:,encoded.input_ids.shape[1]:];raws=client.tok.batch_decode(sampled,skip_special_tokens=True)
        if len(raws)!=len(batch):raise RuntimeError('评审返回数不符')
        for q,raw,ids in zip(batch,raws,sampled):
            seq=ids.tolist();cut=len(seq)>=settings['max_new_tokens'] and client.tok.eos_token_id not in seq
            saved[q['id']]=dict(raw=raw,result=interpret(q,raw,cut,phase),judge_truncated=cut,
                prompt_sha256=q['prompt_sha256'],freeze_commit=commit)
        save(path,saved)
        print(f'{phase} 答案/名单 {len(saved)}/{len(queue)}；耗时{time.time()-start:.0f}秒',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--phase',choices=['baseline','Q2','belief'],required=True);p.add_argument('--freeze-commit',required=True)
    p.add_argument('--check-only',action='store_true');a=p.parse_args();run(a.out,a.source,a.phase,a.freeze_commit,a.check_only)
