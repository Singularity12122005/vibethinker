"""A0预测单独提交之后，串行完成既定正式阶段与评审。"""
from pathlib import Path
import argparse
import re
import subprocess
import sys

from core import load,save
from readouts import token_total
from formal import validate_materials

STAGES=('g1_a0','adaptation','version','computable','capital')


def projection(out,reg,plan):
    lengths=dict(reg['frozen']['budget']['mean_length_assumptions'])
    g1=load(out/'formal_g1_non_a0_generations.json')
    lengths['g1_a0']=sum(r['n_new_tokens'] for r in g1)/len(g1)
    remaining={};quality={}
    for stage in STAGES:
        path=out/f'formal_{stage}_generations.json'
        rows=load(path) if path.exists() else []
        if len(rows)>plan['counts'][stage]:raise RuntimeError('阶段条数超出冻结计划')
        if rows:lengths[stage]=sum(r['n_new_tokens'] for r in rows)/len(rows)
        remaining[stage]=plan['counts'][stage]-len(rows)
        quality[stage]=dict(completed=len(rows),planned=plan['counts'][stage],
            truncated=sum(r['truncated'] for r in rows),looped=sum(r['looped'] for r in rows))
        if rows and quality[stage]['looped']/len(rows)>.05:
            raise RuntimeError('循环诊断超过5%，停止：'+stage)
    actual=token_total(out)
    projected=actual+sum(remaining[s]*lengths[s] for s in STAGES)
    return dict(actual_tokens=actual,remaining_requests=remaining,quality=quality,
        mean_lengths=lengths,projected_total=projected,warning=projected>=1200000,
        pause=actual>=1500000 or projected>1500000)


def run(out,pilot,prereg_commit,prediction_commit):
    for commit in (prereg_commit,prediction_commit):
        if not re.fullmatch('[0-9a-f]{40}',commit):raise RuntimeError('须提供已提交推送的完整提交号')
    reg,materials,_=validate_materials(out,pilot)
    prediction=load(out/'a0_prediction_frozen.json')
    if prediction.get('prediction_commit')!=prediction_commit or not prediction.get('models'):
        raise RuntimeError('A0预测未单独冻结，禁止启动')
    if prediction['frozen_prereg_sha256']!=reg['frozen_sha256']:
        raise RuntimeError('A0预测与当前预注册不对应')
    plan=materials['plan'];code=Path(__file__).resolve().parent
    checkpoints=[]
    for stage in STAGES:
        state=projection(out,reg,plan);checkpoints.append(dict(before_stage=stage,**state))
        save(out/'formal_continuation_checkpoints.json',checkpoints)
        print('生成前预算',stage,state,flush=True)
        if state['pause']:raise RuntimeError('外推超过150万词元或已达暂停线，等待用户决定，不自动删格')
        if state['warning']:print('120万词元预测预警；按既定计划继续',flush=True)
        if state['remaining_requests'][stage]:
            subprocess.run([sys.executable,'-u',str(code/'formal.py'),'--out',str(out),
                '--pilot',str(pilot),'--stage',stage,'--prereg-commit',prereg_commit],check=True)
        else:print('阶段生成已完整，不重复',stage,flush=True)
    for stage in STAGES:
        subprocess.run([sys.executable,'-u',str(code/'formal_judge.py'),'--out',str(out),
            '--pilot',str(pilot),'--stage',stage],check=True)
    print('既定后续生成与评审结束；待独立盲审与冻结分析',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--pilot',type=Path,required=True);ap.add_argument('--prereg-commit',required=True)
    ap.add_argument('--prediction-commit',required=True)
    a=ap.parse_args();run(a.out,a.pilot,a.prereg_commit,a.prediction_commit)
