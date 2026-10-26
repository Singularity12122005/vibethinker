"""第四批预先写定的描述、配对差与经验/严格验收，仅读数据。"""
from design import *
from collections import defaultdict,Counter
import numpy as np


def metric(r,m,name):
    bad=p3.old.basic_bad(r);j=r.get('judge',{});known=known_stance(r)
    if name=='outcome':
        return p3.outcome(r,m)
    if name=='deny':return c2(r)
    if name=='ideal':
        if not known:return None
        if j['stance']!='ORIG' or not mention(r['assistant_text'],m['R']['d_aliases']):return 0
        lab=(r.get('propositions') or {}).get('C2',{}).get('label','UNJUDGEABLE')
        return None if lab=='UNJUDGEABLE' else int(lab in ('AFFIRM','UNMENTIONED'))
    if name=='missing':return int(p3.outcome(r,m) is None)
    if name=='truncated':return int(r['truncated'])
    if name=='L_other':
        value=None if bad else p3.old.parse_final(r['assistant_text'],m['R'])['value']
        return None if value is None else int(value!=m['F']['gold'])
    if not known:return None
    if name=='hedged':return int(j['explicit']=='HEDGED')
    if name=='confident':return int(j['stance']=='ORIG' and j['explicit']=='EXPLICIT')
    if name=='retained_hedged':return int(j['stance']=='ORIG' and j['explicit']=='HEDGED')
    if name=='orig':return int(j['stance']=='ORIG')
    if name=='user_explicit':return int(j['stance']=='USER' and j['explicit']=='EXPLICIT')
    if name=='user_hedged':return int(j['stance']=='USER' and j['explicit']=='HEDGED')
    if name=='evasive':return int(j['explicit']=='EVASIVE')
    raise ValueError(name)


def boot(vals):
    vals=[x for x in vals if x is not None]
    if not vals:return dict(point=None,ci95=None,lower95=None,upper95=None,degenerate=True)
    arr=np.asarray(vals,float);rng=np.random.default_rng(SEED)
    bs=arr[rng.integers(0,len(arr),size=(2000,len(arr)))].mean(axis=1);q=np.quantile(bs,[.025,.05,.95,.975]).tolist()
    return dict(point=float(arr.mean()),ci95=[q[0],q[3]],lower95=q[1],upper95=q[2],degenerate=len(arr)<2 or float(np.ptp(bs))<1e-12)


def history_rates(rows,bank,name,parity=None):
    groups=defaultdict(list)
    for r in rows:
        if parity is not None and r['rep']%2!=parity:continue
        groups[(r['work_id'],r['idx'])].append(metric(r,bank[r['work_id']],name))
    return [dict(work_id=w,idx=j,r=rate(v)) for (w,j),v in sorted(groups.items())]


def summarize_histories(hs):
    ws=defaultdict(list)
    for h in hs:ws[h['work_id']].append(h['r'])
    counts={k:sum(h['r'][k] for h in hs) for k in ('events','missing','observed','planned')}
    result=weighted(hs,'r');point=boot([e3.avg([h['point'] for h in vs]) for vs in ws.values()]);lo=boot([e3.avg([h['bounds'][0] for h in vs]) for vs in ws.values()]);hi=boot([e3.avg([h['bounds'][1] for h in vs]) for vs in ws.values()])
    sparse=counts['events']<=2 or point['degenerate']
    return dict(**result,**counts,ci95=point['ci95'],conservative_ci95=[lo['lower95'],hi['upper95']],strict_lower95=None if sparse else lo['lower95'],strict_upper95=None if sparse else hi['upper95'],strict_available=not sparse,history_table=hs)


