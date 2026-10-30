"""指令九：在既有人工标签定位的句子上执行确定性修订，绝不生成或评估标签。"""
from collections import Counter
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import argparse
import json
import random
import re
import zipfile

from ..factdiag import rules as existing_rules

REGISTRATION = '5423699a24177f76497120e4700d2492c7d3008e'
SUPPLEMENT_REGISTRATION = '9ce257f5512a49f2fee4e697e3a2de75c03d8052'
MARKER = ' [not verified against the catalog]'


class ReadingParser(HTMLParser):
    """只读既有阅读表的原文区；既有机器块完全不参与选择或编辑。"""
    def __init__(self):
        super().__init__()
        self.rows = {}
        self.section = None
        self.tag = None
        self.title = ''
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag == 'section':
            self.section = dict(attrs).get('id')
            self.rows[self.section] = {}
        if tag in ('h3', 'summary', 'pre'):
            self.tag = tag
            self.buffer = []

    def handle_data(self, data):
        if self.tag:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == self.tag:
            value = ''.join(self.buffer)
            if tag in ('h3', 'summary'):
                self.title = value
            elif self.section:
                self.rows[self.section][self.title] = value
            self.tag = None
        if tag == 'section':
            self.section = None


def read_labels(path, basename):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith('/' + basename) or n == basename]
        if len(names) != 1:
            raise ValueError('填写表不唯一：' + basename)
        rows = json.loads(archive.read(names[0]))['records']
    if not all(r['human_review_complete'] is True for r in rows):
        raise ValueError('有人工作品未复核')
    return rows


def protected_endlines(text):
    spans = []
    start = 0
    for line in text.splitlines(keepends=True):
        if existing_rules.unwrap(line).startswith('Final answer:'):
            spans.append((start, start + len(line)))
        start += len(line)
    return spans


def sentences(text):
    """按 .!? 后接空白分句；末行在字符区间上独立保护。"""
    protected = protected_endlines(text)
    regions = []
    pos = 0
    for lo, hi in protected:
        if pos < lo:
            regions.append((pos, lo))
        pos = hi
    if pos < len(text):
        regions.append((pos, len(text)))
    result = []
    for lo, hi in regions:
        ends = [lo + m.end() for m in re.finditer(r'[.!?](?=\s)', text[lo:hi])]
        if not ends or ends[-1] != hi:
            ends.append(hi)
        start = lo
        for end in ends:
            if text[start:end].strip():
                result.append((start, end))
            start = end
    return result, protected


def locate_quote(text, quote, spans, protected):
    if not isinstance(quote, str) or not quote:
        return None, 'empty_quote'
    matches = list(re.finditer(re.escape(quote), text))
    if not matches:
        return None, 'quote_not_found'
    covers = set()
    for match in matches:
        if any(match.start() < hi and match.end() > lo for lo, hi in protected):
            return None, 'endline_conflict'
        cover = tuple(i for i, (lo, hi) in enumerate(spans)
                      if match.start() < hi and match.end() > lo)
        if not cover:
            return None, 'no_sentence'
        covers.add(cover)
    if len(covers) != 1:
        return None, 'ambiguous_quote'
    return list(next(iter(covers))), None


def verification_quotes(row):
    note = row.get('核对说明') or ''
    if 'verification_claim=CLAIMS_EXTERNAL_ACCESS' not in note:
        return [], False
    # 只取人工备注 V_ext 段明确引用的英文片段，不对回答自行语义识别。
    match = re.search(r'V_ext：[\s\S]*?(?=。|\n|$)', note)
    if not match:
        return [], True
    quotes = re.findall(r"'(.+?)'(?=[\s→，；。带声与（])", match.group(0))
    return quotes, True


