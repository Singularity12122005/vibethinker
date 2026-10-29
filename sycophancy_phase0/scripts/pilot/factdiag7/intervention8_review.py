"""干预八全量人工复核出口：不调用模型、不改标签、不计算关系汇总。"""
from copy import deepcopy
from pathlib import Path
import argparse
import html
import json

from .intervention8 import PLAN, INPUTS, CARDS, SUPPLEMENT
from .strong_column import OUTPUT

RECEIVED = 'stage2_batch5_blind20_received.json'
STEM = 'stage2_batch5_full110'
EVENT_FIELDS = ('answer_status', 'W_false', 'W_side', 'W_target', 'adopt_T',
                'false_deny_T', 'challenge', 'V_ext', 'W_third',
                'third_party_claims', 'status', 'status_body_consistency',
                '核对说明', '不确定原因')


def _views(row):
    return [(v['candidate'], v['roles']) for v in row['views']]


def _identity(row, *, card=False):
    return (row['work_id'], row['idx' if card else 'history_index'],
            row['arm'], row['cell'], row['unit'])


def assemble(plan, cards, inputs, strong, received, previous, machine):
    """只整理固定110条；只读已接收盲标的身份，不预填语义标签。"""
    records = plan['records']
    if len(records) != 110 or len({r['human_id'] for r in records}) != 110:
        raise ValueError('固定110条清单不完整')
    if len(cards) != 110 or {r['human_id'] for r in cards} != {r['human_id'] for r in records}:
        raise ValueError('阅读卡与固定清单不一致')
    if received.get('human_review_complete') is not True or not received.get('confirmation_source'):
        raise ValueError('用户首次盲标尚未确认完成')
    originals = received['original_document']['records']
    blind = {r['human_id']: r for r in originals}
    if len(originals) != 20 or len(blind) != 20 or set(blind) != set(plan['blind20']):
        raise ValueError('首次盲标20条编号不符')
    planned = {r['human_id']: r for r in records}
    unique_views = {v['input_id'] for r in cards for v in r['views']}
    if len(unique_views) != 223:
        raise ValueError('子集去重人物范围发生变化')

    def pre(value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        return '<pre>' + html.escape(text) + '</pre>'

    def detail(title, value):
        return '<details><summary>' + html.escape(title) + '</summary>' + pre(value) + '</details>'

    lines = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
             '<title>第五批110条人工复核</title>',
             '<style>body{max-width:1180px;margin:32px auto;padding:0 24px;font:16px/1.7 system-ui;color:#142538}'
             'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px}'
             'section{border-top:3px solid #627d92;margin-top:38px}summary{cursor:pointer;padding:10px;background:#e9eff5}'
             'details{margin:12px 0}.note{padding:16px;background:#fff1cc}a{color:#1363a3}</style>',
             '<h1>第五批：110条人工复核</h1>',
             '<p class="note">采用4A：由用户的另一标注会话起草，用户逐条复核；执行方只提供材料。'
             '下表包含110条正文、完整上下文和阅读辅助，辅助提取不是真值。</p>',
             '<p>填写表110条全部空白，不预填任何机器或既有人工标签。'
             '所有完成标记为false，须用户逐条复核后确认。首次盲标20条原稿单独保存，不被本次填写表覆盖。'
             '资料不足保留未知；前缀与条件可见，不称臂盲。</p>', detail('第五批标注口径补充', SUPPLEMENT)]
    lines.append('<nav>' + ' · '.join('<a href="#' + r['human_id'] + '">' + r['human_id'] + '</a>'
                                    for r in sorted(cards, key=lambda x:x['human_id'])) + '</nav>')
    forms = []
    for card in sorted(cards, key=lambda r:r['human_id']):
        bid = card['human_id']; expected = planned[bid]
        if _identity(card, card=True) != _identity(expected, card=True) or card['views'] != expected['views']:
            raise ValueError('阅读卡身份与清单不符：' + bid)
        if bid in blind and (_identity(blind[bid]) != _identity(card, card=True)
                             or _views(blind[bid]) != _views(card)):
            raise ValueError('首次盲标与固定阅读卡不符：' + bid)
        if card['cell'] == '5.5' and not previous.get(card['response_id'], {}).get('current_answer'):
            raise ValueError('5.5缺少本轮生成前的冻结答案身份登记：' + bid)
        title = f"{bid} · {card['work_id']} · 历史{card['idx']} · {card['unit']} · {card['cell']} · {card['arm']}"
        lines += ['<section id="' + bid + '"><h2>' + html.escape(title) + '</h2>']
        if card['response_id'] in previous:
            lines += ['<h3>本轮生成前的冻结答案身份登记</h3>',
                      '<p>用于理解前轮答案及对话中的矛盾；这是答案身份登记，不是前轮逐字正文，不能作为当前生成命题的引文，也不证明外部核实。</p>',
                      pre(previous[card['response_id']])]
        for title, key in [('原问题', 'question'), ('第三轮用户消息全文', 'user_message'),
                           ('固定前缀与系统记录（非生成正文）', 'fixed_context'),
                           ('完整生成正文', 'response')]:
            lines += ['<h3>' + title + '</h3>', pre(card[key])]
        lines += [detail('冻结材料', card['materials'])]
        for view in card['views']:
            key = view['input_id']; q = inputs[key]; result = strong.get(key, {})
            if (q['person']['name'] != view['candidate'] or q['response_id'] != card['response_id']
                    or any(q[k] != card[k] for k in ('response', 'user_message', 'fixed_context'))):
                raise ValueError('辅助输入与阅读卡不符：' + bid)
            if (result.get('completion') != 'returned' or result.get('raw') is None
                    or any(result.get(k) != q[k] for k in ('input_sha256', 'prompt_sha256'))):
                raise ValueError('子集辅助提取尚未齐备或绑定不符：' + bid)
            lines += ['<h3>' + html.escape('人物：' + view['candidate'] + '；角色：' + '、'.join(view['roles'])) + '</h3>',
                      detail('Astra原始辅助提取（全量列同一提取器，非人工真值）', result['raw'])]
            old = machine.get(key)
            if old is not None and old.get('completion') == 'returned':
                if old.get('input_sha256') != q['input_sha256']:
                    raise ValueError('原机器主列输入绑定不符：' + bid)
                lines += [detail('原机器主列提取（第三版）', old['raw'])]
            else:
                lines += ['<p>本视图无对应原机器主列返回；不代表无错误，不为导出追加调用。</p>']
        form = dict(views=[dict(candidate=v['candidate'], roles=v['roles'], 人工命题=[], 备注=None) for v in card['views']], **{k:None for k in EVENT_FIELDS})
        form['third_party_claims'] = []
        form.update(human_id=bid, work_id=card['work_id'], history_index=card['idx'],
                    arm=card['arm'], cell=card['cell'], unit=card['unit'], human_review_complete=False)
        forms.append(form)
        lines += ['</section>']
    lines += ['<p>请在填写表中逐条确认；明确复核后仍未知可保留null并写明原因。不要更改编号或人物角色。</p></html>']
    document = dict(cohort='batch5_intervention8_full110',
                    说明='4A：用户的另一标注会话起草，执行方只导出空白表及阅读辅助；用户逐条复核后确认。首次盲标20条另存，不被覆盖。',
                    records=forms)
    return '\n'.join(lines), document


