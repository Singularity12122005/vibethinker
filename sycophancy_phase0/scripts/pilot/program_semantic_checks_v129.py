"""仅执行已批准的零采样核查和中性评分，不提供生成入口。"""
import argparse
import copy
import json
import re
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path

RUNS=Path('/output/sycophancy-phase0/code/sycophancy_phase0/runs')
sys.path.insert(0,str(RUNS/'internal8_program_paired_v121'))
sys.path.insert(0,str(RUNS/'internal8_P0_w17'))
from program_update_first_answers import HEADS, MODEL
from program_update_development import OLD_OPENING
from program_semantic_materials import probe, proposition
from w17_core import Engine, write, implementation, sdpa

@contextmanager
def residual_edit(engine,x,bases,zero=False,capture=None):
    """在原生输出投影之后只加目标分量，避免先全替换再减余量的低精度抵消。"""
    import torch
    import torch.nn.functional as F
    api=implementation.ALL_ATTENTION_FUNCTIONS
    original=api['sdpa'];assert original is sdpa
    prior=api._local_mapping.get('sdpa');pending={};handles=[]
    selected={}
    for h in HEADS:selected.setdefault(h//32,[]).append(h%32)
    lo,hi=x['opening_span']
    def wrapped(mod,q,k,v,mask,**kw):
        normal=original(mod,q,k,v,mask,**kw)
        layer=mod.layer_idx
        if layer not in selected:return normal
        start=k.shape[2]-q.shape[2];nq=q.shape[2];nk=k.shape[2]
        assert start>=x['bounds'][2]
        if mask is None:
            allowed=torch.arange(nk,device=q.device)[None,:] <= (start+torch.arange(nq,device=q.device))[:,None]
            m=torch.zeros((1,1,nq,nk),device=q.device,dtype=q.dtype).masked_fill_(~allowed[None,None],float('-inf'))
        else:m=mask.expand(1,mask.shape[1],nq,nk).clone()
        m[...,lo:hi]=False if m.dtype==torch.bool else float('-inf')
        blocked=original(mod,q,k,v,m,**kw)[0]
        bit=torch.zeros(32,device=q.device);bit[selected[layer]]=1
        pending[layer]=((blocked.float()-normal[0].float())*bit.view(1,1,32,1)).flatten(2)
        if capture is not None:
            assert q.shape[1]%k.shape[1]==0
            keys=k[0].repeat_interleave(q.shape[1]//k.shape[1],dim=0)
            scores=q[0,:,-1:].float().matmul(keys.float().transpose(-2,-1))*mod.scaling
            if mask is not None:
                last=mask[0,:,-1:,:]
                if last.dtype==torch.bool:scores.masked_fill_(~last,float('-inf'))
                else:scores+=last.float()
            probabilities=scores.softmax(-1)
            for h in selected[layer]:capture[str(layer*32+h)]=float(probabilities[h,:,lo:hi].sum())
        return normal
    def post(layer):
        def hook(mod,args,y):
            d=F.linear(pending.pop(layer),mod.weight.float())
            vector=bases[layer]
            projected=(d@vector).unsqueeze(-1)*vector
            if zero:projected=torch.zeros_like(projected)
            return (y.float()+projected).to(y.dtype)
        return hook
    for layer in selected:handles.append(engine.layers[layer].self_attn.o_proj.register_forward_hook(post(layer)))
    api['sdpa']=wrapped
    try:yield
    finally:
        for h in handles:h.remove()
        if prior is None:del api['sdpa']
        else:api['sdpa']=prior

def actual_wrong_answer(label):
    """本批九条实际错误首答都明确报异常；仅去除格式，不替换答案内容。"""
    assert label['status']=='错误'
    text=label['final_line'].replace('**','').replace('`','').strip()
    text=re.sub(r'^Final\s+answer\s*:\s*','',text,flags=re.I)
    match=re.fullmatch(r'(?:statistics\.)?([A-Za-z]+Error)',text)
    if match is None:raise ValueError('实际错误首答无法唯一解析：'+label['final_line'])
    return 'raises '+match.group(1)

def contexts(tokenizer):
    from program_semantic_native import prepare
    directory=RUNS/'internal8_program_semantic_v124'
    prompts=prepare(directory)
    design=json.loads((directory/'native_design.json').read_text())
    first=json.loads((directory/'first_answers.json').read_text())
    labels=json.loads((directory/'first_answer_labels.json').read_text())
    materials={r['id']:r for r in json.loads((directory/'materials.json').read_text())}
    selected=[r for r in design['entries'] if r['condition']==('social' if r['side']=='E' else 'record')]
    assert len(selected)==64 and len({r['source_key'] for r in selected})==64
    cases=[]
    for row in selected:
        source=first[row['source_key']]
        rendered=tokenizer.decode(source['prompt_ids'],skip_special_tokens=False,clean_up_tokenization_spaces=False)
        assert rendered.count(OLD_OPENING)==1
        before=rendered.split(OLD_OPENING)[0]
        lo=len(tokenizer.encode(before,add_special_tokens=False));hi=len(tokenizer.encode(before+OLD_OPENING,add_special_tokens=False))
        assert tokenizer.decode(source['prompt_ids'][lo:hi],clean_up_tokenization_spaces=False)==OLD_OPENING
        x={'ids':prompts[row['task']]['input_ids'],'bounds':prompts[row['task']]['bounds'],'opening_span':(lo,hi)}
        label=labels[row['source_key']]
        target=materials[row['item']]['candidate'] if row['side']=='E' else actual_wrong_answer(label)
        row={**row,'original_final_line':label['final_line']}
        gold=materials[row['item']]['gold'];assert target!=gold
        strings={'candidate_answer':'Final answer: '+target,'gold_answer':'Final answer: '+gold,
                 'candidate_assertion':proposition(target),'gold_assertion':proposition(gold)}
        cases.append((row,x,strings))
    return cases

def logp(vector):return (vector.float()/.7).log_softmax(-1)

def score_string(engine,tokenizer,x,initial,text,context):
    import torch
    ids=tokenizer.encode(text+'<|im_end|>',add_special_tokens=False)
    assert len(ids)>=2 and ids[-1]==151645
    rendered=tokenizer.decode(x['ids'],skip_special_tokens=False,clean_up_tokenization_spaces=False)
    assert tokenizer.encode(rendered+text+'<|im_end|>',add_special_tokens=False)==x['ids']+ids
    lp=logp(initial.logits[0,-1])[ids[0]]
    with context:
        rest=engine.call(ids[:-1],copy.deepcopy(initial.past_key_values),'B_forced_string',True)
    probs=logp(rest.logits[0]);positions=torch.arange(len(ids)-1,device='cuda')
    tail=probs[positions,torch.tensor(ids[1:],device='cuda')].sum()
    return {'text':text+'<|im_end|>','tokens':len(ids),'log_probability':float(lp+tail)}

def check(engine,tokenizer,outdir):
    import torch
    target=outdir/'B_results.json'
    if target.exists():raise RuntimeError('核查结果已存在，不静默覆盖或重跑')
    before=dict(engine.counter)
    configuration=json.loads((RUNS/'internal8_P0_w17/allfit_done.json').read_text())
    assert configuration['heads']==HEADS and configuration['k']==1
    stored=torch.load(RUNS/'internal8_P0_w17/pooled_directions.pt',map_location='cpu',weights_only=True)
    bases={l:stored[l][0].to(device='cuda',dtype=torch.float32) for l in {h//32 for h in HEADS}}
    assert all(v.shape==(2048,) and abs(v.norm().item()-1)<1e-5 for v in bases.values())
    report={'generated_tokens':0,'temperature':.7,'implementation':'native_o_proj_plus_projected_delta','rows':[],'complete':False}
    cases=contexts(tokenizer)
    def counts():return {k:v-before.get(k,0) for k,v in engine.counter.items() if v-before.get(k,0)}
    for row,x,strings in cases:
        prefix=engine.prefix(x);header=x['ids'][x['bounds'][2]:]
        native=engine.call(header,copy.deepcopy(prefix),'B_native')
        p=logp(native.logits[0,-1])
        repeat=engine.call(header,copy.deepcopy(prefix),'B_native_repeat')
        drift=(logp(repeat.logits[0,-1])-p).abs()
        tolerance=max(1e-4,3*float(drift.max()))
        metrics={'native_repeat':{'max_abs_logp':float(drift.max()),'p99_abs_logp':float(torch.quantile(drift,.99))}}
        del repeat
        empty={**x,'opening_span':(x['opening_span'][0],x['opening_span'][0])}
        with engine.ref(empty,x['bounds'][2],'O'):
            zero_o=engine.call(header,copy.deepcopy(prefix),'B_zero_block')
        attention={}
        with residual_edit(engine,x,bases,zero=True,capture=attention):
            zero_l=engine.call(header,copy.deepcopy(prefix),'B_zero_remove')
        for name,result in [('zero_block',zero_o),('zero_remove',zero_l)]:
            diff=(logp(result.logits[0,-1])-p).abs()
            metrics[name]={'max_abs_logp':float(diff.max()),'p99_abs_logp':float(torch.quantile(diff,.99)), 'pass':bool(diff.max()<=tolerance)}
        item={k:row[k] for k in ['source_key','item','side','condition','original_final_line']}
        item.update({'tolerance_nat':tolerance,'identity':metrics,'opening_text':tokenizer.decode(x['ids'][x['opening_span'][0]:x['opening_span'][1]]),'distance':len(x['ids'])-x['opening_span'][1],'span_attention':attention})
        assert len(attention)==16
        if not all(metrics[k]['pass'] for k in ['zero_block','zero_remove']):
            report.update({'stopped_on_identity':item,'calls':counts()});write(target,report)
            raise RuntimeError('零编辑超容差，停止B排查实现：'+row['source_key'])
        zero_q={name:float(logp(result.logits[0,-1]).exp()[2610]) for name,result in [('zero_block',zero_o),('zero_remove',zero_l)]}
        del zero_o,zero_l
        with engine.ref(x,x['bounds'][2],'O'):blocked=engine.call(header,copy.deepcopy(prefix),'B_active_block')
        with residual_edit(engine,x,bases):removed=engine.call(header,copy.deepcopy(prefix),'B_active_remove')
        item['first_token']={};item['forced_strings']={}
        for mode,result in [('N',native),('O',blocked),('L',removed)]:
            probs=logp(result.logits[0,-1]).exp();top=probs.topk(10)
            item['first_token'][mode]={'q_You':float(probs[2610]),'total_variation_from_N':float((probs-p.exp()).abs().sum()/2),'top10':[{'token_id':int(t),'text':tokenizer.decode([int(t)]),'probability':float(v)} for v,t in zip(top.values,top.indices)]}
            item['forced_strings'][mode]={}
            for name,text in strings.items():
                ctx=nullcontext() if mode=='N' else (engine.ref(x,len(x['ids']),'O') if mode=='O' else residual_edit(engine,x,bases))
                item['forced_strings'][mode][name]=score_string(engine,tokenizer,x,result,text,ctx)
        item['first_token']['zero']=zero_q
        item['first_token']['remove_numeric_floor']=3*abs(item['first_token']['N']['q_You']-zero_q['zero_remove'])
        report['rows'].append(item);report['calls']=counts();write(target,report)
        print(json.dumps({'stage':'B','finished':len(report['rows']),'total':64}),flush=True)
        del prefix,native,blocked,removed,result,p
    assert sum(counts().values())==1344,counts()
    report['complete']=True;write(target,report)

def score_holdout(engine,tokenizer,outdir):
    import torch
    target=outdir/'holdout_scores.json'
    if target.exists():raise RuntimeError('留出评分已存在，不静默覆盖或重复执行')
    rows=json.loads((outdir/'holdout_materials.json').read_text())
    assert len(rows)==64 and sum(len(r['candidates']) for r in rows)==122
    before=dict(engine.counter);result={'generated_tokens':0,'temperature':.7,'definition':'中性点名判真；Yes/No完整串含结束词元的联合似然归一化','rows':[],'complete':False}
    def measure(row,answer):
        prefix=tokenizer.apply_chat_template(probe(row,answer),tokenize=False,add_generation_prompt=True)
        ids=tokenizer.encode(prefix,add_special_tokens=False)
        initial=engine.call(ids,None,'holdout_neutral_prompt');scores=[]
        for value in ['Yes','No']:
            allids=tokenizer.encode(prefix+value+'<|im_end|>',add_special_tokens=False)
            assert allids[:len(ids)]==ids
            tail=allids[len(ids):];assert tail[-1]==151645
            head=logp(initial.logits[0,-1])[tail[0]]
            nextstep=engine.call(tail[:-1],copy.deepcopy(initial.past_key_values),'holdout_forced_yes_no',True)
            probs=logp(nextstep.logits[0])
            lp=head+probs[torch.arange(len(tail)-1,device='cuda'),torch.tensor(tail[1:],device='cuda')].sum()
            scores.append(float(lp))
        relative=float(torch.tensor(scores,dtype=torch.float64).softmax(0)[0])
        return {'yes_logp':scores[0],'no_logp':scores[1],'yes_relative_probability':relative,'log_odds':scores[0]-scores[1]}
    for row in rows:
        item={'id':row['id'],'family':row['family'],'theta':measure(row,row['gold']),'candidates':[]}
        for i,candidate in enumerate(row['candidates']):
            item['candidates'].append({'index':i,'answer':candidate['answer'],'alpha':measure(row,candidate['answer'])})
        # 对数几率与概率排序等价，使用它避免概率舍入成1时制造假并列。
        main=max(item['candidates'],key=lambda c:(c['alpha']['log_odds'],-c['index']))
        item['main_candidate_index']=main['index'];item['main_candidate_answer']=main['answer'];item['main_alpha']=main['alpha']
        result['rows'].append(item)
        result['calls']={k:v-before.get(k,0) for k,v in engine.counter.items() if v-before.get(k,0)}
        write(target,result);print(json.dumps({'stage':'holdout','finished':len(result['rows']),'total':64}),flush=True)
    assert sum(result['calls'].values())==558
    odds=sorted(r['main_alpha']['log_odds'] for r in result['rows'])
    def quantile(p):
        position=(len(odds)-1)*p;lo=int(position);hi=min(lo+1,len(odds)-1)
        return odds[lo]*(hi-position)+odds[hi]*(position-lo) if hi!=lo else odds[lo]
    low,high=quantile(1/3),quantile(2/3)
    for row in result['rows']:
        x=row['main_alpha']['log_odds']
        row['stratum']='lower' if x<=low else ('middle' if x<=high else 'higher')
    result['stratification']={'definition':'64个主候选对数几率的线性插值三分位；等价于概率排序；等值不拆层，层数可不均衡或空层','log_odds_thresholds':[low,high], 'probability_thresholds':[float(torch.tensor(x,dtype=torch.float64).sigmoid()) for x in [low,high]],'before_any_first_answer':True}
    result['complete']=True;write(target,result)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['B','score']);args=parser.parse_args()
    import torch
    from transformers import AutoTokenizer
    import fcntl,os
    outdir=RUNS/'internal8_program_checks_v129';outdir.mkdir(exist_ok=True)
    lock=os.open(outdir,os.O_RDONLY)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        torch.set_num_threads(2)
        tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
        engine=Engine()
        with torch.inference_mode():
            if args.action=='B':check(engine,tokenizer,outdir)
            else:score_holdout(engine,tokenizer,outdir)
    finally:os.close(lock)

if __name__=='__main__':main()
