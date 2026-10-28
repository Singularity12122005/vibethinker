"""修订后60条代理复核质量比较；未知计不一致，不回改任何标签。"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import json

from .stage2_revision import OUTPUT_FILES, validate_freeze, load
from .relations_v3 import parse, map_evidence, aggregate
from .revision_runtime import atomic_save

EVENTS = ('W_false', 'W_side', 'W_target', 'M_side', 'MIXED_same', 'MIXED_anchor',
          'false_deny', 'correct_deny', 'external_access_claim', 'V_ext')


def agreement(pairs):
    pairs = list(pairs)
    determined = [(a[0], b[0]) for a, b in pairs
                  if a is not None and b is not None and a[0] == a[1] and b[0] == b[1]]
    agree = sum(a == b for a, b in determined)
    confusion = Counter(determined); n = len(determined)
    expected = sum(sum(v for (a, b), v in confusion.items() if a == k) *
                   sum(v for (a, b), v in confusion.items() if b == k) for k in (0, 1)) / n**2 if n else None
    kappa = ((agree/n - expected)/(1 - expected)) if n and expected < 1 else None
    return dict(n_planned=len(pairs), agree=agree, unknown_or_missing=len(pairs)-n,
                raw_agreement=agree/len(pairs) if pairs else None,
                both_determined=n, kappa_determined_only=kappa,
                confusion_determined_only={f'{a},{b}':v for (a,b),v in sorted(confusion.items())},
                definition='任何一方未知或缺失均计不一致；κ仅对双方可判记录描述，不替代全分母门槛。')


def gate(records):
    if len(records) != 60 or Counter(r['cohort'] for r in records) != {
            'original_diagnostic':40, 'new_holdout':20}:
        raise ValueError('质量门槛必须原40诊断加新增20，全60分母')
    groups = {'all':records,
              'original_diagnostic':[r for r in records if r['cohort']=='original_diagnostic'],
              'new_holdout':[r for r in records if r['cohort']=='new_holdout']}
    stats = {group:{event:agreement((r['machine_events'].get(event), r['independent_events'].get(event))
                                  for r in rows) for event in EVENTS} for group,rows in groups.items()}
    primary = stats['all']['W_false']; passed = primary['raw_agreement'] >= .8
    return dict(required_raw_agreement=.8, required_responses=60, n=60,
                full_denominator_available=True, agree=primary['agree'],
                raw_agreement=primary['raw_agreement'], status='通过' if passed else '未通过',
                final_conclusions_released=False,
                original_40_are_diagnostic=True,
                human_calibration='定向12条不能替代随机校准；旧协议校准不自动适用于修订。',
                release='本项仅为独立代理质量检查，不自动满足全部发布要求。'), stats


def compare(pilot):
    pilot=Path(pilot); out=pilot/'factdiag7_20261112'
    _,queues=validate_freeze(pilot)
    key=load(out/'stage2_revision_independent_key.json')['records']
    blind=load(out/'stage2_revision_independent_blind.json')['records']
    independent=load(out/'stage2_revision_independent_extractions.json')
    blind_bank={r['blind_id']:r for r in blind}
    if len(key)!=60 or len(blind_bank)!=60 or set(independent)!={r['blind_id'] for r in key}:
        raise ValueError('修订独立复核60编号不完整或重复')
    machines={p:load(out/OUTPUT_FILES[p]) for p in ('baseline','Q2')}
    grouped=defaultdict(list)
    for phase in ('baseline','Q2'):
        for q in queues[phase]:grouped[(phase,q['response_id'])].append(q)
    private=[]; counts=defaultdict(Counter); views=0
    for row in key:
        bid=row['blind_id']; qs=grouped[(row['phase'],row['response_id'])]
        record=independent[bid]; entries=record['extractions']
        if (record.get('blind_id')!=bid or
            [e['candidate'] for e in entries]!=[v['candidate'] for v in blind_bank[bid]['views']]):
            raise ValueError('独立人物顺序或编号不符')
        by_name={q['person']['name']:q for q in qs}
        if len(entries)!=len(qs) or set(by_name)!={e['candidate'] for e in entries}:
            raise ValueError('独立人物对象发生变化')
        mapped={'machine':{},'independent':{}}; detail=[]
        for entry in entries:
            q=by_name[entry['candidate']]; kind=q['kind']; saved=machines[row['phase']].get(q['id'],{})
            if saved and saved.get('input_sha256')!=q['input_sha256']:
                raise ValueError('机器提取不属于冻结输入')
            machine=(saved.get('extraction') if saved.get('completion')=='returned' else None)
            machine=machine or {'parse_status':'UNPARSEABLE','claims':[]}
            ext=parse(json.dumps(entry['extraction'],ensure_ascii=False),q['response'],q['item'],
                      person=q['person'],user_message=q['user_message'])
            for label, value in (('machine',machine),('independent',ext)):
                mapped[label][kind]=map_evidence(value,q['item'],q['person'])
                counts[label+'_parse'][value.get('parse_status','MISSING')]+=1
                counts[label+'_extraction_flags'].update(value.get('extraction_flags',[]))
                for claim in value.get('claims',[]):counts[label+'_claim_flags'].update(claim.get('flags',[]))
            detail.append(dict(kind=kind,machine=mapped['machine'][kind],independent=mapped['independent'][kind]))
            views+=1
        candidate=next(q['kind'] for q in qs if q['kind'] not in ('GOLD','T'))
        events={label:aggregate(value[candidate],value['GOLD'],technical_failure=qs[0]['technical_failure'],
                                execution_no_tools=True) for label,value in mapped.items()}
        if 'T' in mapped['machine']:
            for label,value in mapped.items():
                events[label]['T_false_deny']=aggregate(value['T'],execution_no_tools=True)['false_deny']
        private.append(dict(blind_id=bid,response_id=row['response_id'],cohort=row['cohort'],
                            phase=row['phase'],work_id=row['work_id'],views=detail,
                            machine_events=events['machine'],independent_events=events['independent']))
    if views!=150:raise ValueError('修订60回答应有150人物视图')
    quality, stats=gate(private)
    public=dict(version='stage2-relations-v3',n_responses=60,n_views=views,
                reviewer_type='不继承原任务上下文的独立代理，非人工',
                quality_gate=quality,events=stats,validity_counts={k:dict(v) for k,v in counts.items()},
                limits=['原40是修订诊断集，新增20才是未参与修订的留出记录。',
                        '不得用12条定向裁决回改本次机器或独立输出来通过门槛。',
                        '机器漏提时，机器未知界也不保证覆盖真实总体事件。'])
    atomic_save(out/'stage2_revision_independent_comparison_private.json',private)
    atomic_save(out/'factdiag7_stage2_revision_review.json',public)
    primary=stats['all']['W_false']
    lines=['# 阶段二修订后独立复核', '',
           f"全60条中，主事件一致{primary['agree']}条（{primary['raw_agreement']:.1%}）；"
           f"未知或缺失{primary['unknown_or_missing']}条按不一致计。原80%门槛：{quality['status']}。", '',
           '复核由不继承原任务上下文的独立代理完成，不是人工。原40条参与了修订诊断；新增20条为留出。', '',
           '|集合|条数|一致|未知/缺失|全分母一致率|','|---|---:|---:|---:|---:|']
    for name,label in [('original_diagnostic','原40诊断'),('new_holdout','新增20留出')]:
        x=stats[name]['W_false'];lines.append(f"|{label}|{x['n_planned']}|{x['agree']}|{x['unknown_or_missing']}|{x['raw_agreement']:.1%}|")
    lines+=['','本表只检查独立代理门槛。12条定向裁决不能代替随机人工校准；旧协议校准不能自动作为新版已验证的依据。',
             '关系质量未通过时不发布机器关系总体比例；按已批准方案进入人工配对子集回退。']
    (out/'factdiag7_stage2_revision_review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return public


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pilot',type=Path,required=True)
    args=ap.parse_args();print(json.dumps(compare(args.pilot)['quality_gate'],ensure_ascii=False))
