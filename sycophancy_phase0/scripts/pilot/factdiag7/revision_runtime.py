"""唯一一轮关系重评：固定5920输入，每输入一次，等待原队列退出后串行执行。"""
from contextlib import contextmanager
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import time

from .stage2_revision import (ORDER, COUNTS, OUTPUT_FILES, PROTOCOL_FILE,
                             validate_freeze, load)


def atomic_save(path, value):
    path = Path(path); tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def old_review_processes():
    found = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p / 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if any(a in (b'scripts.pilot.factdiag5.review_runtime', b'scripts.pilot.factdiag5.continue_reviews')
               for a in args):
            found.append(int(p.name))
    return found


def old_reviews_complete(pilot):
    fifth = Path(pilot) / 'factdiag5_20261112'
    for name, n in (('core_legacy_reviews.json', 5044), ('core_relations_v2.json', 1840)):
        path = fifth / name
        if not path.exists():
            return False
        records = load(path)
        if len(records) > n:
            raise RuntimeError('旧评审输出超过计划')
        if len(records) != n or any(v.get('completion') != 'returned' for v in records.values()):
            return False
    return True


@contextmanager
def exclusive(out):
    import fcntl
    with (out / '.revision.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('已有修订接续或评审进程，禁止重复启动') from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def validate_saved(queues, saved, commit):
    unfinished = False
    for phase in ORDER:
        bank = {q['id']: q for q in queues[phase]}
        if not set(saved[phase]) <= set(bank):
            raise ValueError('已有结果含冻结清单之外的输入')
        for key, record in saved[phase].items():
            if (record.get('input_sha256') != bank[key]['input_sha256'] or
                record.get('revision_commit') != commit or record.get('attempts') != 1):
                raise ValueError('已评输入变化、提交不同或重复尝试')
        if unfinished and saved[phase]:
            raise ValueError('已有结果越过串行前置缺口')
        unfinished = unfinished or len(saved[phase]) < len(bank)


def reserve(saved, batch, commit):
    for q in batch:
        if q['id'] in saved:
            raise ValueError('已派发输入不得重评')
        saved[q['id']] = dict(input_sha256=q['input_sha256'], prompt_sha256=q['prompt_sha256'],
            revision_commit=commit, attempts=1, completion='attempted_result_missing',
            raw=None, extraction={'parse_status': 'UNPARSEABLE', 'claims': []},
            result={'missing': True, 'reason': 'attempt_started_result_not_saved'})


def finish(saved, q, returned):
    from .relations_v3 import parse, map_evidence
    old = saved[q['id']]
    if old['completion'] != 'attempted_result_missing':
        raise ValueError('同次输入不能保存第二份返回')
    cut = returned['judge_truncated']; raw = returned['raw']
    try:
        extraction = ({'parse_status': 'UNPARSEABLE', 'claims': []} if cut else
                      parse(raw, q['response'], q['item'], person=q['person'],
                            user_message=q['user_message']))
        mapped = map_evidence(extraction, q['item'], q['person'])
        result = dict(missing=extraction.get('parse_status') != 'OK', extraction=mapped)
    except (ValueError, TypeError, KeyError) as exc:
        extraction = {'parse_status': 'UNPARSEABLE', 'claims': []}
        result = dict(missing=True, reason='parser_exception', detail=str(exc))
    saved[q['id']] = dict(old, completion='returned', raw=raw, extraction=extraction, result=result,
                         judge_truncated=cut, n_new_tokens=returned.get('n_new_tokens'))


def serial(queues, saved, settings, commit, call_once, write):
    validate_saved(queues, saved, commit)
    start = time.time()
    for phase in ORDER:
        pending = [q for q in queues[phase] if q['id'] not in saved[phase]]
        for offset in range(0, len(pending), settings['batch']):
            batch = pending[offset:offset + settings['batch']]
            reserve(saved[phase], batch, commit); write(phase, saved[phase])
            returned = call_once([q['prompt'] for q in batch], settings['max_new_tokens'])
            if len(returned) != len(batch):
                raise RuntimeError('返回数不符；已派发输入记缺失，不重评')
            for q, result in zip(batch, returned):
                finish(saved[phase], q, result)
            write(phase, saved[phase])
            done = sum(r.get('completion') == 'returned' for r in saved[phase].values())
            tokens = sum(r.get('n_new_tokens', 0) or 0 for rs in saved.values() for r in rs.values())
            print(json.dumps(dict(phase=phase, returned=done, expected=len(queues[phase]),
                  attempted=len(saved[phase]), judge_tokens=tokens, elapsed_seconds=round(time.time()-start)),
                  ensure_ascii=False), flush=True)


def run(pilot, commit, *, check_only=False, wait_old=False):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('必须提供已提交推送的修订冻结号')
    pilot = Path(pilot).resolve(); out = pilot / 'factdiag7_20261112'
    if not check_only and str(pilot) != '/output/sycophancy-phase0/pilot':
        raise RuntimeError('模型评审仅在原A100运行目录执行')
    reg, queues = validate_freeze(pilot)
    saved = {phase: load(out / name) if (out / name).exists() else {}
             for phase, name in OUTPUT_FILES.items()}
    validate_saved(queues, saved, commit)
    pending = sum(len(queues[p]) - len(saved[p]) for p in ORDER)
    print(json.dumps(dict(version=reg['version'], counts=COUNTS, pending=pending), ensure_ascii=False), flush=True)
    if check_only or not pending:
        return
    with exclusive(out):
        saved = {phase: load(out / name) if (out / name).exists() else {}
                 for phase, name in OUTPUT_FILES.items()}
        validate_saved(queues, saved, commit)
        if all(len(saved[p]) == len(queues[p]) for p in ORDER):
            return
        while old_review_processes() or not old_reviews_complete(pilot):
            if not wait_old:
                raise RuntimeError('原评审尚未完整退出')
            if not old_review_processes():
                raise RuntimeError('原队列未完整且无活动进程，须诊断后接续')
            print('等待既有第五批评审完成并退出；本进程未加载模型。', flush=True)
            time.sleep(30)
        # 等待后重查输入与代码；另一个入口无法绕过同一文件锁。
        validate_freeze(pilot)
        gpu = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], text=True).strip()
        if gpu:
            raise RuntimeError('GPU有其他进程，禁止重复加载：' + gpu)
        from ..factdiag5.review_runtime import load_client, infer_once
        settings = load(out / PROTOCOL_FILE)['judge_runtime']
        client = load_client(pilot, settings)
        serial(queues, saved, settings, commit,
               lambda prompts, limit: infer_once(client, prompts, limit),
               lambda phase, records: atomic_save(out / OUTPUT_FILES[phase], records))
        print('修订后5920输入评审完成；须独立复核与报告，不启动阶段三。', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pilot', type=Path, required=True); ap.add_argument('--revision-commit', required=True)
    ap.add_argument('--check-only', action='store_true'); ap.add_argument('--wait-old', action='store_true')
    a = ap.parse_args(); run(a.pilot, a.revision_commit, check_only=a.check_only, wait_old=a.wait_old)
