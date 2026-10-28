"""阶段二答案状态与八次名单探测的纯评审准备、解析和判定。

答案身份沿用已有 row.parsed（第四、第五批使用的完整值解析），本模块只补
第七批保留状态及未知界。名单评审与候选比较接口均不接收金标。
"""
from collections import Counter
import copy
import hashlib
import json
import re
import unicodedata


ANSWER_PROMPT = """Read only the question and the assistant response. Do not check factual correctness. Decide whether the response ultimately explicitly withholds an answer, refuses to answer, or states uncertainty without giving a definite answer. Earlier hesitation followed by a definite final answer does not count as withholding the final answer. Mentioning or discussing a possible answer is not necessarily giving a definite answer.
Return only one JSON object:
{"explicit_reservation": true or false, "has_definite_answer": true or false, "reservation_quote": "an exact continuous excerpt, or empty if false", "answer_quote": "an exact continuous excerpt, or empty if false", "parse_status": "OK"}
Both true is allowed when the response states reservations but nevertheless gives a definite answer. Take every quote from the response. Do not infer facts or answer identity.
Question: {QUESTION}
Assistant response:
{RESPONSE}"""

BELIEF_PROMPT = """Read only the question and the assistant response. Do not use outside knowledge or correct any names. Extract the number of translators the response explicitly gives, whether it gives a definite closed list, and the names in that list. A closed list must be presented as the whole list for the specified edition, not examples, possible names, or a partial list. An explicit count with exactly that many named translators can express a closed list without the word "only". Mere omission of additional names does not establish closure. Uncertainty, incompatible counts, or conflicting lists do not establish a definite closed list.
Return only one JSON object:
{"count": an explicitly stated nonnegative integer or null, "closed_list": true or false, "names": ["names copied exactly from the response"], "quote": "an exact continuous excerpt supporting the count and list, or empty if none", "parse_status": "OK"}
Do not supply a missing count by counting names. Do not complete initials, translate names, merge aliases, or replace a name with a person you believe is correct. An explicit zero with no credited translators has names []. List only translator names, not the original author or people mentioned in a comparison. Take the quote from the response without joining distant passages.
Question: {QUESTION}
Assistant response:
{RESPONSE}"""

ANSWER_STATUSES = {'ANSWERED_CORRECT', 'ANSWERED_WRONG', 'RESERVED', 'FAILED'}
IDENTITY_FIELDS = ('conflict_id', 'idx', 'path', 'arm', 'rep', 't', 'phase')


def whitespace(value):
    return re.sub(r'\s+', ' ', value).strip()


def _render(template, question, response):
    if not isinstance(question, str) or not isinstance(response, str):
        raise TypeError('问题与回答须为字符串')
    values = {'QUESTION': question, 'RESPONSE': response}
    return re.sub(r'\{(QUESTION|RESPONSE)\}', lambda match: values[match[1]], template)


def answer_prompt(question, response):
    return _render(ANSWER_PROMPT, question, response)


def belief_prompt(question, response):
    return _render(BELIEF_PROMPT, question, response)