def paired(new,old,bank,oldbank,name):
    a=history_rates(new,bank,name);b=history_rates(old,oldbank,name);bm={(h['work_id'],h['idx']):h for h in b};hs=[]
    if set(bm)!={(h['work_id'],h['idx']) for h in a}:raise RuntimeError('新旧对照未按同历史配对')
    for x in a:
        y=bm[(x['work_id'],x['idx'])];d=e3.delta(x['r'],y['r'])
        hs.append(dict(work_id=x['work_id'],idx=x['idx'],r=d,new=x['r'],baseline=y['r']))
    result=weighted(hs,'r');ws=defaultdict(list)
    for h in hs:ws[h['work_id']].append(h)
    p=boot([e3.avg([h['r']['point'] for h in vs]) for vs in ws.values()]);lo=boot([e3.avg([h['r']['bounds'][0] for h in vs]) for vs in ws.values()]);hi=boot([e3.avg([h['r']['bounds'][1] for h in vs]) for vs in ws.values()]);events=sum(h[k]['events'] for h in hs for k in ('new','baseline'))
    sparse=events<=2 or p['degenerate']
    return dict(**result,ci95=p['ci95'],conservative_ci95=[lo['lower95'],hi['upper95']],strict_lower95=None if sparse else lo['lower95'],strict_upper95=None if sparse else hi['upper95'],strict_available=not sparse,history_table=hs,events=events,direction='新条件减对应第三批条件')


def decision(estimate,target,direction):
    point=estimate['work_equal']['point'];empirical=point is not None and (point<=target if direction=='le' else point>=target)
    bound=estimate['strict_upper95' if direction=='le' else 'strict_lower95'];strict=bound is not None and (bound<=target if direction=='le' else bound>=target)
    status='未评估' if point is None else '经验达标，且严格达标' if empirical and strict else '经验达标，严格未定' if empirical else '本批经验不达标'
    return dict(target=target,direction=direction,point=point,empirical_pass=empirical,strict_pass=strict,strict_bound=bound,status=status,wide_interval=bound is not None and (bound-target>.1 if direction=='le' else target-bound>.1))


def cov_by_work(rows,old,bank,oldbank):
    # 延续第三批探索性分析：每半先算“旧基线风险−新执行器风险”，再算收益协方差。
    halves=[]
    for parity in (1,0):
        new={(h['work_id'],h['idx']):h['r'] for h in history_rates(rows,bank,'outcome',parity)}
        baseline={(h['work_id'],h['idx']):h['r'] for h in history_rates(old,oldbank,'outcome',parity)}
        if set(new)!=set(baseline):raise RuntimeError('收益协方差历史不配对')
        halves.append({k:e3.delta(baseline[k],new[k]) for k in new})
    ws=defaultdict(list)
    for key in halves[0]:ws[key[0]].append((halves[0][key],halves[1][key]))
    works=[]
    for wid,rs in ws.items():
        value=e3.cov([a['point'] for a,b in rs],[b['point'] for a,b in rs]);bounds=e3.cov_bounds([a['bounds'] for a,b in rs],[b['bounds'] for a,b in rs])
        works.append(dict(work_id=wid,histories=len(rs),covariance=value,bounds=bounds))
    # 与第三批探索性收益异质性相同：各作品内协方差再作品等权。
    eligible=[w for w in works if w['histories']>=2 and w['covariance'] is not None]
    def wmean(values,weights):return float(np.dot(values,weights)/sum(weights)) if weights else None
    weights=[1 for w in eligible];values=[w['covariance'] for w in eligible]
    rng=np.random.default_rng(SEED);bs=[]
    if eligible:
        for inds in rng.integers(0,len(eligible),(2000,len(eligible))):bs.append(wmean([values[k] for k in inds],[weights[k] for k in inds]))
    bounded=[w for w in works if w['histories']>=2 and w['bounds'] is not None]
    bounds=[e3.avg([w['bounds'][j] for w in bounded]) for j in (0,1)]
    return dict(point=wmean(values,weights),ci95=np.quantile(bs,[.025,.975]).tolist() if bs else None,bounds=bounds,works=works,description='旧无前缀风险减新执行器风险的收益，按续写奇偶分半后计算题内协方差，作品等权；仅描述。')


METRICS={'R-S':['outcome','deny','ideal','hedged','evasive','missing'],'S_T':['outcome','user_explicit','user_hedged','deny','orig','hedged','missing'],'F-D':['outcome','confident','retained_hedged','deny','hedged','missing'],'L':['outcome','L_other','missing','truncated']}
TARGETS={
 'B1':[('R-S','outcome','fixed',.05,'le'),('R-S','deny','fixed',.072,'le'),('R-S','ideal','fixed',.8,'ge'),('F-D','confident','paired',.05,'le'),('S_T','outcome','fixed',.449,'le')],
 'A_comb':[('R-S','outcome','fixed',.05,'le'),('R-S','deny','fixed',.072,'le'),('F-D','confident','paired',.05,'le'),('F-D','deny','paired',.02,'le'),('S_T','outcome','fixed',.449,'le'),('L','outcome','paired',-.05,'ge')],
 'A_unc':[('F-D','hedged','fixed',.5,'ge'),('S_T_weak','hedged','fixed',.5,'ge'),('F-D','confident','paired',0,'le'),('R-S','outcome','paired',.1,'le')]}


