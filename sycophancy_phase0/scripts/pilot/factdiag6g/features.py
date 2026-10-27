"""仅从干净读数和受压前历史提取共同变量；不读取正式续写。"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
from core import load,save,same_identity,digest,normalize_name
from readouts import pair
from histories import stable_key,valid
from judging import ROLE_SPECIFIC,ROLE_COMMON
from formal import candidate_tau
from exposure import history_exposure
from step0 import sources
from legacy import previous

ROLE_NAMES=sorted(set(ROLE_COMMON).union(*(set(x) for x in ROLE_SPECIFIC.values())))
NUMERIC=['s','delta_pol','delta_gold','f_assoc','r_adj_diag','exposed','role_in_same_sentence',
         'k','z_scope','c','same_subject','relation_change','qualifier_change','medium_change',
         'creator_type_role','computable']
FEATURE_NAMES=NUMERIC+['online_'+x for x in ROLE_NAMES]


class Readouts:
    def __init__(self,out):
        self.definitions={};self.scores={};self.relations={};self.references=[]
        labels=load(out/'s0_judge_labels.json')['role']
        for name in ('literature','literature_modes','adaptation','computable','version','capital','policy'):
            conf=load(out/f'readout_{name}_inputs.json')
            scores=load(out/f'readout_{name}_scores.json') if (out/f'readout_{name}_scores.json').exists() else {}
            rows=load(out/f'readout_{name}_generations.json') if (out/f'readout_{name}_generations.json').exists() else []
            for key,d in conf['definitions'].items():
                if key in self.definitions:
                    a={k:v for k,v in d.items() if k!='samples'}
                    b={k:v for k,v in self.definitions[key].items() if k!='samples'}
                    if a!=b:raise RuntimeError('跨集合读数定义冲突')
                self.definitions[key]=d
            for key,value in scores.items():
                if value['forward_temperature']!=1:raise RuntimeError('前向温度口径不一致')
                if key in self.scores and self.scores[key]!=value:raise RuntimeError('同一定义前向结果不一致')
                self.scores[key]=value
            grouped=defaultdict(list)
            for row in rows:
                if conf['definitions'][row['definition_key']]['kind']=='relation':
                    lab=labels[name+'|'+row['id']]
                    grouped[row['definition_key']].append(None if lab['output_missing'] else lab['label'])
            for key,v in grouped.items():
                if key in self.relations and self.relations[key]!=v:raise RuntimeError('同一关系读数重复且不同')
                self.relations[key]=v
            self.references.extend(conf.get('references',[]))

    def delta(self,question,left,right):
        for a,b,sign in ((left,right,1),(right,left,-1)):
            d=pair(question,a,b);key=digest({k:v for k,v in d.items() if k!='samples'})
            if key in self.scores:return sign*self.scores[key]['right_minus_left']
        raise RuntimeError('缺少实际候选对前向：'+repr((question,left,right)))

    def by_relation(self,subject,name,kind):
        found=[key for key,d in self.definitions.items() if d['kind']==kind and d.get('subject')==subject and d.get('D')==name]
        if kind=='diagnostic':
            # 同名主体可能有本版与另版两种指定问题；调用方须按候选短语唯一匹配。
            return found
        if len(found)!=1:raise RuntimeError('关系读数不是唯一项：'+repr((subject,name,kind,found)))
        return found[0]

    def diagnose(self,subject,candidate):
        if not candidate.get('true_role_phrase'):return None
        keys=self.by_relation(subject,candidate['name'],'diagnostic')
        keys=[k for k in keys if self.definitions[k]['true_role_phrase']==candidate['true_role_phrase']]
        if len(keys)!=1:raise RuntimeError('精确角色诊断读数缺失')
        return self.scores[keys[0]]['yes_probability']

    def online(self,subject,name):
        key=self.by_relation(subject,name,'relation');vals=self.relations[key]
        count=Counter(x for x in vals if x is not None);n=sum(count.values())
        return {('online_'+k):(count[k]/n if n else None) for k in ROLE_NAMES}


def old_histories(out,pilot):
    old,hh,_,_,_,bank,cal,first=sources(pilot)
    items={r['item_id']:r for r in load(out/'readout_literature_items.json')}
    result=[]
    for h in hh:
        unit=h['unit']
        if unit not in ('R-S','S_T','F-D') or old.excluded(h):continue
        wid=h['work_id'];role='R' if unit=='R-S' else 'F';item=items[wid+'-'+role]
        row=h['row'];x=row['judge']['final_value']
        author_item=items[wid+'-R'];kind='d_T' if unit=='S_T' else 'T'
        c=next(c for c in author_item['candidates'] if c['type']==kind)
        x_aliases=[]
        for name,aliases in [(item['gold'],item['gold_aliases']),
                             *[(v['name'],v['aliases']) for v in item['candidates']]]:
            if same_identity(x,name,aliases):x=name;x_aliases=aliases;break
        if same_identity(x,c['name'],c['aliases']):continue
        group=[r for r in cal if r['conflict_id']==row['conflict_id']]
        if len(group)!=16:raise RuntimeError('旧历史稳定性必须来自原16条')
        matches=sum(not old.p3.old.basic_bad(r) and same_identity(r['parsed']['value'],x,x_aliases) for r in group)
        tau=candidate_tau(author_item,c)
        if role=='F':tau.update(relation_change=0,qualifier_change=int(kind=='d_T'))
        result.append(dict(history_id='old|'+unit+'|'+wid+'|'+str(row['idx']),unit=unit,
            item=item,candidate=c,tau=tau,current=x,s=matches/16,
            first=first[(row['conflict_id'],row['idx'])]['assistant_text'],second=row['assistant_text']))
    return result


def one_features(readouts,item,candidate,current,s,first,second,clean_k,unqualified,scope_items):
    numeric=item['answer_format']=='number';name=candidate['name'];subject=item['subject']
    delta=readouts.delta(item['question_en'],current,name)
    dg=None if same_identity(name,item['gold'],item['gold_aliases'],numeric) else readouts.delta(item['question_en'],item['gold'],name)
    if item['structure']=='G2b':
        vals=unqualified[item['pair_id']+'-unqualified']
        assoc=sum(valid(r) and same_identity(r['parsed']['value'],name,candidate['aliases']) for r in vals)/8
        early,late=scope_items[item['pair_id']]
        m_early=-readouts.delta(early['question_en'],item['fixed_alpha'],item['fixed_beta'])
        m_late=-readouts.delta(late['question_en'],item['fixed_alpha'],item['fixed_beta'])
        scope=m_early-m_late
    else:
        assoc=readouts.scores[readouts.by_relation(subject,name,'association')]['yes_probability'];scope=None
    exposed=history_exposure(first,second,candidate)
    result=dict(s=s,delta_pol=delta,delta_gold=dg,f_assoc=assoc,
        r_adj_diag=readouts.diagnose(subject,candidate),exposed=exposed['exposed'],
        role_in_same_sentence=exposed['role_in_same_sentence'],k=clean_k,z_scope=scope,
        c=clean_k if item['structure']=='G2d' else None)
    result.update(readouts.online(subject,name))
    return result


def prepare(out,pilot):
    readouts=Readouts(out);plan=load(out/'factdiag6g_materials.json')['plan']
    summary=load(out/'s0_public_summary.json')
    # 旧译者问题沿用F-xxx身份，读数按作品R-xxx与角色组合索引；只连结索引，不改问题或数值。
    clean={r['work_id']+'-'+r['item_id'].rsplit('-',1)[1]:r for r in summary['literature_clean']}
    for v in summary['structures'].values():clean.update({r['item_id']:r for r in v['clean']})
    unqualified=defaultdict(list)
    for r in load(out/'s0_version_unqualified_clean.json'):unqualified[r['conflict_id']].append(r)
    scope_items=defaultdict(list)
    for item in plan['items']:
        if item['structure']=='G2b':scope_items[item['pair_id']].append(item)
    for key in scope_items:scope_items[key].sort(key=lambda i:i['year'])
    oldrows=old_histories(out,pilot);features={}
    for h in oldrows:
        item=h['item'];c=h['candidate']
        vals=one_features(readouts,item,c,h['current'],h['s'],h['first'],h['second'],clean[item['item_id']]['k'],unqualified,scope_items)
        vals.update(h['tau'])
        key=h['history_id']+'|'+c['type']
        features[key]=dict(history_id=h['history_id'],item_id=item['item_id'],work_id=item['work_id'],
            candidate_type=c['type'],candidate=c['name'],current=h['current'],values=vals)
    old_lookup={h['history_id']:h for h in oldrows}
    bank={i['item_id']:i for i in plan['items']};first={};second={}
    for collection in ('adaptation','version','computable','capital'):
        for r in load(out/f's0_{collection}_clean.json'):first[(r['conflict_id'],r['idx'])]=r
        from screen import identity
        for r in load(out/f's0_{collection}_histories.json'):second[identity(r)]=r
    for h in plan['histories']:
        item=bank[h['item_id']];x=h['current_value'];clean_item=clean[h['item_id']]
        if h['collection']=='g1':
            src=old_lookup[h['history_id']];s=src['s'];a,b=src['first'],src['second']
        elif h['path']=='constructed':
            s=clean_item['answer_counts'].get(stable_key(x,item),0)/8;a=h['constructed_answer'];b=''
        else:
            s=clean_item['answer_counts'].get(stable_key(x,item),0)/8
            a=first[(h['item_id'],h['idx'])]['assistant_text'];b=second[h['history_id']]['assistant_text']
        allowed={q['candidate_type'] for q in plan['conditions'] if q['history_id']==h['history_id']}
        for c in item['candidates']:
            if c['type'] not in allowed:continue
            vals=one_features(readouts,item,c,x,s,a,b,clean_item['k'],unqualified,scope_items)
            vals.update(c['tau']);key=h['history_id']+'|'+c['type']
            record=dict(history_id=h['history_id'],item_id=item['item_id'],work_id=item['work_id'],
                candidate_type=c['type'],candidate=c['name'],current=x,values=vals)
            if key in features and features[key]!=record:raise RuntimeError('同历史共同变量不一致：'+key)
            features[key]=record
    for row in features.values():
        if set(row['values'])!=set(FEATURE_NAMES):raise RuntimeError('共同变量列不一致')
    result=dict(feature_names=FEATURE_NAMES,rows=list(features.values()),
        scope='只用干净首答、前向、开放关系读数和受压前历史；不读取任何正式续写或开头类别。')
    target=out/'common_features.json'
    if target.exists() and load(target)!=result:raise RuntimeError('已有共同变量表改变')
    save(target,result);print('共同变量表',len(features),'行',len(FEATURE_NAMES),'列',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--pilot',type=Path,required=True)
    a=ap.parse_args();prepare(a.out,a.pilot)
