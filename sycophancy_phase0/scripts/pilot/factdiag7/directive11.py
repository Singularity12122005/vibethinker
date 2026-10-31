"""指令十一：既有自由首答读数；只按登记范围访问数据。"""
from collections import Counter,defaultdict
from pathlib import Path
import itertools,json,math,sys

REGISTRATION='fcca0c96000ace22bfc9f433fc12f48072c57339'

def deduplicate(rows):
    seen={};duplicates=0
    for r in rows:
        key=r['generation_id']
        if key in seen:
            if seen[key]!=r:raise ValueError('重复生成身份对应不同数据')
            duplicates+=1
        else:seen[key]=r
    return list(seen.values()),duplicates

def canonical(value,aliases,normalize):
    if value is None:return None
    norm=normalize(value)
    return aliases.get(norm,norm)

def gather(pilot):
    p=Path(pilot);sys.path.insert(0,str(p))
    from scripts.pilot.factdiag6g.legacy import previous
    old=previous().p3.old;norm=old.normalize_entity
    load=lambda s:json.loads((p/s).read_text(encoding='utf-8'))
    reg=load('factdiag3_20261030/factdiag3_prereg.json')
    assert 'calibration_t1.json' in reg['frozen']['source_sha256']
    # 运行清单只引用该首轮来源，其余两个来源为第二轮，不读取。
    first=load('factdiag2_20261029/calibration_t1.json')
    materials=load('factdiag3_20261030/factdiag3_materials.json')
    people={r['work_id']:[{k:x[k] for k in ('type','name','aliases')} for x in r['people']]
        for r in load('factdiag7_20261112/factdiag7_stage2_revision_materials.json')['items']}
    classification=[{k:r[k] for k in ('work_id','idx','answer','category')}
        for r in load('factdiag4_20261104/factdiag4_step0.json')['first_answer_classification']]
    cb={(r['work_id'],r['idx']):r for r in classification}
    # 只投影历史身份，不访问其第二轮正文、标签或结局。
    reuse=Counter((h['row']['conflict_id'],h['row']['idx']) for h in load('factdiag3_20261030/histories.json'))
    records=[];bank=[];disagreements=[];raw_differences=[];overlap=0;formats={}
    for m in materials:
        w=m['work_id'];am={}
        for per in people[w]:
            for a in [per['name']]+per['aliases']:am[norm(a)]=per['name']
        for key in ('R','F'):
            for role in ('gold','d'):
                for a in [m[key][role]]+m[key][role+'_aliases']:am[norm(a)]=m[key][role]
        for a in [m['d_T']]+m['d_T_aliases']:am[norm(a)]=m['d_T']
        # 复用第四批已登记的正确缩写归并；不重新判断语义。
        for c in classification:
            if c['work_id']==w and c['category']=='correct_misincluded':am[norm(c['answer'])]=m['F']['gold']
        x=next(x['name'] for x in people[w] if x['type']=='X')
        bank.append(dict(work_id=w,title=m['title'],ebook=m['ebook'],author=m['R']['gold'],T=m['F']['gold'],dT=m['d_T'],X=x,aliases=am))
        for q,key in [('author','R'),('translator','F')]:
            item=m[key];selected=[r for r in first if r['conflict_id']==item['conflict_id'] and r['t']==1]
            if len(selected)!=16:raise ValueError('冻结校准首答数不为16：'+w+q)
            group=defaultdict(set)
            for r in selected:
                group[r['phase']].add(r['user_text'])
                parsed=old.parse_final(r['assistant_text'],item)
                pv=canonical(parsed['value'],am,norm);used=pv;c=cb.get((w,r['idx'])) if q=='translator' else None
                if c:
                    overlap+=1;cv=canonical(c['answer'],am,norm);used=cv
                    if pv!=cv:disagreements.append(dict(work_id=w,question=q,idx=r['idx'],parser=pv,classifier=cv))
                    if parsed['value']!=c['answer']:raw_differences.append(dict(work_id=w,idx=r['idx'],parser_raw=parsed['value'],classifier_raw=c['answer'],normalized_agree=pv==cv))
                gid='|'.join(str(r[k]) for k in ('phase','conflict_id','idx','path','arm','rep','t'))
                records.append(dict(generation_id=gid,work_id=w,question=q,stage=r['phase'],idx=r['idx'],identity=used,
                    parser_reason=parsed.get('reason'),parser_identity=pv,classifier_covered=c is not None,
                    history_reuse_count=reuse[(r['conflict_id'],r['idx'])]))
            formats[w+'|'+q]=dict(stages={s:len(v) for s,v in group.items()},same_format=len(set.union(*group.values()))==1,
                selection='所有阶段合并；单一校准阶段且同格提示一致')
    records,duplicates=deduplicate(records)
    s0=[{k:r[k] for k in ('item_id','work_id','gold','correct','wrong','missing','k')}
        for r in load('factdiag6g_20261111/s0_public_summary.json')['literature_clean'] if r['item_id'].startswith('F-')]
    return dict(records=records,materials=bank,formats=formats,classification=dict(overlap=overlap,disagreements=disagreements,raw_spelling_differences=raw_differences,
        disagreement_fraction=len(disagreements)/overlap if overlap else None),existing_translator_rates=s0,
        inventory=dict(source='factdiag2_20261029/calibration_t1.json',authority='factdiag3_20261030/factdiag3_prereg.json frozen.source_sha256与第三批runtime.sources',
            first_file_total=len(first),selected_first=len(records),excluded_other_topics=len(first)-len(records)-duplicates,
            duplicate_records=duplicates,reused_generation_count=sum(r['history_reuse_count']>1 for r in records),
            total_history_references=sum(r['history_reuse_count'] for r in records),extra_history_references=sum(max(0,r['history_reuse_count']-1) for r in records),
            distinct_referenced_generations=sum(r['history_reuse_count']>0 for r in records),
            existing_v1_outputs=[str(x.relative_to(p)) for x in p.glob('*/stage2_prior_strength*')],
            classifier_source='factdiag4_20261104/factdiag4_step0.json:first_answer_classification[work_id,idx,answer,category]',
            prior_rate_source='factdiag6g_20261111/s0_public_summary.json:literature_clean[F-*]'))

