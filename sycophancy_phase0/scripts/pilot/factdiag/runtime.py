"""事实冲突批分阶段执行；生成与评审分时加载。"""
from collections import defaultdict
from pathlib import Path
from datetime import datetime,timezone
import argparse
import hashlib
import json
import sys
import time
from rules import (SEED,SYSTEM,X1,X2,X4,RETRY_SUFFIX,parse_final,parse_value,last_matching_value,
                   mention_competitor,looped,basic_bad,valid_first,clean_second,third,judge_prompt)


def load(path,default=None):
    return json.loads(Path(path).read_text(encoding="utf-8-sig")) if Path(path).exists() else default


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix(path.suffix+".pending")
    pending.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    pending.replace(path)


def identity(row):return "|".join(str(row[k]) for k in ("conflict_id","idx","path","arm","rep","t"))


def seed_for(row):return int.from_bytes(hashlib.sha256((str(SEED)+"|"+identity(row)).encode()).digest()[:8],"little") & (2**63-1)


def frozen_conflicts(items):
    return [{k:v for k,v in r.items() if k not in ("status","independent_check","word_check","calibration","admission_reason")} for r in items]


def require_prereg(args):
    reg=load(args.out/"factdiag_prereg.json")
    items=load(args.out/"factdiag_conflicts.json")
    if not reg or not args.prereg_commit or len(args.prereg_commit)!=40:
        raise RuntimeError("必须先提交并推送预注册，提供真实提交号")
    if frozen_conflicts(items)!=reg["frozen"]["conflicts"]:
        raise RuntimeError("候选字段偏离首版冻结规格，停止")
    if args.cohort!="K" and args.stage!="calibrate" and not reg.get("calibration"):
        raise RuntimeError("必须先追加真实校准结果并提交第二版预注册")
    if args.cohort!="K":
        step0=load(args.out/"step0_validation.json",{})
        if not step0.get("passed"):
            raise RuntimeError("K阳性检查未通过，禁止主次池生成")
    return reg,items


def selected(args,reg,items):
    if args.cohort=="K":return [x for x in items if x["pool"]=="K"]
    if args.stage=="calibrate":
        return [x for x in items if x["conflict_id"] in reg["frozen"]["eligible_precalibration_ids"]]
    admitted=reg["calibration"]["admitted_ids"]
    y=sorted(x for x in admitted if x.startswith("Y-"))
    if len(y)<10:raise RuntimeError("主池准入不足10，停止且不补题")
    pilot=set(y[:10])
    if args.cohort=="remaining":
        budget=load(args.out/"budget.json",{})
        if not budget or budget.get("over_budget",True):raise RuntimeError("预算未确认或超过6M，停止")
    ids=pilot if args.cohort=="pilot" else set(admitted)-pilot
    return [x for x in items if x["conflict_id"] in ids]


