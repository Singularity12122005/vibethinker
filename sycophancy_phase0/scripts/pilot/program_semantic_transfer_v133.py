"""第1.33版：固定64段轮廓、768条三臂续写及暂不判读的128条留出首答。"""
import argparse
import copy
import json
import math
import os
import sys
from collections import Counter
from contextlib import nullcontext
from pathlib import Path

from program_semantic_checks_v129 import RUNS, Engine, HEADS, MODEL, contexts, logp, residual_edit, write
from program_semantic_materials import first_prompts

STAGE = 'internal8_program_transfer_v133'
OUT = RUNS / STAGE
HOLDOUT = RUNS / 'internal8_program_holdout_v133'
CHUNK = 256
LIMIT = 16384
ARMS = ('N', 'O', 'L')


def scope(engine, x, bases, arm, start, zero=False):
    if arm == 'N':
        return nullcontext()
    if arm == 'O':
        context = x if not zero else {**x, 'opening_span': (x['opening_span'][0], x['opening_span'][0])}
        return engine.ref(context, start, 'O')
    assert arm == 'L'
    return residual_edit(engine, x, bases, zero=zero)


def inputs(tokenizer):
    import torch
    previous = json.loads((RUNS / 'internal8_program_checks_v129/B_results.json').read_text())
    assert previous['complete'] and len(previous['rows']) == 64
    prior = {r['source_key']: r for r in previous['rows']}
    assert all(r['identity'][k]['pass'] for r in prior.values() for k in ('zero_block', 'zero_remove'))
    configuration = json.loads((RUNS / 'internal8_P0_w17/allfit_done.json').read_text())
    assert configuration['heads'] == HEADS and configuration['k'] == 1
    stored = torch.load(RUNS / 'internal8_P0_w17/pooled_directions.pt', map_location='cpu', weights_only=True)
    bases = {l: stored[l][0].to(device='cuda', dtype=torch.float32) for l in {h // 32 for h in HEADS}}
    assert all(v.shape == (2048,) and abs(v.norm().item()-1) < 1e-5 for v in bases.values())
    cases = contexts(tokenizer)
    assert {r['source_key'] for r, _, _ in cases} == set(prior)
    for row, x, _ in cases:
        b = prior[row['source_key']]
        assert (row['item'], row['side'], row['condition'], row['original_final_line']) == tuple(b[k] for k in ('item','side','condition','original_final_line'))
        assert len(x['ids'])-x['opening_span'][1] == b['distance']
        delta = b['first_token']['N']['q_You']-b['first_token']['O']['q_You']
        row['entry_effect'] = delta
        row['entry_group'] = ('high' if delta > .10 else 'low') if row['side'] == 'E' else 'U'
    assert Counter(r['entry_group'] for r, _, _ in cases) == {'high':18,'low':37,'U':9}
    return cases, bases


def identity(engine, x, bases, ids, cache, native, start, tag):
    """新分块和逐词元调用形状各验一次；不重做已通过的64段助手头检查。"""
    import numpy as np
    import torch
    reference = logp(native.logits[0])
    results = {}
    for name, arm, zero in [('native_repeat','N',False),('zero_block','O',True),('zero_remove','L',True)]:
        with scope(engine, x, bases, arm, start, zero):
            result = engine.call(ids, copy.deepcopy(cache), 'identity_'+tag+'_'+name, True)
        delta = (logp(result.logits[0])-reference).abs()
        maximum = float(delta.max())
        p99 = 0.0 if maximum == 0 else float(np.quantile(delta.cpu().numpy(), .99))
        results[name] = {'max_abs_logp':maximum, 'p99_abs_logp':p99}
        del result, delta
    tolerance = max(1e-4, 3*results['native_repeat']['max_abs_logp'])
    results['tolerance_nat'] = tolerance
    results['pass'] = all(results[k]['max_abs_logp'] <= tolerance for k in ('zero_block','zero_remove'))
    if not results['pass']:
        write(OUT / 'identity_failure.json', {'shape':tag,'results':results})
        raise RuntimeError('新调用形状零编辑超差，停止全部后续计算')
    return results


def profile(engine, tokenizer, cases, bases):
    import torch
    target = OUT / 'profiles.json'
    report = json.loads(target.read_text()) if target.exists() else {
        'complete':False, 'generated_tokens':0, 'temperature':.7, 'chunk_size':CHUNK,
        'direction':'D_KL(P_N || P_O/L)', 'vocabulary':'完整词表，无截尾',
        'alignment':'下标0预测回答首词，最后下标预测存档结束词元；操作从助手头起持续生效',
        'rows':[], 'identity':{}, 'calls':{}}
    if report['complete']:
        assert len(report['rows']) == 64
        return
    old_calls = Counter(report['calls']); before = Counter(engine.counter)
    done = {r['source_key'] for r in report['rows']}
    native = json.loads((RUNS / 'internal8_program_semantic_v124/native_answers.json').read_text())
    expected_chunks = 0
    for row, x, _ in cases:
        a = native[row['result_key']]
        expected_chunks += math.ceil((len(x['ids'])-x['bounds'][2]+len(a['raw_ids'])-1)/CHUNK)
    assert expected_chunks == 151
    report['core_budget'] = 3*64 + 3*expected_chunks
    report['additional_identity_budget'] = 7
    try:
        for row, x, _ in cases:
            if row['source_key'] in done:
                continue
            source = native[row['result_key']]
            assert source['prompt_ids'] == x['ids'] and not source['truncated']
            raw = source['raw_ids']
            assert raw[-1] in (151643,151645)
            assert tokenizer.decode(raw, skip_special_tokens=True) == source['text']
            header = x['ids'][x['bounds'][2]:]
            suffix = header+raw[:-1]
            prefix = engine.prefix(x)
            caches = {arm:copy.deepcopy(prefix) for arm in ARMS}
            del prefix
            item = {k:row[k] for k in ('source_key','item','family','side','condition','entry_effect','entry_group')}
            item.update({'tokens':len(raw),'actual_logp':{a:[] for a in ARMS},'kl':{'O':[],'L':[]}})
            for offset in range(0,len(suffix),CHUNK):
                chunk = suffix[offset:offset+CHUNK]
                start = x['bounds'][2]+offset
                score_start = max(offset,len(header)-1)
                count = offset+len(chunk)-score_start
                selected_ids = raw[score_start-len(header)+1:score_start-len(header)+1+count]
                assert count == len(selected_ids) and count > 0
                for arm in ARMS:
                    checking = arm == 'N' and not report['identity']
                    pre = copy.deepcopy(caches[arm]) if checking else None
                    with scope(engine,x,bases,arm,start):
                        result = engine.call(chunk,caches[arm],'profile_'+arm,True)
                    caches[arm] = result.past_key_values
                    if checking:
                        report['identity']['block'] = identity(engine,x,bases,chunk,pre,result,start,'block')
                        del pre
                        pos = offset+len(chunk)
                        assert pos < len(suffix)
                        one = [suffix[pos]]
                        one_native = engine.call(one,copy.deepcopy(caches['N']),'identity_single_native',True)
                        report['identity']['single'] = identity(engine,x,bases,one,caches['N'],one_native,x['bounds'][2]+pos,'single')
                        del one_native
                    distribution = logp(result.logits[0,score_start-offset:])
                    assert distribution.shape[0] == count and torch.isfinite(distribution).all()
                    indices = torch.tensor(selected_ids,device='cuda')
                    item['actual_logp'][arm].extend(distribution[torch.arange(count,device='cuda'),indices].cpu().tolist())
                    if arm == 'N':
                        native_logp = distribution
                    else:
                        divergence = (native_logp.exp()*(native_logp-distribution)).sum(-1)
                        assert float(divergence.min()) >= -1e-5
                        item['kl'][arm].extend(divergence.cpu().tolist())
                    del result
                del distribution,native_logp
            assert all(len(v)==len(raw) for v in [*item['actual_logp'].values(),*item['kl'].values()])
            report['rows'].append(item)
            report['calls'] = dict(old_calls+(Counter(engine.counter)-before))
            write(target,report)
            print(json.dumps({'stage':'profile','finished':len(report['rows']),'total':64}),flush=True)
            del caches
        report['complete'] = True
    finally:
        report['calls'] = dict(old_calls+(Counter(engine.counter)-before))
        write(target,report)


def generate_one(engine, tokenizer, ids, initial, seed, arm, x, bases, previous, persist):
    import torch
    import g1_runtime_main as legacy
    sampler = legacy.SeededGumbelSampler([seed],temperature=.7,device='cuda')
    seq = torch.tensor([ids],device='cuda')
    cache = copy.deepcopy(initial.past_key_values)
    scores = initial.logits[0,-1].float()
    raw = []; frozen = previous['raw_ids'] if previous else []
    stops = (legacy.IM_END,legacy.ENDOFTEXT)
    def current(finished):
        ended = raw[-1] in stops
        result = {'raw_ids':list(raw),'text':tokenizer.decode(raw,skip_special_tokens=True),
                  'finished':finished,'truncated':not ended,'tokens':len(raw)}
        if finished and not ended:
            assert len(raw)==LIMIT
            result['incomplete_reason']='length_limit'
        return result
    while True:
        token = sampler(seq,scores[None,:]).argmax(-1).item()
        if len(raw)<len(frozen):
            assert token==frozen[len(raw)], '中断续接与原抽样流不一致，停止'
        raw.append(token)
        if token in stops or len(raw)==LIMIT:
            result=current(True);persist(result);return result
        if len(raw)>len(frozen) and len(raw)%128==0:
            persist(current(False))
        seq=torch.cat((seq,seq.new_tensor([[token]])),dim=1)
        start=len(ids)+len(raw)-1
        with scope(engine,x,bases,arm,start):
            step=engine.call([token],cache,'generate_'+arm)
        scores,cache=step.logits[0,-1].float(),step.past_key_values


def sample(engine, tokenizer, cases, bases):
    import g1_runtime_main as legacy
    assert json.loads((OUT/'profiles.json').read_text())['complete']
    path=OUT/'answers.json'
    rows=json.loads(path.read_text()) if path.exists() else {}
    keys={f"{r['source_key']}__{a}__{i}" for r,_,_ in cases for a in ARMS for i in range(4)}
    assert len(keys)==768 and set(rows)<=keys
    status_path=OUT/'generation_status.json'
    status=json.loads(status_path.read_text()) if status_path.exists() else {'complete':False,'calls':{}}
    old_calls=Counter(status['calls']);before=Counter(engine.counter)
    def save_status():
        status.update({'finished':sum(r['finished'] for r in rows.values()),'total':768,
            'limit_hits':sum(r.get('incomplete_reason')=='length_limit' for r in rows.values()),
            'generated_tokens':sum(len(r['raw_ids']) for r in rows.values()),
            'calls':dict(old_calls+(Counter(engine.counter)-before))})
        write(status_path,status)
    try:
        for row,x,_ in cases:
            source=row['source_key']
            if all(rows.get(f'{source}__{a}__{i}',{}).get('finished') for a in ARMS for i in range(4)):
                continue
            prefix=engine.prefix(x);header=x['ids'][x['bounds'][2]:]
            for arm in ARMS:
                if all(rows.get(f'{source}__{arm}__{i}',{}).get('finished') for i in range(4)):
                    continue
                with scope(engine,x,bases,arm,x['bounds'][2]):
                    initial=engine.call(header,copy.deepcopy(prefix),'generate_header_'+arm)
                for repeat in range(4):
                    key=f'{source}__{arm}__{repeat}'
                    if rows.get(key,{}).get('finished'):
                        continue
                    seed=legacy.derive_seed(STAGE,source,'continuation','shared',repeat,1)
                    def persist(answer):
                        rows[key]={**{k:row[k] for k in ('source_key','item','family','side','condition','entry_effect','entry_group')},
                                   'arm':arm,'repeat':repeat,**answer}
                        write(path,rows);save_status()
                    generate_one(engine,tokenizer,x['ids'],initial,seed,arm,x,bases,rows.get(key),persist)
                    print(json.dumps({'stage':'generation','finished':status['finished'],'total':768,'limit_hits':status['limit_hits']}),flush=True)
                del initial
            del prefix
        assert set(rows)==keys and all(r['finished'] for r in rows.values())
        status['complete']=True
    finally:
        save_status()


def holdout(engine,tokenizer):
    import g1_runtime_main as legacy
    assert json.loads((OUT/'generation_status.json').read_text())['complete']
    HOLDOUT.mkdir(exist_ok=True)
    score_dir=RUNS/'internal8_program_checks_v129'
    scored=json.loads((score_dir/'holdout_scores.json').read_text())
    assert scored['complete'] and len(scored['rows'])==64
    materials=json.loads((score_dir/'holdout_materials.json').read_text())
    assert len(materials)==64 and {r['id'] for r in materials}=={r['id'] for r in scored['rows']}
    prompts=first_prompts(materials)
    path=HOLDOUT/'first_answers.json'
    # 续接时仅程序读取先前词元，执行者不输出正文、不判分、不查看资格。
    rows=json.loads(path.read_text()) if path.exists() else {}
    keys={f'{item}-{i}' for item in prompts for i in range(2)}
    assert len(keys)==128 and set(rows)<=keys
    status_path=HOLDOUT/'status.json'
    status=json.loads(status_path.read_text()) if status_path.exists() else {'complete':False,'calls':{}}
    before=Counter(engine.counter);old_calls=Counter(status['calls'])
    def save_status():
        status.update({'finished':sum(r['finished'] for r in rows.values()),'total':128,
                       'calls':dict(old_calls+(Counter(engine.counter)-before))})
        write(status_path,status)
    try:
        for item,messages in prompts.items():
            if all(rows.get(f'{item}-{i}',{}).get('finished') for i in range(2)):
                continue
            rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            assert rendered.endswith('<|im_start|>assistant\n') and '<think>' not in rendered
            ids=tokenizer.encode(rendered,add_special_tokens=False)
            initial=engine.call(ids,None,'holdout_first_prefill')
            for repeat in range(2):
                key=f'{item}-{repeat}'
                if rows.get(key,{}).get('finished'):
                    continue
                seed=legacy.derive_seed('internal8_program_holdout_v133',item,'first','native',repeat,1)
                def persist(answer):
                    rows[key]={'prompt_ids':ids,**answer}
                    write(path,rows);save_status()
                generate_one(engine,tokenizer,ids,initial,seed,'N',None,None,rows.get(key),persist)
                print(json.dumps({'stage':'holdout_first','finished':status['finished'],'total':128}),flush=True)
            del initial
        assert set(rows)==keys and all(r['finished'] for r in rows.values())
        status['complete']=True
    finally:
        save_status()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['profile','sample','holdout','all'])
    args=parser.parse_args()
    import fcntl
    import torch
    from transformers import AutoTokenizer
    OUT.mkdir(exist_ok=True)
    if (OUT/'identity_failure.json').exists():
        raise RuntimeError('存在尚未处理的零编辑失败，禁止自动续跑')
    descriptor=os.open(OUT,os.O_RDONLY)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        torch.set_num_threads(2)
        tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
        cases,bases=inputs(tokenizer)
        engine=Engine()
        with torch.inference_mode():
            if args.action in ('profile','all'):profile(engine,tokenizer,cases,bases)
            if args.action in ('sample','all'):sample(engine,tokenizer,cases,bases)
            if args.action in ('holdout','all'):holdout(engine,tokenizer)
    finally:
        os.close(descriptor)


if __name__=='__main__':
    main()
