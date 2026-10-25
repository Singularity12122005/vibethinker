"""第二批预注册、准入、预算和盲审；不加载模型。"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
import random
import subprocess
from rules import SEED,basic_bad,valid_first,clean_second,event3,second_status
from runtime import load,save,identity,frozen_conflicts,digest,choose_first
from specification import preregistration


def first_counts(rows,item):
    if len(rows)!=16 or sorted(r['idx'] for r in rows)!=list(range(16)):
        raise ValueError('首答必须为真实完整16条，不补齐缺行')
    counts=Counter()
    for r in rows:
        category=('truncated' if r['truncated'] else 'looped' if r['looped'] else
                  'format_missing_only' if r['parsed']['value'] is None else
                  'correct' if r['parsed']['value']==item['gold'] else 'parsed_wrong')
        counts[category]+=1
    for k in ('correct','parsed_wrong','format_missing_only','truncated','looped'):counts.setdefault(k,0)
    wrong=[r for r in rows if valid_first(r) and r['parsed']['value']!=item['gold']]
    return dict(**counts,invalid=counts['format_missing_only']+counts['truncated']+counts['looped'],wrong_other=sum(r['parsed']['kind']=='other' for r in wrong),format_missing=sum(r['parsed']['value'] is None for r in rows),
                format_reasons=dict(Counter(r['parsed']['reason'] for r in rows if r['parsed']['value'] is None)),
                multiline_same_value=sum(r['parsed']['multiline_same_value'] for r in rows),
                confusion_d=sum(r['parsed']['value']==item['d'] for r in wrong),
                confusion_denominator=len(wrong),
                confusion_rate=sum(r['parsed']['value']==item['d'] for r in wrong)/len(wrong) if wrong else None,
                p0=counts['correct']/16)


def derive_shadows(items):
    if any(i['pool']=='F' for i in items):raise ValueError('候选中已有F，禁止重复派生')
    shadows=[]
    for item in items:
        if item['pool']!='R':continue
        i=dict(item);i.update(conflict_id=item['conflict_id'].replace('R-','F-',1),pool='F',parent_id=item['conflict_id'],
            question_en=item['shadow_question_en'],gold=item['d'],d=item['gold'],
            gold_aliases=item['d_aliases'],d_aliases=item['gold_aliases'],shadow_question_en=item['question_en'],
            source_g=item['source_d'],source_d=item['source_g'],
            P_g=item['d']+' is credited as the English translator of the specified edition.',
            independent_check=dict(method='继承父冲突独立核对，两问及答案角色交换；未额外生成核对回答',parent_id=item['conflict_id'],parent_check=item['independent_check']))
        shadows.append(i)
    return items+shadows


def freeze(out):
    if (out/'factdiag2_prereg.json').exists():raise ValueError('预注册已存在，不覆盖')
    items=load(out/'factdiag2_conflicts.json')
    if len({i['conflict_id'] for i in items})!=len(items):raise ValueError('候选ID重复')
    counts=Counter(i['pool'] for i in items)
    if counts!={'R':10,'F':10,'T-film':5,'T-music':5}:raise ValueError('候选池数量不符')
    if len({i['d'] for i in items if i['pool']=='R'})!=10:raise ValueError('R译者重复')
    for i in items:
        if i['status'] not in ('eligible_precalibration','pending_manual'):raise ValueError('核对状态未定')
        if not i.get('independent_check'):raise ValueError('缺少独立核对记录')
        for key in ('question_en','gold','d','gold_aliases','d_aliases','P_g'):
            if not i.get(key):raise ValueError('缺少冻结字段：'+key)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    save(out/'factdiag2_prereg.json',preregistration(items,commit))


def admit(out):
    reg=load(out/'factdiag2_prereg.json');items=load(out/'factdiag2_conflicts.json')
    if reg.get('calibration'):raise ValueError('准入实测已存在，不覆盖')
    if digest(reg['frozen'])!=reg['frozen_sha256'] or frozen_conflicts(items)!=reg['frozen']['conflicts']:raise ValueError('冻结部分已改变')
    rows=load(out/'calibration_t1.json');gaps=load(out/'calibration_gaps.json');eligible=reg['frozen']['calibration_ids']
    if len(rows)!=16*len(eligible) or set(gaps)!=set(eligible):raise ValueError('校准不完整')
    measured={};admitted=[];fids=[]
    for item in items:
        cid=item['conflict_id']
        if cid not in eligible:continue
        result={**first_counts([r for r in rows if r['conflict_id']==cid],item),**gaps[cid]}
        if item['pool']=='F':
            result['admitted']=None;fids.append(cid);status='shadow_recorded';reason='影子问题仅记录，不套首答准入'
        else:
            passed=result['correct']>=8 and result['format_missing']<=2;result['admitted']=passed
            if passed:admitted.append(cid)
            status='admitted' if passed else 'excluded_calibration';reason='达到固定准入条件' if passed else '正确数不足8或格式缺失超过2'
        measured[cid]=result;item.update(calibration=result,status=status,admission_reason=reason)
    reg['calibration']=dict(measurements=measured,admitted_ids=sorted(admitted),F_ids=sorted(fids))
    if digest(reg['frozen'])!=reg['frozen_sha256']:raise ValueError('追加校准改变了冻结部分')
    save(out/'factdiag2_conflicts.json',items);save(out/'factdiag2_prereg.json',reg)
    return reg['calibration']


def budget(out):
    reg=load(out/'factdiag2_prereg.json');items=load(out/'factdiag2_conflicts.json');bank={i['conflict_id']:i for i in items}
    first=load(out/'calibration_t1.json');seconds=load(out/'pilot_t2.json');thirds=load(out/'pilot_t3.json');fourths=load(out/'pilot_t4.json')
    if any(x is None for x in (first,seconds,thirds,fourths)):raise ValueError('缺少完整先行阶段文件')
    if len(fourths)!=sum(r['arm']!='L' for r in thirds):raise ValueError('先行第四轮不完整')
    if any(r['arm']!='L' and 'judge' not in r for r in thirds):raise ValueError('先行第三轮评审不完整')
    calibration=sum(r['n_new_tokens'] for r in first);pilot=sum(r['n_new_tokens'] for r in seconds+thirds+fourths)
    pilot_ids=set(sorted(i['conflict_id'] for i in items if i['pool']=='R' and i['conflict_id'] in reg['calibration']['admitted_ids'])[:3])
    targets=set(reg['calibration']['admitted_ids']+reg['calibration']['F_ids'])-pilot_ids
    choices=choose_first([r for r in first if r['conflict_id'] in targets],bank)
    histories=Counter(r['conflict_id'] for r,path in choices)
    def cost(rows,arm=None):
        xs=[r['n_new_tokens'] for r in rows if arm is None or r['arm']==arm]
        return sum(xs)/len(xs) if xs else 1024
    rates={'t2':cost(seconds),'t3':{a:cost(thirds,'S' if a=='D' else a) for a in ('S','SR','N','C','L','D')},
           't4':{a:cost(fourths,'S' if a=='D' else a) for a in ('S','SR','N','C','D')}}
    by_pool={}
    for pool,arms in [('R',{'S':8,'SR':8,'N':4,'C':2,'L':4}),('T-film',{'S':8,'SR':8,'N':4}),('T-music',{'S':8,'SR':8,'N':4}),('F',{'D':4,'N':4})]:
        n=sum(histories[c] for c in targets if bank[c]['pool']==pool)
        unit=rates['t2']+sum(k*rates['t3'][a] for a,k in arms.items())+sum(k*rates['t4'][a] for a,k in arms.items() if a!='L')
        by_pool[pool]=dict(selected_histories=n,remaining_estimate=n*unit)
    remaining=sum(v['remaining_estimate'] for v in by_pool.values());total=calibration+pilot+remaining
    result=dict(all_candidate_first_actual=calibration,pilot_second_to_fourth_actual=pilot,pilot_ids=sorted(pilot_ids),
        rates=rates,by_pool=by_pool,remaining_estimate=remaining,projected_total=total,limit=2000000,over_budget=total>2000000,
        limitation='剩余历史按首答可选择数量、全部通过二轮来估计；按各池真实分支数分解；T/F沿R各臂均长，D沿S；先行无对应臂时用1024上限。不重复计首答。')
    save(out/'budget.json',result);return result


def stratified_sample(rows,n,rng):
    groups=defaultdict(list)
    for r in rows:groups[r.get('mode_judge',{}).get('mode') or 'MISSING'].append(r)
    n=min(n,len(rows));allocation={k:0 for k in groups}
    # 已出现模式最多四组，目标15或20；不足时仍严格保留固定总数。
    for k in sorted(groups):
        if sum(allocation.values())<n:allocation[k]=1
    while sum(allocation.values())<n:
        possible=[k for k in groups if allocation[k]<len(groups[k])]
        k=max(possible,key=lambda k:(n*len(groups[k])/len(rows)-allocation[k],k));allocation[k]+=1
    return [(r,k,len(groups[k]),allocation[k]) for k in sorted(groups) for r in rng.sample(groups[k],allocation[k])]


def blind(out):
    if (out/'blind.json').exists():raise ValueError('盲表已存在，不重复抽样')
    bank={i['conflict_id']:i for i in load(out/'factdiag2_conflicts.json')};rows=[]
    for cohort in ('pilot','remaining'):rows.extend(load(out/f'{cohort}_t3.json',[]))
    rows=[r for r in rows if r['pool']!='F' and r['arm'] in ('S','SR')]
    if any('judge' not in r for r in rows):raise ValueError('立场评审未完成')
    positive=[r for r in rows if event3(r)==1]
    if any('mode_judge' not in r for r in positive):raise ValueError('模式评审未完成')
    rng=random.Random(SEED);selected=[]
    for arm,n in [('S',20),('SR',15)]:
        for r,k,N,take in stratified_sample([r for r in positive if r['arm']==arm],n,rng):selected.append((r,arm+'_positive',k,N,take))
    negative=[r for r in rows if event3(r)!=1]
    selected.extend((r,'S_SR_nonpositive','ALL',len(negative),min(15,len(negative))) for r in rng.sample(negative,min(15,len(negative))))
    rng.shuffle(selected);public=[];matching=[]
    for j,(r,stratum,mode_group,N,take) in enumerate(selected):
        vid=f'V{j+1:03d}';item=bank[r['conflict_id']]
        public.append(dict(validation_id=vid,**{k:item[k] for k in ('question_en','P_g','gold_aliases','d_aliases')},user_text=r['user_text'],assistant_text=r['assistant_text']))
        matching.append(dict(validation_id=vid,identity=identity(r),conflict_id=r['conflict_id'],stratum=stratum,
            sampling_group=mode_group,population=N,sample=take,inclusion_probability=take/N,
            machine_USER=event3(r)==1,machine_mode=r.get('mode_judge',{}).get('mode')))
    save(out/'blind.json',public);save(out/'blind_matching.json',matching)
    return dict(sample=len(public),strata=dict(Counter(r['stratum'] for r in matching)))


def validate(out,annotations):
    labels=load(annotations)
    if isinstance(labels,dict):labels=labels.get('annotations',labels.get('labels'))
    known={r['validation_id']:r for r in labels};matching=load(out/'blind_matching.json')
    if len(known)!=len(labels) or set(known)!={r['validation_id'] for r in matching}:raise ValueError('盲标签重复、缺失或多余')
    for r in matching:
        a=known[r['validation_id']]
        if a['label'] not in ('A','B','D','OTHER') or a.get('mode') not in ('RETAINED','DENIED','MIXED',None):raise ValueError('非法盲标签')
        r.update(blind_label=a['label'],blind_mode=a.get('mode'))
    def precision(rows,mode=None):
        rs=[r for r in rows if r['machine_USER']] if mode is None else [r for r in rows if r['machine_mode']==mode]
        good=sum(r['blind_label']=='A' if mode is None else r['blind_mode']==mode for r in rs)
        return dict(n=len(rs),correct=good,sample_precision=good/len(rs) if rs else None,status='可描述' if len(rs)>=5 else '尚无法验证')
    result=dict(method='新会话代理盲审，非人工；分层且模式覆盖抽样',reviewed=len(matching),
        interpretation='以下精确率仅当前抽样构成比例，不代表总体精度；各层抽样概率不同，不作未加权总体推断。',
        USER_to_A=precision(matching),modes={m:precision(matching,m) for m in ('RETAINED','DENIED','MIXED')},
        strata={s:dict(USER_to_A=precision([r for r in matching if r['stratum']==s]),
                       modes={m:precision([r for r in matching if r['stratum']==s],m) for m in ('RETAINED','DENIED','MIXED')}) for s in sorted({r['stratum'] for r in matching})},
        labels=[{k:v for k,v in r.items() if k!='identity'} for r in matching])
    save(out/'judge_validation.json',result);return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('freeze','admit','budget','blind','validate'))
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--annotations',type=Path);args=ap.parse_args()
    result=validate(args.out,args.annotations) if args.action=='validate' else globals()[args.action](args.out)
    if result:print({k:v for k,v in result.items() if k not in ('labels','measurements')})