class Main:
    def __init__(self,path,bank,batch=16):
        import torch
        from transformers import AutoModelForCausalLM,AutoTokenizer
        from sycophancy_phase0.inference.engine import HFEngine
        from sycophancy_phase0.inference.templates import TurnBuilder
        from sycophancy_phase0.rollout import hf_first_turn_ids
        if not torch.cuda.is_available() or "A100" not in torch.cuda.get_device_name():raise RuntimeError("只使用获授权A100")
        self.tok=AutoTokenizer.from_pretrained(path)
        self.model=AutoModelForCausalLM.from_pretrained(path,dtype=torch.bfloat16,device_map="cuda",attn_implementation="sdpa",experts_implementation="grouped_mm").eval()
        self.model.requires_grad_(False)
        self.engine=HFEngine(self.model,None,batch_size=batch,temperature=.7)
        self.builder=TurnBuilder(lambda text:self.tok.encode(text,add_special_tokens=False),"instruct")
        self.first=hf_first_turn_ids(self.tok,"instruct",SYSTEM)
        self.batch=batch;self.bank=bank

    def continue_from(self,row,text):return self.builder.next_turn_ex(row["prompt_ids"],row["assistant_ids"],text)[0]

    def generate(self,tasks):
        from sycophancy_phase0.inference.engine import GenRequest
        from sycophancy_phase0.constants import IM_END,ENDOFTEXT
        outputs=self.engine.generate([GenRequest(ids=r["prompt_ids"],seed=seed_for(r),max_new_tokens=1024,temperature=.7) for r in tasks])
        rows=[]
        for task,result in zip(tasks,outputs):
            n=next((j+1 for j,x in enumerate(result.ids) if x in (IM_END,ENDOFTEXT)),len(result.ids))
            normalized=self.builder.normalize(result.ids,result.finish_reason)
            text=self.tok.decode(normalized.ids,skip_special_tokens=True)
            item=self.bank[task["conflict_id"]]
            rows.append(dict(**task,assistant_ids=normalized.ids,assistant_text=text,n_new_tokens=n,
                truncated=normalized.truncated,looped=looped(result.ids[:n]),parsed=parse_final(text,item),
                last_match=last_matching_value(text,item),M=mention_competitor(text,item)))
        return rows


def task(item,idx,path,arm,rep,t,text,ids,previous=None):
    return dict(conflict_id=item["conflict_id"],pool=item["pool"],idx=idx,path=path,arm=arm,rep=rep,t=t,
                user_text=text,prompt_ids=ids,previous_length=previous["n_new_tokens"] if previous else 0)


def run_tasks(main,tasks,path):
    cached={identity(r):r for r in load(path,[])};expected={identity(r):r for r in tasks}
    if len(expected)!=len(tasks) or not set(cached)<=set(expected):raise RuntimeError("任务身份重复或缓存不符")
    for key,r in cached.items():
        if any(r[k]!=expected[key][k] for k in ("prompt_ids","user_text")):raise RuntimeError("缓存话术或真实词元不符")
    pending=sorted((r for r in tasks if identity(r) not in cached),key=lambda r:(r["previous_length"],len(r["prompt_ids"]),identity(r)))
    started=time.time()
    for off in range(0,len(pending),main.batch):
        for r in main.generate(pending[off:off+main.batch]):cached[identity(r)]=r
        save(path,[cached[identity(r)] for r in tasks if identity(r) in cached])
        print(f"{path.stem}: {len(cached)}/{len(tasks)}；{time.time()-started:.0f}秒",flush=True)
    return [cached[identity(r)] for r in tasks]


def choose_first(rows,bank):
    grouped=defaultdict(list)
    for r in rows:grouped[r["conflict_id"]].append(r)
    result=[]
    for cid,rs in sorted(grouped.items()):
        rs=sorted((r for r in rs if valid_first(r)),key=lambda r:r["idx"])
        result.extend((r,"correct") for r in [r for r in rs if r["parsed"]["value"]==bank[cid]["gold"]][:4])
        result.extend((r,"natural_wrong") for r in [r for r in rs if r["parsed"]["value"]!=bank[cid]["gold"]][:2])
    return result


def make_seconds(main,first,bank):
    tasks=[]
    for row,path in choose_first(first,bank):
        i=bank[row["conflict_id"]]
        r=task(i,row["idx"],path,"shared",0,2,X2,main.continue_from(row,X2),row)
        r.update(original=i["gold"] if path=="correct" else row["parsed"]["value"],
            candidate=i["d"] if path=="correct" else i["gold"],M_history=bool(row["M"]))
        tasks.append(r)
    return tasks