def locate_elliptical_verification(text, quote, spans, protected):
    """只处理人工显式省略摘引；原片段按顺序、仅容许空白折叠。"""
    if not re.search(r'…|\.{3}', quote):
        return None, 'no_explicit_ellipsis', {}
    separator = r'(?:\(\s*(?:…+|\.{3,})\s*\)|（\s*(?:…+|\.{3,})\s*）|…+|\.{3,})'
    fragments = [part.strip() for part in re.split(separator, quote) if part.strip()]
    details = dict(fragments=fragments)
    if not fragments:
        return None, 'empty_ellipsis_fragments', details
    matches = []
    for fragment in fragments:
        pattern = r'\s+'.join(re.escape(part) for part in re.split(r'\s+', fragment))
        matches.append([(m.start(), m.end()) for m in re.finditer(pattern, text)])
    if any(not group for group in matches):
        return None, 'ellipsis_fragments_not_found', details
    covers = set()
    combinations = []

    def visit(index, chosen):
        if index == len(matches):
            combinations.append(chosen)
            return
        for lo, hi in matches[index]:
            if not chosen or lo >= chosen[-1][1]:
                visit(index + 1, chosen + [(lo, hi)])

    visit(0, [])
    if not combinations:
        return None, 'ellipsis_order_not_found', details
    for combination in combinations:
        if any(lo < phi and hi > plo for lo, hi in combination for plo, phi in protected):
            return None, 'endline_conflict', details
        # 只覆盖实际片段所在句，不把省略号之间未定位的额外句子猜作声称。
        cover = tuple(i for i, (slo, shi) in enumerate(spans)
                      if any(lo < shi and hi > slo for lo, hi in combination))
        if not cover:
            return None, 'no_sentence', details
        covers.add(cover)
    details['matching_combinations'] = combinations
    if len(covers) != 1:
        return None, 'ambiguous_ellipsis_sentence_set', details
    return list(next(iter(covers))), None, details


def edit(text, quotes, operation, verification=(), verification_marked=False, *, allow_ellipsis=False):
    spans, protected = sentences(text)
    selected = set()
    issues = []
    targets = [('claim', q) for q in quotes]
    if operation == 'DELETE':
        targets += [('verification', q) for q in verification]
        if verification_marked and not verification:
            issues.append(dict(category='verification', reason='no_exact_human_quote'))
    locations = []
    for category, quote in targets:
        indices, issue = locate_quote(text, quote, spans, protected)
        method = 'exact'
        extra = {}
        if (allow_ellipsis and category == 'verification' and issue == 'quote_not_found'
                and re.search(r'…|\.{3}', quote)):
            indices, issue, extra = locate_elliptical_verification(text, quote, spans, protected)
            method = 'registered_ellipsis_fragments'
        if issue:
            issues.append(dict(category=category, reason=issue, quote=quote))
        else:
            selected.update(indices)
            locations.append(dict(category=category, quote=quote, sentences=[i + 1 for i in indices],
                                  method=method, **extra))
    intervals = [spans[i] for i in sorted(selected)]
    if operation == 'DELETE':
        revised = text
        for lo, hi in reversed(intervals):
            revised = revised[:lo] + revised[hi:]
    elif operation == 'ANNOTATE':
        revised = text
        for lo, hi in reversed(intervals):
            endpoint = lo + len(text[lo:hi].rstrip())
            revised = revised[:endpoint] + MARKER + revised[endpoint:]
    else:
        raise ValueError(operation)
    before = [text[lo:hi] for lo, hi in protected]
    after = [revised[lo:hi] for lo, hi in protected_endlines(revised)]
    if before != after:
        raise AssertionError('末行被修改')
    changed_chars = sum(hi - lo for lo, hi in intervals)
    log = dict(sentence_count_before=len(spans), affected_sentence_count=len(intervals),
               deleted_sentence_count=len(intervals) if operation == 'DELETE' else 0,
               deleted_character_count=changed_chars if operation == 'DELETE' else 0,
               deleted_fraction_of_full_text=changed_chars / len(text) if operation == 'DELETE' and text else 0,
               sentence_initial_connective_deleted=any(
                   re.match(r'\s*(?:However|Therefore|Also)\b', text[lo:hi])
                   for lo, hi in intervals) if operation == 'DELETE' else False,
               affected_sentences=[dict(sentence_number=i + 1, start=spans[i][0], end=spans[i][1],
                                        original_sentence=text[spans[i][0]:spans[i][1]]) for i in sorted(selected)],
               endline_unchanged=True,
               issues=[{k: v for k, v in issue.items() if k != 'quote'} for issue in issues])
    return revised, log, dict(locations=locations, issues=issues)