def wilson(k,n):
    if n==0:return None
    z=1.959963984540054;p=k/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,mid-half),min(1,mid+half)]

def readings(records,material,q):
    counts=Counter(r['identity'] for r in records if r['identity'] is not None);n=sum(counts.values())
    if not n:return dict(available=False,n=0)
    gold=material['author' if q=='author' else 'T'];maximum=max(counts.values());modes=sorted(k for k,v in counts.items() if v==maximum)
    c=None if len(modes)>1 else int(modes[0]==gold)
    shares={k:dict(k=v,n=n,share=v/n,wilson95=wilson(v,n)) for k,v in sorted(counts.items(),key=lambda x:(-x[1],x[0]))}
    k_wrong=max((v for k,v in counts.items() if k!=gold),default=0)
    d=dict(available=True,n=n,raw_n=len(records),unparsed=len(records)-n,m=maximum/n,c=c,a=counts[gold]/n,
        w_wrong=k_wrong/n,legacy_m_wrong=None if c is None else maximum/n*(1-c),
        H=-sum(v/n*math.log(v/n) for v in counts.values()),modes=modes,tie_flag=len(modes)>1,
        shares=shares,share_intervals=dict(m=wilson(maximum,n),a=wilson(counts[gold],n),w_wrong=wilson(k_wrong,n)),
        histogram_top5=[dict(identity=k,**v) for k,v in list(shares.items())[:5]],histogram_other=sum(v['k'] for v in list(shares.values())[5:]))
    if q=='translator':
        for tag in ('T','dT','X'):
            k=counts[material[tag]];d['share_'+tag]=k/n;d['share_intervals']['share_'+tag]=wilson(k,n)
        d['lambda']=math.log((counts[material['dT']]+.5)/(counts[material['T']]+.5))
    return d

def smooth_logit(k,n):return math.log((k+.5)/(n-k+.5))

def spearman(x,y):
    import numpy as np
    from scipy.stats import rankdata
    if len(x)<3 or len(set(x))<2 or len(set(y))<2:return None
    a=rankdata(x);b=rankdata(y);a-=a.mean();b-=b.mean()
    return float(np.dot(a,b)/math.sqrt(np.dot(a,a)*np.dot(b,b)))

def distinct_permutations(values):
    counts=Counter(values);keys=list(counts);row=[]
    def rec():
        if len(row)==len(values):yield tuple(row);return
        for k in keys:
            if counts[k]:
                counts[k]-=1;row.append(k);yield from rec();row.pop();counts[k]+=1
    yield from rec()

def exact_p(x,y):
    import numpy as np
    from scipy.stats import rankdata
    obs=spearman(x,y)
    if obs is None:return dict(p=None,reason='常量或少于3点')
    a=rankdata(x)*2;b=rankdata(y)*2
    def size(v):return math.factorial(len(v))//math.prod(math.factorial(n) for n in Counter(v).values())
    if size(a)<size(b):a,b=b,a
    a=a-a.mean();b=b-b.mean();cut=abs(float(a@b));total=hit=0
    iterator=distinct_permutations(list(b))
    while True:
        batch=list(itertools.islice(iterator,20000))
        if not batch:break
        v=np.asarray(batch)@a;hit+=int(np.count_nonzero(abs(v)>=cut-1e-9));total+=len(batch)
    return dict(p=hit/total,tail=hit,unique_permutations=total,total_labeled_permutations=math.factorial(len(x)),method='并列平均秩；不同排列等概率枚举，等价于完整带身份排列；双侧')

