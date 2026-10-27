"""正式阶段冻结材料、计划和估计规则；不调用模型。"""
from pathlib import Path
import argparse
import hashlib
from core import load,save,digest,SEED,INTERVENTIONS,INTERVENTION_FIELDS
from formal import make_plan,C_PROMPT,A0
from legacy import previous
from judging import ROLE_PROMPT,ROLE_SPECIFIC,ROLE_COMMON
from propositions import PROMPT as PROPOSITION_PROMPT

MODEL_PROTOCOL={
 'target':'完整联合链P(y1)P(y2|y1)P(y3|y1,y2)，先分量相乘再混合',
 'outcomes':dict(y1=['G','D','X','OTHER'],
                 y2=['TRUE_ROLE','FALSE_ROLE','NO_ROLE','DENIED','UNMENTIONED'],
                 y3=['AFFIRM','DENY','UNMENTIONED','N/A']),
 'unknown':'截断、循环、解析缺失、不可判、OTHER角色、版本未明及CONFLICTING不作为负例；似然对相应未知结局求和。全未知样本不贡献拟合或评分。',
 'features':['s','delta_pol','delta_gold','f_assoc','r_adj_diag','r_adj_online_role_distribution',
             'exposed','role_in_same_sentence','k','z_scope','c','same_subject','relation_change',
             'qualifier_change','medium_change','creator_type_role','computable'],
 'A_prime':'三个多项对数几率回归；每个头包含同一共同变量表和干预特征，第二头另加y1独热编码，第三头另加y1、y2独热编码。条件类别效应可加，不另加事后交互。',
 'A':'与A_prime相同，但去掉六个tau特征、r_adj_diag与r_adj_online角色分布。',
 'B':'两个各自独立参数的上述链式分量；分量只用非干预共同变量和前序结局类别，不接收干预特征；干预仅进入混合比例。比例为干预六特征加s、delta_pol及两个曝光变量的对数几率回归。分量标签可交换，不赋予已识别的内部机制含义。',
 'preprocess':'仅用训练项目估计连续变量均值和标准差；缺失用训练均值并附缺失指示。角色分布用冻结评审类别的比例，不用与真实角色一致率代替在线读数。训练中恒定列不估计作用，跨结构预测将其系数固定为0并报告。',
 'weighting':'拟合与留出评分均先续写平均、再历史平均、再项目平均；电影版本主报告方向等权、重抽以电影配对为簇。历史等权评分并列。',
 'penalty':'所有非截距参数采用二次惩罚；候选强度0.001、0.01、0.1，目标函数为项目等权平均负对数似然加0.5*强度*平方范数。各模型用同一候选集。',
 'selection':'仅训练域内按项目固定五折选择惩罚强度；项目按批种子打乱轮流分折，同作品全部历史留在同折；以验证集联合对数似然最大者选择，并列取较大惩罚。A0完全排除。',
 'optimization':'双精度L-BFGS，最多500次迭代，函数容差1e-9、梯度容差1e-6；B三起点（一个相同分量的近坍缩起点、两个种子固定的扰动起点），按训练惩罚目标选取，不据测试表现选取。未收敛须报告。',
 'evaluation':'先文献域训练预测各G2，再留一结构；相同测试样本分别报告y1、y2、y3边际及联合留出评分。部分未知的联合评分对未知维度边际化，并另列完整三维可观测子集和分母。',
 'bootstrap':'每次保留项目内全部历史和续写，按项目重抽2000次；不使用测试结果重新拟合或选特征。',
 'increments':'逐个冻结特征组移除后重新拟合，沿用相应完整模型在训练域选定的惩罚强度；不用A0或测试结果调参。',
 'A0':'G1非A0生成与评审完成后拟合，单独提交预测，再生成A0。两模型共享干预编码；在链接函数可加假定下外推，不把A0低错误率直接判为某模型获胜。',
 'unlearned':'文献域中无变化的medium_change、computable及无可用z_scope的系数不能由文献域学习。其结构数值预测按执行提示独立检验，不把固定零系数称为学到的效应。',
}