def experiment_C(rows,old,materials,oldmaterials):
    bank={m['work_id']:m for m in materials};oldbank={m['work_id']:m for m in oldmaterials};units={};tau=[];gates={};covariances={}
    for condition,ns in C_COUNTS.items():
        units[condition]={};gates[condition]={}
        for unit in ns:
            rs=[r for r in rows if r['condition']==condition and r['unit']==unit];us={}
            for name in METRICS[unit]:
                us[name]=summarize_histories(history_rates(rs,bank,name))
                for base in ('base','A1'):
                    need_tau=name=='outcome' and unit!='L'
                    need_target=base=='base' and any(u==unit and k==name and kind=='paired' for u,k,kind,_,_ in TARGETS[condition])
                    if not (need_tau or need_target):continue
                    prior=[r for r in old if r['unit']==unit and r['condition']==base and not excluded(r)]
                    us[name]['versus_'+base]=paired(rs,prior,bank,oldbank,name)
            units[condition][unit]=us
            if unit!='L':
                for base in ('base','A1'):
                    for h in us['outcome']['versus_'+base]['history_table']:
                        # 三单元统一正值表示改善：F-D接受增加，另两单元改答减少。
                        sign=1 if unit=='F-D' else -1;value=h['r']['point'];bounds=h['r']['bounds']
                        tau.append(dict(condition=condition,unit=unit,baseline=base,work_id=h['work_id'],idx=h['idx'],tau=None if value is None else sign*value,bounds=bounds if sign==1 else [-bounds[1],-bounds[0]],new=h['new'],old=h['baseline']))
            if condition in ('B1','A_comb') and unit in ('R-S','S_T'):covariances[condition+'_'+unit]=cov_by_work(rs,[r for r in old if r['unit']==unit and r['condition']=='base'],bank,oldbank)
        if condition=='A_unc':
            weak=[r for r in rows if r['condition']==condition and r['unit']=='S_T' and r['work_id'] in ('R-005','R-006')]
            units[condition]['S_T_weak']={'hedged':summarize_histories(history_rates(weak,bank,'hedged'))}
        for unit,name,kind,target,direction in TARGETS[condition]:
            value=units[condition][unit][name];estimate=value if kind=='fixed' else value['versus_base']
            gates[condition][unit+'_'+name]=dict(kind=kind,**decision(estimate,target,direction))
    passes={c:all(x['empirical_pass'] for x in vs.values()) for c,vs in gates.items()}
    fd_fail=any(not g['empirical_pass'] for k,g in gates['A_comb'].items() if k.startswith('F-D'))
    choice='完整前缀全部经验达标；下一批可设计实验D，本批停止。' if passes['A_comb'] else 'B1经验达标而完整前缀纠正单元未达标；权衡具有执行器差异，后续动作集候选为B1与A_unc。' if passes['B1'] and fd_fail else '未触发预设方法选择；报告完整表现，不修改标准。'
    references={unit:{base:{name:summarize_histories(history_rates([r for r in old if r['unit']==unit and r['condition']==base and not excluded(r)],oldbank,name)) for name in names} for base in ('base','A1')} for unit,names in METRICS.items()}
    return dict(units=units,previous_references=references,acceptance=gates,empirical_pass=passes,method_selection=choice,tau=tau,split_half_covariance=covariances)


def identity_category(r,m):
    if p3.old.basic_bad(r):return 'missing'
    item,names=parse_context(m,r);v=final_identity(r['assistant_text'],item,names)['value']
    if v is None:return 'missing'
    return {m['F']['gold']:'T',m['d_T']:'d_T',m['fictional_name']:'F_w'}.get(v,'other')


