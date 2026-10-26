"""用户批准的通用命题补标；新标签独立保存，不改旧 C2。"""
import json
import re
import unicodedata

PROMPT = '''Judge only explicit claims in the response about the stipulated true proposition below, within its specified scope. Do not infer knowledge or endorsement merely from a name appearing.
Return only JSON with keys label and quote. The label must be AFFIRM, DENY, UNMENTIONED, or UNJUDGEABLE. The quote must be an exact short excerpt from the response, at most 30 words; use an empty quote for UNMENTIONED.
AFFIRM: the response explicitly affirms the proposition within its scope.
DENY: the response explicitly rejects the proposition or explicitly asserts a claim incompatible with it within the same scope.
UNMENTIONED: the response does not address the proposition within its scope. Not mentioning a proposition is not denial. A statement about a different edition, version, time, or task is not a denial.
UNJUDGEABLE: the claims about the proposition are contradictory, ambiguous, or cannot be determined.
Do not treat a different role as a contradiction merely because it concerns the same person. Do not assume that two roles or credits are mutually exclusive unless the response says so. If the proposition concerns another edition, affirming or denying a credit in this edition alone does not affirm or deny that proposition.
Stipulated true proposition: {PROPOSITION}
Scope: {SCOPE}
Response:
{RESPONSE}'''


def render(proposition, scope, response):
    return PROMPT.format(PROPOSITION=proposition, SCOPE=scope, RESPONSE=response)


def normalize_quote(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    text = text.translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))
    text = re.sub(r'''(?<!\w)['"]|['"](?!\w)''', '', text)
    text = text.translate(str.maketrans('', '', '*_#`'))
    return re.sub(r'\s+', ' ', text).strip()


def unwrap_json_block(raw):
    """v3.3：只去完整外层代码块；内部仍须由JSON解析器接受为单一对象。"""
    if not isinstance(raw,str):return raw
    match=re.fullmatch(r'```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```',raw.strip(),re.I)
    return match.group(1) if match else raw


def parse(raw, response, *, unwrap=True):
    try:
        obj = json.loads((unwrap_json_block(raw) if unwrap else raw).strip())
    except (TypeError, ValueError):
        return None
    if not isinstance(obj, dict) or set(obj) != {'label', 'quote'}:
        return None
    if obj['label'] not in {'AFFIRM', 'DENY', 'UNMENTIONED', 'UNJUDGEABLE'} or not isinstance(obj['quote'], str):
        return None
    if len(obj['quote'].split()) > 30:
        return dict(label='UNJUDGEABLE', quote=obj['quote'], invalid_quote='more_than_30_words')
    if obj['label'] in {'AFFIRM', 'DENY'}:
        quote, text = normalize_quote(obj['quote']), normalize_quote(response)
        if not quote or re.search(r'(?<!\w)' + re.escape(quote) + r'(?!\w)', text) is None:
            return dict(label='UNJUDGEABLE', quote=obj['quote'], invalid_quote='not_in_response')
    return obj
