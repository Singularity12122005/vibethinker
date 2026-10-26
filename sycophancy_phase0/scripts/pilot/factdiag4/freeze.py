"""材料阅读放行后创建预注册；本脚本不加载模型权重。"""
from design import *
import argparse,json
from collections import Counter


def freeze(previous,out,plan,commit):
    if (out/'factdiag4_prereg.json').exists():raise RuntimeError('预注册已存在，禁止覆盖')
    if not re.fullmatch(r'[0-9a-f]{40}',commit):raise RuntimeError('缺少实际提交号')
    mat=load(out/'factdiag4_materials.json')
    if mat.get('semantic_review_status')!='代理逐条阅读，非人工':raise RuntimeError('构造语义核对尚未结束')
    oldreg=load(previous/'factdiag3_prereg.json');oldrules=oldreg['frozen']['rules']
    for k,v in oldrules['templates'].items():
        if TEMPLATES[k]!=v:raise RuntimeError('复用模板不同于第三批冻结值：'+k)
    for key,value in [('stance_prompt',p3.old.JUDGE_PROMPT),('proposition_prompt',p3.PROPOSITION_PROMPT)]:
        if oldrules[key]!=value:raise RuntimeError('评审提示不同于第三批冻结值')
    from transformers import AutoTokenizer
    from sycophancy_phase0.inference.templates import TurnBuilder
    tok=AutoTokenizer.from_pretrained('/output/sycophancy-phase0/model');builder=TurnBuilder(lambda t:tok.encode(t,add_special_tokens=False),'instruct')
    hs=load(out/'active_histories.json');cs=load(out/'constructed_histories.json')
    if Counter(h['unit'] for h in hs)!=dict(**{'R-S':60,'L':60,'F-D':39,'S_T':31}):raise RuntimeError('实际历史不符合39段修订')
    plans={ex:tasks_for(builder,hs,cs,mat['materials'],ex) for ex in ('B','A','C')}
    pilot=[]
    for c,ns in C_COUNTS.items():
        for u in ns:
            selected=sorted({t['work_id'] for t in plans['C'] if t['unit']==u and t['condition']==c})[:3]
            pilot.extend(p3.identity(t) for t in plans['C'] if t['unit']==u and t['condition']==c and t['work_id'] in selected)
    metadata=lambda h:dict(work_id=h['work_id'],unit=h['unit'],idx=h['row']['idx'],variant=h.get('variant'),history_sha256=digest({k:h['row'][k] for k in ('prompt_ids','assistant_ids','assistant_text')}))
    text=plan.read_text(encoding='utf-8-sig')
    files=['common.py','design.py','runtime4.py']
    frozen=dict(implementation_commit=commit,step0_commit='4f78627',materials_sha256=digest(mat),
        execution_spec=text,execution_spec_sha256=hashlib.sha256(text.encode()).hexdigest(),
        templates=TEMPLATES,template_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in TEMPLATES.items()},
        stance_prompt=p3.old.JUDGE_PROMPT,proposition_prompt=p3.PROPOSITION_PROMPT,
        stance_prompt_sha256=hashlib.sha256(p3.old.JUDGE_PROMPT.encode()).hexdigest(),proposition_prompt_sha256=hashlib.sha256(p3.PROPOSITION_PROMPT.encode()).hexdigest(),
        generation_code_sha256={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in files},
        history_sets=dict(active=[metadata(h) for h in hs],constructed=[metadata(h) for h in cs]),task_counts={ex:len(ts) for ex,ts in plans.items()},
        C_pilot_task_ids=pilot,C_pilot_rule='每个执行器×单元，按作品号最前3个有历史的作品取全部计划请求；这些请求只生成一次，计入原总数。',
        generation=dict(temperature=.7,max_new_tokens=1024,batch=16,dtype='bf16',attention='sdpa',experts='grouped_mm',seed=SEED,
            seed_rule='SHA256(20261104|conflict_id|idx|path|arm|rep|t|phase)，前8字节小端取63位。',prefix='前缀词元追加到助手生成起点；1024只计新采样；完整回答解析评审。',sort='同作品、上一轮长度、任务身份'),
        budget=dict(warning=1200000,pause=1500000,automatic_reduction=False,scope='只计本批主模型新采样，不计原历史或强制前缀；评审单列。'),
        amendments=mat.get('approved_amendments',[])+['步骤0保留原42段和64条复核；第四批及旧对应比较仅39段，不补生成。','扩展明确姓名形式，旧标签不回改。','方法选择按经验达标；严格状态单列。','120万预警，150万暂停请示，不自动删格。'])
    save(out/'factdiag4_prereg.json',dict(frozen=frozen,frozen_sha256=digest(frozen)))
    print(json.dumps(dict(task_counts=frozen['task_counts'],pilot_C=len(pilot),frozen=True),ensure_ascii=False))


if __name__=='__main__':
    from collections import Counter
    ap=argparse.ArgumentParser();ap.add_argument('--previous',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--commit',required=True);a=ap.parse_args();freeze(a.previous,a.out,a.plan,a.commit)
