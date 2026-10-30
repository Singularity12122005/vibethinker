"""干预八单一账号运行器；只追加新结果，无重试、无总体关系计算。"""
from pathlib import Path
from decimal import Decimal
import argparse, base64, hashlib, json, os, re, subprocess, sys, time, zlib
from . import strong_codex as runtime
from .intervention8 import PLAN, INPUTS, CARDS, DRAFTS, SUPPLEMENT, SCHEDULE
from .batch5_schedule import remaining_groups, restore_handoff, restore_account_resume

EXE=Path('C:/Users/Singu/AppData/Local/OpenAI/Codex/bin/0ab0e7a8f3779036/codex.exe')
BASE=runtime.BASE

def stop_reason(start,current,outputs):
    if current is None:return '无法读取余额'
    if Decimal(str(current))<Decimal('6500'):return '余额低于6500'
    if Decimal(str(start))-Decimal(str(current))>=Decimal('10000'):return '本次账号积分下降达到10000'
    if len(outputs)>=200 and sum(outputs[-200:])/200>2632.32:return '连续200次平均输出超过先导两倍'
    return None

class BudgetAccount:
    """只重连只读额度服务；没有新额度时不派发模型调用。"""
    def __init__(self, factory=None, notify=None, sleep=None):
        self.factory=factory or self.new_account;self.notify=notify or (lambda state,limits:None)
        self.sleep=sleep or time.sleep;self.account=None;self.last_limits=None
    @staticmethod
    def new_account():
        account=runtime.Account.__new__(runtime.Account)
        try:runtime.Account.__init__(account)
        except Exception:
            if hasattr(account,'p'):
                try:account.close()
                except Exception:
                    if account.p.poll() is None:account.p.kill()
            raise
        return account
    def limits(self):
        waiting=False
        while True:
            try:
                if self.account is None:self.account=self.factory()
                limits=self.account.limits()
            except Exception:
                self.close()
                if not waiting:
                    waiting=True;self.notify('waiting_for_limits',self.last_limits)
                self.sleep(30)
                continue
            self.last_limits=limits
            if waiting:self.notify('limits_recovered',limits)
            return limits
    def call(self,method,params=None):
        if self.account is None:self.limits()
        return self.account.call(method,params)
    def close(self):
        account=self.account;self.account=None
        if account is not None:
            try:account.close()
            except Exception:pass


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

def deliver_review(remote,workspace,exported):
    directory=workspace/'factdiag7-work/human-review';directory.mkdir(exist_ok=True)
    names=[exported[k] for k in ('reading','labels','supplement')]
    allowed={'stage2_batch5_full110_reading.html','stage2_batch5_full110_labels.json','stage2_batch5_annotation_supplement.txt'}
    if set(names)!=allowed:raise ValueError('非授权人工阅读出口')
    bundle=fetch(remote,SETUP+f"out=p/'factdiag7_20261112';value={{name:(out/name).read_text(encoding='utf-8') for name in {names!r}}}")
    for name,content in bundle.items():
        destination=directory/name
        if name.endswith('_labels.json'):
            if destination.exists():continue
            with destination.open('x',encoding='utf-8') as stream:stream.write(content)
        else:destination.write_text(content,encoding='utf-8')
    return names


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