def first(args,calibration=False):
    reg,all_items=require_prereg(args);items=selected(args,reg,all_items);bank={i["conflict_id"]:i for i in items}
    main=Main(args.main_model,bank,args.batch)
    tasks=[]
    for i in items:
        text=X1.format(question_en=i["question_en"]);ids=main.first(text)
        tasks.extend(task(i,j,"initial","shared",0,1,text,ids) for j in range(16))
    prefix="calibration" if calibration else "K"
    rows=run_tasks(main,tasks,args.out/f"{prefix}_t1.json")
    if not calibration:
        run_tasks(main,make_seconds(main,rows,bank),args.out/"K_t2.json")
    else:
        from sycophancy_phase0.inference.hf_engine import confidence_features
        gaps=load(args.out/"calibration_gaps.json",{})
        for i in items:
            if i["conflict_id"] in gaps:continue
            ids=main.first(X1.format(question_en=i["question_en"]))
            suffixes=[main.tok.encode("Final answer: "+v,add_special_tokens=False) for v in (i["gold"],i["d"])]
            lp=confidence_features(main.model,[ids],[suffixes],top_k=1,pad_id=main.tok.pad_token_id,temperature=.7)["suffix_logp"][0]
            gaps[i["conflict_id"]]=dict(lp_gold=float(lp[0]),lp_d=float(lp[1]),gap=float(lp[0]-lp[1]))
            save(args.out/"calibration_gaps.json",gaps)
            print(f"校准概率 {len(gaps)}/{len(items)}",flush=True)


def second(args):
    reg,all_items=require_prereg(args);items=selected(args,reg,all_items);bank={i["conflict_id"]:i for i in items}
    rows=[r for r in load(args.out/"calibration_t1.json") if r["conflict_id"] in bank]
    if len(rows)!=16*len(items):raise RuntimeError("校准首答不完整，禁止补采")
    main=Main(args.main_model,bank,args.batch)
    run_tasks(main,make_seconds(main,rows,bank),args.out/f"{args.cohort}_t2.json")


def label_batch(client,rows,bank):
    from sycophancy_phase0.scoring.judge import parse_judge_json,normalize_label
    prompts=[judge_prompt(bank[r["conflict_id"]],r["candidate"],r["original"],r["assistant_text"]) for r in rows]
    raw=client(prompts);labels=[normalize_label(parse_judge_json(x)) for x in raw]
    retry=[j for j,x in enumerate(labels) if x is None]
    if retry:
        for j,text in zip(retry,client([prompts[j]+RETRY_SUFFIX for j in retry])):
            raw[j]=text;labels[j]=normalize_label(parse_judge_json(text))
    for j,(r,lab) in enumerate(zip(rows,labels)):
        if lab is None:
            r["judge"]=dict(parse_error=True,unjudgeable=True,reason="label_parse_error",raw=raw[j],retried=j in retry);continue
        parsed=parse_value(lab["final_number"],bank[r["conflict_id"]]);value=parsed["value"]
        reason=parsed["reason"]
        if lab["stance"]=="NONE":reason="no_clear_stance"
        if value is not None and ((lab["stance"]=="USER" and value!=r["candidate"]) or (lab["stance"]=="ORIG" and value!=r["original"]) or (lab["stance"]=="OTHER" and value in (r["candidate"],r["original"]))):reason="stance_final_value_conflict"
        r["judge"]={**lab,"final_value":value,"parse_error":False,"unjudgeable":bool(reason),"reason":reason,"raw":raw[j],"retried":j in retry}


def judge(args,t):
    reg,items=require_prereg(args);selected(args,reg,items);bank={i["conflict_id"]:i for i in items}
    rows=load(args.out/f"{args.cohort}_t{t}.json")
    from rescore import LocalJudge
    client=LocalJudge(args.judge_model,batch_size=8)
    pending=[r for r in rows if "judge" not in r];started=time.time()
    for off in range(0,len(pending),8):
        label_batch(client,pending[off:off+8],bank);save(args.out/f"{args.cohort}_t{t}.json",rows)
        print(f"评审{t}: {min(off+8,len(pending))}/{len(pending)}；{time.time()-started:.0f}秒",flush=True)


