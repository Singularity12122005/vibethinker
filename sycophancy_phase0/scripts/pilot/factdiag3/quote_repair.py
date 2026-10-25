"""用户批准的引文显示格式修正；不改变原始评审或立场标签。"""
from collections import Counter
from pathlib import Path
import argparse
import json
import re
import unicodedata

import protocol as p

AMENDMENT_ID = 'quote_display_format_only'


def normalized_quote(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    text = text.translate(str.maketrans('', '', '*_#`\"\'“”‘’'))
    return re.sub(r'\s+', ' ', text).strip()


def supported(quote, response):
    q, r = normalized_quote(quote), normalized_quote(response)
    return bool(q) and re.search(r'(?<!\w)' + re.escape(q) + r'(?!\w)', r) is not None


def reparsed(text, response):
    parsed = p.parse_propositions(text, response)
    if parsed is None:
        return None
    raw = json.loads(text.strip())
    for key, item in parsed.items():
        if item.get('quote_mismatch') and supported(raw[key]['quote'], response):
            parsed[key] = dict(raw[key], quote_format_normalized=True)
    return parsed


def apply(out):
    reg = p.load(out / 'factdiag3_prereg.json')
    amendments = reg.get('postfreeze_amendments', [])
    if not any(a.get('id') == AMENDMENT_ID and a.get('approved_by_user') is True for a in amendments):
        raise RuntimeError('尚无用户批准的显示格式修正记录')
    if 'GENERATION_AND_JUDGING_COMPLETE' not in (out / 'remaining_progress.log').read_text():
        raise RuntimeError('原始评审尚在运行，禁止重写其结果文件')
    files = [(out / name, p.load(out / name)) for name in ('pilot_t3.json', 'remaining_t3.json')]
    if any('propositions_raw' not in row for _, rows in files for row in rows):
        raise RuntimeError('原始命题评审未全部完成')
    counts = Counter()
    for path, rows in files:
        for row in rows:
            value = reparsed(row['propositions_raw'], row['assistant_text'])
            strict = p.parse_propositions(row['propositions_raw'], row['assistant_text'])
            for key in ('C1', 'C2', 'C3'):
                before = (strict or {}).get(key, {})
                after = (value or {}).get(key, {})
                if before.get('quote_mismatch'):
                    counts[key + '_strict_mismatch'] += 1
                if after.get('quote_format_normalized'):
                    counts[key + '_display_recovered'] += 1
                if after.get('quote_mismatch'):
                    counts[key + '_still_unmatched'] += 1
            row['propositions'] = value
        p.save(path, rows)
    reg['quote_repair_result'] = dict(counts)
    p.save(out / 'factdiag3_prereg.json', reg)
    print(json.dumps(dict(counts), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    apply(parser.parse_args().out)
