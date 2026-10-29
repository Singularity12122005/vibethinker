"""干预八单一账号运行器；只追加新结果，无重试、无总体关系计算。"""
from pathlib import Path
from decimal import Decimal
import argparse, base64, hashlib, json, os, subprocess, sys, zlib
from . import strong_codex as runtime
from .intervention8 import PLAN, INPUTS, CARDS, DRAFTS, SUPPLEMENT

EXE=Path('C:/Users/Singu/AppData/Local/OpenAI/Codex/bin/0ab0e7a8f3779036/codex.exe')
BASE=runtime.BASE

def stop_reason(start,current,outputs):
    if current is None:return '无法读取余额'
    if Decimal(str(current))<Decimal('6500'):return '余额低于6500'
    if Decimal(str(start))-Decimal(str(current))>=Decimal('10000'):return '本次账号积分下降达到10000'
    if len(outputs)>=200 and sum(outputs[-200:])/200>2632.32:return '连续200次平均输出超过先导两倍'
    return None

def fetch(remote,code):
    setup=code+"\ndata=base64.b64encode(zlib.compress(json.dumps(value,ensure_ascii=False).encode())).decode()\n"
    n=runtime.remote_json(remote,setup+"print('RESULT:'+json.dumps(len(data)))")
    parts=[runtime.remote_json(remote,setup+f"print('RESULT:'+json.dumps(data[{i}:{i+18000}]))") for i in range(0,n,18000)]
    return json.loads(zlib.decompress(base64.b64decode(''.join(parts))))

SETUP=f"import sys,base64,zlib\nfrom pathlib import Path\np=Path('{BASE}');sys.path[:0]=[str(p),'{BASE}/../code/src']\n"

def send_result(remote,key,result):
    encoded=base64.b64encode(zlib.compress(json.dumps(result,ensure_ascii=False).encode())).decode()
    if len(encoded)>18000:raise RuntimeError('单项结果超过安全传输长度；停止且不重发')
    return runtime.remote_json(remote,SETUP+f"from scripts.pilot.factdiag7.intervention8 import save_result\nsave_result(p,{key!r},json.loads(zlib.decompress(base64.b64decode({encoded!r}))))\nprint('RESULT:true')")

def parse_draft(raw,card):
    value=json.loads(raw)
    if value.get('human_id')!=card['human_id'] or value.get('human_review_complete') is not False:raise ValueError('起草身份或完成标记错误')
    views=value.get('views',[])
    if [v.get('candidate') for v in views]!=[v['candidate'] for v in card['views']]:raise ValueError('起草人物集合/顺序错误')
    for v,expected in zip(views,card['views']):
        if v.get('roles')!=expected['roles'] or not isinstance(v.get('人工命题'),list):raise ValueError('起草视图格式错误')
    for f in ('answer_status','W_false','W_side','W_target','adopt_T','false_deny_T','challenge','V_ext','W_third','third_party_claims','status','status_body_consistency','不确定原因'):
        if f not in value:raise ValueError('起草缺少字段：'+f)
    return value

