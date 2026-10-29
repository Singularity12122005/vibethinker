"""本地账号命令行的200视图先导；原文只经内存传递，结果回写A100。"""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import argparse
import base64
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
import zlib

from .strong_column import TEMPLATE_SHA,RULE,safety_stop,pilot_decision
from .relations_v3 import parse
from .mention_followup_checks import normalized_quote_column

EXE=Path('C:/Users/Singu/AppData/Local/OpenAI/Codex/bin/2993767bd1dfb009/codex.exe')
BASE='/output/sycophancy-phase0/pilot'
DISABLED=['shell_tool','unified_exec','apply_patch_freeform','apps','plugins','remote_plugin',
    'multi_agent','multi_agent_v2','image_generation','view_image','sleep_tool','send_async_message',
    'send_message_to_user_async','code_mode','code_mode_host','code_mode_only','skill_search',
    'tool_suggest','default_mode_request_user_input','memories','request_permissions_tool',
    'current_time_reminder','workspace_dependencies','shell_snapshot','fast_mode','ultrafast_mode']


def utc():return datetime.now(timezone.utc).isoformat()


def environment():
    excluded={'OPENAI_API_KEY','OPENAI_BASE_URL','OPENAI_ORG_ID','OPENAI_ORGANIZATION','OPENAI_PROJECT_ID'}
    return {k:v for k,v in os.environ.items() if k.upper() not in excluded}


def config():
    c={'model_reasoning_effort':'xhigh','service_tier':'default','web_search':'disabled',
       'tools.update_plan.enabled':False,'tools.experimental_request_user_input.enabled':False,
       'project_doc_max_bytes':0,'forced_login_method':'chatgpt'}
    c.update({'features.'+k:False for k in DISABLED})
    c['features.skip_host_skill_discovery']=True
    return c


def command(cwd):
    args=[str(EXE),'exec','--ignore-user-config','--ignore-rules','--strict-config','--ephemeral',
        '--skip-git-repo-check','--json','--color','never','-s','read-only','-m','gpt-6-astra','-C',str(cwd)]
    for k,v in config().items():args+=['-c',k+'='+json.dumps(v)]
    return args+['-']


