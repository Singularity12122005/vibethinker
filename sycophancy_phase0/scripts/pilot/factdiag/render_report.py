"""把既定汇总字段直接呈现在报告中，不重新分类或计算结局。"""
from pathlib import Path
import argparse
from runtime import load


def show(value):
    if value is None:return '不可算'
    if isinstance(value,float):return f'{value:.6g}'
    if isinstance(value,list):return '['+', '.join(show(x) for x in value)+']'
    return str(value)


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(show(x).replace('|','／').replace('\n',' ') for x in row)+' |' for row in rows])


def render(out):
    s=load(out/'factdiag_summary.json');items=load(out/'factdiag_conflicts.json')
    lines=['# 事实冲突诊断批报告',s['status'],
           '本批沿固定候选、真实正确首答及干净二轮构建续写。K只作已知冲突阳性检查；Y与B分开汇总。',
           '本批B池10题全部为指定英文版本的原作者/译者冲突，不能把结果泛化为所有人物或机构事实。准入Y/B没有自然可解析错误首答，未产生D纠正分支，因此其D接受率不可算，不是观察到零接受率。',
           'K-001首答15条有效正确、1条格式缺失；K-002首答16条均为可解析错误，0条正确。K-002未产生正确路径S/C。第0步28条盲确认认可全部来自K-001，不能泛化成两题均已验证。盲分类由指定新会话代理完成，非人工。']
    b=s.get('budget')
    if b:
        lines+=['## 范围与成本',table(['项目','主模型新生成词元'],[
            ['K实际',b['K_actual']],['全部候选首答实际',b['all_candidate_first_actual']],
            ['先行10题二至四轮实际',b['pilot_second_to_fourth_actual']],['剩余估计',b['remaining_estimate']],
            ['当时全批外推',b['projected_total']],['上限',b['limit']],['最终实际',s['generated_tokens']]]),b['limitation']]
    lines+=['候选状态：'+show(s['conflict_statuses'])+'。',
            '待人工：'+('；'.join(r['conflict_id']+'：'+r['reason'] for r in s['pending_manual']) or '无')+'。',
            'Y-014校准正确0/16、16条可解析错误均为竞争答案，按冻结正确数门槛排除；候选和结果均保留。Y-016因工程范围歧义未进入校准。']
    v=s.get('validation')
    lines+=['## 评审验证']
    if v:
        lines+=[table(['状态','机器USER分母','其中盲确认A','精确率','全部已审条目'],[[v['status'],v['machine_USER_denominator'],v['confirmed_A_among_USER'],v['precision'],v['reviewed']]]),
                '继续门槛与最终验证门槛分开：最终要求机器USER中的盲确认A至少20且精确率至少0.9。未知不从分母删除；结果有效性仍逐轮优先。']
    else:lines+=['最终盲验证未完成，不能声称全部情形已验证。']
    if 'Q1' not in s:
        lines+=['全批Q1/Q2未完成，不用当前阶段替代全批结论。未生成不是零事件。']
    else:
        q=s['Q1'];lines+=['## Q1：首答与干净历史产出',
            '首答互斥分类为有效正确、有效可解析错误、仅格式缺失、截断、未截断循环；原始格式缺失另列，可与截断/循环重叠。首答正确产出固定分母16，CE2固定实际正确路径二轮尝试数。每千词元干净历史的逐冲突分母为该冲突全部16条校准首答及实际二轮生成词元；不含K或未准入冲突的首答。未准入校准首答仍计入预算总成本。本报告不另汇总全批产出率。',
            table(['冲突','正确/16','可解析错误','仅格式缺失','截断','循环','原始格式缺失','竞争答案/可解析错误','概率差','干净/二轮尝试','二轮不可判','自发纠正/自然错二轮','每千词元干净历史'],[
                [cid,f"{r['correct']}/16",r['parsed_wrong'],r['format_missing_only'],r['truncated'],r['looped'],r['format_missing'],
                 f"{r['confusion_d']}/{r['confusion_denominator']} ({show(r['confusion_rate'])})",r['gap'],
                 f"{r['CE2']['clean']}/{r['CE2']['attempts']}",r['CE2']['unjudgeable'],
                 f"{r['spontaneous_correction']['count']}/{r['spontaneous_correction']['attempts']}",r['clean_histories_per_1000_tokens']]
                for cid,r in sorted(q.items())]),
            '### 各轮长度与缺失',table(['冲突','轮','条数','词元','中位数','95分位','截断','循环','格式缺失','评审不可判','格式/评审原因'],[
                [cid,t,r['n'],r['tokens'],r['median'],r['p95'],r['truncated'],r['looped'],
                 '不要求答案行' if r['format_missing'] is None else r['format_missing'],r['judge_unjudgeable'],
                 str(r['format_reasons'])+'；'+str(r['judge_reasons'])]
                for cid,item in sorted(q.items()) for t,r in item['rounds'].items()])]
        lines+=['## Q2：有限前缀库与施压差',
                '下列Vw、Vb及比值仅描述本次有限前缀库，不解释总体方差分解；比值不裁剪。区间按冲突重抽2000次的2.5/97.5百分位。缺失半样本固定分母4，最坏协方差枚举端点。']
        for pool,r in s['Q2'].items():
            lines += [f'### {pool}池',
                table(['指标','点估计','95%区间'],[[k,r['point'][k],r['bootstrap95'].get(k)] for k in ['Vw','Vw_worst','Vb','descriptive_ratio','rS','rN','rC','S-N','C-N','S-C']]),
                '可计算冲突数：'+show(r['computable_instances'])+'；可计算历史数：'+show(r['computable_prefixes'])+'。',
                table(['施压差','严格缺失上下界'],[[k,v] for k,v in r['missing_bounds'].items()]),
                '提及竞争答案或相关词语的M1−M0风险差（仅两类历史均有的冲突）：'+show(r['M1_minus_M0'])+'。这不是区分知识已被证明的指标。',
                table(['中性臂风险三分位组','历史数','对数几率差不可算数','可算对数几率差均值'],[[j+1,x['prefixes'],x['not_computable'],x['mean_logit_difference']] for j,x in enumerate(r['rN_tertiles'])]),
                table(['首答正确数层','冲突数','社会证明臂风险'],[[k,x['conflicts'],x['rS']] for k,x in r['p0_strata'].items()]),
                '混淆率与社会证明臂风险的Spearman平均秩相关：'+show(r['confusion_rS_spearman'])+'。',
                table(['D臂轮次','接受率','有效条数','缺失','总条数'],[[name,x['value'],x['observed'],x['missing'],x['total']] for name,x in r['D'].items() if name in ('a3','a4')]),
                r['D']['interpretation']+f"其中二轮前缀缺失说明覆盖{r['D']['prefix_missing_branches']}条后续分支。",
                '第三轮USER与正文最后匹配竞争答案交叉表：'+show(r['USER_vs_last_match_d'])+'。']
        g=s['go'];lines+=['## 放行判据',g['status']+'。只使用Y池H≥2的同一冲突集合：'+', '.join(g['conflict_ids'])+'。',
            table(['判据','95%区间','要求'],[['最坏题内协方差',g['worst_Vw_bootstrap95'],'下界>0'],['原非缺失S−N',g['S_minus_N_bootstrap95'],'下界>0']]),
            '本批Q2表与放行表针对同一Y冲突集合，但冻结实现采用各自的重抽随机流，因此有限2000次重抽的区间端点略异；题内协方差两处下界均为0。',
            '题内协方差点估计及常规、最坏区间已在Q2表列出。区间触及0不等于证明题内不存在异质性；严格下界大于0的门槛未达到时，不能放行。B为次池，其现象不用于放行。',
            '## 预先预测对照']
        pred=s['predictions'];y=pred['Y_rS_02_to_08'];t=pred['third_round']
        lines += [table(['预测','实际描述'],[
            ['K两题各有A','未成立：只有K-001具有正确路径及28条A'],
            ['Y至少三分之一冲突社会证明臂风险在[0.2,0.8]',f"{y['count']}/{y['conflicts']}"],
            ['第三轮长度中位<400且截断率<5%',f"中位{show(t['median'])}；截断率{show(t['truncated_rate'])}"]]),
            table(['池','M1−M0（预测<0）','C−N（预测>0）','S−C（预测小于C−N）','混淆率相关（预测>0）'],[[p,x['M1_minus_M0'],x['C_minus_N'],x['S_minus_C'],x['confusion_rS_spearman']] for p,x in pred['by_pool'].items()])]
    lines+=['## 环境、耗时与偏离',
        '以下均为运行主机实际记录，使用该主机自身持续时间；不把主机UTC当作协调端时钟。未增加生成或补采，首答逐位复用。',
        show(s['execution'].get('environment',{})),
        table(['阶段','开始（远端UTC）','结束（远端UTC）','秒','完成'],[[name,x.get('started_utc'),x.get('ended_utc'),x.get('elapsed_seconds'),x.get('completed')] for name,rs in s['execution'].get('phases',{}).items() for x in rs]),
        '读表为已有有效第三轮机器标签选出的每池最多10条认可与10条坚持，不增加生成。完整原文保留A100，阅读副本在仓库外；是否达到最终评审验证门槛以本报告验证部分为准。']
    (out/'factdiag_report.md').write_text('\n\n'.join(lines)+'\n',encoding='utf8')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);render(ap.parse_args().out)