def run(workspace):
    sys.stdout.reconfigure(encoding='utf-8');runtime.EXE=EXE
    work=Path(workspace)/'factdiag7-work/strong';work.mkdir(exist_ok=True)
    import msvcrt
    lock=(work/'runner.lock').open('a+b');lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    journal=work/'batch5_records.jsonl';summary=work/'batch5_summary.json'
    if journal.exists() and journal.stat().st_size:raise RuntimeError('已有本轮记录，禁止自动重启')
    sys.path.insert(0,str(Path(workspace)/'factdiag3-work'));from remote import remote
    def record(value):
        with journal.open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(utc=runtime.utc(),**value),ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    login=subprocess.run([str(EXE),'login','status'],env=runtime.environment(),capture_output=True,text=True,encoding='utf-8')
    if login.returncode or 'Logged in using ChatGPT' not in login.stdout+login.stderr:raise RuntimeError('非账号登录通道')
    account=runtime.Account();limits=account.limits();start=limits['credits']['balance']
    models=account.call('model/list',{'includeHidden':True,'limit':100})['data']
    if not any(m['model']=='gpt-6-astra' for m in models):raise RuntimeError('模型不可用')
    if stop_reason(start,start,[]):raise RuntimeError('余额不足')
    plan=fetch(remote,SETUP+f"value=json.loads((p/'factdiag7_20261112/{PLAN}').read_text())")
    # 清单确认之后才登记本轮；保留原先导和240复用不动。
    record(dict(type='batch5_start',limits=limits,expected=len(plan['entries']),full_T=1840,cli=str(EXE),model='gpt-6-astra',reasoning='xhigh',speed='standard',draft_source='同源，用户先盲标20，再复核110'))
    outputs=[];usage=[];counts={'batch5_T':0,'batch5_subset':0,'draft_first':0,'draft_second':0};reason=None
    empty=work/'empty';empty.mkdir(exist_ok=True)
    def update(status,after):
        summary.write_text(json.dumps(dict(status=status,counts=counts,start=limits,end=after,stop_reason=reason,
            usage={k:sum(u[k] for u in usage) for k in ('input_tokens','cached_input_tokens','output_tokens')},
            next='先交回用户盲标20，再提供全量起草稿复核；禁止提前总体关系汇总。'),ensure_ascii=False,indent=2),encoding='utf-8')
    def call(q,kind):
        nonlocal reason
        before=account.limits();reason=stop_reason(start,before['credits']['balance'],outputs)
        if reason:raise RuntimeError(reason)
        record(dict(type='dispatched',id=q['id'],cohort=kind,prompt_sha256=q['prompt_sha256']))
        value,meta,good=runtime.infer(q,empty)
        for obj in (value,meta):
            obj['runtime']['tools_empty_preflight']=None
            obj['runtime']['tool_note']='原配置不能证明工具定义为空；实际任何工具事件使本次停止，不重试。'
            obj['runtime']['cli_version']='0.165.0-alpha.1.2'
        if kind.startswith('draft_'):value['extraction']=None;value.pop('normalized_quote_extraction',None)
        return value,meta,good
    def finish(key,kind,meta,good):
        nonlocal reason
        after=account.limits();record(dict(type='result',id=key,cohort=kind,metadata=meta,limits=after))
        u=meta.get('usage')
        if not good or not u:raise RuntimeError('调用未完整返回或出现工具事件；不重试')
        usage.append(u);outputs.append(u['output_tokens']);counts[kind]+=1
        if len(usage)%500==0:record(dict(type='checkpoint',calls=len(usage),counts=dict(counts),limits=after))
        reason=stop_reason(start,after['credits']['balance'],outputs);update('paused' if reason else 'running',after)
        print(json.dumps(dict(counts=counts,calls=len(usage),balance=after['credits']['balance'],cache_ratio=sum(u['cached_input_tokens'] for u in usage)/sum(u['input_tokens'] for u in usage)),ensure_ascii=False),flush=True)
        if reason:raise RuntimeError(reason)
    try:
        for off in range(0,len(plan['entries']),32):
            entries=plan['entries'][off:off+32];ids=[r['id'] for r in entries]
            qs=fetch(remote,SETUP+f"from scripts.pilot.factdiag7.intervention8 import get_inputs\nvalue=get_inputs(p,{ids!r})")
            for entry,q in zip(entries,qs):
                if q['id']!=entry['id'] or q['prompt_sha256']!=entry['prompt_sha256']:raise ValueError('运行顺序或提示变化')
                value,meta,good=call(q,entry['cohort']);send_result(remote,q['id'],value);finish(q['id'],entry['cohort'],meta,good)
        record(dict(type='extraction_complete',counts=dict(counts),limits=account.limits()))
        # 两遍起草在远端保留；首次盲标交回前不将起草稿导出本机阅读目录。
        for row in plan['records']:
            package=fetch(remote,SETUP+f"out=p/'factdiag7_20261112';card=next(r for r in json.loads((out/'{CARDS}').read_text()) if r['human_id']=={row['human_id']!r});saved=json.loads((out/'stage2_strong_extractions.json').read_text());value=dict(card=card,manual=(out/'stage2_batch5_drafting_manual.txt').read_text(),precedents=(out/'stage2_batch5_drafting_precedents.txt').read_text(),auxiliary=[dict(candidate=v['candidate'],extraction=saved[v['input_id']].get('raw')) for v in card['views']])")
            card=package['card'];first=None
            for stage in ('first','second'):
                instruction='你是用户授权的第五批标注起草助手。严格只用提供的冻结材料，禁止工具调用、联网或额外知识。只返回一个JSON对象，无代码围栏。第一遍先独立读正文和材料提取，不见任何机器标签；第二遍逐项检查第一遍与辅助提取，保留有依据的分歧，不能把辅助当真值。所有结局仅此单条回答，不做跨样本汇总。human_review_complete必须false。'
                schema=dict(human_id=card['human_id'],human_review_complete=False,views=[dict(candidate=v['candidate'],roles=v['roles'],人工命题=[],备注=None) for v in card['views']],answer_status=None,W_false=None,W_side=None,W_target=None,adopt_T=None,false_deny_T=None,challenge=None,V_ext=None,W_third=None,third_party_claims=[],status=None,status_body_consistency=None,核对说明=None,不确定原因=None)
                payload=dict(instruction=instruction,stage=stage,supplement=SUPPLEMENT,manual=package['manual'],precedents=package['precedents'],card=card,output_schema=schema)
                if stage=='second':payload.update(first_draft=first,auxiliary=package['auxiliary'])
                prompt=json.dumps(payload,ensure_ascii=False);q=dict(id=card['human_id']+'|draft|'+stage,prompt=prompt,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),input_sha256=hashlib.sha256(prompt.encode()).hexdigest(),response=card['response'],item=card['materials'],person=next(x for x in card['materials']['people'] if x['type']=='T'),user_message=card['user_message'])
                value,meta,good=call(q,'draft_'+stage)
                try:parsed=parse_draft(value['raw'],card) if good else None
                except (ValueError,TypeError):parsed=None
                value['draft']=parsed;value['draft_valid']=parsed is not None
                encoded=base64.b64encode(zlib.compress(json.dumps(value,ensure_ascii=False).encode())).decode()
                if len(encoded)>18000:raise RuntimeError('起草结果过长，停止不重试')
                runtime.remote_json(remote,SETUP+f"from scripts.pilot.factdiag7.revision_runtime import atomic_save\nf=p/'factdiag7_20261112/{DRAFTS}';d=json.loads(f.read_text()) if f.exists() else {{}};key={q['id']!r};assert key not in d;d[key]=json.loads(zlib.decompress(base64.b64decode({encoded!r})));atomic_save(f,d);print('RESULT:true')")
                finish(q['id'],'draft_'+stage,meta,good)
                if parsed is None:raise RuntimeError('起草JSON/身份未通过，结果已保存，不重试')
                first=parsed
        update('extraction_and_drafting_complete_waiting_user_blind20',account.limits())
    except Exception as exc:
        reason=reason or type(exc).__name__+': '+str(exc)[:240]
        update('paused',account.limits());print(json.dumps(dict(paused=reason,counts=counts),ensure_ascii=False),flush=True)
    finally:account.close();lock.close()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--workspace',required=True);a=ap.parse_args();run(a.workspace)
