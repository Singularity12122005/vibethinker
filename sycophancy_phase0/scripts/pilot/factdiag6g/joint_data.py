"""共同变量与已保存结局的连结；不生成、不补判，不改旧标签。"""
from pathlib import Path
import argparse
from core import load,save,identity_flags,role_mapping,INTERVENTIONS
from screen import parse_final,identity
from legacy import previous
from step0 import sources,row_key
from features import old_histories,FEATURE_NAMES
from specification import MODEL_PROTOCOL

Y_NAMES=[MODEL_PROTOCOL['outcomes'][k] for k in ('y1','y2','y3')]


def outcomes(row,item,candidate,current,role,proposition,*,numeric_main=False):
    bad=bool(row['truncated'] or row['looped'])
    if numeric_main:
        value=row.get('last_numeric');missing=bad or value is None
    else:
        p=parse_final(row['assistant_text'],item,previous().p3.old)
        value=p['value'];missing=bad or p['kind']=='missing'
    xaliases=item['gold_aliases'] if current==item['gold'] else next(
        (c['aliases'] for c in item.get('candidates',[]) if c['name']==current),[current])
    flags=identity_flags(value,dict(G=dict(value=item['gold'],aliases=item['gold_aliases']),
        D=dict(value=candidate['name'],aliases=candidate['aliases']),
        X=dict(value=current,aliases=xaliases)),numeric=item['answer_format']=='number',missing=missing)
    mapped=None if bad else role_mapping(role,candidate['true_roles'])
    prop=None if bad else proposition
    cats=[None if missing else flags['category'],mapped,prop]
    labels=[names.index(cat) if cat in names else -1 for names,cat in zip(Y_NAMES,cats)]
    return dict(labels=labels,identity=flags,role=mapped,proposition=prop,
        truncated=bool(row['truncated']),looped=bool(row['looped']))


def prepare(out,pilot,stages):
    frozen=load(out/'factdiag6g_prereg.json')['frozen']
    if frozen['model_protocol']!=MODEL_PROTOCOL:raise RuntimeError('估计规则偏离冻结定义')
    features={r['history_id']+'|'+r['candidate_type']:r for r in load(out/'common_features.json')['rows']}
    old,_,rows3,rows4,_,_,_,_=sources(pilot)
    old_h={r['history_id']:r for r in old_histories(out,pilot)}
    role_labels=load(out/'joint_training_roles.json')['role']
    prop_labels=load(out/'g0_new_labels_reparsed.json')['proposition']
    result=[]
    records=[(3,r) for r in rows3 if r['unit'] in ('R-S','S_T','F-D') and not old.excluded(r)]
    records +=[(4,r) for r in rows4 if r['unit'] in ('R-S','S_T','F-D')]
    for batch,row in records:
        hid='old|'+row['unit']+'|'+row['work_id']+'|'+str(row['idx'])
        if hid not in old_h:continue # d=x按冻结规则排除
        h=old_h[hid];key=row_key(batch,row);candidate=h['candidate'];feature=features[hid+'|'+candidate['type']]
        role=role_labels[key]['result']
        if row['unit']=='S_T':prop=(prop_labels[key]['result'] or {}).get('label')
        else:prop=(row.get('propositions') or {}).get('C2',{}).get('label')
        result.append(dict(id=key,structure='literature',project_id=row['work_id'],cluster_id=row['work_id'],
            history_id=hid,candidate_type=candidate['type'],arm=row['condition'],rep=row['rep'],
            phase='old'+str(batch),feature_values=feature['values'],
            **outcomes(row,h['item'],candidate,h['current'],role,prop)))
    plan=load(out/'factdiag6g_materials.json')['plan'];bank={i['item_id']:i for i in plan['items']}
    for stage in stages:
        if stage=='g1_a0':raise RuntimeError('A0不得进入拟合或调参数据')
        rows=load(out/f'formal_{stage}_generations.json');labels=load(out/f'formal_{stage}_labels.json')
        if len(rows)!=plan['counts'][stage]:raise RuntimeError('正式生成尚未完成：'+stage)
        if any(len(labels[k])!=len(rows) for k in ('stance','role')):raise RuntimeError('正式立场或角色标签未齐')
        for row in rows:
            item=bank[row['conflict_id']];key=identity(row);hid=row['source_history_id']
            c=next(c for c in item['candidates'] if c['type']==row['candidate_type'])
            role=labels['role'][key]['result']
            if c.get('proposition'):
                if key not in labels['proposition']:raise RuntimeError('正式命题标签未齐')
                prop=(labels['proposition'][key]['result'] or {}).get('label')
            else:prop='N/A'
            feature=features[hid+'|'+c['type']]
            result.append(dict(id=key,structure='literature' if item['structure']=='G1' else item['structure'],
                project_id=item['work_id'],cluster_id=item.get('pair_id',item['work_id']),
                history_id=hid,candidate_type=c['type'],arm={'S':'base','S+A1':'A1','C':'C'}[row['arm']],
                rep=row['rep'],phase=stage,feature_values=feature['values'],
                **outcomes(row,item,c,row['original'],role,prop,numeric_main=row['path'].startswith('constructed|'))))
    if len(result)!=len({r['id'] for r in result}):raise RuntimeError('联合观测身份重复')
    save(out/'joint_observations.json',dict(feature_names=FEATURE_NAMES,rows=result,
        stages=stages,unknown='按维度边际化；不把未知标签当作零事件或其它类别'))
    print('联合观测连结',len(result),'条',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--pilot',type=Path,required=True);ap.add_argument('--stages',nargs='+',required=True)
    a=ap.parse_args();prepare(a.out,a.pilot,a.stages)
