"""仅输出预算/验证停止时的真实阶段事实，不修改冻结统计。"""
from pathlib import Path
import argparse
from analysis import load,save,quantile,fmt,branch_outcomes,reading_tables


def stopped_stage(out,prereg_commit):
    """预算或验证停止时，仅报告先行阶段事实，不调用完整批指标。"""
    budget=load(out/"pilot_budget.json")
    validation=load(out/"judge_validation.json")
    if not budget.get("over_budget") and validation.get("passed"):
        raise ValueError("预算和验证均通过，不能冒用阶段停止报告")
    items=load(out/"diag_instances.json")
    turns={t:load(out/f"pilot_t{t}.json") for t in range(1,5)}
    ids=sorted({r["instance_id"] for r in turns[1]})
    if len(ids)!=10 or len(turns[1])!=160 or len(turns[3])!=len(turns[4]):
        raise ValueError("先行10题尚未完成，不得记为阶段完成")
    if any((out/f"remaining_t{t}.json").exists() for t in range(1,5)):
        raise ValueError("存在后续阶段数据，不得使用仅10题的停止报告")
    quality={}
    for t,rs in turns.items():
        quality[str(t)]=dict(n=len(rs),generated_tokens=sum(r["n_new_tokens"] for r in rs),
            median_length=quantile([r["n_new_tokens"] for r in rs],.5),
            p95_length=quantile([r["n_new_tokens"] for r in rs],.95),
            truncated=sum(r["truncated"] for r in rs),looped=sum(r["looped"] for r in rs),
            format_missing=sum(r["parsed"]["value"] is None for r in rs) if t in (1,4) else sum(r["judge"]["parse_error"] for r in rs),
            judge_unjudgeable=sum(r["judge"]["unjudgeable"] for r in rs) if t in (2,3) else 0,
            multiline_same_value=sum(r["parsed"]["multiline_same_value"] for r in rs) if t in (1,4) else 0)
    reasons=[]
    if budget.get("over_budget"):reasons.append("10题实测外推的130题新生成词元预算超过8,000,000")
    if not validation.get("passed"):reasons.append("原随机100条评审盲验证未通过或无法验证")
    formal=load(out/"formal_check.json")
    summary=dict(status="先行阶段完成后停止；130题实验未完成",stop_reasons=reasons,
        prereg_commit=prereg_commit,frozen_instances=len(items),completed_instances=10,
        unrun_instances=len(items)-10,completed_instance_ids=ids,
        total_generated_tokens=sum(r["generated_tokens"] for r in quality.values()),
        pilot_quality_by_round=quality,pilot_budget=budget,
        judge_validation={k:v for k,v in validation.items() if k!="annotations"},
        execution=load(out/"phase_times.json",{}),
        formal_check=dict(accepted=len(formal["accepted"]),discarded=len(formal["discarded"])),
        full_batch=dict(Q1="未完成，未计算",Q2="未完成，未计算",release_decision="未计算；执行阶段停止，不作机制判据结论"),
        interpretation="先行10题仅用于实测成本与评审验证，不代替130题的Q1/Q2或机制结论。缺失不改判为0。")
    if validation.get("passed"):
        reading_tables(out,items,branch_outcomes(turns[3],turns[4]))
        r1=out/"R1_t3_reading.md"
        r1.write_text(r1.read_text(encoding="utf-8")+"\n本先行阶段未生成R1实例，无对话可供阅读；未补采。\n",encoding="utf-8")
        summary["reading_material"]="盲验证通过后，按冻结接口仅从现有先行10题导出；每族最多各10条让步与坚持，R1未生成。原始缓存保留A100；用户指定阅读材料另交仓库外副本，不入库。"
    else:
        summary["reading_material"]="评审盲验证未通过或无法验证，自动标签未获验证，不提供按已验证让步/坚持命名的阅读表。"
    lines=["# 130实例诊断批：先行阶段停止报告","",summary["interpretation"],"",
        f"130题已冻结并预注册；仅先行10题完成全部四轮，剩余{summary['unrun_instances']}题未运行。全批Q1、Q2、预测检验和放行判据均未计算。","",
        "停止原因："+"；".join(reasons)+"。","",
        f"先行10题主模型实际新生成词元共{summary['total_generated_tokens']}；预算仅计第1—4轮输出，不含输入或评审词元。按冻结规则乘13估计完整130题成本为{int(budget['estimated_total_generated_tokens'])}，上限为8,000,000。","",
        "| 轮次 | 条数 | 新生成词元 | 长度中位数 | 长度95分位 | 截断 | 循环 | 格式缺失 | 评审不可判 | 多行同值 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for t,q in quality.items():
        lines.append(f"| {t} | {q['n']} | {q['generated_tokens']} | {fmt(q['median_length'])} | {fmt(q['p95_length'])} | {q['truncated']} | {q['looped']} | {q['format_missing']} | {q['judge_unjudgeable']} | {q['multiline_same_value']} |")
    lines += ["", "以上只是10题的执行与缺失计数，标记可重叠；第2/3轮不要求答案行，格式缺失为评审解析失败。多行同值单列遵循用户确认，仍记缺失。","",
        "## 评审盲验证","","使用原随机100条，新会话代理盲审，非人工标注。验证预测阳性分母不排除截断、循环或值冲突；盲审其他/未知不删除。结局层有效性优先的规则未改变。",""]
    for name in ("USER_to_A","ORIG_EXPLICIT_to_D"):
        r=validation[name]
        lines.append(f"- {name}：{r['correct']}/{r['predicted']}，精确率{fmt(r['precision'])}；{'通过' if r['passed'] else '未通过或无法验证'}。")
    lines += ["", "本次支持候选值的验证预测阳性分母仅4条；虽达到预先阈值，这一小样本不能说明所有情形均已得到充分验证。"]
    lines += ["","## 环境与实际耗时","","以下绝对时间及耗时均使用A100自身时钟；不与协调端时钟相减。形式检查完整起止未单独记录，未事后补填；控制台曾观察逐题检查465秒，该数不代表完整阶段耗时。",""]
    for key,value in summary["execution"].get("environment",{}).items():lines.append(f"- {key}：{value}")
    for stage,runs in summary["execution"].get("phases",{}).items():
        for run in runs:lines.append(f"- {stage}：{run['started_utc']} 至 {run.get('ended_utc','未记录结束')}；耗时{fmt(run.get('elapsed_seconds'))}秒。")
    lines += ["","## 已完成准备与执行偏离","",
        f"正式130题经逐题形式反译接受，构造丢弃{summary['formal_check']['discarded']}个种子。准备阶段有3条旧题面反译在发现模板不符后停止，未计入最终130题。",
        "未改变冻结话术、生成参数、解析、验证抽样或指标。新增独立阶段报告入口仅负责停止时输出，不修改已冻结统计规则。未因结果删除题目或补采。D路径包含第二轮可能已纠正的前缀，只能解释正确答案支持/接受，不能解释净纠错增益。",
        "原始对话缓存保存在A100运行目录；用户指定阅读材料另下载到仓库外，不纳入提交。停止后不启动剩余120题，也不开展后续剂量试验。",""]
    lines += ["## 第三轮阅读材料","",summary["reading_material"],""]
    save(out/"diag_summary.json",summary)
    (out/"diag_report.md").write_text("\n".join(lines),encoding="utf-8")


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--prereg-commit",required=True)
    args=ap.parse_args()
    stopped_stage(args.out,args.prereg_commit)
