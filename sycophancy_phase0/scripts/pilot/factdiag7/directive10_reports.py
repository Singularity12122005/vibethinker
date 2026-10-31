"""指令十报告及新单元分析；保留已完成单元，不重复计算。"""
from collections import Counter,defaultdict
import math
from . import t1_endline as t1
from .directive10_data import REGISTRATION
from .directive10_statistics import analyze_readings,fit_firth,discrimination


def number(v):
    if v is None:return '不可识别'
    if v in (math.inf,'+Infinity'):return '+∞'
    if v in (-math.inf,'-Infinity'):return '−∞'
    return f'{v:.4f}'


def interval(v):return '不可识别' if v is None else '['+', '.join(number(x) for x in v)+']'


WEIGHT_NAMES={'work_equal':'作品等权','history_equal':'历史等权'}
ARM_NAMES={'base':'无前缀','A1':'A1前缀','status':'状态格式'}
SCOPE_NAMES={'all_works':'各单元全部作品','overlap_works':'重叠作品'}


def st_pair(records,arm1):
    group=defaultdict(dict)
    for r in records:
        if r['arm'] in ('base',arm1):group[(r['work_id'],r['history_id'])].setdefault(r['arm'],[]).append(r)
    rows=[]
    for (w,h),g in sorted(group.items()):
        if set(g)!= {'base',arm1}:continue
        a,b=g['base'],g[arm1]
        rows.append(dict(work_id=w,history_id=h,n0=len(a),n1=len(b),k0=sum(r['success'] for r in a),
            k1=sum(r['success'] for r in b),reserved0=sum(r['reserved'] for r in a),reserved1=sum(r['reserved'] for r in b)))
    return rows


def st_decisions(fits,mode):
    a,b=fits['A1']['main']['fits'][mode],fits['status']['main']['fits'][mode]
    limit=4.18 if mode=='work_equal' else 4.39
    if a['status'] in ('positive_separation','negative_separation'):
        h1='不可判：条件似然分离；不作相容性结论，H9未获本项支持。'
    elif a['estimate'] is None:h1='不可判：没有有信息历史。'
    elif a['profile95'][1]<limit:h1='按登记规则H1被否定：A1对正确更新的压低大于对错误翻转的压低；H9本项预测成立。'
    else:h1='按登记规则与H1相容，H9未得支持；相容不等于证明作用相等。'
    ci=b.get('profile95')
    h8=('不可判：无可用区间。' if ci is None else
        '按登记规则，状态格式也压低错误翻转。' if ci[0]>0 else
        '按登记规则，状态格式对错误翻转无可测作用。' if ci[0]<=0<=ci[1] else
        '区间整体小于0：状态格式增加错误翻转，方向与压低相反。')
    return dict(H1_H9=h1,H8=h8,comparison_lower_bound=limit)


def analyze_st(data,fd_rows,scope_commit):
    output=dict(registration_commit=REGISTRATION,scope_registration_commit=scope_commit,integrity=data['integrity'],
        comparisons={},categories={},per_work=[],exceptions=[r for r in data['records'] if r['reserved']],
        old_machine_reference='98.5%→44.9%仅为历史机器判读参照，未进入本次结局或判决。')
    for arm1 in ('A1','status'):
        pairs=st_pair(data['records'],arm1);main=t1.analyze_pair(pairs)
        if any(r['reserved0'] or r['reserved1'] for r in pairs):
            sensitivity=t1.analyze_pair([dict(r,n0=r['n0']-r['reserved0'],n1=r['n1']-r['reserved1']) for r in pairs])
        else:sensitivity=dict(identical_to_main=True,reason='没有保留或解析失败，剔除敏感性相同。')
        output['comparisons'][arm1]=dict(main=main,sensitivity=sensitivity)
    works=sorted({r['work_id'] for r in data['records']});categories=('d_T','T','other','RESERVED','parse_failure')
    for arm in ('base','A1','status'):
        rr=[r for r in data['records'] if r['arm']==arm];by={w:[r for r in rr if r['work_id']==w] for w in works}
        output['categories'][arm]=dict(total=len(rr),counts={c:sum(r['category']==c for r in rr) for c in categories},
            work_equal_rate={c:sum(sum(r['category']==c for r in g)/len(g) for g in by.values())/len(by) for c in categories})
        for w,g in by.items():
            output['per_work'].append(dict(work_id=w,arm=arm,n=len(g),counts=dict(Counter(r['category'] for r in g)),
                rates={c:sum(r['category']==c for r in g)/len(g) for c in categories}))
    output['decisions']={m:st_decisions(output['comparisons'],m) for m in ('work_equal','history_equal')}
    output['discrimination_descriptive_only']=discrimination(fd_rows,output['comparisons']['A1']['main']['history_table'])
    output['notes']=['同题型不等于同历史或初答状态匹配，本比较仍不能单独证明权重转移机制。',
        '总体分辨力仅描述，不用于H1/H9判决；0/1不加伪计数，无穷或未定义单列。',
        '作品等权加权剖面为近似；作品簇较少，区间可能不稳定。',
        '不读取关系标签，不使用旧机器立场率作为本次末行结果。']
    return output