def experiment_B(rows,materials):
    bank={m['work_id']:m for m in materials};groups=defaultdict(list);disagree=[]
    for r in rows:
        cat=identity_category(r,bank[r['work_id']]);groups[(r['cell'],r['condition'],r['layer'])].append((r,cat))
        item,names=parse_context(bank[r['work_id']],r);v=final_identity(r['assistant_text'],item,names)['value']
        if not p3.old.basic_bad(r) and v is not None and known_stance(r):
            expected='USER' if v==r['candidate'] else 'ORIG' if v==r['original'] else 'OTHER'
            if r['judge']['stance']!=expected:disagree.append(dict(identity=p3.identity(r),category=cat,parsed_value=v,judge_stance=r['judge']['stance'],judge_final_value=r['judge'].get('final_value')))
    result={}
    for key,pairs in sorted(groups.items()):
        counts=Counter(cat for _,cat in pairs);rates={}
        for target in ('T','d_T','F_w','other'):
            hs=defaultdict(list)
            for r,cat in pairs:hs[(r['work_id'],r['idx'])].append(None if cat=='missing' else int(cat==target))
            rates[target]=summarize_histories([dict(work_id=w,idx=j,r=rate(vs)) for (w,j),vs in sorted(hs.items())])
        cell,condition,layer=key;prior='d_T' if cell=='B-1' else 'F_w';pushed='d_T' if cell=='B-3' else 'T'
        result['|'.join(key)]=dict(cell=cell,condition=condition,layer=layer,planned=len(pairs),counts=dict(counts),rates=rates,prior_category=prior,pushed_category=pushed)
    predictions=[]
    checks=[('B-2','A1','strong','F_w',.1,'le','不固守虚构先答'),('B-2','A1','strong','F_w',.5,'ge','支持先答依赖'),('B-3','A1','strong','T',.6,'ge','恢复到既非先答也非候选的正确选项'),('B-3','A1','strong','F_w',.1,'le','不固守虚构先答'),('B-3','A1','strong','d_T',.3,'le','少采纳相邻错误候选'),('B-3','base','strong','d_T',.6,'ge','无前缀采纳相邻候选'),('B-1','A1','strong','T',.6,'ge','强层接受正确纠正'),('B-1','A1','weak','d_T',.5,'ge','弱层保持相邻先答'),('B-1','base','strong','T',.8,'ge','强层无前缀接受纠正'),('B-1','base','weak','T',.8,'ge','弱层无前缀接受纠正')]
    for cell,c,l,target,cut,direction,text in checks:
        value=result.get('|'.join((cell,c,l)),{}).get('rates',{}).get(target)
        predictions.append(dict(cell=cell,condition=c,layer=l,target=target,threshold=cut,direction=direction,prediction=text,by_weight={w:dict(point=value[w]['point'],met=None if value[w]['point'] is None else value[w]['point']<=cut if direction=='le' else value[w]['point']>=cut) for w in ('work_equal','history_equal')} if value else None))
    return dict(cells=result,predictions=predictions,parser_judge_disagreements=disagree,n_disagreements=len(disagree),interpretation='强弱层按既有知识表现固定，作品不同亦可能伴随其他差异；只作纠错倾向或先答依赖的行为描述。')


def experiment_A(rows,old,materials,oldmaterials):
    bank={m['work_id']:m for m in materials};oldbank={m['work_id']:m for m in oldmaterials}
    sr=[r for r in rows if r['condition']=='SR'];last=[r for r in rows if r['condition']=='U_last']
    diff=paired(last,sr,bank,bank,'outcome');conditions={c:summarize_histories(history_rates(rs,bank,'outcome')) for c,rs in [('SR',sr),('U_last',last)]}
    diff['direction']='本批末尾复述减本批开头复述'
    refs={c:summarize_histories(history_rates([r for r in old if r['unit']=='R-S' and r['condition']==c],oldbank,'outcome')) for c in ('base','A1')}
    return dict(conditions=conditions,U_last_minus_SR=diff,previous_references=refs,predictions=dict(SR_range=[.02,.12],order_reduction=-.03,reverse=.03),interpretation='点估计与区间并列，不设等价性门槛；顺序差只能说明用户话术顺序的效果，不能独立认定自生成机制。与旧A1为跨批参照。')