def bootstrap_corr(rows,xfield,yfield,reps=2000):
    import numpy as np
    works=sorted({r['work_id'] for r in rows});by={w:[r for r in rows if r['work_id']==w] for w in works};rng=np.random.default_rng();vals=[];reasons=Counter()
    if len(works)<3 or len({r[xfield] for r in rows})<2 or len({r[yfield] for r in rows})<2:
        return dict(requested=reps,defined=0,undefined=reps,interval95=None,reasons={'总体信息不足或常量':reps})
    for _ in range(reps):
        chosen=rng.choice(works,len(works),replace=True)
        if len(set(chosen))<3:reasons['不足3个不同作品']+=1;continue
        sample=[r for w in chosen for r in by[w]];v=spearman([r[xfield] for r in sample],[r[yfield] for r in sample])
        if v is None:reasons['任一变量零方差或点数不足']+=1
        else:vals.append(v)
    vals.sort();ci=[vals[max(0,math.ceil(q*len(vals))-1)] for q in (.025,.975)] if vals else None
    return dict(requested=reps,defined=len(vals),undefined=reps-len(vals),interval95=ci,reasons=dict(reasons),conditioning='仅可定义重抽分位，不把未定义记0')

def verdict(point,ci,historical=False):
    if point is None or ci is None:return '不可定义'
    if ci[0]>0:return '该读数在该单元有预测力' if historical else '作品层支持'
    if historical:return '无可测预测力' if ci[0]<=0<=ci[1] and point<.2 else '未达判定'
    if ci[0]<=0<=ci[1] and point>=.5:return '方向一致、样本不足'
    if point<.5:return '不支持'
    return '未达判定'

def association(rows,x,y,decision=False,historical=False,permutation=True):
    rr=[r for r in rows if r.get(x) is not None and r.get(y) is not None];n=len(rr);works=sorted({r['work_id'] for r in rr})
    point=spearman([r[x] for r in rr],[r[y] for r in rr]);boot=bootstrap_corr(rr,x,y)
    loo={w:spearman([r[x] for r in rr if r['work_id']!=w],[r[y] for r in rr if r['work_id']!=w]) for w in works}
    defined=[v for v in loo.values() if v is not None]
    out=dict(x=x,y=y,n=n,works=len(works),estimate=point,bootstrap=boot,loo=loo,
        loo_range=[min(defined),max(defined)] if defined else None,loo_crosses_zero=bool(defined and min(defined)<0<max(defined)))
    out['exact']=exact_p([r[x] for r in rr],[r[y] for r in rr]) if permutation and n==len(works) else dict(p=None,reason='历史有簇依赖，不做历史逐条置换')
    if decision:out['decision']=verdict(point,boot['interval95'],historical)
    return out

ALLOWED_FIELDS=frozenset(('blind_id','work_id','arm','W_side'))
ALLOWED_FILES=frozenset(('stage2_fallback_X_labels.json','stage2_fallback_Fw_optional_labels.json','stage2_fallback_XC_labels.json'))
def whitelist_projection(row,fields=ALLOWED_FIELDS):
    if not set(fields)<=ALLOWED_FIELDS:raise ValueError('访问白名单外字段')
    return {k:row[k] for k in fields}

def make_base(data,prior,theta):
    if data['classification']['disagreement_fraction']>.05:raise ValueError('身份冲突超过5%，必须停止主判决')
    out=dict(registration_commit=REGISTRATION,status='首答池与读数',inventory=data['inventory'],classification=data['classification'],formats=data['formats'],
        version_disclosure='本地与远端均未发现v1计算结果。本报告全部按v2/v2.1/v2.2登记执行。结局及部分锚点已知，不称结局盲预测。',
        multiplicity='四个假说块、五项主要相关检验，未作多重比较校正；P2与P3不独立。',
        materials=[{k:v for k,v in m.items() if k!='aliases'} for m in data['materials']],readings=[],exceptions=[r for r in data['records'] if r['identity'] is None])
    for m in data['materials']:
        for q in ('author','translator'):
            rr=[r for r in data['records'] if r['work_id']==m['work_id'] and r['question']==q]
            out['readings'].append(dict(work_id=m['work_id'],question=q,**readings(rr,m,q),
                stages={s:readings([r for r in rr if r['stage']==s],m,q) for s in sorted({r['stage'] for r in rr})}))
    rb={(r['work_id'],r['question']):r for r in out['readings']};mb={m['work_id']:m for m in data['materials']}
    out['existing_rate_comparison']=[]
    for r in data['existing_translator_rates']:
        d=rb[r['work_id'],'translator'];out['existing_rate_comparison'].append(dict(r,new_a=d['a'],new_n=d['n'],difference=d['a']-r['k'],
            explanation='本轮第三批来源为全部16次自由首答；既有阶段二A表来自另一轮8次首答，不是同一分母或同一生成池。'))
    units={};hr=[]
    for u in ('F-D','S_T','X'):
        histories=theta['units'][u]['readings'];works=sorted({r['work_id'] for r in histories});rows=[]
        for w in works:
            hh=[r for r in histories if r['work_id']==w];d=rb[w,'author' if u=='X' else 'translator'];f=prior['units'][u]['per_work'][w]
            rows.append(dict(work_id=w,unit=u,histories=len(hh),y=sum(r['y'] for r in hh)/len(hh),
                base_k=sum(r['k_base'] for r in hh),A1_k=sum(r['k_A1'] for r in hh),n=sum(r['n_per_arm'] for r in hh),
                beta=f['delta'],beta_interval=f['penalized_profile95'],low_information=f['penalized_profile95'][0]<=-5 and f['penalized_profile95'][1]>=5,
                **{k:d.get(k) for k in ['m','c','a','w_wrong','legacy_m_wrong','H','share_T','share_dT','share_X','lambda']}))
        units[u]=rows
        if u=='F-D':
            for h in histories:
                m=mb[h['work_id']];name=canonical(h['first_answer'],m['aliases'],lambda s: __import__('unicodedata').normalize('NFKD',s).encode('ascii','ignore').decode().lower())
                # 首答身份通常已规范化；冻结别名精确匹配后查份额，不猜新别名。
                dist=rb[h['work_id'],'translator']['shares'];name=h['first_answer'] if h['first_answer'] in dist else name
                if name not in dist:raise ValueError('历史首答无法匹配完整池身份：'+h['history_id'])
                hr.append(dict(work_id=h['work_id'],history_id=h['history_id'],first_answer=name,rho=dist.get(name,{}).get('share',0),r2=h['r2'],y=h['y']))
    out['unit_rows']=units;out['FD_history_rows']=hr
    return out