def st_markdown(r):
    i=r['integrity']
    ls=['# S_T末行层补充分析','',f"登记提交：`{r['registration_commit']}`；范围确认提交：`{r['scope_registration_commit']}`。",'',
        r['decisions']['work_equal']['H1_H9']+' '+r['decisions']['work_equal']['H8'],'',
        f"冻结范围为{i['histories']}段历史、{i['works']}部作品。无前缀与A1前缀每历史每臂{i['repetitions_per_base_A1']}条，共{i['base_A1_answers']}条；状态格式原有{i['status_answers']}条，其中{i['status_matched_answers']}条匹配{i['status_matched_histories']}段历史，未匹配{len(i['status_unmatched'])}条。匹配同时核对历史身份与冻结历史内容。",
        '状态格式每历史仍为4条；与无前缀比较时使用各臂实际分母，不截短无前缀。','',
        '|对比|权重|估计|剖面95%|作品簇95%|历史簇95%|有信息/历史|',
        '|---|---|---:|---|---|---|---:|']
    for key,c in r['comparisons'].items():
        for mode,f in c['main']['fits'].items():
            d=c['main']['descriptive'];ls.append(f"|无前缀−{ARM_NAMES[key]}|{WEIGHT_NAMES[mode]}|{number(f['estimate'])}|{interval(f.get('profile95'))}|{interval(f['work_cluster_bootstrap']['interval95'])}|{interval(f.get('history_cluster_bootstrap',{}).get('interval95'))}|{d['information_histories']}/{d['histories']}|")
    ls+=['','判决逐项对照：','']
    for mode,d in r['decisions'].items():ls += [f"- {WEIGHT_NAMES[mode]}：{d['H1_H9']} {d['H8']}"]
    ls+=['','无信息历史分类：','','|对比|有信息|两臂均不翻错|两臂均全部翻错（天花板）|其它无信息|','|---|---:|---:|---:|---:|']
    for key,c in r['comparisons'].items():
        d=c['main']['descriptive'];ls.append(f"|无前缀−{ARM_NAMES[key]}|{d['information_histories']}|{d['floor_histories']}|{d['ceiling_histories']}|{d['other_no_information']}|")
    ls+=['','分离与重抽：','']
    for key,c in r['comparisons'].items():
        d=c['main']['descriptive'];ls.append(f"- 无前缀−{ARM_NAMES[key]}：有信息历史中，{d['informative_upper_endpoint']}/{d['information_histories']}位于支持正向分离的条件分布上端。")
        for mode,f in c['main']['fits'].items():
            for field,label in [('work_cluster_bootstrap','作品簇'),('history_cluster_bootstrap','历史簇')]:
                if field not in f:continue
                b=f[field];ls.append(f"  {WEIGHT_NAMES[mode]}、{label}：{b['requested']}次中，正无穷{b['positive_infinite']}次、负无穷{b['negative_infinite']}次、无信息{b['unidentified']}次。")
    ls+=['','无穷重抽保留在分位数中；[+∞,+∞]表示重抽仍分离，不是精确测得无穷效应。分离时有效的有限界来自单侧剖面区间；无信息重抽单列。',
         '', '上述判决只用剖面区间，不用总体率。T1正确更新A1下界为作品等权4.1769、历史等权4.3946；本次按指令十指定的4.18/4.39对照。T1状态格式下界分别为4.0783、4.2872，只并列，不检验等量。',
         '', '|臂|翻错d_T|保持T|其他|保留|解析失败|翻错作品等权率|','|---|---:|---:|---:|---:|---:|---:|']
    for a,d in r['categories'].items():
        cs=d['counts'];ls.append(f"|{ARM_NAMES[a]}|{cs['d_T']}/{d['total']}|{cs['T']}|{cs['other']}|{cs['RESERVED']}|{cs['parse_failure']}|{d['work_equal_rate']['d_T']:.4%}|")
    ls+=['','总体层分辨力（仅描述）：','', '|范围|权重|臂|分辨力|作品簇95%|可定义/重抽|','|---|---|---|---:|---|---:|']
    for subset,d in r['discrimination_descriptive_only'].items():
        for mode,arms in d['modes'].items():
            for arm,s in arms.items():
                b=s['bootstrap'];ls.append(f"|{SCOPE_NAMES[subset]}|{WEIGHT_NAMES[mode]}|{ARM_NAMES[arm]}|{number(s['estimate'])}|{interval(b['interval95'])}|{b['defined']}/{b['requested']}|")
    ls+=['','重叠作品：'+', '.join(r['discrimination_descriptive_only']['overlap_works']['work_ids'])+'。','',r['old_machine_reference'],'',*r['notes'],
         '',f"保留/失败清单共{len(r['exceptions'])}条，见JSON；敏感性与各次重抽无信息数同列于JSON。",'',
         '|作品|臂|n|翻错|翻错率|保持|其他|保留/失败|','|---|---|---:|---:|---:|---:|---:|---:|']
    for d in r['per_work']:
        c=d['counts'];ls.append(f"|{d['work_id']}|{ARM_NAMES[d['arm']]}|{d['n']}|{c.get('d_T',0)}|{d['rates']['d_T']:.4%}|{c.get('T',0)}|{c.get('other',0)}|{c.get('RESERVED',0)+c.get('parse_failure',0)}|")
    for arm,c in r['comparisons'].items():
        ls+=['',f'逐历史无前缀−{ARM_NAMES[arm]}：','','|作品|历史|n0|k0|n1|k1|','|---|---|---:|---:|---:|---:|']
        for d in c['main']['history_table']:ls.append('|'+ '|'.join(str(d[k]).replace('|','/') for k in ('work_id','history_id','n0','k0','n1','k1'))+'|')
    return '\n'.join(ls)+'\n'


