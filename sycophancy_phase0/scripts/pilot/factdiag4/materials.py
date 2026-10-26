"""冻结前的姓名形式审计与构造历史；仅用CPU，语义审核另行逐条完成。"""
from common import *
from source_audit import FICTIONAL,SEARCHES,DATE
from collections import Counter
import argparse,copy


def replace_names(text,aliases,target):
    # 单次最长优先匹配，避免第二次替换新植入的姓名。
    aliases=sorted(set(aliases),key=lambda x:(-len(x),x))
    pattern=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(x) for x in aliases)+r')(?!\w)',re.I)
    changes=[]
    def sub(match):
        old=match.group();stem=re.sub(r"['’]s$",'',old,flags=re.I)
        # Common为普通词的出现不替换；姓名用法由逐条阅读确认。
        if stem=='common':return old
        suffix=old[len(stem):]
        new=(target if len(stem.split())>1 else target.split()[-1])+suffix
        changes.append(dict(start=match.start(),old=old,new=new))
        return new
    return pattern.sub(sub,text),changes


def make(previous,out):
    hs=source_histories(previous);oldmat=load(previous/'factdiag3_materials.json');ms=copy.deepcopy(oldmat)
    bank={m['work_id']:m for m in ms}
    first={(r['conflict_id'],r['idx']):r for r in load(previous.parent/'factdiag2_20261029/calibration_t1.json')}
    audits=[]
    for m in ms:
        old=next(x for x in oldmat if x['work_id']==m['work_id'])
        m['F']['gold_aliases']=forms(old['F']['gold_aliases'])
        m['R']['d_aliases']=m['F']['gold_aliases'][:]
        m['d_T_aliases']=forms(old['d_T_aliases'])
        if m['work_id'] in FICTIONAL:
            m['fictional_name']=FICTIONAL[m['work_id']];m['fictional_aliases']=forms([m['fictional_name']]);m['fictional_search']=SEARCHES[m['work_id']]
        m['alias_amendment']=dict(source=m['F']['source_g'],rule='明确姓名的首字母缩写、中间名省略、姓氏与所有格形式；只在第四批材料生效。',added_gold=[x for x in m['F']['gold_aliases'] if x not in old['F']['gold_aliases']],added_dT=[x for x in m['d_T_aliases'] if x not in old['d_T_aliases']])
        if m['work_id']=='R-002':m['alias_amendment']['approved_example']='B. Jowett = Benjamin Jowett；用户确认排除F-D的4、10、11段，旧文件不改。'
        groups=[m['F']['gold_aliases'],m['d_T_aliases']]+([m['fictional_aliases']] if m.get('fictional_name') else [])
        for a,b in itertools.combinations(groups,2):
            if {p3.old.normalize_entity(x) for x in a}&{p3.old.normalize_entity(x) for x in b}:raise RuntimeError('不同人别名碰撞：'+m['work_id'])
    for h in hs:
        if h['unit'] not in ('F-D','S_T'):continue
        m=bank[h['work_id']];r=first[(h['row']['conflict_id'],h['row']['idx'])]
        parsed=p3.old.parse_final(r['assistant_text'],m['F']);old_correct=r['parsed']['value']==m['F']['gold'];new_correct=parsed['value']==m['F']['gold']
        audits.append(dict(work_id=h['work_id'],unit=h['unit'],idx=r['idx'],raw_value=p3.old.raw_final_value(r['assistant_text']),old_value=r['parsed']['value'],new_value=parsed['value'],same_identity=new_correct,approved_exclusion=excluded(h)))
        if h['unit']=='F-D' and new_correct and not excluded(h):raise RuntimeError('发现新的F-D误纳，停止报告：'+str(audits[-1]))
        if h['unit']=='S_T' and not new_correct:raise RuntimeError('S_T首答无法按补充别名确认：'+str(audits[-1]))
    candidates=[]
    for h in hs:
        if h['unit']!='S_T' or h['work_id'] not in FAMILY_B:continue
        wid=h['work_id'];m=bank[wid];row=h['row'];r1=first[(row['conflict_id'],row['idx'])]
        for variant,target in [('H_adj',m['d_T']),('H_fab',m['fictional_name'])]:
            aliases=m['d_T_aliases'] if variant=='H_adj' else m['fictional_aliases']
            existing=mention(r1['assistant_text'],aliases) or mention(row['assistant_text'],aliases)
            t1,c1=replace_names(r1['assistant_text'],m['F']['gold_aliases'],target)
            t2,c2=replace_names(row['assistant_text'],m['F']['gold_aliases'],target)
            candidates.append(dict(work_id=wid,idx=row['idx'],layer=FAMILY_B[wid],variant=variant,target=target,
                existing_target=existing,source_first=r1,source_history=h,t1=t1,t2=t2,changes=[c1,c2],
                requires_common_review=wid=='R-004',status='excluded_existing_target' if existing else 'pending_semantic_review'))
    n=Counter(x['work_id'] for x in candidates if x['variant']=='H_adj')
    if n!={'R-002':6,'R-004':6,'R-007':6,'R-005':3,'R-006':3}:raise RuntimeError('实验B基底不是冻结24段：'+str(n))
    save(out/'construction_candidates.json',candidates)
    save(out/'factdiag4_materials.json',dict(materials=ms,alias_form_audit=audits,source_histories=193,active_histories=190,exclusions=[dict(work_id=w,idx=j,unit='F-D') for w,j in sorted(EXCLUDED)],date=DATE,semantic_review_status='pending'))
    print(Counter(x['status'] for x in candidates));print('别名形式审计完成：',len(audits),'条，未发现额外误纳。')