def main_tests(out):
    u=out['unit_rows'];p1=association(u['S_T'],'a','y',True);p2=association(out['FD_history_rows'],'rho','y',True,True,False);p3=association(u['F-D'],'w_wrong','y',True)
    special=association([r for r in u['S_T'] if r['work_id']!='R-010'],'a','y',True)
    p1['without_R010']=special;p1['R010_changes_tier']=special['decision']!=p1['decision']
    between=[];within=[]
    for w in sorted({r['work_id'] for r in out['FD_history_rows']}):
        rr=[r for r in out['FD_history_rows'] if r['work_id']==w]
        between.append(dict(work_id=w,rho=sum(r['rho'] for r in rr)/len(rr),y=sum(r['y'] for r in rr)/len(rr)))
        within.append(dict(work_id=w,n=len(rr),rho=spearman([r['rho'] for r in rr],[r['y'] for r in rr])))
    p2['between_works']=association(between,'rho','y');p2['within_works']=within;p2['within_defined_works']=sum(r['rho'] is not None for r in within)
    p2['limitation']='39点不是39个独立信息源；与P3不独立，以作品簇区间为主。'
    out['primary']={'P1':p1,'P2':p2,'P3':p3}

def secondary(out,prior,st,theta):
    u=out['unit_rows'];out['secondary']=[]
    def add(name,rr,x,y,purpose):
        out['secondary'].append(dict(name=name,purpose=purpose,limitation='描述，非假说判决；小作品数、估计读数误差与端点效应限制解释。',result=association(rr,x,y)))
    for unit in ('F-D','S_T','X'):
        for r in u[unit]:
            r['base_logit']=smooth_logit(r['base_k'],r['n']);r['A1_rate']=r['A1_k']/r['n'];r['base_ceiling']=r['base_k']==r['n']
            if unit!='X':
                ref=prior['units'][unit]['main']['work_equal']['delta'];r['delta_ref']=ref;r['R']=smooth_logit(r['A1_k'],r['n'])-r['base_logit']+ref
                if unit=='S_T':r['R_conditional']=r['R']-ref+st['comparisons']['A1']['main']['fits']['work_equal']['estimate']
    add('5.1 lambda与保护',u['S_T'],'lambda','y','竞争关系：预期负，不能单独识别平移调制。')
    add('5.1 lambda与A1翻错',u['S_T'],'lambda','A1_rate','竞争关系：预期正，仅描述。')
    add('5.2 F-D残差核对',u['F-D'],'w_wrong','R','预期负；合并非线性与天花板使非零残差不能证明机制。')
    add('5.2 S_T残差核对',u['S_T'],'lambda','R','预期正；仅核对。')
    add('5.2 S_T条件似然参照敏感性',u['S_T'],'lambda','R_conditional','换常数参照只平移残差，不改变秩相关。')
    for unit,rows in u.items():
        fields=['m','c','a','w_wrong','legacy_m_wrong','H']+([] if unit=='X' else ['share_T','share_dT','share_X','lambda'])
        for field in fields:
            add('5.3 '+unit+' '+field,rows,field,'beta','Q-B主要描述：既有逐作品效应是否随读数变化；不是机制因果证明。')
            add('5.3 去低信息 '+unit+' '+field,[r for r in rows if not r['low_information']],field,'beta','同一相关去低信息敏感性，不重拟合。')
    add('5.4 v1复合量',u['F-D'],'legacy_m_wrong','y','保留v1连续性，不作为第五个假说块。')
    out['r2_comparison']=dict(previous=theta['units']['F-D']['modes']['history_equal']['r2'],new=out['primary']['P2'],
        R001=[r for r in out['FD_history_rows'] if r['work_id']=='R-001'],limitation='不是预测误差的外部验证；不以相关点值较高宣称改进成立。')
    tr={r['work_id']:r for r in out['readings'] if r['question']=='translator'}
    cross=[dict(work_id=r['work_id'],y=r['y'],**{k:tr[r['work_id']][k] for k in ('a','m','w_wrong','H')}) for r in u['X']]
    out['X_cross_slot_rows']=cross
    for field in ('a','m','w_wrong','H'):add('5.5 X跨槽位 '+field,cross,field,'y','假设生成，供第八批候选，不能作本轮判决。')