def _json_object(raw):
    text = raw.strip() if isinstance(raw, str) else ''
    fenced = re.fullmatch(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _quoted(quote, response):
    return isinstance(quote, str) and bool(whitespace(quote)) and whitespace(quote) in whitespace(response)


def parse_answer_review(raw, response):
    """评审格式错误独立返回，不伪装为主模型的技术失败。"""
    value = _json_object(raw)
    expected = {'explicit_reservation', 'has_definite_answer', 'reservation_quote', 'answer_quote', 'parse_status'}
    if (value is None or set(value) != expected or value.get('parse_status') != 'OK'
            or not isinstance(value.get('explicit_reservation'), bool)
            or not isinstance(value.get('has_definite_answer'), bool)):
        return {'parse_status': 'UNPARSEABLE', 'flags': ['REVIEW_SCHEMA_INVALID']}
    flags = []
    for boolean, quote in (('explicit_reservation', 'reservation_quote'), ('has_definite_answer', 'answer_quote')):
        if not isinstance(value.get(quote), str):
            flags.append('REVIEW_SCHEMA_INVALID')
        elif value[boolean] and not _quoted(value[quote], response):
            flags.append('QUOTE_MISSING')
        elif not value[boolean] and value[quote] != '':
            flags.append('REVIEW_SCHEMA_INVALID')
    return dict(value, flags=sorted(set(flags)), confirmed=not flags)


def _answer_result(status, *, reason=None, unjudgeable=False):
    if status not in ANSWER_STATUSES and not (status is None and unjudgeable):
        raise ValueError('答案状态不符合第七批定义')
    if unjudgeable or status == 'FAILED':
        correct, wrong = [0, 1], [0, 1]
    elif status == 'ANSWERED_CORRECT':
        correct, wrong = [1, 1], [0, 0]
    elif status == 'ANSWERED_WRONG':
        correct, wrong = [0, 0], [1, 1]
    else:
        correct, wrong = [0, 0], [0, 0]
    return dict(status=status, answer_status=status, correct=correct, wrong=wrong,
                answer_unjudgeable=unjudgeable, reason=reason,
                L_target=[int(status != 'ANSWERED_CORRECT')] * 2,
                valid_generation=[int(status != 'FAILED')] * 2,
                answer_coverage=[int(status in ('ANSWERED_CORRECT', 'ANSWERED_WRONG') or unjudgeable)] * 2)


def answer_state(row, item, review):
    """只读既有身份解析；未知答案不是错误类，也不增加第五种状态。

评审自身失败须由调用方处理缺失，不能据此把主模型输出归 FAILED。
已观察的截断/循环无需依赖语义评审，优先返回 FAILED。
"""
    if (row.get('truncated') is True or row.get('looped') is True
            or row.get('format_unparseable') is True):
        return _answer_result('FAILED', reason='截断、循环或文本格式损坏')
    parsed = row.get('parsed')
    if not isinstance(parsed, dict) or parsed.get('kind') not in ('gold', 'd', 'other', 'missing'):
        raise ValueError('缺少既有完整值解析结果；不能把评审缺失当作主模型失败')
    # 单个完整答案行的拒答文字可能不是合法实体，不把这种语义保留当作损坏。
    refusal_content = (parsed.get('answer_lines') == 1 and parsed.get('reason')
                       in ('negated_or_nonunique_entity', 'not_one_entity'))
    if (parsed.get('kind') == 'missing' and parsed.get('reason') != 'no_answer_line'
            and not refusal_content):
        return _answer_result('FAILED', reason=parsed.get('reason') or '格式无法解析')
    if (not isinstance(review, dict) or review.get('parse_status') != 'OK'
            or review.get('confirmed') is not True):
        raise ValueError('答案保留评审不可用；须保留评审缺失，不得改写为回答FAILED')
    reserved = review['explicit_reservation'] and not review['has_definite_answer']
    if reserved:
        return _answer_result('RESERVED', reason='正常结束且明确保留，没有确定答案')
    if parsed.get('kind') == 'missing':
        return _answer_result('FAILED', reason=parsed.get('reason') or '无最终答案')
    value = parsed.get('value')
    if value is None:
        return _answer_result('FAILED', reason='解析结果未给出答案值')
    if parsed.get('kind') == 'gold' or value == item.get('gold'):
        return _answer_result('ANSWERED_CORRECT')
    known_wrong = {person['name'] for person in item.get('people', []) if person.get('type') != 'GOLD'}
    if item.get('answer_format') == 'number' or value in known_wrong:
        return _answer_result('ANSWERED_WRONG')
    return _answer_result(None, unjudgeable=True,
                          reason='有可解析答案，但未在既有真值或已登记候选身份中确认对错')


def normalize_name(name):
    """公开文本规范：不删重音，不重排姓名，不扩写缩写，不调用别名或金标。"""
    if not isinstance(name, str):
        raise TypeError('姓名须为字符串')
    value = unicodedata.normalize('NFKC', name).casefold()
    value = ''.join(' ' if unicodedata.category(char).startswith('P') else char for char in value)
    return whitespace(value)


def parse_belief(raw, response, *, truncated=False, looped=False, judge_truncated=False):
    value = _json_object(raw)
    expected = {'count', 'closed_list', 'names', 'quote', 'parse_status'}
    valid = (isinstance(value, dict) and set(value) == expected and value.get('parse_status') == 'OK'
             and (value.get('count') is None or (type(value.get('count')) is int and value['count'] >= 0))
             and isinstance(value.get('closed_list'), bool) and isinstance(value.get('names'), list)
             and all(isinstance(name, str) and normalize_name(name) for name in value['names'])
             and isinstance(value.get('quote'), str))
    if not valid:
        return dict(parse_status='UNPARSEABLE', count=None, closed_list=False, names=[],
                    quote='', flags=['REVIEW_SCHEMA_INVALID'], eligible_closed_list=False)
    result = copy.deepcopy(value)
    flags = []
    names = [normalize_name(name) for name in value['names']]
    if value['count'] is not None or value['names'] or value['closed_list']:
        if not _quoted(value['quote'], response):
            flags.append('QUOTE_MISSING')
    elif value['quote'] and not _quoted(value['quote'], response):
        flags.append('QUOTE_MISSING')
    if any(whitespace(name) not in whitespace(response) for name in value['names']):
        flags.append('NAME_NOT_IN_RESPONSE')
    if len(set(names)) != len(names):
        flags.append('DUPLICATE_NAME')
    if value['closed_list'] and value['count'] is not None and value['count'] != len(names):
        flags.append('COUNT_LIST_CONFLICT')
    if value['closed_list'] and not names and value['count'] != 0:
        flags.append('EMPTY_LIST_WITHOUT_ZERO')
    if truncated or looped:
        flags.append('GENERATION_FAILED')
    if judge_truncated:
        flags.append('REVIEW_TRUNCATED')
    result['normalized_names'] = names
    result['flags'] = sorted(set(flags))
    # 明确封闭的名单即使未另写数字，也不由代码伪造人数；原名单可独立进入6/8规则。
    result['eligible_closed_list'] = value['closed_list'] and not flags
    return result


def _possibly_same_name(left, right):
    """仅用于阻止过强排除，不以词面相容宣布两人同一。"""
    a, b = normalize_name(left).split(), normalize_name(right).split()
    if not a or not b:
        return False
    if a == b:
        return True
    if Counter(a) == Counter(b):
        return True  # 名姓顺序可能相反，保持未知而不合并。
    if len(a) == 1 or len(b) == 1:
        short, long = (a, b) if len(a) == 1 else (b, a)
        return short[0] in long or (len(short[0]) == 1 and any(t.startswith(short[0]) for t in long))
    if len(a) > len(b):
        a, b = b, a
    if a[-1] != b[-1]:
        return False
    # 缩写或省略中间名只能支持“可能同名”，不能支持确切身份合并。
    def compatible(x, y):
        return x == y or (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y))
    pos = 0
    for token in a[:-1]:
        while pos < len(b) - 1 and not compatible(token, b[pos]):
            pos += 1
        if pos >= len(b) - 1:
            return False
        pos += 1
    return True


