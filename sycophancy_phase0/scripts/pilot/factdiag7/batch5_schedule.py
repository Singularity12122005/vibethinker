"""用户批准的子集优先交接；不重抽、不重发、不重置本轮预算。"""
from collections import Counter


def remaining_groups(plan, completed):
    selected = {v['input_id'] for r in plan['records'] for v in r['views']}
    entries = plan['entries']
    allowed = {r['id'] for r in entries}
    if len(selected) != 223 or not selected <= allowed or not set(completed) <= allowed:
        raise ValueError('子集或已完成项不属于冻结清单')
    pending = [r for r in entries if r['id'] not in completed]
    # 两组内部均保持冻结清单中的相对顺序。
    return ([r for r in pending if r['id'] in selected],
            [r for r in pending if r['id'] not in selected])


def restore_handoff(records, plan, saved, control, commit):
    starts = [r for r in records if r['type'] == 'batch5_start']
    if len(starts) != 1 or any(r['type'] == 'subset_first_resume' for r in records):
        raise ValueError('本次交接只能接续唯一原运行器一次')
    if control.get('mode') != 'subset_then_export_then_remaining' or control.get('resume_commit') != commit:
        raise ValueError('交接授权或提交号不符')
    sent = [r for r in records if r['type'] == 'dispatched']
    returned = [r for r in records if r['type'] == 'result']
    ids = [r['id'] for r in returned]
    if len(set(ids)) != len(ids) or [r['id'] for r in sent] != ids:
        raise ValueError('存在重复派发或未保存结果，禁止交接后重发')
    entries = plan['entries']; n = len(ids)
    if ids != [r['id'] for r in entries[:n]] or control.get('blocked_fetch_ids') != [r['id'] for r in entries[n:n+32]]:
        raise ValueError('未证实原队列在下一批未派发边界退出')
    if not control['blocked_fetch_ids'] or set(saved) != set(ids):
        raise ValueError('远端保存集合与本地返回集合不同')
    counts = Counter(); usage = []
    for dispatch, result, entry in zip(sent, returned, entries):
        meta = result['metadata']; actual = saved[result['id']]
        if (dispatch['cohort'] != entry['cohort'] or result['cohort'] != entry['cohort']
                or actual.get('cohort') != entry['cohort']
                or meta.get('completion') != 'returned' or actual.get('completion') != 'returned'
                or meta.get('cli_exit_code') != 0 or meta.get('unexpected_item_types')
                or not meta.get('usage') or meta.get('attempts') != 1):
            raise ValueError('原队列有调用异常，不作为正常交接')
        for key in ('input_sha256', 'prompt_sha256'):
            if meta.get(key) != entry[key] or actual.get(key) != entry[key]:
                raise ValueError('已保存结果绑定不符')
        if dispatch['prompt_sha256'] != entry['prompt_sha256'] or actual.get('usage') != meta['usage']:
            raise ValueError('派发提示或已保存用量不符')
        usage.append(meta['usage']); counts[entry['cohort']] += 1
    return dict(limits=starts[0]['limits'], usage=usage, completed=set(ids),
                counts={k:counts[k] for k in ('batch5_T','batch5_subset','draft_first','draft_second')})


def restore_account_resume(records, plan, saved, control, *, expected_returned=405):
    """只接续用户授权的额度查询故障；任何未保存派发均拒绝重发。"""
    handoffs=[i for i,r in enumerate(records) if r['type']=='subset_first_resume']
    if len(handoffs)!=1 or any(r['type']=='account_read_resume' for r in records):
        raise ValueError('额度故障接续必须有唯一既有调序，且未接续过')
    sent=[r for r in records if r['type']=='dispatched']
    results=[r for r in records if r['type']=='result'];ids=[r['id'] for r in results]
    if len(ids)!=expected_returned or len(set(ids))!=len(ids) or [r['id'] for r in sent]!=ids:
        raise ValueError('派发与保存边界不完整或已变化，不重发')
    earlier=records[:handoffs[0]];prior_ids={r['id'] for r in earlier if r['type']=='result'}
    prior=restore_handoff(earlier,plan,{k:v for k,v in saved.items() if k in prior_ids},control,control['resume_commit'])
    priority,remainder=remaining_groups(plan,prior['completed'])
    order=[r['id'] for r in earlier if r['type']=='result']+[r['id'] for r in priority+remainder]
    selected={v['input_id'] for r in plan['records'] for v in r['views']}
    if ids!=order[:len(ids)] or set(saved)!=set(ids) or not selected<=set(ids):
        raise ValueError('与已批准子集优先顺序或远端保存集合不符')
    if not any(r['type']=='human_review_export_ready' for r in records):
        raise ValueError('人工材料交付状态不完整')
    bank={r['id']:r for r in plan['entries']};counts=Counter();usage=[]
    for dispatch,result in zip(sent,results):
        key=result['id'];entry=bank[key];meta=result['metadata'];actual=saved[key]
        if any(x.get('cohort')!=entry['cohort'] for x in (dispatch,result,actual)):
            raise ValueError('提取用途不符')
        if (meta.get('completion')!='returned' or actual.get('completion')!='returned'
                or meta.get('attempts')!=1 or actual.get('attempts')!=1
                or meta.get('cli_exit_code')!=0 or actual.get('cli_exit_code')!=0
                or meta.get('unexpected_item_types') or actual.get('unexpected_item_types')
                or not meta.get('usage') or actual.get('usage')!=meta['usage']):
            raise ValueError('已有调用缺失或异常，不作为安全接续')
        for field in ('input_sha256','prompt_sha256'):
            if meta.get(field)!=entry[field] or actual.get(field)!=entry[field]:raise ValueError('已保存提取绑定错误')
        if dispatch['prompt_sha256']!=entry['prompt_sha256']:raise ValueError('派发绑定错误')
        usage.append(meta['usage']);counts[entry['cohort']]+=1
    return dict(limits=prior['limits'],usage=usage,completed=set(ids),
                counts={k:counts[k] for k in ('batch5_T','batch5_subset','draft_first','draft_second')})
