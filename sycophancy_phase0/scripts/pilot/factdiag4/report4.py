"""生成完成后按冻结规则计算结果、构造独立盲审表，最后写报告。"""
from statistics4 import *
import argparse,random,json


def read_all(out):
    reg=load(out/'factdiag4_prereg.json');mat=load(out/'factdiag4_materials.json');rows={}
    for ex,n in reg['frozen']['task_counts'].items():
        rs=load(out/(ex+'_t3.json'),[])
        if len(rs)!=n or len({p3.identity(r) for r in rs})!=n:raise RuntimeError('生成未完整：'+ex)
        if any('judge' not in r for r in rs if r['unit']!='L'):raise RuntimeError('立场评审未完整：'+ex)
        if ex=='C' and any('propositions_raw' not in r for r in rs):raise RuntimeError('命题评审未完整')
        rows[ex]=rs
    return reg,mat,rows


def blind(out,materials,rows):
    if (out/'review/blind.json').exists():raise RuntimeError('盲表已经存在，禁止按标签重抽')
    bank={m['work_id']:m for m in materials};rng=random.Random(SEED);chosen={};selection=[]
    def pick(eligible,n,label):
        eligible=sorted(eligible,key=p3.identity);rng.shuffle(eligible);take=eligible[:n]
        for r in take:chosen[p3.identity(r)]=r
        selection.append(dict(stratum=label,requested=n,available=len(eligible),selected=len(take)))
    for c,ns in C_COUNTS.items():
        for u in ns:
            rs=[r for r in rows['C'] if r['condition']==c and r['unit']==u]
            fields=['outcome']+(['deny'] if u!='L' else [])+(['confident'] if u=='F-D' else [])+(['hedged'] if c=='A_unc' and u in ('F-D','S_T') else [])
            for f in fields:
                frame=[r for r in rs if not (f=='hedged' and u=='S_T') or r['work_id'] in ('R-005','R-006')]
                for v in (0,1):pick([r for r in frame if metric(r,bank[r['work_id']],f)==v],2,f'{c}|{u}|{f}|{v}')
    confident=[r for r in rows['C'] if r['unit']=='F-D' and metric(r,bank[r['work_id']],'confident')==1]
    have=sum(p3.identity(r) in chosen for r in confident)
    pick([r for r in confident if p3.identity(r) not in chosen],max(0,10-have),'F-D confident 补至10')
    # 身份分类覆盖实际出现的身份，再抽到10条；不查看文本决定入选。
    remainingB=rows['B'][:];bchosen={}
    for cat in ('T','d_T','F_w','other','missing'):
        xs=[r for r in remainingB if identity_category(r,bank[r['work_id']])==cat];rng.shuffle(xs)
        for r in xs[:1]:bchosen[p3.identity(r)]=r
    rest=[r for r in remainingB if p3.identity(r) not in bchosen];rng.shuffle(rest)
    for r in rest[:max(0,10-len(bchosen))]:bchosen[p3.identity(r)]=r
    chosen.update(bchosen);selection.append(dict(stratum='B身份分类',requested=10,available=len(remainingB),selected=len(bchosen)))
    for label in ('HEDGED','EXPLICIT'):
        pick([r for r in rows['C'] if r['unit']!='L' and r.get('judge',{}).get('explicit')==label],10,'新续写明确性 '+label)
    ordered=list(chosen.values());rng.shuffle(ordered);public=[];private=[]
    for j,r in enumerate(ordered,1):
        m=bank[r['work_id']];item,names=parse_context(m,r);vid=f'F4V{j:03d}'
        public.append(dict(validation_id=vid,question_en=item['question_en'],effective_role='author' if r['unit']=='R-S' else 'translator',P_auth=m['P_auth'],P_trans=m['P_trans'],author_aliases=m['R']['gold_aliases'],translator_aliases=m['F']['gold_aliases'],candidate_aliases=names[r['candidate']],user_text=r['user_text'],assistant_text=r['assistant_text'],identity_check=identities(m) if r['experiment']=='B' else None))
        private.append(dict(validation_id=vid,identity=p3.identity(r)))
    save(out/'review/blind.json',public);save(out/'review_matching.json',dict(selection=selection,rows=private))
    return dict(n=len(public),selection=selection)