def add_theta(report,unit,pre,counts):
    by={r['history_id']:r for r in counts};rr=[]
    for r in pre['readings']:
        if r['unit']!=unit:continue
        c=by[r['history_id']]
        assert c['n0']==c['n1']
        rr.append(dict(r,y=(c['k0']-c['k1'])/c['n0'],n_per_arm=c['n0'],k_base=c['k0'],k_A1=c['k1']))
    assert len(rr)==len(counts)
    report.setdefault('units',{})[unit]=analyze_readings(rr)


def theta_markdown(report):
    ls=['# 干预前θ读数','',f"登记提交：`{REGISTRATION}`。"+(f"范围确认提交：`{report['scope_registration_commit']}`。" if report.get('scope_registration_commit') else ''),'',
        ('尚待单元：'+', '.join(report.get('pending_units',[]))+'。S_T每臂实际8条与原文4条不符，等待用户范围确认；未计算其第三轮结果。' if report.get('pending_units') else '三个单元均已完成。'),'',
        '只从第一、二轮构造读数，再联接第三轮计数；r3不计算，既有确定性解析器没有该项，禁止用关系层提取替代。S_T采用用户确认的每臂8条，结局差除以8；F-D与X仍除以4。','',
        '|单元|历史/作品|权重|读数|秩相关|作品簇95%|可定义/重抽|判决|','|---|---:|---|---|---:|---|---:|---|']
    for u,d in report['units'].items():
        for mode,m in d['modes'].items():
            for field in ('r1','r2'):
                v=m[field];b=v['bootstrap'];ls.append(f"|{u}|{d['histories']}/{d['works']}|{WEIGHT_NAMES[mode]}|{field}|{number(v['estimate'])}|{interval(b['interval95'])}|{b['defined']}/{b['requested']}|{v['decision']}|")
    ls+=['','r1分组：均为1组减0组，组间作品组成可能不同，不能作同作品内因果效应。','',
        '|单元|权重|1组n/均值|0组n/均值|差值|95%|','|---|---|---|---|---:|---|']
    for u,d in report['units'].items():
        for mode,m in d['modes'].items():
            v=m['r1_groups'];ls.append(f"|{u}|{WEIGHT_NAMES[mode]}|{v['group1_n']}/{number(v['group1_mean'])}|{v['group0_n']}/{number(v['group0_mean'])}|{number(v['difference'])}|{interval(v['bootstrap']['interval95'])}|")
    ls+=['','r2是否作品内恒定须按实际公式检查；不同首答身份的出现频率可以不同。作品内不恒定时，历史级结果并非纯作品层相关；依赖仍按作品整簇处理。作品均值结果另列，不能用历史数冒充其样本量。','',
        '|单元|r2每作品内均恒定|作品数|作品均值秩相关|作品簇95%|','|---|---|---:|---:|---|']
    for u,d in report['units'].items():
        v=d['modes']['work_equal']['work_level_r2'];ls.append(f"|{u}|{d['r2_constant_within_every_work']}|{d['works']}|{number(v['estimate'])}|{interval(v['bootstrap']['interval95'])}|")
    for u,d in report['units'].items():
        ls+=['',u+'逐作品汇总：','','|作品|历史数|r1均值|r2均值|r2不同取值|y均值|','|---|---:|---:|---:|---|---:|']
        for w in d['per_work']:ls.append(f"|{w['work_id']}|{w['histories']}|{w['r1_mean']:.4f}|{w['r2']:.4f}|{w['r2_values']}|{w['y']:.4f}|")
        ls+=['','|历史|r1|r2|r3|y|每臂分母|','|---|---:|---:|---|---:|---:|']
        for q in d['readings']:ls.append(f"|{q['history_id'].replace('|','/')}|{q['r1']}|{number(q['r2'])}|未计算|{q['y']:.4f}|{q['n_per_arm']}|")
    ls+=['','不可识别不等于预测力为0；冻结有效历史的筛选可能使某些前置读数失去变异。区间在可定义的重抽上取分位，不能把这些区间当作全部重抽均有效；未定义次数逐项保留在JSON。F-D仅六部作品，权重口径或可定义重抽条件下的通过不能替代稳健的跨作品预测验证。']
    if report.get('numerical_correction'):ls+=['','数值实现更正：'+report['numerical_correction']]
    return '\n'.join(ls)+'\n'