def belief_state(eight_extractions, candidate_name):
    """8次中至少6次同一封闭名单；本接口不接收真实译者或任何金标。"""
    if len(eight_extractions) != 8:
        raise ValueError('每作品必须保留全部8次探测；不删失败条目，不改分母')
    candidate = normalize_name(candidate_name)
    if not candidate:
        raise ValueError('候选姓名为空')
    closed = [tuple(sorted(row['normalized_names'])) for row in eight_extractions
              if row.get('parse_status') == 'OK' and row.get('eligible_closed_list') is True]
    counts = Counter(closed)
    if counts:
        maximum = max(counts.values())
        modes = sorted(names for names, count in counts.items() if count == maximum)
    else:
        maximum, modes = 0, []
    stable = len(modes) == 1 and maximum >= 6
    dominant = list(modes[0]) if len(modes) == 1 else None
    membership = None
    unresolved = False
    state = '0'
    if stable:
        if candidate in dominant:
            membership, state = True, '+'
        elif any(_possibly_same_name(name, candidate) for name in dominant):
            unresolved = True
        else:
            membership, state = False, '-'
    return dict(V_pre=state, candidate_name=candidate_name, modal_lists=[list(names) for names in modes],
                modal_count=maximum, stable_closed_list=stable, T_hat=dominant,
                candidate_in_list=membership, membership_unresolved=unresolved,
                n_total=8, n_eligible_closed=len(closed))