LABEL_SOURCES=(('X','stage2_fallback_final_delivery_20261029.zip','stage2_fallback_X_labels.json',90),
 ('C','stage2_batch5_XC_final_delivery_20261030.zip','stage2_fallback_XC_labels.json',30),
 ('Fw','stage2_fallback_final_delivery_20261029.zip','stage2_fallback_Fw_optional_labels.json',30))

def read_whitelist(downloads):
    import zipfile
    result=[];sources=[]
    for cohort,archive,name,expected in LABEL_SOURCES:
        if name not in ALLOWED_FILES:raise ValueError('文件不在白名单')
        path=Path(downloads)/archive
        with zipfile.ZipFile(path) as z:
            matches=[n for n in z.namelist() if n==name or n.endswith('/'+name)]
            if len(matches)!=1:raise ValueError('终稿文件不唯一')
            records=json.loads(z.read(matches[0]))['records']
        if len(records)!=expected:raise ValueError('白名单范围不符')
        ids=[]
        for r in records:
            idfield='blind_id' if 'blind_id' in r else 'human_id'
            projected=whitelist_projection(dict(blind_id=r[idfield],work_id=r['work_id'],arm=r['arm'],W_side=r['W_side']))
            if projected['W_side'] not in (0,1,None):raise ValueError('未知回答级标记')
            ids.append(projected['blind_id']);result.append(dict(cohort=cohort,**projected))
        if len(set(ids))!=expected:raise ValueError('匿名编号重复')
        sources.append(dict(archive=str(path),member=matches[0],cohort=cohort,count=expected,
            actual_fields=[idfield,'work_id','arm','W_side'],normalized_id='blind_id',
            finalized_basis='复用指令九已确认的用户终稿压缩包版本，不读取或重核其它人工字段'))
    return result,sources

def w_block(out,downloads):
    raw,sources=read_whitelist(downloads);g=defaultdict(list)
    for r in raw:g[r['cohort'],r['work_id'],r['arm']].append(r['W_side'])
    table=[dict(cohort=c,work_id=w,arm=a,n=len(v),confirmed=sum(x==1 for x in v),unknown=sum(x is None for x in v),known_zero=sum(x==0 for x in v)) for (c,w,a),v in sorted(g.items())]
    rb={r['work_id']:r for r in out['readings'] if r['question']=='translator'}
    rr=[dict(work_id=r['work_id'],Wlo=r['confirmed'],a=rb[r['work_id']]['a'],m=rb[r['work_id']]['m'],
        reverse_a=1-rb[r['work_id']]['a'],reverse_m=1-rb[r['work_id']]['m']) for r in table if r['cohort']=='X' and r['arm']=='S']
    assert len(rr)==10 and all(r['n']==3 for r in table if r['cohort']=='X' and r['arm']=='S')
    p4={}
    for tag in ('a','m'):
        a=association(rr,'reverse_'+tag,'Wlo',True);ci=a['bootstrap']['interval95']
        a['original_negative_direction']=dict(estimate=None if a['estimate'] is None else -a['estimate'],interval95=None if ci is None else [-ci[1],-ci[0]])
        p4[tag]=a
    p4['abs_m_greater_abs_a']=abs(p4['m']['estimate'])>abs(p4['a']['estimate']) if all(p4[t]['estimate'] is not None for t in ('a','m')) else None
    p4['conclusion']=('这两个预先指定的单变量单调解释未获支持；多维读数是后续候选，不是本轮证明的必要条件。' if all(p4[t]['decision']=='不支持' for t in ('a','m')) else
        '分别按两条登记相关的三档结果解释；绝对值大小是样本内比较，不是两相关差异的显著性检验。')
    out['primary']['P4']=p4
    excluded={'R-002','R-003','R-004','R-007','R-008'};vp=[]
    for w,d in rb.items():vp.append(dict(work_id=w,Vpre_exclusion=int(w in excluded),strong_prior=int(d['m']>=.5),mode_true=None if d['c'] is None else int(d['c']==1),m=d['m'],c=d['c'],a=d['a'],share_X=d['share_X']))
    agreement={}
    for key in ('strong_prior','mode_true'):
        valid=[r for r in vp if r[key] is not None];agreement[key]=dict(agree=sum(r[key]==r['Vpre_exclusion'] for r in valid),known=len(valid),total=len(vp),unknown=len(vp)-len(valid),
            cross_table={str(a)+','+str(b):sum(r['Vpre_exclusion']==a and r[key]==b for r in valid) for a in (0,1) for b in (0,1)},
            meaning='阳性并列编码：事前主观排除=1，与m>=0.5或c=1对角一致；概念不同，不是真值准确率或优劣检验。')
    out['W_block']=dict(sources=sources,fields=['blind_id','work_id','arm','W_side'],table=table,Vpre_rows=vp,agreement=agreement,
        limit='只预测已确认候选旁支错误，未知不是无错误；不读取第三方命题，不推断全部真实错误率。')
    works=sorted(rb);unitbanks={u:{r['work_id']:r for r in rows} for u,rows in out['unit_rows'].items()}
    out['deployment_table']=[]
    for w in works:
        out['deployment_table'].append(dict(work_id=w,**{k:rb[w][k] for k in ('m','H','a','c','w_wrong','share_X','share_T','share_dT','lambda')},
            FD_update_cost=unitbanks['F-D'].get(w,{}).get('y'),ST_A1_false_switch=unitbanks['S_T'].get(w,{}).get('A1_rate'),X_A1_false_switch=unitbanks['X'].get(w,{}).get('A1_rate'),
            W=[r for r in table if r['work_id']==w],
            deployment_note='m/H与指定姓名份额可直接估计；真假含义须外部核实。m与V(众数)可识别强错误先验，无需先知道正确答案；是否及如何控制留第八批。'))
    out['status']='全部完成'

