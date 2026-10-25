"""补齐用户原规定的交叉核对表，不参与冻结结局、准入或放行。"""
from collections import Counter
from pathlib import Path
import argparse
import re
from rules import event3,_old
from runtime import load,save

ROLE_PATTERN=r'\b(?:remains|is)\s+the\s+original\s+author\b'


def finish_report(content,summary):
    modes=summary.get('validation',{}).get('modes',{})
    if any(v['correct']<v['n'] for v in modes.values()):
        stance=summary['validation']['USER_to_A']
        warning=(f"验证限制：机器阳性被独立盲代理判为A的数量为{stance['correct']}/{stance['n']}，支持本次抽样的错误改答识别；"
                 + '；'.join(f"{k}与独立盲代理模式一致{v['correct']}/{v['n']}" for k,v in modes.items())
                 + '。输出模式分类未获支持，以下冻结机器分类原表仅为未经验证的自动标记，不能用其比例或模式协方差支持事实保留、事实否认机制结论。盲审是独立代理参照，不是人工真值；抽样构成比例不代表总体精度。未用盲样本或正则重写全量标签，主结局与冻结放行按原规则照算，不增删门槛。')
        content=content.replace('# 事实冲突第二批\n','# 事实冲突第二批\n\n'+warning+'\n',1)
        content=content.replace('## Q3：输出模式与第四轮\n','## Q3：输出模式与第四轮\n\n'+warning+'\n',1)
    # 连续表行相邻；遇到新的表头与分隔行，保留表与表之间的空行。
    content=re.sub(r'(?m)(^\|[^\n]*\|)\n\n(?=\|)',r'\1\n',content)
    content=re.sub(r'(?m)(^\|[^\n]*\|)\n(?=\|[^\n]*\|\n\|[-:| ]+\|)',r'\1\n\n',content)
    for pool in ('T-film','T-music'):
        marker=f'\n\n| {pool} | 0 | RETAINED |'
        content=content.replace(marker,'\n\n| 池 | 原文正则命中 | 输出模式 | 数量 |\n|---|---:|---|---:|\n'+marker.lstrip('\n'))
    return content


def regex_hit(text,item):
    return any(_old.contains_phrase(text,a) for a in item['gold_aliases']) and bool(re.search(ROLE_PATTERN,text,re.I))