def run(workspace, *, prioritize_subset=False, schedule_commit=None, resume_after_account_read=False, resume_commit=None):
    sys.stdout.reconfigure(encoding='utf-8');runtime.EXE=EXE
    work=Path(workspace)/'factdiag7-work/strong';work.mkdir(exist_ok=True)
    import msvcrt
    lock=(work/'runner.lock').open('a+b');lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    journal=work/'batch5_records.jsonl';summary=work/'batch5_summary.json'
    existing=journal.exists() and journal.stat().st_size
    if prioritize_subset and resume_after_account_read:raise RuntimeError('不能混用两种接续入口')
    if existing and not (prioritize_subset or resume_after_account_read):raise RuntimeError('已有本轮记录，禁止自动重启')
    if resume_after_account_read and (not existing or not re.fullmatch('[a-f0-9]{40}',resume_commit or '')):raise RuntimeError('额度查询故障接续须明确授权及真实提交号')
    if prioritize_subset and (not existing or not schedule_commit):raise RuntimeError('子集优先须显式接续既有运行并给提交号')
    sys.path.insert(0,str(Path(workspace)/'factdiag3-work'));from remote import remote
    def record(value):
        with journal.open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(utc=runtime.utc(),**value),ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    login=subprocess.run([str(EXE),'login','status'],env=runtime.environment(),capture_output=True,text=True,encoding='utf-8')
    if login.returncode or 'Logged in using ChatGPT' not in login.stdout+login.stderr:raise RuntimeError('非账号登录通道')
    def initial_wait(state,after):
        if summary.exists():
            value=json.loads(summary.read_text('utf-8'));value['status']=state
            value['stop_reason']='额度服务暂时不可读；等待重连期间不派发' if state=='waiting_for_limits' else None
            summary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(stage=state),ensure_ascii=False),flush=True)
    account=BudgetAccount(notify=initial_wait);current=account.limits();limits=current;start=limits['credits']['balance']
    models=account.call('model/list',{'includeHidden':True,'limit':100})['data']
    if not any(m['model']=='gpt-6-astra' for m in models):raise RuntimeError('模型不可用')
    if stop_reason(start,start,[]):raise RuntimeError('余额不足')
    plan=fetch(remote,SETUP+f"value=json.loads((p/'factdiag7_20261112/{PLAN}').read_text())")
    outputs=[];usage=[];counts={'batch5_T':0,'batch5_subset':0,'draft_first':0,'draft_second':0};reason=None;completed=set()
    if prioritize_subset or resume_after_account_read:
        records=[json.loads(line) for line in journal.read_text('utf-8').splitlines() if line.strip()]
        state=fetch(remote,SETUP+f"out=p/'factdiag7_20261112';control=json.loads((out/'{SCHEDULE}').read_text());saved=json.loads((out/'stage2_strong_extractions.json').read_text());plan=json.loads((out/'{PLAN}').read_text());allowed={{r['id'] for r in plan['entries']}};value=dict(control=control,saved={{k:{{f:v.get(f) for f in ('cohort','completion','input_sha256','prompt_sha256','usage','attempts','cli_exit_code','unexpected_item_types')}} for k,v in saved.items() if k in allowed}})")
        if resume_after_account_read:
            restored=restore_account_resume(records,plan,state['saved'],state['control'])
            schedule_commit=state['control']['resume_commit']
        else:
            restored=restore_handoff(records,plan,state['saved'],state['control'],schedule_commit)
        limits=restored['limits'];start=limits['credits']['balance'];usage=restored['usage'];counts=restored['counts'];completed=restored['completed']
        outputs=[u['output_tokens'] for u in usage]
        reason=stop_reason(start,current['credits']['balance'],outputs)
        if reason:account.close();raise RuntimeError(reason)
        record(dict(type='account_read_resume' if resume_after_account_read else 'subset_first_resume',schedule_commit=schedule_commit,resume_commit=resume_commit,counts=dict(counts),limits=current,original_start_balance=start,authorization='用户明确要求继续跑；从未派发项接续，预算累计不重置，4A不执行起草'))
    else:
        # 清单确认之后才登记本轮；保留原先导和240复用不动。
        record(dict(type='batch5_start',limits=limits,expected=len(plan['entries']),full_T=1840,cli=str(EXE),model='gpt-6-astra',reasoning='xhigh',speed='standard',draft_source='用户另一标注会话4A；本运行器不执行起草'))
    empty=work/'empty';empty.mkdir(exist_ok=True)
    def update(status,after):
        summary.write_text(json.dumps(dict(status=status,counts=counts,start=limits,end=after,stop_reason=reason,
            usage={k:sum(u[k] for u in usage) for k in ('input_tokens','cached_input_tokens','output_tokens')},
            next='4A：子集齐备即导出材料，用户标注会话起草；其余全量继续，禁止提前总体关系汇总。'),ensure_ascii=False,indent=2),encoding='utf-8')
    def budget_state(state,after):
        nonlocal reason
        reason='额度服务暂时不可读；等待重连期间不派发' if state=='waiting_for_limits' else None
        update('waiting_for_limits' if state=='waiting_for_limits' else 'running',after)
        record(dict(type=state,counts=dict(counts),limits=after))
        print(json.dumps(dict(stage=state,counts=counts),ensure_ascii=False),flush=True)
    account.notify=budget_state
    update('running',current)
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
        # A100已确认保存，先记完成，额度服务故障不得掩盖已完成调用。
        record(dict(type='result',id=key,cohort=kind,metadata=meta,limits=None))
        u=meta.get('usage')
        if not good or not u:raise RuntimeError('调用未完整返回或出现工具事件；不重试')
        usage.append(u);outputs.append(u['output_tokens']);counts[kind]+=1
        after=account.limits()
        if len(usage)%500==0:record(dict(type='checkpoint',calls=len(usage),counts=dict(counts),limits=after))
        reason=stop_reason(start,after['credits']['balance'],outputs);update('paused' if reason else 'running',after)
        print(json.dumps(dict(counts=counts,calls=len(usage),balance=after['credits']['balance'],cache_ratio=sum(u['cached_input_tokens'] for u in usage)/sum(u['input_tokens'] for u in usage)),ensure_ascii=False),flush=True)
        if reason:raise RuntimeError(reason)
    def extract(entries_to_run):
        for off in range(0,len(entries_to_run),32):
            entries=entries_to_run[off:off+32];ids=[r['id'] for r in entries]
            qs=fetch(remote,SETUP+f"from scripts.pilot.factdiag7.intervention8 import get_inputs\nvalue=get_inputs(p,{ids!r},schedule_commit={schedule_commit!r})")
            for entry,q in zip(entries,qs):
                if q['id']!=entry['id'] or q['prompt_sha256']!=entry['prompt_sha256']:raise ValueError('运行顺序或提示变化')
                value,meta,good=call(q,entry['cohort']);send_result(remote,q['id'],value);finish(q['id'],entry['cohort'],meta,good)
                completed.add(q['id'])

    try:
        if resume_after_account_read:
            pending=[r for r in plan['entries'] if r['id'] not in completed]
            extract(pending)
            record(dict(type='extraction_complete',counts=dict(counts),limits=account.last_limits))
            update('extraction_complete_waiting_full110_review',account.last_limits)
        elif prioritize_subset:
            priority,remainder=remaining_groups(plan,completed)
            extract(priority)
            selected={v['input_id'] for row in plan['records'] for v in row['views']}
            if not selected<=completed:raise RuntimeError('子集人物视图未齐备，不导出')
            record(dict(type='subset_extraction_complete',views=len(selected),counts=dict(counts)))
            exported=runtime.remote_json(remote,SETUP+"from scripts.pilot.factdiag7.intervention8_review import export\nprint('RESULT:'+json.dumps(export(p)))")
            delivered=deliver_review(remote,Path(workspace),exported)
            record(dict(type='human_review_export_ready',files=exported,local_files=delivered))
            extract(remainder)
            record(dict(type='extraction_complete',counts=dict(counts),limits=account.limits()))
            update('extraction_complete_waiting_full110_review',account.limits())
        else:
            extract(plan['entries'])
            record(dict(type='extraction_complete',counts=dict(counts),limits=account.limits()))
            exported=runtime.remote_json(remote,SETUP+"from scripts.pilot.factdiag7.intervention8_review import export\nprint('RESULT:'+json.dumps(export(p)))")
            deliver_review(remote,Path(workspace),exported)
            update('extraction_complete_waiting_full110_review',account.limits())
    except Exception as exc:
        reason=reason or type(exc).__name__+': '+str(exc)[:240]
        update('paused',account.last_limits);print(json.dumps(dict(paused=reason,counts=counts),ensure_ascii=False),flush=True)
    finally:account.close();lock.close()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--workspace',required=True)
    ap.add_argument('--prioritize-subset',action='store_true');ap.add_argument('--schedule-commit')
    ap.add_argument('--resume-after-account-read',action='store_true');ap.add_argument('--resume-commit')
    a=ap.parse_args();run(a.workspace,prioritize_subset=a.prioritize_subset,schedule_commit=a.schedule_commit,resume_after_account_read=a.resume_after_account_read,resume_commit=a.resume_commit)
