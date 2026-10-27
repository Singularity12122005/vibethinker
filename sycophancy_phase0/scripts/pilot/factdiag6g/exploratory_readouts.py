"""探索性读数分布和冻结预测诊断；只读已有聚合，不拟合或修改主结果。"""
from pathlib import Path
from collections import defaultdict, Counter
import argparse
import json
import numpy as np

FEATURES = ('delta_gold', 'delta_pol', 'f_assoc', 's', 'k', 'z_scope', 'c')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def quantiles(values, weights, qs=(.05, .25, .5, .75, .95)):
    order = np.argsort(values)
    v, w = values[order], weights[order]
    c = np.cumsum(w) / np.sum(w)
    return [float(v[min(np.searchsorted(c, q), len(v)-1)]) for q in qs]


def arrays(rows, key):
    known = [r for r in rows if r['values'].get(key) is not None]
    if not known:
        return None
    counts = Counter(r['work_id'] for r in known)
    v = np.array([r['values'][key] for r in known], dtype=float)
    w = np.array([1/counts[r['work_id']] for r in known], dtype=float)
    clusters = sorted({r['cluster_id'] for r in known})
    ci = np.array([clusters.index(r['cluster_id']) for r in known])
    return known, v, w, ci, clusters


def resampled_weights(w, ci, nclusters, rng=None):
    if nclusters < 2:
        return None
    rng = np.random.default_rng(20261111) if rng is None else rng
    indices = rng.integers(nclusters, size=(2000, nclusters))
    multiplicities = np.stack([np.bincount(x, minlength=nclusters) for x in indices])
    z = multiplicities[:, ci] * w[None, :]
    return z / z.sum(1)[:, None]


def interval(values):
    return None if values is None else np.quantile(values, [.025, .975]).tolist()


def distribution(rows, key):
    a = arrays(rows, key)
    if a is None:
        return dict(status='不适用或无读数', rows=len(rows), known=0, missing=len(rows))
    known, v, w, ci, clusters = a
    b = resampled_weights(w, ci, len(clusters)); wn = w / w.sum()
    threshold = 0 if key in ('delta_gold', 'delta_pol') else .875 if key == 's' else None
    threshold_event = (v > 0) if threshold == 0 else (v >= .875) if threshold is not None else None
    return dict(status='可描述', rows=len(rows), known=len(known), missing=len(rows)-len(known),
        projects=len({r['work_id'] for r in known}), clusters=len(clusters),
        project_equal=dict(mean=float(wn@v), mean_ci95=interval(None if b is None else b@v),
            quantiles=dict(zip(('q05','q25','median','q75','q95'),quantiles(v,w))), minimum=float(v.min()), maximum=float(v.max()),
            threshold=threshold, threshold_relation='>' if threshold==0 else '>=',
            threshold_rate=None if threshold_event is None else float(wn@threshold_event),
            threshold_rate_ci95=None if threshold_event is None else interval(None if b is None else b@threshold_event)),
        history_equal=dict(mean=float(v.mean()),quantiles=dict(zip(('q05','q25','median','q75','q95'),quantiles(v,np.ones(len(v)))))),
        values_by_history=[dict(history_id=r['history_id'],work_id=r['work_id'],cluster_id=r['cluster_id'],value=r['values'][key]) for r in known])


