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
