"""等待已启动重评正常结束，再串行执行已冻结的阶段二A；不接第三阶段。"""
from pathlib import Path
import argparse,fcntl,json,os,subprocess,time
from stage2_plan import load
from stage2_freeze import validate


def baseline_processes():
    found=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:args=(path/'cmdline').read_bytes().split(b'\0')
        except OSError:continue
        words=[a.decode(errors='replace') for a in args if a]
        if any(x.endswith('/stage2_judge.py') for x in words) and '--phase' in words:
            if words[words.index('--phase')+1]=='baseline':found.append(int(path.name))
    return found


def complete(out,filename,expected):
    p=out/filename
    if not p.exists():return False
    value=load(p)
    if len(value)>expected:raise RuntimeError('输出数超过冻结计划：'+filename)
    return len(value)==expected


def run(out,pilot,commit):
    validate(out)
    with (out/'stage2_continue.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while not complete(out,'stage2_baseline_extractions.json',1200) or baseline_processes():
            if not baseline_processes() and not complete(out,'stage2_baseline_extractions.json',1200):
                raise RuntimeError('既有重评尚未完成且无运行进程；先诊断，不能跳过')
            time.sleep(30)
        # 本队列不会与原重评共用显卡；每步自身仍检查占用与冻结内容。
        python='/output/sycophancy-phase0/venv-experts/bin/python';folder=Path(__file__).parent
        source=pilot/'factdiag6g_20261111'
        jobs=[
            ('stage2_runtime.py','belief','stage2_belief_generations.json',80,'--pilot',pilot),
            ('stage2_runtime.py','Q2','stage2_Q2_generations.json',960,'--pilot',pilot),
            ('stage2_judge.py','Q2','stage2_Q2_extractions.json',2880,'--source',source),
            ('stage2_outcomes.py','belief','stage2_belief_outcomes.json',80,'--source',source),
            ('stage2_outcomes.py','baseline','stage2_baseline_outcomes.json',600,'--source',source),
            ('stage2_outcomes.py','Q2','stage2_Q2_outcomes.json',960,'--source',source)]
        env=dict(os.environ);env['PYTHONPATH']='/output/sycophancy-phase0/code/src'
        env['OMP_NUM_THREADS']='1';env['OPENBLAS_NUM_THREADS']='1'
        for script,phase,name,n,source_flag,source_path in jobs:
            if complete(out,name,n):
                print('已完成，接续下一步：'+name,flush=True);continue
            cmd=[python,'-u',str(folder/script),'--out',str(out),source_flag,str(source_path),
                 '--phase',phase,'--freeze-commit',commit]
            print('开始：'+name,flush=True)
            result=subprocess.run(cmd,env=env)
            if result.returncode:raise RuntimeError('执行异常，队列停止：'+name+'，退出码='+str(result.returncode))
            if not complete(out,name,n):raise RuntimeError('进程退出但预定输入未完整：'+name)
        print('阶段二A生成与机器评审完成；接续第五批及原定独立复核，不启动第三阶段。',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--pilot',type=Path,required=True);p.add_argument('--freeze-commit',required=True)
    a=p.parse_args();run(a.out,a.pilot,a.freeze_commit)