def write_review(directory, reading, document):
    """阅读页可刷新；已有人工填写表永不覆盖。"""
    directory = Path(directory)
    labels = directory / (STEM + '_labels.json')
    preserved = labels.exists()
    if not preserved:
        with labels.open('x', encoding='utf-8') as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
    (directory / (STEM + '_reading.html')).write_text(reading, encoding='utf-8')
    (directory / 'stage2_batch5_annotation_supplement.txt').write_text(SUPPLEMENT, encoding='utf-8')
    return dict(responses=len(document['records']), labels_preserved=preserved,
                supplement='stage2_batch5_annotation_supplement.txt',
                reading=STEM + '_reading.html', labels=STEM + '_labels.json')


def export(pilot):
    p = Path(pilot); out = p / 'factdiag7_20261112'
    def load(name):
        return json.loads((out / name).read_text(encoding='utf-8'))
    previous = {}
    for row in json.loads((p / 'factdiag5_20261112/core_generations.json').read_text(encoding='utf-8')):
        previous[row['request_id']] = {k:row.get(k) for k in ('source_history_id', 'current_answer', 'first_answer_description')}
    reading, labels = assemble(load(PLAN), load(CARDS), load(INPUTS), load(OUTPUT),
                               load(RECEIVED), previous, load('stage2_revision_batch5_extractions.json'))
    return write_review(out, reading, labels)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pilot', type=Path, required=True)
    print(json.dumps(export(ap.parse_args().pilot), ensure_ascii=False))
