"""人工回退三列校准：仅质量一致率，不输出按臂关系事件比例。"""
from collections import defaultdict
from pathlib import Path
import argparse
import json

from .fallback_calibration import KEY
from .stage2_revision import build_inputs,load,OUTPUT_FILES
from .mention_holdout import ready,column_extraction
from .relations_v3 import map_evidence,aggregate

COLUMNS=('original','reprompt','normalized_quote')
ARMS=('S','S+A0','S+A1')


def human_bound(value):
    if value is None:return [0,1]
    if type(value) is int and value in (0,1):return [value,value]
    if isinstance(value,list) and value in ([0,0],[0,1],[1,1]):return value[:]
    raise ValueError('人工事件只能为0、1、null或合法两端界；不能把文本猜成标签')


def agreement(pairs):
    """同一计划分母；下界标记一致与确定项一致均不替代保守门槛。"""
    pairs=[(human_bound(a),human_bound(b)) for a,b in pairs]
    known=[(a,b) for a,b in pairs if a[0]==a[1] and b[0]==b[1]]
    matches=sum(a==b for a,b in known)
    n=len(pairs)
    return dict(planned=n,both_determined=len(known),conservative_matches=matches,
        conservative_agreement=matches/n if n else None,
        lower_marker_matches=sum(a[0]==b[0] for a,b in pairs),
        lower_marker_agreement=sum(a[0]==b[0] for a,b in pairs)/n if n else None,
        determined_agreement=matches/len(known) if known else None,
        unknown_in_either=n-len(known),threshold=.8,
        calibrated=bool(n and matches/n>=.8))


def selected_human_rows(keys,document,cohort,priority60=False):
    if cohort not in ('X_main','Fw_optional'):raise ValueError('未知人工集合')
    if priority60 and cohort!='X_main':raise ValueError('优先60仅用于X主集')
    if document.get('cohort')!=cohort:raise ValueError('人工集合身份不符')
    expected=[r for r in keys if r['cohort']==cohort]
    rows=document.get('records',[])
    if len(rows)!=len(expected) or len({r.get('human_id') for r in rows})!=len(rows):
        raise ValueError('人工文件必须保留完整90或30条；延期项留空，不删除')
    provided={r['human_id']:r for r in rows}
    if set(provided)!={r['human_id'] for r in expected}:raise ValueError('人工编号集合不符')
    selected=[]
    for k in expected:
        r=provided[k['human_id']]
        if (r.get('blind_id'),r.get('work_id'),r.get('history_index'),r.get('arm'))!=(k['blind_id'],k['work_id'],k['idx'],k['arm']):
            raise ValueError('人工标签与已抽样身份不符')
        if priority60 and k['arm']=='S+A0':continue
        if r.get('human_review_complete') is not True:
            raise ValueError('人工尚未逐条确认完成，空表不能当成全未知并直接判门槛')
        selected.append((k,human_bound(r.get('W_false'))))
    expected_n=60 if priority60 else 90 if cohort=='X_main' else 30
    if len(selected)!=expected_n:raise ValueError('校准分母改变')
    return selected


def run(pilot,labels_path,cohort,*,priority60=False):
    pilot=Path(pilot);out=pilot/'factdiag7_20261112'
    keys=load(out/KEY)['records'];human=load(labels_path)
    selected_human=selected_human_rows(keys,human,cohort,priority60)
    # 必须已完成三列所需输入；不为校准而提前调用评审模型。
    plan,reprompt=ready(pilot);selected_ids={r['id'] for r in plan['entries']}
    queues=build_inputs(pilot);saved={p:load(out/OUTPUT_FILES[p]) for p in ('baseline','Q2')}
    grouped=defaultdict(list)
    for phase in saved:
        for q in queues[phase]:
            if q['kind']!='T':grouped[(phase,q['response_id'])].append(q)
    pairs={column:defaultdict(list) for column in COLUMNS}
    for row,truth in selected_human:
        qs=grouped[(row['phase'],row['response_id'])]
        if len(qs)!=2 or {q['kind'] for q in qs}!={row['candidate_type'],'GOLD'}:
            raise ValueError('人工主事件只含候选与原作者，不扩人物')
        mapped={column:{} for column in COLUMNS}
        for q in qs:
            original=saved[row['phase']][q['id']]
            if original.get('input_sha256')!=q['input_sha256']:raise ValueError('机器输入身份不符')
            for column,e in column_extraction(q,original,reprompt,selected_ids).items():
                mapped[column][q['kind']]=map_evidence(e,q['item'],q['person'])
        for column,views in mapped.items():
            event=aggregate(views[row['candidate_type']],views['GOLD'],
                technical_failure=qs[0]['technical_failure'],execution_no_tools=True)['W_false']
            pairs[column]['all'].append((event,truth))
            pairs[column][row['arm']].append((event,truth))
    stats={column:{arm:agreement(p) for arm,p in groups.items()} for column,groups in pairs.items()}
    report=dict(cohort=cohort,candidate_type='X' if cohort=='X_main' else 'F_w',
        arms=['S','S+A1'] if priority60 else list(ARMS),responses=len(selected_human),
        primary='original',secondary_one='reprompt',secondary_two='normalized_quote',
        gate_definition='双方均确定且一致才计一致；任何一方未知算不一致，全部已登记计划分母不缩。',
        human_design='固定前缀可见，臂对人工可见；机器和独立代理作为阅读辅助，不称人工完全盲审。',
        interpretation='达到0.80仅标经事后人工集校准；总体及分臂校准分别列出。覆盖范围仅限此候选类型和实际人工臂，不追认原列留出通过，不放行第五批。',
        relation_population_rates_computed=False,columns=stats)
    suffix='X_priority60' if priority60 else cohort
    dest=out/('stage2_fallback_calibration_'+suffix+'.json')
    if dest.exists() and load(dest)!=report:raise RuntimeError('已有不同人工校准报告，先确认是否用户更新标签')
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot',type=Path,required=True);parser.add_argument('--labels',type=Path,required=True)
    parser.add_argument('--cohort',choices=['X_main','Fw_optional'],required=True);parser.add_argument('--priority60',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.pilot,args.labels,args.cohort,priority60=args.priority60),ensure_ascii=False))
