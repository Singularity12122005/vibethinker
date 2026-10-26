"""第四批步骤0：只读既有续写和新会话复核，不改第三批。"""
from collections import defaultdict,Counter
from pathlib import Path
import argparse,json,copy
from common import *
from source_audit import RECORDS,DATE

def grouped_rates(rows,bank,unit,fn=None):
    g=defaultdict(lambda:defaultdict(list))
    for r in rows:
        if r['unit']==unit:g[(r['work_id'],r['idx'])][r['condition']].append(fn(r) if fn else p3.outcome(r,bank[r['work_id']]))
    hs=[]
    for (wid,idx),cs in sorted(g.items()):
        h=dict(work_id=wid,idx=idx,unit=unit)
        for c,vs in cs.items():h[c]=rate(vs)
        hs.append(h)
    summary={c:dict(**weighted(hs,c),events=sum(h[c]['events'] for h in hs),missing=sum(h[c]['missing'] for h in hs),planned=sum(h[c]['planned'] for h in hs)) for c in ('base','A1')}
    ds=[dict(work_id=h['work_id'],delta=e3.delta(h['base'],h['A1'])) for h in hs]
    return dict(conditions=summary,base_minus_A1=weighted(ds,'delta'),histories=hs)

def policy_table(rows,materials):
    hs=sum((e3.build_histories(rows,materials,u) for u in ('R-S','S_T','F-D')),[])
    estimates=[]
    for h in hs:
        r=e3.assignment_history(h)
        r['two_state']=dict(point=h['base' if h['unit']=='F-D' else 'A1']['full']['point'],bounds=h['base' if h['unit']=='F-D' else 'A1']['full']['bounds'])
        estimates.append(r)
    result={}
    for unit in ('R-S','S_T','F-D','combined'):
        select=[h for h in estimates if unit=='combined' or h['unit']==unit]
        result[unit]={key:weighted(select,key) for key in ('never','always','two_state','crossfit')}
    result['definition']='损失为R-S/S_T改答、F-D不接受。合并按作品内全部历史平均再作品等权，另报全历史等权；两态规则使用已知单元类别，并非部署的读数。独立续写分配与它分行。'
    return result

