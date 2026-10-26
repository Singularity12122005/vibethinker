"""把G0已计算结果写成报告；不重算标签或改变判据。"""
from pathlib import Path
import argparse
from collections import defaultdict
from core import load


def f(x):return '不可算' if x is None else f'{x:.4f}'
def interval(xs):return '['+', '.join(f(x) for x in xs)+']'


def write(path):
    s=load(path);g=s['G0d'];repair=s['proposition_reader_repair'];blind=s['blind_validation']
    lines=['# 第六批 G 步骤0：既有数据分析', '',
      '本文件完成 G0，不代表 S0 或整批实验已经完成。执行依据为用户提交的 v3.3（905207c）及已批准的 A0 顺序修订。正式新续写尚未生成。', '',
      '主要结果：共同线段约束在作者问题和译者抗压单元中产生的拟合损失超过预设噪声校准阈值；在纠正单元中没有超过，且该单元的留出预测优于无约束参照。端点和混合比例不可唯一识别，本结果不把它们认定为内部处理机制。译者抗压单元依赖的新命题标签只有 12/20 与独立代理一致，其结论受测量限制。', '',
      '## G0a：开头类别与错误的事后关联','',
      '| 数据范围 | 开头类别 | 错误数 / 非缺失数 | 缺失 | 比例 | 两端界 |',
      '|---|---|---:|---:|---:|---|']
    labels={'ACCOMMODATING':'顺应','DELIBERATIVE':'审慎'}
    for r in s['G0a']['rows']:
        lines.append(f"| {r['block']} | {labels.get(r['opening'],r['opening'])} | {r['events']}/{r['observed']} | {r['missing']} | {f(r['point'])} | {interval(r['bounds'])} |")
    lines+=['','第三批作者问题的两项数值预测均未达到：审慎类错误率为 0.10，高于 0.05；顺应类为 0.4234，低于 0.80。两类差为 0.3234，未触发预写的“差小于0.3”条件。审慎类只有10条。分类定义包含道歉或认同语气，因此顺应开头不能直接等同最终采纳候选。以上是事后关联，不进入事前预测模型，不作中介因果解释。', '',
      '## G0b：受压前实际答案的稳定性与来源','',
      '纠正单元沿用39段有效历史；其中9段的第1、2轮答案不同。稳定性、相邻真实分类与来源核对按第2轮实际答案计算，第1轮旧分类保留在同名JSON。旧批各臂接受标签和代价不回改。3段来源不确定，单列而不记为非相邻。','',
      '| 稳定 | 相邻真实 | 历史数 / 39 | 涉及作品数 | A1代价：作品等权 | A1代价：历史等权 |',
      '|---|---|---:|---:|---:|---:|']
    for c in s['G0b']['cells']:
        r=c['A1_cost']
        lines.append(f"| {'是' if c['stable'] else '否'} | {'是' if c['adjacent_true'] else '否'} | {c['n']}/39 | {r['works']} | {f(r['work_equal']['point'])} | {f(r['history_equal']['point'])} |")
    lines+=['','这些单元的代价没有结局缺失，两端界与点估计相同。稳定且相邻真实的8段全部来自同一作品；稳定但非相邻的格为空。因此该表定位了已有代价，不能单独区分稳定性与相邻真实各自的作用。', '',
      '## G0c：历史曝光','',
      '按冻结规则，对60段作者历史与全部候选草案计算姓氏曝光及同句角色词。相邻署名候选是否进入正式条件仍须通过开放关系读数门槛；下表不提前启用它们。','',
      '| 候选类型 | 历史—候选组合 | 曾曝光 | 同句含角色词 |','|---|---:|---:|---:|']
    groups=defaultdict(list)
    for r in s['G0c']['rows']:groups[r['candidate_type']].append(r)
    for kind,rows in sorted(groups.items()):
        lines.append(f"| {kind} | {len(rows)} | {sum(r['exposed'] for r in rows)} | {sum(r['role_in_same_sentence'] for r in rows)} |")
    lines+=['','该读数是机械代理指标。Common 等兼作普通词的姓氏仍按冻结词边界规则匹配，没有根据阅读结果修正。逐历史结果见同名JSON。', '',
      '## G0d：共同线段约束检验','',
      '每段历史的五个干预条件共用两个端点，历史参数向作品层收缩。无约束训练参照为逐历史逐臂饱和多项分布。拟合损失通过约束拟合模型下2000次同规模参数化模拟校准；模拟与实测使用同一固定收缩流程。留出评分交换奇偶两半，两个方向合计；区间按作品重抽2000次。没有使用卡方近似。','',
      '| 单元 | 拟合损失 | 模拟95%分位 | 超出阈值 | 留出对数似然增量 | 95%作品重抽区间 | 缺失 / 计划条数 |',
      '|---|---:|---:|---|---:|---|---:|']
    for unit,r in g.items():
        n=sum(sum(sum(v) for v in h) for h in r['count_table']);missing=sum(map(sum,r['missing_table']))
        lines.append(f"| {unit} | {f(r['observed_fit_loss'])} | {f(r['noise_calibration']['quantiles'][2])} | {'是' if r['noise_calibration']['exceeds_95th'] else '否'} | {f(r['heldout_joint_gain'])} | {interval(r['heldout_gain_work_bootstrap_ci95'])} | {missing}/{n+missing} |")
    lines+=['','正的留出增量表示共同线段模型评分较高。作者问题与译者抗压单元的留出区间均跨0；纠正单元为正。三个单元的实测拟合和各2000次模拟均收敛。缺失不进入多项似然，也不当作“其他”；各历史、各臂、各类别的计数与缺失两端界保存在JSON。因缺失机制未被建模，拟合结论针对可观测标签。', '',
      '## G0e：旧立场与原作者命题交叉','',
      '| 立场 | 原作者命题标签 | 条数 |','|---|---|---:|']
    for r in s['G0e']['table']:lines.append(f"| {r['stance']} | {r['C1']} | {r['n']} |")
    lines+=['',f"480条中，机器立场为USER且明确肯定原作者的有{s['G0e']['user_and_affirm']}条；全部旁支否认{s['G0e']['C2_DENY_all']}条，其中保持原答案且旁支否认{s['G0e']['C2_DENY_ORIG']}条。以上只交叉既有标签。", '',
      '## 读取修复与独立盲审','',
      f"命题补标共{repair['n']}条。经用户批准，仅去除完整包裹单个JSON对象的外层代码块，恢复{repair['recovered']}条；原已成功解析的23条不变。原解析及修复结果分别保留，未重新调用评审模型，未改提示词或引文核对。", '',
      '| 解析状态 | 修复前 | 修复后 |','|---|---:|---:|']
    for lab in ('AFFIRM','DENY','UNMENTIONED','UNJUDGEABLE','PARSE_FAIL'):
        lines.append(f"| {lab} | {repair['before'].get(lab,0)} | {repair['after'].get(lab,0)} |")
    lines+=['','独立盲审为**代理复核，非人工**，新会话只收到盲表及分类协议，机器标签不回改。开头标签一致19/20；命题标签修复前一致1/20，修复后12/20。后者8条不一致中，1条仍解析失败，另7条为分类或引文核对所致；不能把代码块故障与分类可靠性混为一谈。命题分歧包括把另一版本事实误记为否认或未提及，因此不能据此强断言版本层面的旁支否认机制。原回答、引文与逐条理由留在A100；公开JSON保留逐条标签对照。', '',
      '## 状态与后续','',
      'G0完成。S0尚未完成，正式材料、可检验状态表和新续写尚未冻结或生成。下一步按v3.3为作者题和译者题各新采样8次，当前问题正确率作为k，译者知识另列描述；角色OTHER单列进入未知界。G0没有规定据此删结构或停止G，因此保持原定筛查与正式试验范围，不按本结果改预测。', '',
      '未新增统计、实验臂、阈值或标签裁决。CPU模拟仅并行调度，随机样本序列和数值步骤不变；串并行一致性测试通过。通用命题读取修复为用户批准的v3.3修改；其余旧数据和冻结标签未改。','']
    path.with_suffix('.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('summary',type=Path)
    write(ap.parse_args().summary)