def finalize(previous,out,review_path):
    from transformers import AutoTokenizer
    from sycophancy_phase0.inference.templates import TurnBuilder
    from sycophancy_phase0.constants import IM_END
    tok=AutoTokenizer.from_pretrained('/output/sycophancy-phase0/model')
    builder=TurnBuilder(lambda t:tok.encode(t,add_special_tokens=False),'instruct')
    candidates=load(out/'construction_candidates.json');reviews=load(review_path)
    rb={(r['work_id'],r['idx'],r['variant']):r for r in reviews}
    if len(rb)!=len(candidates) or len(rb)!=len(reviews):raise RuntimeError('必须逐变体完成语义阅读')
    mat=load(out/'factdiag4_materials.json');bank={m['work_id']:m for m in mat['materials']};accepted=[];public=[]
    for x in candidates:
        key=(x['work_id'],x['idx'],x['variant']);review=rb[key];h=x['source_history'];old=h['row'];r1=x['source_first'];m=bank[x['work_id']]
        for correction in review.get('pronoun_corrections',[]):
            field=correction['field'];before=correction['before'];after=correction['after']
            if field not in ('t1','t2') or x[field].count(before)!=1:raise RuntimeError('代词修正定位不唯一：'+str(key))
            # 清单保留含上下文的原片段与改后片段，逐条阅读已确认指代译者。
            x[field]=x[field].replace(before,after)
        if review['decision'] not in ('accept','exclude'):raise RuntimeError('无有效语义判断')
        if x['existing_target'] and review['decision']!='exclude':raise RuntimeError('原含替换名必须排除')
        if review['decision']=='accept':
            if not all(x['changes']):raise RuntimeError('两轮必须都有替换')
            for t in (x['t1'],x['t2']):
                if not mention(t,[x['target'],x['target'].split()[-1]]):raise RuntimeError('替换名未出现')
                residual=[a for a in m['F']['gold_aliases'] if mention(t,[a])]
                if residual and not (x['work_id']=='R-004' and all(a.casefold() in ('common',"common's",'common’s') for a in residual) and review.get('common_ordinary_only')):raise RuntimeError('残余真实姓名：'+str(key)+str(residual))
            expected=builder.next_turn_ex(r1['prompt_ids'],r1['assistant_ids'],old['user_text'])[0]
            if expected!=old['prompt_ids']:raise RuntimeError('原第二轮词元与重建不符：'+str(key))
            y1=tok.encode(x['t1'],add_special_tokens=False)+[IM_END];y2=tok.encode(x['t2'],add_special_tokens=False)+[IM_END]
            new=copy.deepcopy(old);new.update(prompt_ids=builder.next_turn_ex(r1['prompt_ids'],y1,old['user_text'])[0],assistant_ids=y2,assistant_text=x['t2'],original=x['target'],original_raw=x['target'],n_new_tokens=len(y2))
            item=dict(work_id=x['work_id'],unit='B',variant=x['variant'],layer=x['layer'],row=new,first_user_text=r1['user_text'],first_assistant_text=x['t1'])
            accepted.append(item)
            sha=digest({k:new[k] for k in ('prompt_ids','assistant_ids','assistant_text')})
        else:sha=None
        public.append(dict(work_id=x['work_id'],idx=x['idx'],variant=x['variant'],target=x['target'],decision=review['decision'],reason=review['reason'],common_ordinary_only=review.get('common_ordinary_only',False),history_sha256=sha,
            replacement_mapping=dict(original=m['F']['gold'],replacement=x['target'],full_name_rule='多词别名→全名，单词别名→姓氏；所有格保留'),replacement_occurrences=x['changes'],
            pronoun_corrections=review.get('pronoun_corrections',[]),has_specific_facts=review['has_specific_facts'],specific_fact_excerpt=review.get('specific_fact_excerpt'),semantic_note=review.get('semantic_note')))
    mat['semantic_review_status']='代理逐条阅读，非人工';mat['construction_review']=public
    mat['approved_amendments']=['仅修正指向替换名的性别代词，不润色其他文字。','排除文本内部未被撤回的矛盾及名字之外的原译者专属事实；年代、版本、生平等细节不修补。','按作品报告构造基底剩余数；不足3条仍如实报告，不补历史。']
    mat['construction_remaining_by_work']={w:dict(H_adj=sum(h['work_id']==w and h['variant']=='H_adj' for h in accepted),H_fab=sum(h['work_id']==w and h['variant']=='H_fab' for h in accepted)) for w in FAMILY_B}
    save(out/'constructed_histories.json',accepted);save(out/'factdiag4_materials.json',mat)
    save(out/'active_histories.json',[h for h in source_histories(previous) if not excluded(h)])
    print('构造准入',Counter(x['variant'] for x in accepted),'计划B续写',sum(8 if x['variant']=='H_adj' else 16 for x in accepted))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['prepare','finalize']);ap.add_argument('--previous',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--review',type=Path);a=ap.parse_args()
    make(a.previous,a.out) if a.stage=='prepare' else finalize(a.previous,a.out,a.review)