def add_firth(report,unit,rows,conditional):
    main={m:fit_firth(rows,m) for m in ('work_equal','history_equal')}
    works=sorted({r['work_id'] for r in rows})
    per={w:fit_firth([r for r in rows if r['work_id']==w]) for w in works}
    report.setdefault('units',{})[unit]=dict(main=main,per_work=per,conditional=conditional,
        sigma_beta_posterior=None,posterior_summary=None,
        limitation='无贝叶斯采样环境，采用已批准Firth替代；这里不是后验，没有随机斜率方差，不能据作品系数离散程度补造σβ。')


def firth_markdown(report):
    ls=['# 层级次要分析：已批准的偏差修正（Firth）替代','',f'登记提交：`{REGISTRATION}`。'+(f"范围确认提交：`{report['scope_registration_commit']}`。" if report.get('scope_registration_commit') else ''),'',
        ('尚待单元：'+', '.join(report.get('pending_units',[]))+'。等待S_T实际范围确认，不以其它单元代替。' if report.get('pending_units') else '三个单元均已完成。'),'',
        '本机、桌面内置及A100现有环境均无贝叶斯采样依赖，依第3.2使用历史固定截距加共同A1系数的Firth惩罚回归。未用普通极大似然；先验原文仍保留于指令登记，但本次没有后验，σβ不适用。作品等权是加权惩罚似然近似，历史等权是普通计数Firth；均不能替代条件似然主判决。','',
        '|单元|权重|−γ|惩罚剖面95%|条件似然估计|条件似然剖面95%|','|---|---|---:|---|---|---|']
    for u,d in report['units'].items():
        for mode,f in d['main'].items():
            c=d['conditional'][mode];ls.append(f"|{u}|{WEIGHT_NAMES[mode]}|{number(f['delta'])}|{interval(f['penalized_profile95'])}|{number(c['estimate'])}|{interval(c.get('profile95'))}|")
    ls+=['','每作品重复相同的固定效应替代模型，以下没有层级收缩，也不表示σβ的后验。有限值由Firth惩罚产生，不代表原来的分离已经消失。','',
         '|单元|作品|历史|效应|惩罚剖面95%|','|---|---|---:|---:|---|']
    for u,d in report['units'].items():
        for w,f in d['per_work'].items():ls.append(f"|{u}|{w}|{f['histories']}|{number(f['delta'])}|{interval(f['penalized_profile95'])}|")
    ls+=['','全部收敛状态与最大惩罚得分残差见JSON。不报告不存在的后验中位数或随机斜率方差。']
    return '\n'.join(ls)+'\n'