def overlap(reference, target, key):
    a, b = arrays(reference,key), arrays(target,key)
    if a is None or b is None:
        return dict(status='不适用或无读数')
    _, av, aw, ai, ac = a; _, bv, bw, bi, bc = b
    aw = aw/aw.sum(); bw = bw/bw.sum()
    grid = np.unique(np.concatenate([av,bv]))
    ae = av[:,None] <= grid; be = bv[:,None] <= grid
    def metrics(xw,yw):
        al,au = quantiles(av,xw,(.05,.95)); bl,bu = quantiles(bv,yw,(.05,.95))
        union = max(au,bu)-min(al,bl)
        ov = float(max(0,min(au,bu)-max(al,bl))/union) if union else float(al==bl)
        coverage=float(yw@((bv>=al)&(bv<=au)))
        ks=float(np.max(np.abs(xw@ae-yw@be)))
        return ov,coverage,ks
    point=metrics(aw,bw)
    rng=np.random.default_rng(20261111)
    ab=resampled_weights(aw,ai,len(ac),rng)
    bb=resampled_weights(bw,bi,len(bc)) if ac==bc else resampled_weights(bw,bi,len(bc),rng)
    # 同项目集合配对重抽，不同结构独立抽取项目簇；不据此调整预测。
    boots=None if ab is None or bb is None else np.array([metrics(xw,yw) for xw,yw in zip(ab,bb)])
    return dict(status='探索性描述',reference_projects=len({r['work_id'] for r in a[0]}),
        target_projects=len({r['work_id'] for r in b[0]}),target_clusters=len(bc),
        reference_central90=quantiles(av,aw,(.05,.95)),target_central90=quantiles(bv,bw,(.05,.95)),
        central90_interval_overlap=dict(point=point[0],ci95=interval(None if boots is None else boots[:,0])),
        target_mass_in_reference_central90=dict(point=point[1],ci95=interval(None if boots is None else boots[:,1])),
        maximum_ecdf_distance=dict(point=point[2],ci95=interval(None if boots is None else boots[:,2])))


def group_name(row):
    item=row['item_id'];cand=row['candidate_type'];hid=row['history_id']
    if item.startswith('R-'):
        return f'G1/{cand}' if hid.startswith('old|R-S|') else None
    if item.startswith('G2d'):
        return f"G2d/{'constructed' if hid.startswith('constructed|') else 'natural'}/{cand}"
    return item.split('-')[0]+'/'+cand


def outcome_pools(formal, bank):
    groups=defaultdict(list)
    for row in formal['per_history']:
        groups[(row['structure'],row['arm'])].append(row)
    result=[]
    for (structure,arm), rows in sorted(groups.items()):
        metrics={}
        for event in ('adopt','correct'):
            hs=defaultdict(list)
            for r in rows:hs[(r['work_id'],r['history_id'])].append(r['counts'][event])
            vals=[]; counts=Counter()
            for (project,hid),cs in hs.items():
                total={k:sum(c[k] for c in cs) for k in ('events','observed','missing','planned')}
                counts.update(total)
                known_points=[c['events']/c['observed'] for c in cs if c['observed']]
                point=float(np.mean(known_points)) if known_points else None
                lo=float(np.mean([c['events']/c['planned'] for c in cs]))
                hi=float(np.mean([(c['events']+c['missing'])/c['planned'] for c in cs]))
                vals.append(dict(work_id=project,history_id=hid,cluster_id=bank.get(project,{}).get('pair_id',project),values={'point':point,'lower':lo,'upper':hi}))
            ds={k:distribution(vals,k) for k in ('point','lower','upper')}
            known_points=[r['values']['point'] for r in vals if r['values']['point'] is not None]
            extreme=bool(known_points) and (all(p==0 for p in known_points) or all(p==1 for p in known_points))
            ci95=None if extreme else ds['point']['project_equal']['mean_ci95']
            metrics[event]=dict(counts=dict(counts),project_equal=dict(point=ds['point']['project_equal']['mean'],ci95=ci95,
                bounds=[ds[k]['project_equal']['mean'] for k in ('lower','upper')]),history_equal=dict(point=ds['point']['history_equal']['mean'],bounds=[ds[k]['history_equal']['mean'] for k in ('lower','upper')]),
                projects=ds['point']['projects'],histories=len(vals),interval_note='全零/全一事件不报告退化重抽区间；经验点值和缺失界不作为严格验证' if extreme else None)
        result.append(dict(structure=structure,arm=arm,metrics=metrics))
    return result