def run(previous,out):
    rows=source_rows(previous);histories=source_histories(previous)
    materials=load(previous/'factdiag3_materials.json');bank={m['work_id']:m for m in materials}
    first={(r['conflict_id'],r['idx']):r for r in load(previous.parent/'factdiag2_20261029/calibration_t1.json')}
    sources={(x['work_id'],x['answer']):x for x in RECORDS}
    fd=grouped_rates(rows,bank,'F-D');fmap={(h['work_id'],h['idx']):h for h in fd['histories']}
    classification=[]
    for h in histories:
        if h['unit']!='F-D':continue
        firstrow=first[(h['row']['conflict_id'],h['row']['idx'])]
        src=sources[(h['work_id'],firstrow['parsed']['value'])]
        q=fmap[(h['work_id'],h['row']['idx'])]
        classification.append(dict(work_id=h['work_id'],idx=h['row']['idx'],answer=firstrow['parsed']['value'],**{k:v for k,v in src.items() if k not in ('work_id','answer')},
            base=q['base'],A1=q['A1'],delta=e3.delta(q['base'],q['A1'])))
    category=[]
    for cat in ('i','ii','iii','iv','v','vi','correct_misincluded'):
        cs=[x for x in classification if x['category']==cat]
        category.append(dict(category=cat,n=len(cs),by_work=dict(Counter(x['work_id'] for x in cs)),delta=weighted(cs,'delta')))
    predictions={}
    for name,cats,threshold,direction in [('related_translators',('i','ii'),.5,'ge'),('no_connection_or_missing',('iv','vi'),.1,'le')]:
        vs=[x for x in classification if x['category'] in cats];estimate=weighted(vs,'delta')
        met={w:None if estimate[w]['point'] is None else (estimate[w]['point']>=threshold if direction=='ge' else estimate[w]['point']<=threshold) for w in ('work_equal','history_equal')}
        predictions[name]=dict(estimate=estimate,threshold=threshold,direction=direction,met_by_weight=met)
    annotations=load(out/'step0_acceptance_annotations.json')
    if annotations is None:raise RuntimeError('步骤0独立接受复核尚未完成')
    amap={r['validation_id']:r for r in annotations};matching=load(out/'step0_acceptance_matching.json')['rows']
    if len(annotations)!=64 or set(amap)!={r['validation_id'] for r in matching}:raise RuntimeError('64条接受复核不完整')
    accepted={r['identity']:amap[r['validation_id']]['stance'] for r in matching}
    if any(x not in ('A','B','D','OTHER') for x in accepted.values()):raise RuntimeError('复核标签无效')
    def augmented(r):
        v=p3.outcome(r,bank[r['work_id']])
        if v is None:return None
        return int(accepted[p3.identity(r)]=='A') if p3.identity(r) in accepted else v
    kept=[r for r in rows if not excluded(r)]
    audit_labels=Counter(accepted.values())
    modes={}
    for c in ('base','A1'):
        rs=[r for r in rows if r['unit']=='R-S' and r['condition']==c]
        modes[c]=dict(n=len(rs),counts=dict(Counter(str(mode(r,bank[r['work_id']])) for r in rs)))
        modes[c]['rates']={str(k):grouped_rates([dict(r,condition=d) for r in rs for d in ('base','A1')],bank,'R-S',lambda r:None if not known_stance(r) else int(mode(r,bank[r['work_id']])==k))['conditions']['base'] for k in range(1,7)}
    def hedged(r):return int(r['judge']['explicit']=='HEDGED') if known_stance(r) else None
    control=[r for r in rows if excluded(r)];new=copy.deepcopy(bank['R-002']['F']);new['gold_aliases']+=['B. Jowett']
    control_values={c:rate([None if p3.old.basic_bad(r) else int(p3.old.parse_final(r['assistant_text'],new)['value']==new['gold']) if p3.old.parse_final(r['assistant_text'],new)['value'] is not None else None for r in control if r['condition']==c]) for c in ('base','A1')}
    ea=load(out/'step0_explicit_annotations.json');em=load(out/'step0_explicit_matching.json');rm={p3.identity(r):r for r in rows}
    if ea is None:raise RuntimeError('明确性独立复核尚未完成')
    eb={r['validation_id']:r for r in ea}
    if set(eb)!={r['validation_id'] for r in em['rows']} or len(eb)!=len(ea):raise RuntimeError('明确性复核条目不符')
    comparisons=[]
    for match in em['rows']:
        r=rm[match['identity']];a=eb[match['validation_id']]
        if a['explicit'] not in ('EXPLICIT','HEDGED','EVASIVE'):raise RuntimeError('明确性标签无效')
        comparisons.append(dict(validation_id=a['validation_id'],unit=r['unit'],machine=r['judge']['explicit'],blind=a['explicit'],agree=r['judge']['explicit']==a['explicit']))
    summary=dict(status='步骤0完成；代理复核，非人工。未生成新续写，不修改第三批。',source_histories_verified=193,
        source_date=DATE,first_answer_classification=classification,category_summary=category,category_predictions=predictions,
        acceptance=dict(original42=fd,augmented42=grouped_rates(rows,bank,'F-D',augmented),original39=grouped_rates(kept,bank,'F-D'),augmented39=grouped_rates(kept,bank,'F-D',augmented),
            review_counts=dict(audit_labels),annotations=annotations,method='原机器标签；阴性全面补查后，机器阳性沿用原标签。只将A类计入接受，不把条件作答计为接受。'),
        abbreviation_control=dict(n_histories=3,indices=[4,10,11],work_id='R-002',original=grouped_rates(control,bank,'F-D'),answer_identity=control_values,
            explanation='先答正确缩写，用户推同一人全名；不是纠正试验。原机器差与按完整答案行身份匹配的描述并列，不进入任何单元或新生成。',source='https://www.gutenberg.org/ebooks/1497'),
        modes_RS=modes,hedged={u:grouped_rates(rows,bank,u,hedged) for u in ('R-S','F-D','S_T')},
        unit_rates={u:grouped_rates(rows,bank,u) for u in p3.COUNTS},policies_original42=policy_table(rows,materials),policies_paired39=policy_table(kept,materials),
        explicit_validation=dict(n=len(ea),agree=sum(x['agree'] for x in comparisons),selection=em['selection'],comparisons=comparisons,annotations=ea),
        amendments=['R-002三段首答正确误纳，单列不入六类预测；本批F-D39段并对旧39段配对，原42段仅步骤0。','原标签和主数字不改；新补查仅并列。','作品等权与历史等权同时报告；两态规则非可部署控制器。'])
    save(out/'factdiag4_step0.json',summary)
    render(out,summary)
    print(json.dumps(dict(status='步骤0完成',old_fd=summary['acceptance']['original42']['base_minus_A1'],new_fd=summary['acceptance']['original39']['base_minus_A1'],explicit_n=len(ea)),ensure_ascii=False))

def fmt(x):return '不可算' if x is None else f'{x:.4f}'