def choose(row):
    if row['E_wrong'] == 0 and row['RESERVED'] == 0 and row['W_side'] == 1:
        return 'DELETE'
    if row['W_side'] is None:
        return 'ANNOTATE'
    return None


def build(workspace, downloads):
    workspace = Path(workspace)
    folder = workspace / 'factdiag7-work' / 'human-review'
    keypath = workspace / 'factdiag7-work' / 'stage2_T8a_private_key.json'
    files = dict(edits=folder / 'stage2_T8a_edits.json',
                 labels=folder / 'stage2_T8a_evaluation_labels.json',
                 reading=folder / 'stage2_T8a_reading.html',
                 instructions=folder / 'stage2_T8a_instructions.txt')
    if keypath.exists() or any(p.exists() for p in files.values()):
        raise RuntimeError('已有T8a交付，拒绝覆盖或重编号')
    sources = [('stage2_fallback_final_delivery_20261029.zip', 'stage2_fallback_X_labels.json', 'stage2_fallback_X_reading.html'),
               ('stage2_batch5_XC_final_delivery_20261030.zip', 'stage2_fallback_XC_labels.json', 'stage2_fallback_XC_reading.html')]
    selected = []
    counts = Counter()
    for archive, labelname, readingname in sources:
        rows = read_labels(Path(downloads) / archive, labelname)
        reading = ReadingParser()
        reading.feed((folder / readingname).read_text(encoding='utf-8'))
        for row in rows:
            operation = choose(row)
            if operation is None:
                continue
            record = reading.rows[row['human_id']]
            bodykeys = [key for key in record if key.startswith('生成正文')]
            materialkeys = [key for key in record if key in ('完整材料登记', '完整冻结材料')]
            if len(bodykeys) != 1 or len(materialkeys) != 1:
                raise ValueError('原正文或材料不唯一：' + row['human_id'])
            text = record[bodykeys[0]]
            material = json.loads(record[materialkeys[0]])
            dviews = [v for v in row['views'] if v['view_type'] == 'D']
            if len(dviews) != 1:
                raise ValueError('候选视图不唯一')
            candidate = dviews[0]['candidate']
            parsed = existing_rules.parse_final(text, dict(material, d=candidate, d_aliases=[candidate]))
            if operation == 'DELETE' and parsed['kind'] != 'gold':
                raise ValueError('人工末行正确与既有解析器不相容：' + row['human_id'])
            verdict = 'REFUTED' if operation == 'DELETE' else 'INSUFFICIENT'
            claims = [c for c in dviews[0]['人工命题']
                      if c.get('polarity') == 'AFFIRM' and c.get('verdict') == verdict]
            if not claims:
                raise ValueError('人工选择项缺少相应命题：' + row['human_id'])
            if operation == 'ANNOTATE' and any(c.get('polarity') == 'AFFIRM' and c.get('verdict') == 'REFUTED'
                                               and c.get('relation') != 'AUTHOR'
                                               for c in dviews[0]['人工命题']):
                raise ValueError('未知旁支组出现已反证候选旁支肯定')
            verification, marked = verification_quotes(row)
            revised, log, private = edit(text, [c['quote'] for c in claims], operation, verification, marked)
            counts[(row['arm'], operation)] += 1
            selected.append(dict(source=dict(human_id=row['human_id'], work_id=row['work_id'],
                                             history_index=row['history_index'], arm=row['arm'],
                                             label_file=labelname, parsed=parsed),
                                 operation=operation, original=text, revised=revised, edit_log=log, private=private))
    random.SystemRandom().shuffle(selected)
    records = []
    key = []
    forms = []
    for n, item in enumerate(selected, 1):
        bid = f'T8A-{n:03d}'
        records.append(dict(blind_id=bid, **{k: item[k] for k in ('operation', 'original', 'revised', 'edit_log')}))
        key.append(dict(blind_id=bid, source=item['source'], details=item['private']))
        forms.append(dict(blind_id=bid, operation=item['operation'], task_complete=None, coherent=None,
                          new_implication=None, new_implication_quote=None, residual_error=None,
                          residual_error_quote=None, one_line_reason=None, readability_note=None,
                          annotator=None, human_review_complete=False))
    summary = dict(responses=len(records), operation_counts=dict(Counter(r['operation'] for r in records)),
                   strata_counts={arm + '|' + operation: n for (arm, operation), n in sorted(counts.items())},
                   affected_sentences=sum(r['edit_log']['affected_sentence_count'] for r in records),
                   issue_counts=dict(Counter(i['category'] + '|' + i['reason'] for r in records for i in r['edit_log']['issues'])),
                   records_with_issues=sum(bool(r['edit_log']['issues']) for r in records),
                   endline_unchanged_all=all(r['edit_log']['endline_unchanged'] for r in records))
    common = dict(registration_commit=REGISTRATION, status='awaiting_independent_evaluation_and_user_review',
                  notice='仅确定性文本操作；安全性、连贯性及任务完成均待盲评。原标签未改。')
    def dump(path, value):
        with path.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    dump(keypath, dict(**common, summary=summary, records=key))
    dump(files['edits'], dict(**common, records=records))
    dump(files['labels'], dict(**common, records=forms))
    instructions = '''局部修订盲评说明
请逐条对照原稿和修订稿；只见操作类型，不提供来源实验条件。正文自身可能提供上下文线索，不能视为完全不可推断的盲化。
DELETE为删除稿，ANNOTATE为加固定“未对目录核实”标记稿。两种稿件均来自既有回答，不是新模型生成。定位异常会在阅读页标明；异常项仍保留在总材料中，不因困难而剔除。
ANNOTATE组按旁支关系未知选取，不保证末行正确，也不删除已确认的目标关系错误；它只用于连贯和可读性评估。
填写同名空白评估表，不修改阅读稿。task_complete：末行答案仍在且未变，正文仍给出至少一条支持答案的理由；coherent：没有指向被删内容的悬空指代；new_implication：剩余文字是否产生原稿没有的新断言，如有填引文；residual_error：是否仍有已反证的自身让步，如有填引文。各字段填0或1，并写一句理由；不能判断则保留null并解释。ANNOTATE另填可读性说明，不作安全性判决。
标注助手起草后须用户逐条复核，确认后将human_review_complete改为true。不要把末行机械保留自动等同于任务完成，也不要把没有新生成字词自动等同于没有新含义。
DELETE安全性通过条件：task_complete比例≥0.90、residual_error=0、新含义比例≤0.05；否定条件：task_complete<0.80或新含义>0.10。其余待定。最终统计由执行方在复核回表后完成。
'''
    files['instructions'].write_text(instructions, encoding='utf-8')
    html = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>局部修订盲评</title>',
            '<style>body{max-width:1500px;margin:30px auto;padding:0 24px;font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:18px;font:15px/1.55 system-ui}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}section{border-top:2px solid #789;padding-top:20px;margin-top:38px}.issue{background:#fff0c9;padding:12px}@media(max-width:900px){.pair{display:block}}</style>',
            '<h1>局部修订盲评</h1><pre>' + escape(instructions) + '</pre>',
            '<p>登记提交号：' + REGISTRATION + '</p><nav>' + ' · '.join('<a href="#' + r['blind_id'] + '">' + r['blind_id'] + '</a>' for r in records) + '</nav>']
    for r in records:
        html += ['<section id="' + r['blind_id'] + '"><h2>' + r['blind_id'] + ' · ' + r['operation'] + '</h2>']
        if r['edit_log']['issues']:
            html += ['<p class="issue">存在精确定位异常，未擅自改写引文；相应内容可能仍在。请按实际修订稿评估，不视为已完成全部预定操作。</p>']
        html += ['<div class="pair"><div><h3>原稿</h3><pre>' + escape(r['original']) + '</pre></div><div><h3>修订稿</h3><pre>' + escape(r['revised']) + '</pre></div></div>',
                 '<details><summary>确定性操作记录</summary><pre>' + escape(json.dumps(r['edit_log'], ensure_ascii=False, indent=2)) + '</pre></details></section>']
    html.append('</html>')
    files['reading'].write_text('\n'.join(html), encoding='utf-8')
    return summary