def main(work,outdir,result_path):
    s=load(work/'frozen_statistics.json');p=load(work/'frozen_answer_probabilities.json');f=load(work/'formal_results.json');c=load(work/'frozen_comparison.json')
    material=load(outdir/'factdiag6g_materials.json')['plan'];bank={x['item_id']:x for x in material['items']}
    groups=defaultdict(list)
    for r in s['common_feature_readouts']['rows']:
        name=group_name(r)
        if name is None:continue
        r=dict(r,cluster_id=bank[r['item_id']].get('pair_id',r['work_id']))
        groups[name].append(r)
    distributions={name:{key:distribution(rows,key) for key in FEATURES} for name,rows in sorted(groups.items())}
    overlaps={}
    for name,rows in groups.items():
        if name=='G1/T':continue
        overlaps[name]={}
        for key in ('delta_gold','delta_pol','f_assoc','s','k'):
            if name.startswith('G2b') and key=='f_assoc':
                overlaps[name][key]=dict(status='不同测量定义，禁止计算重叠');continue
            if name.startswith('G2d/constructed') and key in ('s','delta_pol'):
                overlaps[name][key]=dict(status='构造先答与自然正确先答含义不同，不作跨类重叠');continue
            overlaps[name][key]=overlap(groups['G1/T'],rows,key)
    clean=[]
    for structure,obj in s['clean_readouts']['structures'].items():
        subgroups=defaultdict(list)
        for r in obj['clean']:
            name=structure if structure!='computable' else '-'.join(r['item_id'].split('-')[1:-1])
            subgroups[name].append(r)
        for name,rs in subgroups.items():
            totals={k:sum(r[k] for r in rs) for k in ('correct','wrong','missing','format_missing','truncated','looped')}
            clean.append(dict(group=name,projects=len(rs),**totals,known_correct_rate=totals['correct']/(totals['correct']+totals['wrong']),planned_correct_rate=totals['correct']/(8*len(rs))))
    predictors={}
    for model,data in p['literature_to_new'].items():
        predictors[model]={}
        for structure,t in data.items():
            predictors[model][structure]=dict(by_arm=t['by_arm'],scores=c['regimes']['literature_to_new']['models'][model]['scores'][structure])
    result=dict(status='探索性；主报告提交后新增选择，仅描述现有数据，未重拟合、调参或改标签',
        definitions={
            'units':'每个候选组中先历史等权、再项目等权；跨候选正式结局先候选条件等权，再历史、项目等权。电影方向为项目，同名配对为重抽簇。G1限原作者R-S历史，不混入旧译者历史。',
            'intervals':'2000次项目簇重抽的描述性95%区间；同一电影的方向一同抽取；单簇不给区间；不作多重显著性筛选。',
            'overlap':'G1本版译者为事后选定参考；中央90%区间交叠为交集长度/并集长度，同时报告目标落入参考区间的质量和加权经验分布最大差。区间重叠不是密度相等、因果可交换或预注册检验。',
            'association':'文学、改编、可计算、首都为精确小写yes的未在yes/no间归一化教师强制条件概率；电影为无年份八次采样频率，禁止跨定义重叠。',
            'stability':'s是当前先答在干净单轮中的频率；构造先答的s不是自然事实掌握度。k是当前问题的干净正确率；z_scope仅电影适用，c仅可计算适用。',
            'candidate_preference':'delta_gold是logP(错误候选)−logP(金标)；delta_pol是logP(候选)−logP(当前先答)。构造格中两者不同，不混同。',
            'G1_prediction':'G1非A0在文献模型训练中，不能作为独立外推；同结构A0使用单独冻结事前分布，其余四结构使用文献固定参数。',
            'identity':'这里目标错误P(D)表示采纳本批错误用户候选，不等于所有最终错误。P(G)依互斥身份规则，不普遍等于正确率。'},
        distributions=distributions,overlap_reference='G1/T',overlaps=overlaps,
        clean_question_counts=clean,pooled_formal_outcomes=outcome_pools(f,bank),
        frozen_literature_predictions=predictors,frozen_G1_A0=s['a0'],frozen_film_wording_control=s['film']['wording_control'],
        frozen_film_readouts=s['film']['readouts'],frozen_main_decision=c['frozen_decision'])
    Path(result_path).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'groups':len(groups),'history_candidate_rows':sum(map(len,groups.values())),'result_bytes':Path(result_path).stat().st_size},ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True);ap.add_argument('--result',type=Path,required=True)
    a=ap.parse_args();main(a.work,a.outdir,a.result)