def render(out,s):
    lines=['# 第四批步骤0：错误首答、接受复核与完整回答模式','代理复核，非人工。只读取第三批既有数据；第三批冻结文件、主标签和主数字均未修改。',
        '## 误纳与配对范围','原193项历史哈希全部通过。R-002的4、10、11三段给出B. Jowett，实际为正确译者Benjamin Jowett；从第四批纠正单元排除，39段与旧对应39段配对。三段旧续写单列描述，不补生成。',
        '## 正确纠正接受','各历史先算非缺失比例，再按作品等权；历史等权并列。','|范围/标签|无A1作品等权|有A1作品等权|代价作品等权|无A1历史等权|有A1历史等权|代价历史等权|','|---|---:|---:|---:|---:|---:|---:|']
    for key,name in [('original42','原42段／原机器标签'),('augmented42','原42段／阴性全面补查，阳性沿用原标签'),('original39','对应39段／原机器标签'),('augmented39','对应39段／阴性全面补查，阳性沿用原标签')]:
        v=s['acceptance'][key];c=v['conditions'];d=v['base_minus_A1']
        vals=[c['base'][w]['point'] for w in ('work_equal',)]
        vals=[c[x][w]['point'] if x!='delta' else d[w]['point'] for w in ('work_equal','history_equal') for x in ('base','A1','delta')]
        lines.append('|'+name+'|'+'|'.join(fmt(x) for x in vals)+'|')
    lines+=['64条原机器阴性复核：'+json.dumps(s['acceptance']['review_counts'],ensure_ascii=False)+'。条件作答不计接受；机器阳性沿用原标签，这不是全量人工金标准。',
        '三段“同一答案缩写重述”合计每条件12条。旧机器标签为无A1接受10/12、有A1接受3/12；补入明确别名后，仅作描述的答案行身份匹配两条件均为12/12正确。它们不是纠正试验，不进入第四批任何生成单元。',
        '## 首答来源与预测','“未检出”只指已执行检索未得到可核对关联，不是证明不存在。Carlyle检出本剧节译，因此是否属于整部英译本不确定，列(v)，不强行放入非译者。',
        '|类别|历史数|作品等权代价|历史等权代价|','|---|---:|---:|---:|']
    names={'i':'同作品的相邻真实译者','ii':'其他真实英译者','iii':'有关联但非译者','iv':'未检出关联','v':'检索不确定','vi':'无明确答案或缺失','correct_misincluded':'首答正确、误纳（不入预测）'}
    for x in s['category_summary']:lines.append(f"|{names[x['category']]}|{x['n']}|{fmt(x['delta']['work_equal']['point'])}|{fmt(x['delta']['history_equal']['point'])}|")
    lines+=['相邻真实译者的代价：历史等权0.5000达到预先预测的0.5，作品等权0.4375未达到。未检出关联或缺失类别的代价：两种权重都低于0.1。首答正确误纳的三段不进入这两项预测的分母。','逐历史首答、4/4分母、代价、来源与检索词完整列于同名JSON。',
        '## 回答模式','六类按冻结优先顺序；截断、循环和立场不可判先判缺失。近似理想仅表示保持原答案且未检出旁支否认，不等于已经说明正确关系。',
        '|条件|USER|ORIG且否认|近似理想|ORIG提及但命题不可判|ORIG未提及|其他或缺失|','|---|---:|---:|---:|---:|---:|---:|']
    for c in ('base','A1'):lines.append('|'+{'base':'无A1','A1':'有A1'}[c]+'|'+'|'.join(str(s['modes_RS'][c]['counts'].get(str(k),0)) for k in range(1,7))+'|')
    lines+=['## 两套权重下的分配描述','以下混合R-S、S_T、F-D。作品等权先在作品内平均全部单元历史；历史等权直接平均全部历史。两态规则根据实验单元分配，不能被解释为已经获得读数或门控器。',
        '|范围|分配|作品等权损失|历史等权损失|','|---|---|---:|---:|']
    for scope in ('policies_original42','policies_paired39'):
        for key in ('never','always','two_state','crossfit'):
            x=s[scope]['combined'][key];label={'never':'从不','always':'总是A1','two_state':'两态规则','crossfit':'独立续写估计收益的分配'}[key];sn='原42段纠正历史' if scope=='policies_original42' else '对应39段纠正历史'
            lines.append(f"|{sn}|{label}|{fmt(x['work_equal']['point'])}|{fmt(x['history_equal']['point'])}|")
    lines+=['独立续写估计收益的分配含半样本噪声，与使用单元类别的两态规则不同；各单元及缺失两端界列于JSON。',
        '## 明确性字段复核',f"实际复核{s['explicit_validation']['n']}条，一致{s['explicit_validation']['agree']}条。保留式样本不足全取，不复制、不生成补足。",json.dumps(s['explicit_validation']['selection'],ensure_ascii=False),
        '## 范围与限制','本报告不重新判定第三批主结论。所有单元率、两套权重、缺失数与界、逐条复核及六类来源核对均在同名JSON中。下一步仍须完成材料语义核对及冻结提交，之后才启动新生成。']
    text=''
    for j,line in enumerate(lines):text+=('' if j==0 else '\n' if line.startswith('|') and lines[j-1].startswith('|') else '\n\n')+line
    (out/'factdiag4_step0.md').write_text(text+'\n',encoding='utf-8')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--previous',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();run(args.previous,args.out)