def budget_projection(plan,s0):
    # G1尚未生成，用执行提示中第四批164词元均长；其余用各自S0试运行实测。
    lengths={'g1_non_a0':164,'g1_a0':164}
    lengths.update({k:v['quality']['trial']['mean_tokens'] for k,v in s0['structures'].items()})
    additions={k:plan['counts'][k]*lengths[k] for k in plan['counts']}
    total=s0['budget']['tokens']+sum(additions.values())
    return dict(observed_tokens=s0['budget']['tokens'],mean_length_assumptions=lengths,
        planned_requests=plan['counts'],projected_new_tokens=additions,projected_total=total,
        warning=1200000,user_decision=1500000,warning_reached=total>=1200000,
        pause_required=total>1500000,
        limitation='干预可能改变长度；本外推不把估计当硬上限，G1后按实测更新。评审与教师强制不计入主模型新生成词元。')


def prepare(out,pilot,protocol_path,implementation_commit):
    plan,_=make_plan(out,pilot);s0=load(out/'s0_public_summary.json')
    protocol=protocol_path.read_text(encoding='utf-8-sig')
    materials=dict(plan=plan,capital_exclusions=s0['capital_exclusions'],
        readout_scope='所有读数为本批所需数据；与第五批各归各批，不混用。',
        tau_notes='creator_type_role取候选在替代问题中的角色；真实无关译者及导演为1，非同主体不自动改成0。数值普通元素对照无命名操作角色。',
        literature_I=s0['readouts']['I_eligibility'])
    p3=previous().p3;old=load(pilot/'factdiag3_20261030/factdiag3_prereg.json')
    t=old['frozen']['rules']['templates']
    templates={k:t[k] for k in ('system','x1','x2','S_D','A1')}
    templates.update(C=C_PROMPT,A0=A0)
    if templates['A1']!=p3.A1 or templates['S_D']!=p3.old.S3:raise RuntimeError('前批模板不符')
    judgments=dict(stance=p3.old.JUDGE_PROMPT,role=ROLE_PROMPT,
                   role_specific=ROLE_SPECIFIC,role_common=ROLE_COMMON,proposition=PROPOSITION_PROMPT)
    frozen=dict(implementation_commit=implementation_commit,
        execution_protocol=protocol,execution_protocol_sha256=hashlib.sha256(protocol.encode()).hexdigest(),
        materials_sha256=digest(materials),templates=templates,
        template_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in templates.items()},
        judgments=judgments,judgment_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in judgments.items() if isinstance(v,str)},
        generation=dict(seed=SEED,seed_rule='sha256(批种子|conflict_id|idx|path|arm|rep|t|phase)前8字节小端、取63位',
            temperature=.7,max_new_tokens=1024,batch=16,dtype='bf16',attention='sdpa',experts='grouped_mm',
            prefix='追加到助手生成起点；1024只计新采样词元；完整回答送解析与评审',forward_temperature=1.0),
        screen_states={k:v['states'] for k,v in s0['structures'].items()},
        readout_inventory=s0['readouts']['inventory'],model_protocol=MODEL_PROTOCOL,
        intervention_fields=INTERVENTION_FIELDS,interventions=INTERVENTIONS,
        missing='缺失不计零事件；事件报告两端界；评审与解析不一致单列。第2轮无法确定x的历史不分支；d=x按候选条件排除。',
        parsing='实体沿既有严格答案行与别名整值匹配；G2d主格按最后数值，其他数值按答案行整值；联合导演只有完整联合署名为相同身份。身份优先D→X→G。',
        budget=budget_projection(plan,s0),
        sequence=['G0和S0独立提交','冻结','G1非A0','评审与拟合','单独冻结A0预测','A0','G2c','检查点','G2b','G2d','G2a','评审与盲审','跨域分析与报告'])
    if frozen['budget']['pause_required']:raise RuntimeError('S0外推超过150万，须用户决定')
    prereg=dict(frozen=frozen,frozen_sha256=digest(frozen),
        A0_prediction_status='尚未拟合，禁止生成A0；将在G1非A0评审后单独冻结')
    for name,value in [('factdiag6g_materials.json',materials),('factdiag6g_prereg.json',prereg)]:
        path=out/name
        if path.exists() and load(path)!=value:raise RuntimeError('既有冻结文件不同，禁止覆盖：'+name)
        save(path,value)
    print('正式材料与规则已写入，仍须提交推送后生成',plan['counts'],frozen['budget'],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--pilot',type=Path,required=True);ap.add_argument('--protocol',type=Path,required=True)
    ap.add_argument('--implementation-commit',required=True)
    a=ap.parse_args();prepare(a.out,a.pilot,a.protocol,a.implementation_commit)