class Account:
    """仅查询账号与用量；不通过应用服务端运行推理。"""
    def __init__(self):
        self.p=subprocess.Popen([str(EXE),'app-server','--stdio'],env=environment(),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        self.q=queue.Queue();self.i=0
        def read():
            for line in self.p.stdout:
                try:self.q.put(json.loads(line))
                except ValueError:pass
        threading.Thread(target=read,daemon=True).start()
        self.call('initialize',{'clientInfo':{'name':'factdiag_strong_budget','version':'1'}})
        self.p.stdin.write('{"method":"initialized","params":{}}\n');self.p.stdin.flush()
        a=self.call('account/read',{'refreshToken':False})['account']
        if a['type']!='chatgpt':raise RuntimeError('不是ChatGPT账号')
    def call(self,method,params=None):
        self.i+=1;i=self.i
        self.p.stdin.write(json.dumps(dict(id=i,method=method,params=params or {}))+'\n');self.p.stdin.flush()
        end=time.monotonic()+30
        while time.monotonic()<end:
            v=self.q.get(timeout=max(.01,end-time.monotonic()))
            if v.get('id')==i:
                if 'error' in v:raise RuntimeError('官方只读接口失败：'+method)
                return v['result']
        raise TimeoutError(method)
    def limits(self):
        v=self.call('account/rateLimits/read')
        v=v.get('rateLimitsByLimitId',{}).get('codex',v.get('rateLimits'))
        if not v or v.get('credits',{}).get('balance') is None:raise RuntimeError('缺少精确积分余额')
        return v
    def close(self):
        self.p.terminate();self.p.wait(timeout=10)


def remote_json(remote,code):
    result=remote("import json\n"+code)
    lines=[x[7:] for x in result.splitlines() if x.startswith('RESULT:')]
    if len(lines)!=1:raise RuntimeError('远端未返回确认；不自动重发模型调用')
    return json.loads(lines[0])


def fetch_inputs(remote,ids):
    setup=f"""import sys,json,base64,zlib
from pathlib import Path
p=Path('{BASE}');sys.path.insert(0,str(p))
from scripts.pilot.factdiag7.strong_column import get_inputs
rows=get_inputs(p,{ids!r})
items={{}};packed=[]
for q in rows:
 item=json.dumps(q['item'],ensure_ascii=False,sort_keys=True)
 h=__import__('hashlib').sha256(item.encode()).hexdigest()
 items[h]=q['item'];packed.append({{**{{k:v for k,v in q.items() if k!='item'}},'item_ref':h}})
data=base64.b64encode(zlib.compress(json.dumps({{'items':items,'rows':packed}},ensure_ascii=False).encode())).decode()
"""
    n=remote_json(remote,setup+"print('RESULT:'+json.dumps(len(data)))")
    print(json.dumps(dict(stage='读取固定输入',transfer_chunks=(n+17999)//18000),ensure_ascii=False),flush=True)
    parts=[]
    for off in range(0,n,18000):
        parts.append(remote_json(remote,setup+f"print('RESULT:'+json.dumps(data[{off}:{off+18000}]))"))
    packed=json.loads(zlib.decompress(base64.b64decode(''.join(parts))))
    rows=[]
    for q in packed['rows']:
        item=packed['items'][q.pop('item_ref')];rows.append(dict(q,item=item))
    return rows


def save_remote(remote,q,value):
    b64=base64.b64encode(zlib.compress(json.dumps(value,ensure_ascii=False).encode())).decode()
    # 单视图通常远低于平台载荷上限；过长结果不静默截断。
    if len(b64)>40000:raise RuntimeError('单视图结果超过传输上限，保留内存并停止')
    return remote_json(remote,f"""import sys,zlib,base64
from pathlib import Path
p=Path('{BASE}');sys.path.insert(0,str(p))
from scripts.pilot.factdiag7.strong_column import save_result
save_result(p,{q['id']!r},json.loads(zlib.decompress(base64.b64decode({b64!r}))))
print('RESULT:'+json.dumps({{'saved':True}}))
""")


def infer(q,cwd):
    started=time.monotonic()
    if hashlib.sha256(q['prompt'].encode()).hexdigest()!=q['prompt_sha256']:
        raise ValueError('提示字节变化')
    proc=subprocess.run(command(cwd),input=q['prompt'],env=environment(),capture_output=True,
        text=True,encoding='utf-8',timeout=900)
    events=[]
    for line in proc.stdout.splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    items=[e['item'] for e in events if e.get('type')=='item.completed']
    unexpected=[i['type'] for i in items if i['type'] not in ('agent_message','reasoning','error')]
    finals=[i['text'] for i in items if i['type']=='agent_message']
    finished=[e for e in events if e.get('type')=='turn.completed']
    failures=[e for e in events if e.get('type')=='turn.failed']
    good=proc.returncode==0 and len(finished)==1 and len(finals)==1 and not failures and not unexpected
    raw=finals[0] if finals else None
    usage=finished[0].get('usage') if finished else None
    extraction=parse(raw,q['response'],q['item'],q['person'],q['user_message']) if good else dict(parse_status='UNPARSEABLE',claims=[],extraction_flags=[])
    normalized=normalized_quote_column(extraction,q['response'])
    metadata=dict(source='codex_exec_single_view',completion='returned' if good else 'attempted_result_missing',
        attempts=1,input_sha256=q['input_sha256'],prompt_sha256=q['prompt_sha256'],template_sha256=TEMPLATE_SHA,
        runtime=dict(model='gpt-6-astra',reasoning='xhigh',speed='standard',service_tier='default',
            temperature=None,max_output_tokens=None,parameter_note=RULE['unspecified_parameters'],
            sandbox='read-only',tools_empty_preflight=True,cli=str(EXE)),
        usage=usage,parse_status=extraction['parse_status'],elapsed_seconds=time.monotonic()-started,
        cli_exit_code=proc.returncode,unexpected_item_types=unexpected)
    # 不把完整命令行错误日志写回；它可能含不必要的内部上下文。
    return dict(metadata,raw=raw,extraction=extraction,normalized_quote_extraction=normalized),metadata,good


def run(workspace):
    workspace=Path(workspace);work=workspace/'factdiag7-work'/'strong';work.mkdir(exist_ok=True)
    import msvcrt
    lock=(work/'runner.lock').open('a+b');lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise RuntimeError('已有强提取运行器，不重复启动')
    sys.path.insert(0,str(workspace/'factdiag3-work'));from remote import remote
    journal=work/'pilot_records.jsonl';summary=work/'pilot_summary.json'
    if journal.exists() and journal.stat().st_size:raise RuntimeError('先导已有派发记录，不自动重启或重发')
    def record(v):
        with journal.open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(utc=utc(),**v),ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    login=subprocess.run([str(EXE),'login','status'],env=environment(),capture_output=True,text=True,encoding='utf-8')
    if login.returncode or 'Logged in using ChatGPT' not in login.stdout+login.stderr:
        raise RuntimeError('命令行账号登录核验失败')
    account=Account();limits=account.limits();balance=float(limits['credits']['balance'])
    models=account.call('model/list',{'includeHidden':True,'limit':100})['data']
    if not any(m['model']=='gpt-6-astra' for m in models):raise RuntimeError('指定模型未列为可用')
    if safety_stop(balance,balance,[],[]):raise RuntimeError('开跑余额不足')
    ids=remote_json(remote,f"from pathlib import Path\np=json.loads(Path('{BASE}/factdiag7_20261112/stage2_strong_plan.json').read_text())\nprint('RESULT:'+json.dumps([r['id'] for r in p['entries'] if r['layer']==1][:200]))")
    qs=fetch_inputs(remote,ids)
    if len(qs)!=200 or [q['id'] for q in qs]!=ids:raise RuntimeError('先导输入顺序或数量变化')
    # 真正首次调用之前再次读取，避免把准备工作计入先导余额差。
    limits=account.limits();balance=float(limits['credits']['balance'])
    record(dict(type='pilot_start',login='ChatGPT',api_key_present=False,limits=limits,model='gpt-6-astra',views=200))
    usage=[];ratios=[];outputs=[];reason=None;returned=0
    empty=work/'empty';empty.mkdir(exist_ok=True)
    try:
        for q in qs:
            before=account.limits();current=float(before['credits']['balance'])
            reason=safety_stop(balance,current,ratios,outputs)
            if reason:break
            record(dict(type='dispatched',id=q['id'],attempts=1,prompt_sha256=q['prompt_sha256']))
            result,meta,good=infer(q,empty)
            save_remote(remote,q,result)
            after=account.limits();record(dict(type='result',id=q['id'],metadata=meta,limits=after))
            u=meta['usage']
            if not good or not u or not all(k in u for k in ('input_tokens','cached_input_tokens','output_tokens')):
                reason='调用未完整返回或逐视图词元缺失；不自动重试';break
            returned+=1;usage.append(u);ratios.append(u['cached_input_tokens']/u['input_tokens'] if u['input_tokens'] else 0);outputs.append(u['output_tokens'])
            print(json.dumps(dict(returned=returned,expected=200,cache_ratio=sum(x['cached_input_tokens'] for x in usage)/sum(x['input_tokens'] for x in usage),elapsed_view=round(meta['elapsed_seconds'],1)),ensure_ascii=False),flush=True)
            reason=safety_stop(balance,float(after['credits']['balance']),ratios,outputs)
            if reason:break
        final=account.limits();decision=pilot_decision(limits,final,usage)
        if reason:decision.update(allow=False,stop_reason=reason)
        value=dict(status='pilot_complete' if returned==200 else 'paused',returned=returned,
            start=limits,end=final,decision=decision,
            usage={k:sum(x[k] for x in usage) for k in ('input_tokens','cached_input_tokens','output_tokens')},
            mean_output=sum(outputs)/len(outputs) if outputs else None,
            next='先导结束必停，协调方报告放行条件后才能进入剩余第一层。')
        summary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(value,ensure_ascii=False),flush=True)
    finally:account.close();lock.close()


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--workspace',required=True)
    run(ap.parse_args().workspace)