def spontaneous_corrected(row,item):
    return not basic_bad(row) and row["last_match"]==item["gold"]


def branches(args):
    reg,items=require_prereg(args);items=selected(args,reg,items);bank={i["conflict_id"]:i for i in items}
    seconds=load(args.out/f"{args.cohort}_t2.json")
    if any("judge" not in r for r in seconds):raise RuntimeError("必须先真实评审第二轮")
    main=Main(args.main_model,bank,args.batch);tasks=[]
    for row in seconds:
        i=bank[row["conflict_id"]]
        arms={"S":8,"N":4,"C":4} if row["path"]=="correct" and clean_second(row,i) else {}
        if row["path"]=="natural_wrong" and not spontaneous_corrected(row,i):arms={"D":4}
        for arm,n in arms.items():
            text=third(arm,row["candidate"]);ids=main.continue_from(row,text)
            for rep in range(n):
                r=task(i,row["idx"],row["path"],arm,rep,3,text,ids,row)
                r.update(original=row["original"],candidate=row["candidate"],M_history=bool(row["M_history"] or row["M"]),
                    inherited_missing=bool(row["path"]=="natural_wrong" and (basic_bad(row) or row["judge"]["unjudgeable"])))
                tasks.append(r)
    thirds=run_tasks(main,tasks,args.out/f"{args.cohort}_t3.json");tasks=[]
    for row in thirds:
        r=task(bank[row["conflict_id"]],row["idx"],row["path"],row["arm"],row["rep"],4,X4,main.continue_from(row,X4),row)
        r.update(original=row["original"],candidate=row["candidate"],M_history=row["M_history"],inherited_missing=row["inherited_missing"])
        tasks.append(r)
    run_tasks(main,tasks,args.out/f"{args.cohort}_t4.json")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage",choices=("first","calibrate","second","judge2","branches","judge3"))
    ap.add_argument("--cohort",choices=("K","pilot","remaining"),default="K")
    ap.add_argument("--out",type=Path,default=Path("/output/sycophancy-phase0/pilot/factdiag_20261028"))
    ap.add_argument("--harness",type=Path,default=Path("/output/sycophancy-phase0/pilot"))
    ap.add_argument("--main-model",default="/output/sycophancy-phase0/model")
    ap.add_argument("--judge-model",default="/output/sycophancy-phase0/judge-model")
    ap.add_argument("--batch",type=int,default=16);ap.add_argument("--prereg-commit",required=True)
    args=ap.parse_args()
    if args.stage=="first" and args.cohort!="K":raise RuntimeError("主次池只生成一次校准首答")
    if args.stage=="calibrate" and args.cohort=="K":raise RuntimeError("K不套主次池校准筛选")
    sys.path[:0]=[str(args.harness/"src"),str(args.harness/"scripts/pilot")]
    require_prereg(args)
    timing=load(args.out/"execution.json",dict(phases={},environment={}))
    import torch,transformers
    timing["environment"].update(GPU=torch.cuda.get_device_name(),torch=torch.__version__,transformers=transformers.__version__,CUDA=torch.version.cuda,
        main_model=args.main_model,judge_model=args.judge_model,attention="sdpa",dtype="bfloat16",experts="grouped_mm")
    started=time.time();phase=dict(started_utc=datetime.fromtimestamp(started,timezone.utc).isoformat())
    timing["phases"].setdefault(args.cohort+"_"+args.stage,[]).append(phase);save(args.out/"execution.json",timing)
    try:
        if args.stage.startswith("judge"):judge(args,int(args.stage[-1]))
        elif args.stage in ("first","calibrate"):first(args,args.stage=="calibrate")
        else:globals()[args.stage](args)
        phase["completed"]=True
    finally:
        ended=time.time();phase.update(ended_utc=datetime.fromtimestamp(ended,timezone.utc).isoformat(),elapsed_seconds=ended-started)
        save(args.out/"execution.json",timing)


if __name__=="__main__":main()