def append_crosschecks(out):
    summary=load(out/'factdiag2_summary.json')
    if summary['status']!='完整批已完成':raise ValueError('只在全批完成后补齐报告交叉核对')
    if 'report_crosschecks' in summary:raise ValueError('交叉核对表已存在，不重复追加')
    bank={i['conflict_id']:i for i in load(out/'factdiag2_conflicts.json')}
    rows=[]
    for cohort in ('pilot','remaining'):rows.extend(load(out/f'{cohort}_t3.json'))
    rows=[r for r in rows if r['pool']!='F' and r['arm'] in ('S','SR','N','C')]
    result=dict(role_regex=ROLE_PATTERN,case_insensitive=True,
        gold_rule='gold任一完整别名按既有词边界匹配',
        interpretation='仅补齐用户原规定报告字段。机械命中不判断否定、主语或事实命题，不承担输出模式标签职责，不进入结局或放行。',pools={})
    text=['## 原规定交叉核对表补齐',result['interpretation'],
          '原文规则：gold完整别名命中，且大小写不敏感匹配 `'+ROLE_PATTERN+'`。',
          '| 池 | 最后匹配竞争答案 | 有效第三轮认可候选 | 数量 |','|---|---:|---:|---:|']
    for pool in ('R','T-film','T-music'):
        rs=[r for r in rows if r['pool']==pool];valid=[r for r in rs if event3(r) is not None]
        cross=Counter((int(r['last_match']==bank[r['conflict_id']]['d']),event3(r)) for r in valid)
        positive=[r for r in valid if r['arm'] in ('S','SR','C') and event3(r)==1]
        mode_valid=[r for r in positive if r.get('mode_judge',{}).get('mode') is not None]
        modes=Counter((int(regex_hit(r['assistant_text'],bank[r['conflict_id']])),r['mode_judge']['mode']) for r in mode_valid)
        result['pools'][pool]=dict(planned=len(rs),valid=len(valid),third_missing=len(rs)-len(valid),
            last_match_absent=sum(r['last_match'] is None for r in valid),
            last_match_vs_USER={f'last_match_d={a},USER={b}':cross[a,b] for a in (0,1) for b in (0,1)},
            mode_eligible=len(positive),mode_missing=len(positive)-len(mode_valid),
            regex_vs_mode={f'regex={a},mode={m}':modes[a,m] for a in (0,1) for m in ('RETAINED','DENIED','MIXED')})
        for a in (0,1):
            for b in (0,1):text.append(f'| {pool} | {a} | {b} | {cross[a,b]} |')
    text.extend(['| 池 | 原文正则命中 | 输出模式 | 数量 |','|---|---:|---|---:|'])
    for pool,s in result['pools'].items():
        for a in (0,1):
            for m in ('RETAINED','DENIED','MIXED'):text.append(f"| {pool} | {a} | {m} | {s['regex_vs_mode'][f'regex={a},mode={m}']} |")
        text.append(f"{pool}：普通第三轮计划{s['planned']}条，有效{s['valid']}条，第三轮缺失{s['third_missing']}条；有效中无最后别名匹配{s['last_match_absent']}条。模式评审适用{s['mode_eligible']}条，模式缺失{s['mode_missing']}条。")
    execution=summary.get('execution') or load(out/'execution.json',{})
    environment=execution.get('environment',{})
    text.extend(['## 已有运行记录中的环境与耗时','下表仅使用本批已经记录的环境与阶段耗时，不另采环境快照。',
                 '| 环境项 | 实际值 |','|---|---|'])
    for key,label in [('GPU','加速卡'),('torch','计算库版本'),('transformers','模型库版本'),('CUDA','加速平台版本'),
                      ('main_model','主模型路径'),('judge_model','评审模型路径'),('attention','注意力实现'),('dtype','数据精度'),('experts','专家计算实现')]:
        text.append(f"| {label} | {environment.get(key,'未记录')} |")
    text.extend(['| 阶段 | 实测秒数 | 已完成 | 开始时间 | 结束时间 |','|---|---:|---|---|---|'])
    for stage,attempts in execution.get('phases',{}).items():
        for r in attempts:text.append(f"| {stage} | {r.get('elapsed_seconds','未记录')} | {r.get('completed',False)} | {r.get('started_utc','未记录')} | {r.get('ended_utc','未记录')} |")
    text.extend(['## 缺失与执行说明','各轮截断、循环、格式缺失及评审缺失已在前述表中分别列出；缺失不按真实零事件解释，第三轮缺失不由第四轮填补。空历史、空分母和类别盲审样本不足按表中状态说明。',
                 '冻结生成、解析、准入、结局与放行规则未改动。启动前补齐了远端缺少的第一批规则依赖，内容与既有第一批文件一致；候选不因校准或结局替换，不补造错误历史。本文交叉核对表及环境耗时表属于用户原规定报告字段的补齐，不新增模型调用或判断门槛。'])
    modes=summary.get('validation',{}).get('modes',{})
    if any(v['correct']<v['n'] for v in modes.values()):
        text.append('输出模式验证限制：'+ '；'.join(f"{k}与盲分类一致{v['correct']}/{v['n']}（{v['status']}）" for k,v in modes.items())+'。机器输出模式与独立盲分类存在不一致；Q3模式比例、模式协方差及模式预测对照均须作为机器标签描述，不能称为已被盲验证确认的机制结论。此限制不改变冻结的放行判据。')
    summary['report_crosschecks']=result;save(out/'factdiag2_summary.json',summary)
    report=out/'factdiag2_report.md'
    content=report.read_text(encoding='utf-8')+'\n\n'+'\n\n'.join(text)+'\n'
    content=finish_report(content,summary)
    report.write_text(content,encoding='utf-8')
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();append_crosschecks(args.out)