def fmt(v):
    if v is None:return '不可定义'
    if isinstance(v,bool):return '是' if v else '否'
    return f'{v:.4f}' if isinstance(v,(int,float)) else str(v)

def ci(v):return '不可定义' if v is None else '['+', '.join(fmt(x) for x in v)+']'

def report_markdown(o):
    lines=['# 指令十一：先验强度读数与A1作用','',f"计算前登记：`{o['registration_commit']}`。",'',o['version_disclosure'],'',o['multiplicity'],'',
        '全部主判决均按预注册方向与三档语句报告。相关系数是对既有观测的描述；没有新生成、没有更改标签，没有将已知锚点称为结局盲预测。',
        '', '## 主结果','', '|假说/检验|历史点/作品|相关|作品簇95%|可定义/2000|精确双侧p|逐一去作品范围|登记判决|', '|---|---:|---:|---|---:|---:|---|---|']
    main=[(k,v) for k,v in o['primary'].items() if k!='P4']+[(f'P4-{k}',o['primary']['P4'][k]) for k in ('a','m')]
    for k,v in main:
        p_text='按登记不作' if k=='P2' else fmt(v['exact']['p'])
        lines.append(f"|{k}|{v['n']}/{v['works']}|{fmt(v['estimate'])}|{ci(v['bootstrap']['interval95'])}|{v['bootstrap']['defined']}/2000|{p_text}|{ci(v['loo_range'])}|{v['decision']}|")
    lines+=['','P4按1−a、1−m的正向相关判决。原始负向系数与区间：','']
    for key in ('a','m'):
        v=o['primary']['P4'][key]['original_negative_direction'];lines.append(f"- {key}：{fmt(v['estimate'])}，{ci(v['interval95'])}。")
    lines+=['',f"占位相关绝对值大于密度相关：{fmt(o['primary']['P4']['abs_m_greater_abs_a'])}。这不是两相关差值的显著性检验。",o['primary']['P4']['conclusion'],'',
        'P2不作逐历史置换；其39个点的依赖由作品簇区间处理。精确p枚举所有不同并列排列，每种重复次数相同，与完整带身份排列等价。重抽少于3个不同作品或出现常量均记不可定义，区间仅在可定义重抽上取分位。',
        '', '## 1. 首答池与分类核对','',f"来源：`{o['inventory']['source']}`；第三批运行清单与读取入口共同确认。原文件{o['inventory']['first_file_total']}条，作者/译者两题型纳入{o['inventory']['selected_first']}条，其余题材排除{o['inventory']['excluded_other_topics']}条。",'',
        f"生成身份重复{o['inventory']['duplicate_records']}条。原冻结历史共{o['inventory']['total_history_references']}次引用，涉及{o['inventory']['distinct_referenced_generations']}条不同首答；其中{o['inventory']['reused_generation_count']}条被复用，额外引用{o['inventory']['extra_history_references']}次，在池内仍各计一次。未进入历史的首答也保留。",'',
        f"分类器重叠{o['classification']['overlap']}条，规范化身份不一致{len(o['classification']['disagreements'])}条；未触发5%停止条件。第四批已登记的正确缩写与冻结别名用于身份归并，未创建新的语义标签。",'',
        '全部为单一校准阶段，各作品同题型提示一致，按v2.2合并全部；没有依据m/a差异挑选阶段。下表的校准阶段数就是全部来源数，阶段m/a与主池一致。','',
        '|作品|题型|阶段数|原始n|份额分母|保留/解析失败|m|a|','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in o['readings']:lines.append(f"|{r['work_id']}|{'作者' if r['question']=='author' else '译者'}|{len(r['stages'])}|{r['raw_n']}|{r['n']}|{r['unparsed']}|{fmt(r['m'])}|{fmt(r['a'])}|")
    lines+=['','|作品|标题|电子书号|冻结译者T|另一译者d_T|候选X|','|---|---|---|---|---|---|']
    for r in o['materials']:lines.append('|'+ '|'.join(str(r[k]) for k in ('work_id','title','ebook','T','dT','X'))+'|')
    lines+=['','旧译者正确率表对照：','','|作品|本池a/分母|既有表率/分母|差值|','|---|---|---|---:|']
    for r in o['existing_rate_comparison']:lines.append(f"|{r['work_id']}|{fmt(r['new_a'])}/{r['new_n']}|{fmt(r['k'])}/{r['correct']+r['wrong']+r['missing']}|{fmt(r['difference'])}|")
    lines+=['','既有表来自`factdiag6g_20261111/s0_public_summary.json`，本轮来自第三批运行清单的16次首答。来源与分母不同，不能将差异当作本轮解析器错误；未把既有正确率替代新池读数。','',
        '## 2. 完整读数','', '|作品|题型|m|c|并列|a|最大错误份额|旧复合量|熵|','|---|---|---:|---|---|---:|---:|---:|---:|']
    for r in o['readings']:lines.append(f"|{r['work_id']}|{'作者' if r['question']=='author' else '译者'}|{fmt(r['m'])}|{fmt(r['c'])}|{fmt(r['tie_flag'])}|{fmt(r['a'])}|{fmt(r['w_wrong'])}|{fmt(r['legacy_m_wrong'])}|{fmt(r['H'])}|")
    lines+=['','|作品|T份额|另一译者份额|X份额|竞争对数几率|众数|','|---|---:|---:|---:|---:|---|']
    for r in o['readings']:
        if r['question']=='translator':lines.append(f"|{r['work_id']}|{fmt(r['share_T'])}|{fmt(r['share_dT'])}|{fmt(r['share_X'])}|{fmt(r['lambda'])}|{', '.join(r['modes'])}|")
    lines+=['','全部身份直方图、前五身份加其余、各份额Wilson区间及逐阶段读数见同名JSON。众数的区间为选中身份的逐项区间，不是选择后同时区间。相关把估计份额当观测，尚未传播首答抽样误差。','',
        '## 3. 结局、平移残差与效应复用','', '|单元|作品|历史数|无前缀k/n|A1 k/n|率差y|既有效应及区间|低信息|R|天花板|','|---|---|---:|---|---|---:|---|---|---:|---|']
    for unit,rr in o['unit_rows'].items():
        for r in rr:lines.append(f"|{unit}|{r['work_id']}|{r['histories']}|{r['base_k']}/{r['n']}|{r['A1_k']}/{r['n']}|{fmt(r['y'])}|{fmt(r['beta'])} {ci(r['beta_interval'])}|{fmt(r['low_information'])}|{fmt(r.get('R'))}|{fmt(r['base_ceiling'])}|")
    lines+=['','逐作品效应直接来自指令十，没有重拟合。X的R未计算。合并logit不等于历史logit均值，加之天花板平滑，R不为零不能证明平移被调制。S_T条件似然参照敏感性在JSON完整并列；换参照常数不会改变残差的秩。','',
        '## 4. 主判决的敏感性与P2依赖','']
    p=o['primary']['P1'];v=p['without_R010'];lines += [f"P1去掉只有1段历史的R-010：相关{fmt(v['estimate'])}，区间{ci(v['bootstrap']['interval95'])}，判决“{v['decision']}”；是否跨档：{fmt(p['R010_changes_tier'])}。",'']
    p=o['primary']['P2'];v=p['between_works'];lines += [f"P2作品间均值相关{fmt(v['estimate'])}，区间{ci(v['bootstrap']['interval95'])}；作品内可定义{p['within_defined_works']}/{len(p['within_works'])}部。P2与P3不独立。",'', '|作品|历史数|作品内相关|','|---|---:|---:|']
    for r in p['within_works']:lines.append(f"|{r['work_id']}|{r['n']}|{fmt(r['rho'])}|")
    lines+=['','|历史|首答身份|无筛选份额ρ|旧r2|y|','|---|---|---:|---:|---:|']
    for r in o['FD_history_rows']:lines.append(f"|{r['history_id'].replace('|','/')}|{r['first_answer']}|{fmt(r['rho'])}|{fmt(r['r2'])}|{fmt(r['y'])}|")
    lines+=['','各主检验的逐一去作品相关：','','|检验|去掉作品|相关|','|---|---|---:|']
    for name,v in main:
        for w,rho in v['loo'].items():lines.append(f'|{name}|{w}|{fmt(rho)}|')
    sensitive=[name for name,v in main if v['loo_crosses_zero']]
    lines+=['','逐一去作品后相关范围跨0、标为“单作品敏感”的主检验：'+('、'.join(sensitive) if sensitive else '无')+'。']
    lines+=['','## 5. 次要描述（无判决）','', '|项目|n/作品|相关|95%|精确p|去作品范围|用途|','|---|---:|---:|---|---:|---|---|']
    for s in o['secondary']:
        v=s['result'];lines.append(f"|{s['name']}|{v['n']}/{v['works']}|{fmt(v['estimate'])}|{ci(v['bootstrap']['interval95'])}|{fmt(v['exact']['p'])}|{ci(v['loo_range'])}|{s['purpose']}|")
    lines+=['','每行重抽可定义数及逐一去作品值在JSON；常量或不足3作品不填0。5.3是Q-B主要描述，5.2仅核对。没有把任何次要相关升级为主判决。',
        '逐作品偏差修正效应按既有原值排名；若效应非常接近零，其微小排序可能来自数值优化误差，未事后按有利结果合并。',
        '',f"旧r2历史等权相关{fmt(o['r2_comparison']['previous']['estimate'])}，区间{ci(o['r2_comparison']['previous']['bootstrap']['interval95'])}，直接复用。无筛选ρ的主结果见P2；二者不是独立预测验证，不能凭点值差断言改进。",'',
        '## 6. 人工字段白名单与编造位置','']
    for s in o['W_block']['sources']:lines.append(f"- `{s['archive']}` 内 `{s['member']}`：{s['count']}条；实际字段 `{', '.join(s['actual_fields'])}`。")
    lines+=['','匿名编号字段在终稿中名为human_id，投影后统一记blind_id；语义仍为既有匿名编号。终稿资格复用先前接收结果，不读取其它人工字段。本次没有读取命题、备注、机器列或Astra列。','',o['W_block']['limit'],'',
        '|集合|作品|臂|已确认|未知|已知零|分母|','|---|---|---|---:|---:|---:|---:|']
    for r in o['W_block']['table']:lines.append(f"|{r['cohort']}|{r['work_id']}|{r['arm']}|{r['confirmed']}|{r['unknown']}|{r['known_zero']}|{r['n']}|")
    lines+=['','|作品|事前主观排除|m≥0.5|c=1|a|X份额|','|---|---:|---:|---|---:|---:|']
    for r in o['W_block']['Vpre_rows']:lines.append(f"|{r['work_id']}|{r['Vpre_exclusion']}|{r['strong_prior']}|{fmt(r['mode_true'])}|{fmt(r['a'])}|{fmt(r['share_X'])}|")
    for k,r in o['W_block']['agreement'].items():
        label={'strong_prior':'强先验分类','mode_true':'众数为真分类'}[k]
        lines+=['',f"{label}与事前排除阳性编码的一致数：{r['agree']}/{r['total']}，可判{r['known']}，未知{r['unknown']}。{r['meaning']} 交叉计数(事前排除,读数分类)：{r['cross_table']}。"]
    lines+=['','m≥0.5严格按用户规则，包含恰好一半，未改成>0.5。读数分类一致数只是两个不同定义的描述对照，不能凭此选定第八批传感器。','',
        '## 7. 可部署读数与连续结局对照','', '|作品|m|H|a|c|最大错误份额|X份额|F-D损失|S_T剩余翻错率|X剩余翻错率|','|---|---:|---:|---:|---|---:|---:|---:|---:|---:|']
    for r in o['deployment_table']:lines.append(f"|{r['work_id']}|{fmt(r['m'])}|{fmt(r['H'])}|{fmt(r['a'])}|{fmt(r['c'])}|{fmt(r['w_wrong'])}|{fmt(r['share_X'])}|{fmt(r['FD_update_cost'])}|{fmt(r['ST_A1_false_switch'])}|{fmt(r['X_A1_false_switch'])}|")
    lines+=['','m、H和指定名字份额可直接估计；a、最大错误份额、c及竞争几率的真假解释需要外部确定正确身份。部署代理m与V(众数)能识别强错误先验，并不要求先知道正确答案；但由此应采取的动作及其效果仍待第八批。本轮不冻结体制阈值、不交分类混淆表；未覆盖单元的空值不当作零代价。',
        '', '## 对登记锚点的实际核对（描述，不新增判决）','',
        'R-006《浮士德》的译者首答为16/16正确，S_T的A1保护率差却只有1/6；它没有落在预期的准确率低端，是“先验准确即可预测强保护”的重要限制。R-005《悲惨世界》的两位译者各8/16，并列众数，因此c为未知，不能描述成已确认的唯一错误众数；连续最大错误份额仍为0.5。',
        'R-003《父与子》的译者首答全部落在同一错误身份上，但X主集S臂的候选旁支编造为3/3，三臂合计5/9。因此登记锚点中“强错误占位、编造低”的概括不适用于本轮P4指定的S臂；这一反例保留，不以其它臂替换。',
        '十部作品的share_X均为0。R-009候选John Oxenford的0/16与登记的“大于0”预期不符，而已复核候选旁支编造仍为X主集8/9、C臂3/3。这说明自由首答中的候选出现频率在本池没有区分力，不说明该人物关联绝对不存在；0/16的Wilson上界约0.194。R-008与R-005同样share_X=0，但编造结局不同，单靠此读数不能区分。',
        'm≥0.5在全部十作品均成立，作为二元分类没有样本内变异；与事前排除表5/10的一致数不代表有效预测。占位说的连续相关较强，但主区间仍跨0；不能据本轮选定某个传感器已经胜出。',
        '', '## 保留、解析失败与检查','',f"保留/解析失败共{len(o['exceptions'])}条，逐项原因见JSON。规范化分类器冲突{len(o['classification']['disagreements'])}条。11项要求的针对性检查通过；没有重复既有指令九/十拟合。"]
    if o['exceptions']:
        lines+=['','|生成身份|作品|题型|解析原因|','|---|---|---|---|']
        for r in o['exceptions']:lines.append(f"|{r['generation_id'].replace('|','/')}|{r['work_id']}|{'作者' if r['question']=='author' else '译者'}|{r['parser_reason']}|")
    return '\n'.join(lines)+'\n'
