"""第五批独立复核专用读取及一次提交；不读取材料真值、机器标签或条件映射。"""
from pathlib import Path
import argparse
import json
import sys


BLIND = 'factdiag5_independent_blind.json'
LABELS = 'factdiag5_independent_labels'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def validate_submission(card, value):
    if not isinstance(value, dict) or set(value) != {'blind_id', 'review_complete', 'annotations'}:
        raise ValueError('提交须含盲号、已完成标记和全部规定标签')
    if value['blind_id'] != card['blind_id'] or value['review_complete'] is not True:
        raise ValueError('盲号不符或尚未复核完成；空白表不能视作全缺失标签')
    labels = value['annotations']; expected = card['submission']['annotations']
    if not isinstance(labels, dict) or set(labels) != set(expected):
        raise ValueError('标签对象须与本卡完全一致，不漏标签、不扩大人物')
    if labels['supported_answer'] is not None and not isinstance(labels['supported_answer'], str):
        raise ValueError('支持答案只能为原值字符串或null')
    if labels['explicit'] is not None and not isinstance(labels['explicit'], str):
        raise ValueError('明确程度须保存原返回字符串或明确缺失null')
    if 'status' in labels and labels['status'] is not None and not isinstance(labels['status'], str):
        raise ValueError('末行状态须保存原返回字符串或明确缺失null')
    if 'relations_v3' in labels:
        rel = labels['relations_v3']; target = expected['relations_v3']['candidate']
        if not isinstance(rel, dict) or set(rel) != {'candidate', 'extraction'} or rel['candidate'] != target:
            raise ValueError('关系人物须逐字对应本卡唯一对象')
        if rel['extraction'] is not None and not isinstance(rel['extraction'], (dict, str)):
            raise ValueError('关系提取须为原JSON对象、原返回文本或明确缺失null')
    for name in ('propositions', 'evidence_disputed'):
        if name in labels and labels[name] is not None and not isinstance(labels[name], (dict, str)):
            raise ValueError('语义标签须为原返回文本、JSON对象或明确缺失null')
    return value


def card_bank(blind):
    cards = {r['blind_id']: r for r in blind['records']}
    if len(cards) != len(blind['records']) or any(
            len(k) != 7 or not k.startswith('F5I') or not k[3:].isdigit() for k in cards):
        raise ValueError('盲号重复或格式无效')
    return cards


def load_submissions(folder, blind):
    cards = card_bank(blind); directory = Path(folder) / LABELS
    saved = {}
    if directory.exists():
        for path in sorted(directory.glob('*.json')):
            if path.stem not in cards:
                raise ValueError('标签目录包含计划外盲号')
            value = load(path); validate_submission(cards[path.stem], value)
            saved[path.stem] = value
    return saved


def submit(folder, blind, incoming):
    """逐盲号独占新建，不能覆盖；同一份提交可安全确认，解析失败不触发重评。"""
    cards = card_bank(blind)
    if not isinstance(incoming, list) or len({r.get('blind_id') for r in incoming}) != len(incoming):
        raise ValueError('一次提交必须为无重复盲号的列表')
    # 先完整核查输入身份；随后每个标签文件只允许首次创建。
    for value in incoming:
        if value.get('blind_id') not in cards:
            raise ValueError('提交盲号不在已抽定清单')
        validate_submission(cards[value['blind_id']], value)
    directory = Path(folder) / LABELS; directory.mkdir(exist_ok=True)
    for value in incoming:
        path = directory / (value['blind_id'] + '.json')
        if path.exists():
            if load(path) != value:
                raise RuntimeError('已有不同独立标签，禁止覆盖或重评：' + value['blind_id'])
            continue
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
    saved = load_submissions(folder, blind)
    return dict(done=len(saved), planned=len(cards))


def access(folder, operation, *, offset=0, count=1, incoming=None):
    folder = Path(folder); blind = load(folder / BLIND)
    card_bank(blind)
    if operation == 'protocol':
        return dict(protocol=blind['protocol'], relation_protocol=blind['relation_protocol'],
                    responses=len(blind['records']), storage='只读盲卡与自身提交；不读取材料、机器标签或私有映射。')
    if operation == 'read':
        if not 0 <= offset < len(blind['records']) or not 1 <= count <= 3:
            raise ValueError('一次只读1至3张有效盲卡')
        return blind['records'][offset:offset + count]
    if operation == 'submit':
        return submit(folder, blind, incoming)
    if operation == 'status':
        saved = load_submissions(folder, blind)
        return dict(done=len(saved), planned=len(blind['records']), completed_ids=sorted(saved))
    raise ValueError('仅支持protocol/read/submit/status')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('protocol', 'read', 'submit', 'status'))
    parser.add_argument('--offset', type=int, default=0); parser.add_argument('--count', type=int, default=1)
    args = parser.parse_args()
    folder = Path('/output/sycophancy-phase0/pilot/factdiag5_20261112')
    result = access(folder, args.operation, offset=args.offset, count=args.count,
                    incoming=json.load(sys.stdin) if args.operation == 'submit' else None)
    print(json.dumps(result, ensure_ascii=False))