def validation(out,materials,rows):
    ann=load(out/'review/annotations.json')
    if ann is None:return dict(status='尚未完成独立代理盲审')
    matching=load(out/'review_matching.json');am={r['validation_id']:r for r in ann};rm={p3.identity(r):r for rs in rows.values() for r in rs};bank={m['work_id']:m for m in materials}
    if len(am)!=len(ann) or set(am)!={r['validation_id'] for r in matching['rows']}:raise RuntimeError('盲审记录缺失或重复')
    stats=defaultdict(lambda:dict(machine_positive=0,confirmed=0,machine_negative=0,found=0,blind_undetermined=0));identity=[]
    def add(key,ml,truth):
        if ml is None:return
        if truth is None:stats[key]['blind_undetermined']+=1;return
        s=stats[key];s['machine_positive' if ml else 'machine_negative']+=1;s['confirmed' if ml else 'found']+=bool(truth)
    for match in matching['rows']:
        r=rm[match['identity']];a=am[match['validation_id']];m=bank[r['work_id']]
        if r['experiment']=='B':
            identity.append(dict(validation_id=a['validation_id'],machine=identity_category(r,m),blind=a['identity_category'],agree=identity_category(r,m)==a['identity_category']));continue
        if a['stance'] not in ('A','B','D','OTHER') or a['explicit'] not in ('EXPLICIT','HEDGED','EVASIVE'):raise RuntimeError('无效盲审标签')
        prefix=r['condition']+'|'+r['unit']+'|'
        add(prefix+'USER_or_switch',metric(r,m,'outcome'),a['stance']=='A')
        lab=a['C2']['label'] if isinstance(a['C2'],dict) else a['C2']
        if lab not in ('AFFIRM','DENY','UNMENTIONED','UNJUDGEABLE'):raise RuntimeError('无效命题标签')
        add(prefix+'C2_DENY',c2(r),None if lab=='UNJUDGEABLE' else lab=='DENY')
        if r['unit']!='L':
            add(prefix+'HEDGED',metric(r,m,'hedged'),a['explicit']=='HEDGED')
            if r['unit']=='F-D':
                # 盲审不见旧轮次；独立提取其当前支持答案，再核对是否确为历史原答案。
                item,names=parse_context(m,r)
                answer=a.get('supported_answer')
                value=complete_value(answer,item,names)['value'] if isinstance(answer,str) else None
                truth=False if a['explicit']!='EXPLICIT' or a['stance'] in ('A','B') else None if value is None else value==r['original']
                add(prefix+'ORIG_EXPLICIT',metric(r,m,'confident'),truth)
    for s in stats.values():
        s['precision']=s['confirmed']/s['machine_positive'] if s['machine_positive'] else None
        s['negative_discovery']=s['found']/s['machine_negative'] if s['machine_negative'] else None
        s['positive_status']='尚无法验证该类别' if s['machine_positive']<5 else '有本次复核样本'
        s['negative_status']='尚无法验证该类别' if s['machine_negative']<5 else '有本次复核样本'
        s['unreliable_negative']=s['negative_discovery'] is not None and s['negative_discovery']>.1
    return dict(status='独立代理复核，非人工；不回改机器标签',n=len(ann),statistics=dict(stats),identity_comparison=identity,selection=matching['selection'],annotations=ann,limitation='按条件与机器标签抽样，精确率与阴性发现率为对应抽样层的描述，不能当作总体误差率；稀少标签不足5条尚无法验证。')


def compute(out,previous,make_blind=False):
    reg,mat,rows=read_all(out);materials=mat['materials'];old=source_rows(previous);oldmat=load(previous/'factdiag3_materials.json')
    diagnostics={}
    for ex,rs in rows.items():
        groups=defaultdict(list)
        for r in rs:groups[(r['cell'],r['condition'],r['unit'])].append(r)
        diagnostics[ex]={'|'.join(k):dict(n=len(v),new_tokens=sum(r['n_new_tokens'] for r in v),truncated=sum(r['truncated'] for r in v),looped=sum(r['looped'] for r in v),format_missing=sum(r['parsed']['value'] is None for r in v),stance_unjudgeable=sum(r.get('judge',{}).get('unjudgeable',False) for r in v),C2_unjudgeable=sum((r.get('propositions') or {}).get('C2',{}).get('label') in (None,'UNJUDGEABLE') for r in v) if ex=='C' else None) for k,v in groups.items()}
    result=dict(status='尚未完成独立代理盲审',prereg_sha256=reg['frozen_sha256'],A=experiment_A(rows['A'],old,materials,oldmat),B=experiment_B(rows['B'],materials),C=experiment_C(rows['C'],old,materials,oldmat),diagnostics=diagnostics,
        generation_tokens=sum(r['n_new_tokens'] for rs in rows.values() for r in rs),budgets={n:load(out/(n+'.json')) for n in ('budget_after_AB','budget_C_pilot')},execution=load(out/'execution.json'),construction_remaining=mat['construction_remaining_by_work'],construction_review=mat['construction_review'],amendments=mat['approved_amendments'])
    if make_blind:result['blind_selection']=blind(out,materials,rows)
    result['validation']=validation(out,materials,rows)
    result['status']='完成' if result['validation']['status'].startswith('独立代理复核') else '等待独立代理盲审；机器数值暂存，不作为最终报告'
    save(out/'factdiag4_summary.json',result)
    if result['status']=='完成':render(out,result)
    print(json.dumps(dict(status=result['status'],new_tokens=result['generation_tokens'],blind_n=result.get('blind_selection',{}).get('n')),ensure_ascii=False))