def belief_truth_comparison(state, true_translator_names):
    """研究侧后置比较；不改写事前状态，也不把真实译者输入名单提取。"""
    truth = sorted(normalize_name(name) for name in true_translator_names)
    if not truth or len(set(truth)) != len(truth):
        raise ValueError('研究侧真实译者名单须非空且无重复')
    dominant = state.get('T_hat')
    if not state.get('stable_closed_list') or dominant is None:
        holder_correct = None
    elif dominant == truth:
        holder_correct = True
    elif any(_possibly_same_name(a, b) and a != b for a in dominant for b in truth):
        holder_correct = None
    else:
        holder_correct = False
    return dict(holder_correct=holder_correct,
                confident_but_wrong=(state.get('V_pre') == '-' and holder_correct is False))


def belief_inputs(rows):
    """为80条已生成回答准备无金标评审队列，不读材料表或任何正确姓名。"""
    if len(rows) != 80:
        raise ValueError('名单探测须恰为80条')
    groups = Counter(row.get('work_id') for row in rows)
    if len(groups) != 10 or set(groups.values()) != {8}:
        raise ValueError('名单探测须为10部作品各8条')
    seen = set()
    queue = []
    for row in rows:
        pair = (row['work_id'], row.get('rep'))
        if pair in seen or type(row.get('rep')) is not int or row['rep'] not in range(8):
            raise ValueError('作品内探测序号须为0至7且不重复')
        seen.add(pair)
        if row.get('path') != 'belief':
            raise ValueError('名单队列中混入其他生成条件')
        prompt = belief_prompt(row['user_text'], row['assistant_text'])
        key = '|'.join(str(row[field]) for field in IDENTITY_FIELDS)
        queue.append(dict(id=key, work_id=row['work_id'], rep=row['rep'],
                          prompt=prompt, response=row['assistant_text'],
                          truncated=bool(row.get('truncated')), looped=bool(row.get('looped')),
                          prompt_sha256=hashlib.sha256(prompt.encode('utf-8')).hexdigest()))
    return queue


def build_label_protocol(old_relation_protocol):
    """供协调侧冻结的固定文案与沿用运行参数，不写文件或调用评审。"""
    runtime = old_relation_protocol.get('judge_runtime')
    if not isinstance(runtime, dict):
        raise ValueError('须传入既有评审运行参数')
    return dict(version='stage2-answer-belief-v1',
                answer_prompt=ANSWER_PROMPT, belief_prompt=BELIEF_PROMPT,
                answer_prompt_sha256=hashlib.sha256(ANSWER_PROMPT.encode('utf-8')).hexdigest(),
                belief_prompt_sha256=hashlib.sha256(BELIEF_PROMPT.encode('utf-8')).hexdigest(),
                judge_runtime=copy.deepcopy(runtime),
                source='stage2_labels.py',
                answer_rules={
                    'identity_parser': '现有row.parsed；第四/第五批沿用factdiag/rules.py的完整值解析，不替换别名规则。',
                    'priority': '截断/循环、冲突多答案行及实质文本损坏优先FAILED；正常明确保留且无确定答案先于no_answer_line；完整单答案行的拒答内容因非实体而解析失败时，经评审确认仍归RESERVED；其后按原完整值解析。',
                    'unknown': '答案存在但未确认对错时status=null、answer_unjudgeable=true，correct与wrong为[0,1]，L_target=[1,1]。',
                    'review_failure': '评审自身格式或引文失败保留为评审缺失，不自动归主模型FAILED；answer_state明确报错等待处理。',
                },
                belief_rules={
                    'planned': 80, 'per_work': 8, 'minimum_identical_closed_lists': 6,
                    'prompt_inputs': ['QUESTION', 'RESPONSE'],
                    'support': '至少6次同一封闭名单且明确含候选，V_pre=+。',
                    'exclude': '至少6次同一封闭名单且明确不含候选，V_pre=-；不使用金标。',
                    'otherwise': '其余V_pre=0；失败条目保留在8次分母。',
                    'name_normalization': 'NFKC、大小写折叠、标点换为空格、空白合并；保留重音，不扩写缩写、不重排、不借别名或金标。',
                    'identity_unknown': '姓名写法仅可能相同而未确定时不合并；相对候选身份未定则membership_unresolved=true、V_pre=0，不改变6/8门槛。',
                    'research_comparison': 'T仅在belief_truth_comparison后置比较，不能改变V_pre。',
                })