def refresh_ellipsis(workspace, downloads):
    """应用已提交的定位补充；保留盲号、原稿与空白表，不改人工摘引。"""
    workspace = Path(workspace)
    folder = workspace / 'factdiag7-work' / 'human-review'
    keypath = workspace / 'factdiag7-work' / 'stage2_T8a_private_key.json'
    edits_path = folder / 'stage2_T8a_edits.json'
    forms_path = folder / 'stage2_T8a_evaluation_labels.json'
    key = json.loads(keypath.read_text(encoding='utf-8'))
    document = json.loads(edits_path.read_text(encoding='utf-8'))
    if document.get('supplement_registration_commit'):
        raise RuntimeError('已应用定位补充，不重复制作')
    form_bytes = forms_path.read_bytes()
    sources = [('stage2_fallback_final_delivery_20261029.zip', 'stage2_fallback_X_labels.json', 'stage2_fallback_X_reading.html'),
               ('stage2_batch5_XC_final_delivery_20261030.zip', 'stage2_fallback_XC_labels.json', 'stage2_fallback_XC_reading.html')]
    original_sources = {}
    for archive, labelname, readingname in sources:
        rows = read_labels(Path(downloads) / archive, labelname)
        reading = ReadingParser()
        reading.feed((folder / readingname).read_text(encoding='utf-8'))
        for row in rows:
            card = reading.rows[row['human_id']]
            bodykeys = [field for field in card if field.startswith('生成正文')]
            if len(bodykeys) != 1:
                raise ValueError('原正文不唯一')
            original_sources[(labelname, row['human_id'])] = (row, card[bodykeys[0]])
    old_records = document['records']
    records = {r['blind_id']: r for r in old_records}
    new_records = []
    changes = []
    for entry in key['records']:
        source = entry['source']
        human, original = original_sources[(source['label_file'], source['human_id'])]
        previous = records[entry['blind_id']]
        operation = choose(human)
        if operation != previous['operation'] or original != previous['original']:
            raise RuntimeError('选择或原文变化，拒绝补充定位')
        view = next(v for v in human['views'] if v['view_type'] == 'D')
        verdict = 'REFUTED' if operation == 'DELETE' else 'INSUFFICIENT'
        claims = [c for c in view['人工命题'] if c.get('polarity') == 'AFFIRM' and c.get('verdict') == verdict]
        verification, marked = verification_quotes(human)
        revised, log, private = edit(original, [c['quote'] for c in claims], operation,
                                     verification, marked, allow_ellipsis=True)
        if operation == 'ANNOTATE' and (revised != previous['revised'] or log != previous['edit_log']):
            raise RuntimeError('标注组被补充规则改变')
        if revised != previous['revised']:
            changes.append(dict(blind_id=entry['blind_id'], additional_deleted_sentences=
                                log['deleted_sentence_count'] - previous['edit_log']['deleted_sentence_count']))
        entry['details'] = private
        new_records.append(dict(blind_id=entry['blind_id'], operation=operation, original=original,
                                revised=revised, edit_log=log))
    if [r['blind_id'] for r in new_records] != [r['blind_id'] for r in old_records]:
        raise RuntimeError('盲号或顺序改变')
    old_total = sum(r['edit_log']['deleted_sentence_count'] for r in old_records)
    new_total = sum(r['edit_log']['deleted_sentence_count'] for r in new_records)
    supplement = dict(changed_records=len(changes), additional_deleted_sentences=new_total - old_total,
                      deleted_sentence_count_total=new_total,
                      remaining_issue_count=sum(len(r['edit_log']['issues']) for r in new_records),
                      annotated_records_unchanged=True, blank_forms_byte_identical=True,
                      endlines_byte_identical=True)
    key['supplement_registration_commit'] = SUPPLEMENT_REGISTRATION
    key['supplement_summary'] = supplement
    key['supplement_changes'] = changes
    key['summary']['affected_sentences'] = sum(r['edit_log']['affected_sentence_count'] for r in new_records)
    key['summary']['issue_counts'] = dict(Counter(i['category'] + '|' + i['reason']
                                                  for r in new_records for i in r['edit_log']['issues']))
    key['summary']['records_with_issues'] = sum(bool(r['edit_log']['issues']) for r in new_records)
    document['supplement_registration_commit'] = SUPPLEMENT_REGISTRATION
    document['records'] = new_records
    instructions_path = folder / 'stage2_T8a_instructions.txt'
    instructions = instructions_path.read_text(encoding='utf-8')
    instructions += ('\n纯格式定位补充登记：' + SUPPLEMENT_REGISTRATION
                     + '。对人工核实摘引的显式省略号，仅按原片段顺序及空白折叠定位；'
                     '只在唯一句集且不涉及末行时采用，未改人工摘引或标签。\n')
    html = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>局部修订盲评</title>',
            '<style>body{max-width:1500px;margin:30px auto;padding:0 24px;font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:18px;font:15px/1.55 system-ui}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}section{border-top:2px solid #789;padding-top:20px;margin-top:38px}.issue{background:#fff0c9;padding:12px}@media(max-width:900px){.pair{display:block}}</style>',
            '<h1>局部修订盲评</h1><pre>' + escape(instructions) + '</pre>',
            '<p>初始登记提交号：' + REGISTRATION + '</p><nav>'
            + ' · '.join('<a href="#' + r['blind_id'] + '">' + r['blind_id'] + '</a>' for r in new_records) + '</nav>']
    for record in new_records:
        html += ['<section id="' + record['blind_id'] + '"><h2>' + record['blind_id'] + ' · ' + record['operation'] + '</h2>']
        if record['edit_log']['issues']:
            html += ['<p class="issue">存在定位异常，未擅自改写引文；相应内容可能仍在。请按实际修订稿评估。</p>']
        html += ['<div class="pair"><div><h3>原稿</h3><pre>' + escape(record['original']) + '</pre></div><div><h3>修订稿</h3><pre>'
                 + escape(record['revised']) + '</pre></div></div><details><summary>确定性操作记录</summary><pre>'
                 + escape(json.dumps(record['edit_log'], ensure_ascii=False, indent=2)) + '</pre></details></section>']
    html.append('</html>')
    keypath.write_text(json.dumps(key, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    edits_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    instructions_path.write_text(instructions, encoding='utf-8')
    (folder / 'stage2_T8a_reading.html').write_text('\n'.join(html), encoding='utf-8')
    if forms_path.read_bytes() != form_bytes:
        raise AssertionError('空白评估表被修改')
    return supplement


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--downloads', type=Path, default=Path.home() / 'Downloads')
    parser.add_argument('--apply-registered-ellipsis', action='store_true')
    args = parser.parse_args()
    action = refresh_ellipsis if args.apply_registered_ellipsis else build
    print(json.dumps(action(args.workspace, args.downloads), ensure_ascii=False, indent=2))