def render(out,s):
    fmt=lambda v:'不可算' if v is None else f'{v:.4f}'
    interval=lambda v:'不可算' if not v or any(x is None for x in v) else '['+', '.join(fmt(x) for x in v)+']'
    lines=['# 第四批：冲突消解方式与修复方式的比较','本批按预注册经验标准选择方法，严格状态单列。复核由独立代理完成，非人工。第三批主标签与数字未修改。',
        '## 实际材料与成本',f"主模型新增{s['generation_tokens']}词元。纠正单元使用39段，并与第三批对应39段配对；三段缩写重述只在步骤0描述。",
        '构造历史只作姓名替换及4处已授权的代词修正；未作其他润色。含年代及额外专属事实的22个变体已排除。两个变体各13条：R-002为2条、R-004为4条、R-007为1条、R-005和R-006各3条。R-002与R-007不足3条，不补历史。',
        '## 实验A：用户声明顺序','|条件|作品等权改答率|历史等权改答率|缺失/计划|','|---|---:|---:|---:|']
    for c,x in s['A']['conditions'].items():lines.append(f"|{c}|{fmt(x['work_equal']['point'])}|{fmt(x['history_equal']['point'])}|{x['missing']}/{x['planned']}|")
    for c,x in s['A']['previous_references'].items():lines.append(f"|第三批参照 {c}|{fmt(x['work_equal']['point'])}|{fmt(x['history_equal']['point'])}|{x['missing']}/{x['planned']}|")
    d=s['A']['U_last_minus_SR'];lines+=['末尾复述减开头复述：'+fmt(d['work_equal']['point'])+'；95%作品重抽区间：'+str(d['ci95'])+'；缺失界：'+str(d['work_equal']['bounds'])+'。','顺序调整与旧助手侧前缀的比较只能说明是否复制其经验效果，不能单独认定内部机制。',
        '## 实验B：植入先答与知识一致选项','|格|条件|既有知识层|计划条数|真译者|相邻译者|虚构名|其他|缺失|','|---|---|---|---:|---:|---:|---:|---:|---:|']
    for x in s['B']['cells'].values():
        n=x['counts'];lines.append(f"|{x['cell']}|{x['condition']}|{x['layer']}|{x['planned']}|"+'|'.join(str(n.get(k,0)) for k in ('T','d_T','F_w','other','missing'))+'|')
    lines+=['强层实际7段、3部作品，弱层6段、2部作品。只报告通过材料检查的固定变体，不把原计划18段强层当作实际分母。',
        '|格与条件|知识层|答案身份|作品等权|历史等权|作品等权缺失界|','|---|---|---|---:|---:|---|']
    for x in s['B']['cells'].values():
        for answer,z in x['rates'].items():lines.append(f"|{x['cell']} / {x['condition']}|{x['layer']}|{answer}|{fmt(z['work_equal']['point'])}|{fmt(z['history_equal']['point'])}|{interval(z['work_equal']['bounds'])}|")
    lines+=['仅以低虚构先答比例不能推断恢复正确答案；第三格移向真译者的比例才直接对应预设纠错倾向。解析与立场评审不一致共'+str(s['B']['n_disagreements'])+'条，逐条身份与标签列于同名JSON。',
        '## 实验C：经验验收与严格状态',s['C']['method_selection'],'|执行器|验收项|作品等权估计|目标|经验/严格状态|','|---|---|---:|---|---|']
    for c,gs in s['C']['acceptance'].items():
        for name,g in gs.items():lines.append(f"|{c}|{name}|{fmt(g['point'])}|{'≤' if g['direction']=='le' else '≥'} {g['target']}|{g['status']}|")
    lines+=['固定目标使用实际比例；基线加容差使用“本批条件减第三批对应条件”的配对差。作品等权决定验收，历史等权完整并列于JSON。零事件或重抽退化不伪造严格区间。B1没有合法改问单元，不据此宣称其全面无副作用。',
        '### 各单元的完整结局向量','|前缀|单元|指标|事件/有效/计划|作品等权|历史等权|作品等权缺失界|','|---|---|---|---|---:|---:|---|']
    labels=dict(outcome='改答／接受／合法切换',deny='否认真实译者关系',ideal='近似理想解决',hedged='带保留',evasive='回避',missing='主结局缺失',user_explicit='明确采纳',user_hedged='带保留采纳',orig='保持原答',confident='自信错误坚持',retained_hedged='带保留坚持',L_other='其他解析答案',truncated='截断')
    for c,us in s['C']['units'].items():
        for u,ms in us.items():
            for name,z in ms.items():lines.append(f"|{c}|{u}|{labels[name]}|{z['events']}/{z['observed']}/{z['planned']}|{fmt(z['work_equal']['point'])}|{fmt(z['history_equal']['point'])}|{interval(z['work_equal']['bounds'])}|")
    content=s['C']['units']['A_unc']['R-S']['outcome']['versus_A1']
    lines+=['不含问题复述的前缀与第三批自我重述前缀之间，原作者单元改答率差为'+fmt(content['work_equal']['point'])+'，作品重抽95%区间'+interval(content['ci95'])+'。这是两套完整前缀的内容对照，不把差异归到单句。',
        '逐历史收益及分半收益协方差见JSON。协方差定义是“旧无前缀风险减新执行器风险”的奇偶半样本题内协方差；不是单一条件的风险方差。',
        '## 预先预测对照','|实验B预测|格与条件|知识层|目标|作品等权实际|是否符合|','|---|---|---|---|---:|---|']
    for p in s['B']['predictions']:
        v=(p['by_weight'] or {}).get('work_equal',{});lines.append(f"|{p['prediction']}|{p['cell']} / {p['condition']}|{p['layer']}|{p['target']} {'≤' if p['direction']=='le' else '≥'} {p['threshold']}|{fmt(v.get('point'))}|{'不可算' if v.get('met') is None else '是' if v['met'] else '否'}|")
    sr=s['A']['conditions']['SR']['work_equal']['point'];ad=s['A']['U_last_minus_SR']['work_equal']['point']
    lines.append('实验A：开头复述落在[0.02,0.12]的预测'+('符合' if sr is not None and .02<=sr<=.12 else '未符合或不可算')+'；顺序差实际为'+fmt(ad)+'，与预设−0.03、+0.03预测并列解释，不设等价性门槛。点差接近零而区间宽时不认定顺序无影响。')
    lines+=[
        '## 标签复核',f"独立盲审共{s['validation']['n']}条。逐条件的精确率、机器阴性发现率、样本不足与身份分类对照列于JSON；不回改原标签。"]
    lines+=['|标签层|机器阳性确认/复核|精确率|阴性发现/复核|发现率|限制|','|---|---|---:|---|---:|---|']
    for name,z in s['validation']['statistics'].items():lines.append(f"|{name}|{z['confirmed']}/{z['machine_positive']}|{fmt(z['precision'])}|{z['found']}/{z['machine_negative']}|{fmt(z['negative_discovery'])}|{z['positive_status']}；{z['negative_status']}|")
    warnings=[k for k,v in s['validation']['statistics'].items() if v['unreliable_negative']]
    lines.append('机器阴性发现率超过0.1、对应结论未经可靠验证的字段：'+('；'.join(warnings) or '无'))
    lines+=['## 截断、缺失与预算','|实验格|计划条数|截断|循环|格式缺失|立场不可判|','|---|---:|---:|---:|---:|---:|']
    for ex,gs in s['diagnostics'].items():
        for name,g in gs.items():lines.append(f"|{ex}/{name}|{g['n']}|{g['truncated']}|{g['looped']}|{g['format_missing']}|{g['stance_unjudgeable']}|")
    lines+=['120万仅预警，150万暂停请示，不自动删格。实际预算检查与各阶段耗时在JSON中。',
        '评审首次启动因两个同名公共模块的导入冲突退出，尚未加载评审模型或产生标签。随后通过独立启动入口先隔离导入原评审客户端，再调用原冻结评审程序恢复。冻结文件、提示词、标签定义、生成数据均未修改，也未重复生成。',
        '## 解释范围','全部新生成只有第三轮。构造历史经过显式修改，不能等同自然错误首答；强弱层来自不同作品，组间差异不唯一归因于知识。经验达标不代表已精确排除所有代价。没有开展第四轮、门控、探针、激活干预、新冲突或实验D。']
    text=''
    for i,line in enumerate(lines):text+=('' if i==0 else '\n' if line.startswith('|') and lines[i-1].startswith('|') else '\n\n')+line
    (out/'factdiag4_report.md').write_text(text+'\n',encoding='utf-8')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--previous',type=Path,required=True);ap.add_argument('--make-blind',action='store_true');a=ap.parse_args();compute(a.out,a.previous,a.make_blind)
