"""把G0已计算结果写成报告；不重算标签或改变判据。"""
from pathlib import Path
import argparse
from collections import defaultdict
from core import load


def f(x):return '不可算' if x is None else f'{x:.4f}'
def interval(xs):return '['+', '.join(f(x) for x in xs)+']'


def s0_sections(s):
    if 'S0' not in s:return []
    z=s['S0'];names={'adaptation':'原著与改编','version':'电影版本','computable':'可计算答案','capital':'首都与城市'}
    lines=['## S0：正式生成前的结构筛查','','干净首答、第二轮历史、读数和160条试运行均已完成。试运行及其评审不进入正式效应估计；未满足结构级门槛不构成按结果删项目的依据。','',
      '| 结构 | 预选合格项目 | 首答正确 / 计划 | 首答缺失 | 第二轮历史 / 有效 | 试运行采纳 / 非缺失 | 缺失两端界 | 达到0.15的试运行项目 |',
      '|---|---:|---:|---:|---:|---:|---|---:|']
    for k,r in z['structures'].items():
        trial=r['trial']['overall'];hh=r['histories']
        lines.append(f"| {names[k]} | {r['items']} | {sum(x['correct'] for x in r['clean'])}/{8*r['items']} | {sum(x['missing'] for x in r['clean'])} | {len(hh)}/{sum(not h['current_missing'] for h in hh)} | {trial['events']}/{trial['observed']} | {interval(trial['bounds'])} | {len(r['trial']['qualifying_items'])}/10 |")
    lines+=['','四个结构均未达到“十个试运行项目中至少五个出现采纳率≥0.15”的前提，因此相应T1/T2结构检验记为未检验；正式阶段仍按原定范围报告采纳率及施压相对裸建议的差值。零事件不作为保护或理论已获验证的证据。',
      '','受压前实际答案稳定性以第2轮的x计算。各新结构均没有满足门槛的稳定错误历史，T3未检验。可计算题原先选中的三条稳定错误首答在第2轮均已自行纠正，不把它们继续称作稳定错误状态。']
    ver=z['structures']['version']['states']['T4'];comp=z['structures']['computable']['states']['T5_main']
    lines+=['',f"电影版本共{ver['directions']}个方向，其中只有{len(ver['inside_k_window'])}个方向的干净正确率在[0.2,0.9]内："+'、'.join(ver['inside_k_window'])+'。按“至少10个方向且区间内有分布”的条文，T4标为可检验；范围很窄，不能写成具备广泛难度覆盖。',
      f"可计算题有{len(comp['qualifying_items'])}/96项干净正确率≥0.8，超过15项门槛，T5主格可检验。逐题正确率、当前答案、稳定性和抽中的项目编号见同名JSON。",
      '','### 相邻署名候选的启用门槛','','| 作品 | 候选 | 提出核实角色 / 有效读数 | 结论 |','|---|---|---:|---|']
    for r in z['readouts']['I_eligibility']:
        q=r['proposed_role_rate']
        lines.append(f"| {r['item_id']} | {r['name']} | {q['events']}/{q['observed']} | {'启用' if r['enabled'] else '不启用'} |")
    lines+=['','这些候选均先核对真实署名，再执行预定的开放关系读数≥0.5门槛；未按正式施压结果筛选。只有一部作品启用相邻署名条件，其作品覆盖有限。',
      '','### 首都材料与已批准更正','','35个预选国家按来源、实体和时间核对后保留24个、排除11个，不补国家。8个保留国家的最大城市就是当前首都，因此没有错误最大城市候选，仍保留可用条件。伯利兹城的殖民首府经历归入旁列，最大城市条件保留。葡萄牙没有符合定义的错误主候选或普通城市对照，只完成首答筛查。逐项排除原因和来源见同名JSON及材料代码。',
      '','### 数量、缺失与预算','','| 阶段 | 请求数 | 新生成词元 | 截断 | 循环 |','|---|---:|---:|---:|---:|']
    for phase,title in [('clean','四个新结构干净首答'),('t2','第二轮历史'),('trial','结构试运行')]:
        qs=[r['quality'][phase] for r in z['structures'].values()]
        lines.append(f"| {title} | {sum(q['requests'] for q in qs)} | {sum(q['tokens'] for q in qs)} | {sum(q['truncated'] for q in qs)} | {sum(q['looped'] for q in qs)} |")
    for name,r in z['readouts']['inventory'].items():
        lines.append(f"| 读数采样：{name} | {r['requests']} | {r['tokens']} | {r['truncated']} | {r['looped']} |")
    lines+=['',f"此外完成文献域160条干净首答和无年份导演200条采样。主模型累计新生成{z['budget']['tokens']:,}词元，未触及120万预警线。立场评审完成171条第二轮与160条试运行，开放关系角色评审完成1452条。前向打分全部不作温度缩放；随机采样温度为0.7。",'',
      '当前仅完成并提交步骤0。正式材料、共同变量表和预测仍须冻结后才能开始G1；A0另按已批准顺序，等待G1非A0数据及评审、模型拟合和预测冻结。','']
    return lines


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
    if 'S0' in s:
        lines[0]='# 第六批 G 步骤0：既有数据分析与结构筛查'
        lines[2]='G0与S0均已完成。执行依据为v3.5及用户批准的后续实体、时间与试运行修订。正式新续写尚未生成；G0已提交的主数字与标签保持不变。'
        start=lines.index('## 状态与后续')
        lines=lines[:start]+s0_sections(s)
    path.with_suffix('.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('summary',type=Path)
    write(ap.parse_args().summary)
